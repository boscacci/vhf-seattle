from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from talkingboats.audio_processing import (
    PublicClipAudioRejected,
    assert_publishable_public_clip_audio,
    process_public_clip_audio,
)
from talkingboats.channel_metadata import channel_label, public_monitored_channel_labels
from talkingboats.clip_transcriber import (
    ClipReader,
    RecentTranscribedClip,
    S3ClipReader,
    UploadedClipStore,
)
from talkingboats.security import assert_public_safe

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
PUBLIC_EXCLUDED_CHANNELS = ("WX",)
ClipAudioProcessor = Callable[[Path, Path], None]
ClipAudioQualityGate = Callable[[Path], None]
ProgressReporter = Callable[[int, int], None]
SkipReporter = Callable[[int, int, str], None]

ALLOWED_CLIP_FIELDS = {
    "id",
    "public_title",
    "channel",
    "channel_label",
    "started_at",
    "duration_seconds",
    "transcript_public",
    "audio_public_filename",
    "interestingness_score",
    "tags",
}

ALLOWED_STATS_FIELDS = {
    "busiest_hours",
    "channel_counts",
    "channel_labels",
    "vessel_type_counts",
    "generated_at",
    "clip_count",
}

ALLOWED_VESSEL_FIELDS = {
    "mmsi",
    "name",
    "vessel_type",
    "distance_nm",
    "confidence",
}

ALLOWED_AIS_FIELDS = {
    "lat",
    "lon",
    "speed_knots",
    "course_degrees",
    "observed_at",
}


class PublicExportError(ValueError):
    pass


def sanitize_public_manifest(private_manifest: Mapping[str, Any]) -> dict[str, Any]:
    clips = []
    for clip in private_manifest.get("clips", []):
        if not isinstance(clip, Mapping):
            raise PublicExportError("clips must contain objects")
        if not clip.get("approved_public"):
            continue
        if str(clip.get("channel") or "").upper() in PUBLIC_EXCLUDED_CHANNELS:
            continue
        clips.append(_sanitize_clip(clip))

    channel_counts = _channel_counts_for_public_clips(clips)
    stats = _copy_allowed(private_manifest.get("stats", {}), ALLOWED_STATS_FIELDS)
    stats["clip_count"] = len(clips)
    stats["channel_counts"] = channel_counts
    stats["channel_labels"] = public_monitored_channel_labels(channel_counts)

    public_manifest = {
        "generated_at": private_manifest.get("generated_at"),
        "site": {
            "title": private_manifest.get("site", {}).get("title", "Elliott Bay VHF"),
            "subtitle": private_manifest.get("site", {}).get(
                "subtitle",
                "Live Elliott Bay marine VHF audio and recent receiver clips.",
            ),
        },
        "stats": stats,
        "clips": clips,
    }
    assert_public_safe(public_manifest)
    return public_manifest


def export_public_site(
    private_manifest_path: Path,
    site_source_dir: Path,
    output_dir: Path,
    audio_source_dir: Path | None = None,
    *,
    clip_audio_processor: ClipAudioProcessor | None = process_public_clip_audio,
) -> dict[str, Any]:
    private_manifest = json.loads(private_manifest_path.read_text(encoding="utf-8"))
    public_manifest = sanitize_public_manifest(private_manifest)

    with _preserved_analysis_dir(output_dir) as preserved_analysis:
        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.copytree(site_source_dir, output_dir)
        _restore_analysis_dir(output_dir, preserved_analysis)

        clips_dir = output_dir / "clips"
        clips_dir.mkdir(exist_ok=True)
        if audio_source_dir:
            _copy_approved_audio(
                public_manifest,
                audio_source_dir,
                clips_dir,
                clip_audio_processor=clip_audio_processor,
            )

        (output_dir / "public_manifest.json").write_text(
            json.dumps(public_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return public_manifest


def export_recent_clip_site(
    *,
    clip_db_path: Path,
    site_source_dir: Path,
    output_dir: Path,
    clip_reader: ClipReader,
    limit: int = 1000,
    clip_audio_processor: ClipAudioProcessor | None = process_public_clip_audio,
    clip_audio_quality_gate: ClipAudioQualityGate | None = assert_publishable_public_clip_audio,
    progress: ProgressReporter | None = None,
    skip_progress: SkipReporter | None = None,
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    store = UploadedClipStore(clip_db_path)
    clips = store.recent_transcribed(limit=limit, excluded_channels=PUBLIC_EXCLUDED_CHANNELS)

    with _preserved_analysis_dir(output_dir) as preserved_analysis:
        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.copytree(site_source_dir, output_dir)
        _restore_analysis_dir(output_dir, preserved_analysis)

        clips_dir = output_dir / "clips"
        clips_dir.mkdir(exist_ok=True)
        total_clips = len(clips)
        publishable_clips = []
        for index, source_clip in enumerate(clips, start=1):
            if progress:
                progress(index, total_clips)
            public_clip = _public_clip_from_recent(source_clip)
            destination = clips_dir / public_clip["audio_public_filename"]
            if clip_audio_processor is None and clip_audio_quality_gate is None:
                clip_reader.download(source_clip.key, destination)
                publishable_clips.append(source_clip)
                continue
            with tempfile.NamedTemporaryFile(suffix=Path(source_clip.key).suffix) as handle:
                raw_clip_path = Path(handle.name)
                clip_reader.download(source_clip.key, raw_clip_path)
                try:
                    if clip_audio_quality_gate is not None:
                        clip_audio_quality_gate(raw_clip_path)
                except PublicClipAudioRejected as exc:
                    if skip_progress:
                        skip_progress(index, total_clips, str(exc))
                    continue
                if clip_audio_processor is None:
                    shutil.copy2(raw_clip_path, destination)
                else:
                    clip_audio_processor(raw_clip_path, destination)
                publishable_clips.append(source_clip)

        public_manifest = _recent_clip_manifest(publishable_clips)
        (output_dir / "public_manifest.json").write_text(
            json.dumps(public_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return public_manifest


class _preserved_analysis_dir:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self._tempdir: tempfile.TemporaryDirectory[str] | None = None
        self.path: Path | None = None

    def __enter__(self) -> Path | None:
        source = self.output_dir / "analysis"
        if not source.exists():
            return None
        self._tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tempdir.name) / "analysis"
        shutil.copytree(source, self.path)
        return self.path

    def __exit__(self, *_exc_info: object) -> None:
        if self._tempdir is not None:
            self._tempdir.cleanup()


def _restore_analysis_dir(output_dir: Path, preserved_analysis: Path | None) -> None:
    if preserved_analysis is None:
        return
    destination = output_dir / "analysis"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(preserved_analysis, destination)


def _sanitize_clip(clip: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = _copy_allowed(clip, ALLOWED_CLIP_FIELDS)

    filename = sanitized.get("audio_public_filename")
    if filename is not None:
        sanitized["audio_public_filename"] = _safe_public_audio_filename(str(filename))

    if "ais_context" in clip:
        sanitized["ais_context"] = _round_location(
            _copy_allowed(clip["ais_context"], ALLOWED_AIS_FIELDS)
        )
    if "vessel_context" in clip:
        vessels = clip["vessel_context"]
        if not isinstance(vessels, list):
            raise PublicExportError("vessel_context must be a list")
        sanitized["vessel_context"] = [
            _copy_allowed(vessel, ALLOWED_VESSEL_FIELDS) for vessel in vessels
        ]
    sanitized.setdefault("channel_label", channel_label(str(sanitized.get("channel") or "")))

    required = ["id", "public_title", "channel", "started_at"]
    missing = [field for field in required if not sanitized.get(field)]
    if missing:
        raise PublicExportError(f"approved clip is missing public fields: {', '.join(missing)}")

    return sanitized


def _copy_allowed(source: Any, allowed_fields: set[str]) -> dict[str, Any]:
    if not source:
        return {}
    if not isinstance(source, Mapping):
        raise PublicExportError("expected object")
    return {field: source[field] for field in allowed_fields if field in source}


def _channel_counts_for_public_clips(clips: list[dict[str, Any]]) -> dict[str, int]:
    channel_counts: dict[str, int] = {}
    for clip in clips:
        channel = str(clip["channel"])
        channel_counts[channel] = channel_counts.get(channel, 0) + 1
    return channel_counts


def _round_location(ais_context: dict[str, Any]) -> dict[str, Any]:
    for field in ("lat", "lon"):
        if field in ais_context and ais_context[field] is not None:
            ais_context[field] = round(float(ais_context[field]), 3)
    return ais_context


def _safe_public_audio_filename(filename: str) -> str:
    path = Path(filename)
    if path.name != filename or filename.startswith("."):
        raise PublicExportError("audio_public_filename must be a plain filename")
    if path.suffix.lower() not in {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}:
        raise PublicExportError("audio_public_filename must be an audio file")
    return filename


def _copy_approved_audio(
    public_manifest: Mapping[str, Any],
    audio_source_dir: Path,
    clips_dir: Path,
    *,
    clip_audio_processor: ClipAudioProcessor | None,
) -> None:
    source_root = audio_source_dir.resolve()
    for clip in public_manifest["clips"]:
        filename = clip.get("audio_public_filename")
        if not filename:
            continue
        source = audio_source_dir / filename
        if not source.exists():
            raise PublicExportError(f"approved audio file does not exist: {source}")
        if not source.resolve().is_relative_to(source_root):
            raise PublicExportError("approved audio file escapes source directory")
        destination = clips_dir / filename
        if clip_audio_processor is None:
            shutil.copy2(source, destination)
        else:
            clip_audio_processor(source, destination)


def _recent_clip_manifest(clips: list[RecentTranscribedClip]) -> dict[str, Any]:
    generated_at = _format_utc(datetime.now(UTC))
    channel_counts: dict[str, int] = {}
    public_clips = []
    for clip in clips:
        channel_counts[clip.channel] = channel_counts.get(clip.channel, 0) + 1
        public_clips.append(_public_clip_from_recent(clip))
    public_manifest = {
        "generated_at": generated_at,
        "site": {
            "title": "Elliott Bay VHF",
            "subtitle": "Live Elliott Bay marine VHF audio and recent receiver clips.",
        },
        "stats": {
            "generated_at": generated_at,
            "clip_count": len(public_clips),
            "channel_counts": channel_counts,
            "channel_labels": public_monitored_channel_labels(channel_counts),
        },
        "clips": public_clips,
    }
    assert_public_safe(public_manifest)
    return public_manifest


def _public_clip_from_recent(clip: RecentTranscribedClip) -> dict[str, Any]:
    clip_id = _public_clip_id(clip.key)
    return {
        "id": clip_id,
        "public_title": _public_clip_title(clip),
        "channel": clip.channel,
        "channel_label": channel_label(clip.channel),
        "started_at": clip.started_at,
        "ended_at": clip.ended_at,
        "duration_seconds": clip.duration_seconds,
        "transcript_public": clip.transcript,
        "audio_public_filename": _public_audio_filename(clip),
    }


def _public_clip_title(clip: RecentTranscribedClip) -> str:
    started_at = _parse_utc(clip.started_at).astimezone(PACIFIC_TZ)
    hour = started_at.hour % 12 or 12
    minute = f"{started_at.minute:02d}"
    meridian = "AM" if started_at.hour < 12 else "PM"
    time_zone = started_at.tzname() or "PT"
    return (
        f"VHF {clip.channel} - {started_at.strftime('%b')} {started_at.day}, "
        f"{started_at.year} {hour}:{minute} {meridian} {time_zone}"
    )


def _public_clip_id(key: str) -> str:
    return f"clip-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}"


def _public_audio_filename(clip: RecentTranscribedClip) -> str:
    started_at = _parse_utc(clip.started_at)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    channel = "".join(character.lower() for character in clip.channel if character.isalnum())
    digest = f"sha{hashlib.sha256(clip.key.encode('utf-8')).hexdigest()[:12]}"
    return f"{stamp}-vhf-{channel}-{digest}{_suffix_for_content_type(clip.content_type)}"


def _suffix_for_content_type(content_type: str) -> str:
    return {
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/aac": ".aac",
        "audio/flac": ".flac",
        "audio/m4a": ".m4a",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
    }.get(content_type, ".audio")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise PublicExportError("clip timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the sanitized Elliott Bay VHF site.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--private-manifest", type=Path)
    source.add_argument("--clip-db-path", type=Path)
    parser.add_argument("--site-source", type=Path, default=Path("public-site"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/public-site"))
    parser.add_argument("--audio-source-dir", type=Path)
    parser.add_argument("--raw-bucket")
    parser.add_argument("--aws-region", default="us-west-2")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--public-audio-ffmpeg-path")
    parser.add_argument("--public-audio-ffprobe-path")
    parser.add_argument(
        "--min-public-audio-duration-seconds",
        type=float,
        default=1.0,
        help="Skip recent clips shorter than this during public export.",
    )
    parser.add_argument(
        "--min-public-audio-peak-db",
        type=float,
        default=-50.0,
        help="Skip recent clips whose raw peak audio level is below this.",
    )
    parser.add_argument(
        "--no-public-audio-processing",
        action="store_true",
        help="Copy public clip audio without export-time compression and normalization.",
    )
    parser.add_argument(
        "--no-public-audio-quality-gate",
        action="store_true",
        help="Publish recent clip audio without duration and level checks.",
    )
    args = parser.parse_args()
    clip_audio_processor = None
    if not args.no_public_audio_processing:

        def clip_audio_processor(source_path: Path, output_path: Path) -> None:
            process_public_clip_audio(
                source_path,
                output_path,
                ffmpeg_path=args.public_audio_ffmpeg_path,
            )
    clip_audio_quality_gate = None
    if not args.no_public_audio_quality_gate:

        def clip_audio_quality_gate(source_path: Path) -> None:
            assert_publishable_public_clip_audio(
                source_path,
                min_duration_seconds=args.min_public_audio_duration_seconds,
                min_peak_db=args.min_public_audio_peak_db,
                ffprobe_path=args.public_audio_ffprobe_path,
                ffmpeg_path=args.public_audio_ffmpeg_path,
            )

    if args.clip_db_path is not None:
        if not args.raw_bucket:
            parser.error("--clip-db-path requires --raw-bucket")
        export_recent_clip_site(
            clip_db_path=args.clip_db_path,
            site_source_dir=args.site_source,
            output_dir=args.output_dir,
            clip_reader=S3ClipReader(bucket=args.raw_bucket, aws_region=args.aws_region),
            limit=args.limit,
            clip_audio_processor=clip_audio_processor,
            clip_audio_quality_gate=clip_audio_quality_gate,
            progress=_print_export_progress,
            skip_progress=_print_skip_progress,
        )
    else:
        assert args.private_manifest is not None
        export_public_site(
            private_manifest_path=args.private_manifest,
            site_source_dir=args.site_source,
            output_dir=args.output_dir,
            audio_source_dir=args.audio_source_dir,
            clip_audio_processor=clip_audio_processor,
        )


def _print_export_progress(index: int, total: int) -> None:
    print(f"Processing public clip audio {index}/{total}", file=sys.stderr, flush=True)


def _print_skip_progress(index: int, total: int, reason: str) -> None:
    print(f"Skipping public clip audio {index}/{total}: {reason}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
