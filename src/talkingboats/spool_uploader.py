from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import wave
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from heapq import nlargest
from pathlib import Path
from typing import Literal, Protocol

from talkingboats.audio_processing import process_canonical_clip_audio

ALLOWED_CHANNELS = {
    "05A",
    "06",
    "09",
    "10",
    "13",
    "14",
    "16",
    "22A",
    "65A",
    "66A",
    "67",
    "68",
    "69",
    "71",
    "72",
    "73",
    "74",
    "77",
    "78A",
}
CONTENT_TYPES = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}
Channel = Literal[
    "05A",
    "06",
    "09",
    "10",
    "13",
    "14",
    "16",
    "22A",
    "65A",
    "66A",
    "67",
    "68",
    "69",
    "71",
    "72",
    "73",
    "74",
    "77",
    "78A",
]


class StatResult(Protocol):
    st_size: int
    st_mtime: float


@dataclass(frozen=True)
class SpooledAudioClip:
    channel: Channel
    audio_path: Path
    started_at: datetime
    content_type: str
    idempotency_key: str
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    audio_profile: str | None = None


@dataclass(frozen=True)
class UploadResult:
    bucket: str
    key: str
    bytes_uploaded: int


UploadFunc = Callable[..., UploadResult]
Runner = Callable[..., object]
DurationProbe = Callable[[Path], float | None]


class ClipPreparationError(Exception):
    """Raised when local clip preparation fails before any upload attempt."""


def infer_spool_channel(path: Path) -> Channel:
    for part in (path.name, path.parent.name):
        if channel := _normalize_spool_channel(part):
            return channel
        for token in re.split(r"[^A-Za-z0-9]+", part):
            if channel := _normalize_spool_channel(token):
                return channel
    raise ValueError(f"could not infer channel from path: {path}")


def discover_completed_audio_files(
    *,
    spool_root: Path,
    now: datetime,
    min_age_seconds: float,
    stat_func=None,
    duration_probe: DurationProbe | None = None,
    max_candidates: int | None = None,
) -> list[SpooledAudioClip]:
    stat_func = stat_func or (lambda path: path.stat())
    duration_probe = duration_probe or probe_audio_duration_seconds
    clips: list[SpooledAudioClip] = []
    if not spool_root.exists():
        return clips
    candidates: list[tuple[datetime, datetime, Path, Channel]] = []
    for audio_path in spool_root.rglob("*"):
        if not audio_path.is_file() or audio_path.suffix.lower() not in CONTENT_TYPES:
            continue
        stat = stat_func(audio_path)
        if stat.st_size <= 0:
            continue
        modified_at = datetime.fromtimestamp(stat.st_mtime, UTC)
        if (now - modified_at).total_seconds() < min_age_seconds:
            continue
        try:
            channel = infer_spool_channel(audio_path)
        except ValueError:
            continue
        candidates.append(
            (
                _started_at_from_filename(audio_path) or modified_at,
                modified_at,
                audio_path,
                channel,
            )
        )
    if max_candidates is not None:
        candidates = nlargest(
            max(0, max_candidates),
            candidates,
            key=lambda candidate: (candidate[0], candidate[1], str(candidate[2])),
        )
    for filename_started_at, modified_at, audio_path, channel in candidates:
        metadata = _read_audio_metadata(audio_path)
        started_at = (
            _metadata_datetime(metadata, "started_at") or filename_started_at or modified_at
        )
        ended_at = _metadata_datetime(metadata, "ended_at")
        duration_seconds = _metadata_positive_float(metadata.get("duration_seconds"))
        if ended_at is not None and ended_at <= started_at:
            ended_at = None
        if duration_seconds is None:
            duration_seconds = duration_probe(audio_path)
        if duration_seconds is None and ended_at is not None:
            measured_seconds = (ended_at - started_at).total_seconds()
            if measured_seconds > 0:
                duration_seconds = round(measured_seconds, 3)
        if ended_at is None and duration_seconds is not None:
            ended_at = started_at + timedelta(seconds=duration_seconds)
        clips.append(
            SpooledAudioClip(
                channel=channel,
                audio_path=audio_path,
                started_at=started_at,
                content_type=CONTENT_TYPES[audio_path.suffix.lower()],
                idempotency_key=_idempotency_key(
                    channel=channel,
                    started_at=started_at,
                    path=audio_path,
                ),
                ended_at=ended_at,
                duration_seconds=duration_seconds,
            )
        )
    return sorted(clips, key=lambda clip: clip.started_at, reverse=True)


def prune_completed_audio_files(
    *,
    spool_root: Path,
    now: datetime,
    min_age_seconds: float,
    max_retained_files: int | None,
    stat_func=None,
) -> int:
    """Discard oldest stable recognized clips when an edge spool exceeds its cap.

    The capture process can keep recording while the LAN is unavailable.  A
    bounded spool preserves the newest, most useful clips and prevents an
    outage from consuming the Pi's storage indefinitely.  Files younger than
    ``min_age_seconds`` are intentionally left alone so an in-progress writer
    is never pruned.
    """
    if max_retained_files is None:
        return 0
    if max_retained_files < 0:
        raise ValueError("max_retained_files must not be negative")
    stat_func = stat_func or (lambda path: path.stat())
    if not spool_root.exists():
        return 0

    candidates: list[tuple[datetime, datetime, Path]] = []
    for audio_path in spool_root.rglob("*"):
        if not audio_path.is_file() or audio_path.suffix.lower() not in CONTENT_TYPES:
            continue
        stat = stat_func(audio_path)
        if stat.st_size <= 0:
            continue
        modified_at = datetime.fromtimestamp(stat.st_mtime, UTC)
        if (now - modified_at).total_seconds() < min_age_seconds:
            continue
        try:
            infer_spool_channel(audio_path)
        except ValueError:
            continue
        candidates.append(
            (_started_at_from_filename(audio_path) or modified_at, modified_at, audio_path)
        )

    if len(candidates) <= max_retained_files:
        return 0
    retained_paths = {
        path
        for _, _, path in nlargest(
            max_retained_files,
            candidates,
            key=lambda candidate: (candidate[0], candidate[1], str(candidate[2])),
        )
    }
    pruned = 0
    for _, _, audio_path in candidates:
        if audio_path in retained_paths:
            continue
        audio_path.unlink(missing_ok=True)
        for metadata_path in (
            audio_path.with_suffix(".json"),
            audio_path.with_name(f"{audio_path.name}.json"),
        ):
            metadata_path.unlink(missing_ok=True)
        pruned += 1
    return pruned


def upload_spooled_clip(*, api_url: str, ingest_token: str, clip: SpooledAudioClip) -> UploadResult:
    if not api_url:
        raise ValueError("api_url is required")
    if not ingest_token:
        raise ValueError("ingest_token is required")
    api_url = api_url.rstrip("/")
    payload = {
        "channel": clip.channel,
        "started_at": _format_utc(clip.started_at),
        "content_type": clip.content_type,
        "idempotency_key": clip.idempotency_key,
    }
    if clip.ended_at is not None:
        payload["ended_at"] = _format_utc(clip.ended_at)
    if clip.duration_seconds is not None:
        payload["duration_seconds"] = clip.duration_seconds
    if clip.audio_profile is not None:
        payload["audio_profile"] = clip.audio_profile
    presign_request = urllib.request.Request(
        f"{api_url}/api/ingest/clips/presign",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-TalkingBoats-Ingest-Token": ingest_token,
        },
        method="POST",
    )
    with urllib.request.urlopen(presign_request, timeout=30) as response:
        presign = json.loads(response.read().decode("utf-8"))

    audio_bytes = clip.audio_path.read_bytes()
    put_request = urllib.request.Request(
        presign["upload_url"],
        data=audio_bytes,
        headers=dict(presign.get("required_headers", {})),
        method="PUT",
    )
    with urllib.request.urlopen(put_request, timeout=120):
        pass
    return UploadResult(
        bucket=presign["bucket"],
        key=presign["key"],
        bytes_uploaded=len(audio_bytes),
    )


def process_spool_once(
    *,
    spool_root: Path,
    api_url: str,
    ingest_token: str,
    min_age_seconds: float,
    delete_after_upload: bool,
    now: datetime | None = None,
    stat_func=None,
    upload_func: UploadFunc = upload_spooled_clip,
    audio_filter: str | None = None,
    mp3_bitrate: str = "64k",
    ffmpeg_path: str = "ffmpeg",
    runner: Runner = subprocess.run,
    failed_root: Path | None = None,
    max_files: int | None = 100,
    max_retained_files: int | None = None,
    fallback_to_original_on_prepare_error: bool = False,
    duration_probe: DurationProbe | None = None,
    min_duration_seconds: float = 0.0,
    max_synchronous_channels: int = 0,
) -> int:
    if min_duration_seconds < 0:
        raise ValueError("min_duration_seconds must not be negative")
    if max_synchronous_channels < 0:
        raise ValueError("max_synchronous_channels must not be negative")
    uploaded = 0
    now = now or datetime.now(UTC)
    failed_root = failed_root or spool_root.parent / f"{spool_root.name}-failed"
    quarantine_stale_empty_audio_files(
        spool_root=spool_root,
        now=now,
        min_age_seconds=min_age_seconds,
        failed_root=failed_root,
        stat_func=stat_func,
    )
    pruned = prune_completed_audio_files(
        spool_root=spool_root,
        now=now,
        min_age_seconds=min_age_seconds,
        max_retained_files=max_retained_files,
        stat_func=stat_func,
    )
    if pruned:
        _log_event(
            "spool_clips_pruned",
            pruned=pruned,
            max_retained_files=max_retained_files,
        )
    clips = discover_completed_audio_files(
        spool_root=spool_root,
        now=now,
        min_age_seconds=min_age_seconds,
        stat_func=stat_func,
        duration_probe=duration_probe,
        max_candidates=max_files,
    )
    if max_files is not None:
        clips = clips[: max(0, max_files)]
    if max_synchronous_channels:
        burst_groups: dict[datetime, list[SpooledAudioClip]] = {}
        for clip in clips:
            started_at_second = clip.started_at.replace(microsecond=0)
            burst_groups.setdefault(started_at_second, []).append(clip)
        burst_paths: set[Path] = set()
        for started_at, group in burst_groups.items():
            channels = sorted({clip.channel for clip in group})
            if len(channels) <= max_synchronous_channels:
                continue
            for clip in group:
                _discard_spooled_clip(clip.audio_path)
                burst_paths.add(clip.audio_path)
            _log_event(
                "spool_synchronous_burst_discarded",
                started_at=_format_utc(started_at),
                channel_count=len(channels),
                channels=channels,
                clip_count=len(group),
                max_synchronous_channels=max_synchronous_channels,
            )
        clips = [clip for clip in clips if clip.audio_path not in burst_paths]
    for clip in clips:
        if clip.duration_seconds is not None and clip.duration_seconds < min_duration_seconds:
            _discard_spooled_clip(clip.audio_path)
            _log_event(
                "spool_short_clip_discarded",
                channel=clip.channel,
                audio_file=clip.audio_path.name,
                duration_seconds=clip.duration_seconds,
                min_duration_seconds=min_duration_seconds,
            )
            continue
        try:
            with prepared_spooled_clip_for_upload(
                clip,
                audio_filter=audio_filter,
                mp3_bitrate=mp3_bitrate,
                ffmpeg_path=ffmpeg_path,
                runner=runner,
                fallback_to_original_on_prepare_error=fallback_to_original_on_prepare_error,
            ) as upload_clip:
                result = upload_func(api_url=api_url, ingest_token=ingest_token, clip=upload_clip)
        except ClipPreparationError as exc:
            failed_path = quarantine_spooled_clip(
                clip=clip,
                spool_root=spool_root,
                failed_root=failed_root,
                error=exc,
            )
            _log_event(
                "spool_clip_quarantined",
                channel=clip.channel,
                audio_file=clip.audio_path.name,
                failed_file=str(failed_path),
                error=f"{type(exc.__cause__ or exc).__name__}: {exc.__cause__ or exc}",
            )
            continue
        except Exception as exc:  # noqa: BLE001 - one bad upload must not block later clips.
            _log_event(
                "spool_clip_upload_failed",
                channel=clip.channel,
                audio_file=clip.audio_path.name,
                error=f"{type(exc).__name__}: {exc}",
            )
            continue
        uploaded += 1
        _log_event(
            "spool_clip_uploaded",
            channel=clip.channel,
            audio_file=clip.audio_path.name,
            uploaded_audio_file=upload_clip.audio_path.name,
            key=result.key,
            bytes_uploaded=result.bytes_uploaded,
        )
        if delete_after_upload:
            clip.audio_path.unlink(missing_ok=True)
    return uploaded


def quarantine_stale_empty_audio_files(
    *,
    spool_root: Path,
    now: datetime,
    min_age_seconds: float,
    failed_root: Path,
    stat_func=None,
) -> int:
    stat_func = stat_func or (lambda path: path.stat())
    quarantined = 0
    if not spool_root.exists():
        return quarantined
    for audio_path in sorted(spool_root.rglob("*")):
        if not audio_path.is_file() or audio_path.suffix.lower() not in CONTENT_TYPES:
            continue
        stat = stat_func(audio_path)
        if stat.st_size > 0:
            continue
        modified_at = datetime.fromtimestamp(stat.st_mtime, UTC)
        if (now - modified_at).total_seconds() < min_age_seconds:
            continue
        try:
            channel = infer_spool_channel(audio_path)
        except ValueError:
            continue
        started_at = _started_at_from_filename(audio_path) or modified_at
        clip = SpooledAudioClip(
            channel=channel,
            audio_path=audio_path,
            started_at=started_at,
            content_type=CONTENT_TYPES[audio_path.suffix.lower()],
            idempotency_key=_idempotency_key(
                channel=channel,
                started_at=started_at,
                path=audio_path,
            ),
        )
        error = ClipPreparationError("stale empty spool file")
        failed_path = quarantine_spooled_clip(
            clip=clip,
            spool_root=spool_root,
            failed_root=failed_root,
            error=error,
        )
        _log_event(
            "spool_empty_clip_quarantined",
            channel=clip.channel,
            audio_file=clip.audio_path.name,
            failed_file=str(failed_path),
            error=str(error),
        )
        quarantined += 1
    return quarantined


def probe_audio_duration_seconds(path: Path) -> float | None:
    if path.suffix.lower() in {".wav", ".wave"}:
        wav_duration = _try_wav_duration_seconds(path)
        if wav_duration is not None:
            return wav_duration

    ffprobe_path = os.getenv("TALKINGBOATS_EDGE_UPLOAD_FFPROBE_PATH", "ffprobe")
    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-hide_banner",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return _parse_probe_duration_seconds(result.stdout)


def _read_audio_metadata(path: Path) -> dict[str, object]:
    for metadata_path in (path.with_suffix(".json"), path.with_name(f"{path.name}.json")):
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _metadata_datetime(metadata: dict[str, object], field: str) -> datetime | None:
    value = metadata.get(field)
    if not isinstance(value, str):
        return None
    try:
        return _parse_utc(value)
    except ValueError:
        return None


def _metadata_positive_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return round(parsed, 3) if parsed > 0 else None


def _try_wav_duration_seconds(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wav:
            frame_rate = wav.getframerate()
            if frame_rate <= 0:
                return None
            return round(wav.getnframes() / frame_rate, 3)
    except (OSError, EOFError, wave.Error):
        return None


def _parse_probe_duration_seconds(stdout: str) -> float | None:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines or lines[-1].upper() == "N/A":
        return None
    return _metadata_positive_float(lines[-1])


@contextmanager
def prepared_spooled_clip_for_upload(
    clip: SpooledAudioClip,
    *,
    audio_filter: str | None,
    mp3_bitrate: str = "64k",
    ffmpeg_path: str = "ffmpeg",
    runner: Runner = subprocess.run,
    fallback_to_original_on_prepare_error: bool = False,
) -> Iterator[SpooledAudioClip]:
    del audio_filter, fallback_to_original_on_prepare_error
    with tempfile.TemporaryDirectory(prefix="talkingboats-spool-upload-") as tempdir:
        upload_path = Path(tempdir) / f"{clip.audio_path.stem}-canonical.mp3"
        try:
            result = process_canonical_clip_audio(
                clip.audio_path,
                upload_path,
                bitrate=mp3_bitrate,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=os.getenv(
                    "TALKINGBOATS_EDGE_UPLOAD_FFPROBE_PATH",
                    "ffprobe",
                ),
                runner=runner,
            )
        except Exception as exc:  # noqa: BLE001 - daemon quarantines this local input.
            raise ClipPreparationError(f"{type(exc).__name__}: {exc}") from exc
        yield replace(
            clip,
            audio_path=upload_path,
            content_type="audio/mpeg",
            duration_seconds=result.duration_seconds or clip.duration_seconds,
            ended_at=(
                clip.started_at + timedelta(seconds=result.duration_seconds)
                if result.duration_seconds is not None
                else clip.ended_at
            ),
            audio_profile=result.audio_profile,
            idempotency_key=_idempotency_key(
                channel=clip.channel,
                started_at=clip.started_at,
                path=upload_path,
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload completed multichannel audio spool files.")
    parser.add_argument("--spool-root", type=Path, default=Path("/opt/talkingboats/spool/airband"))
    parser.add_argument("--api-url", default=os.getenv("TALKINGBOATS_PRIVATE_API", ""))
    parser.add_argument("--ingest-token", default=os.getenv("TALKINGBOATS_INGEST_TOKEN", ""))
    parser.add_argument("--min-age-seconds", type=float, default=10.0)
    parser.add_argument(
        "--min-duration-seconds",
        type=_nonnegative_float,
        default=os.getenv("TALKINGBOATS_SPOOL_MIN_DURATION_SECONDS", "1"),
        help="Discard completed clips shorter than this duration before upload.",
    )
    parser.add_argument(
        "--max-synchronous-channels",
        type=_nonnegative_int,
        default=os.getenv("TALKINGBOATS_SPOOL_MAX_SYNCHRONOUS_CHANNELS", "3"),
        help="Discard same-second bursts spanning more than this many channels; 0 disables.",
    )
    parser.add_argument("--poll-seconds", type=float, default=20.0)
    parser.add_argument(
        "--mp3-bitrate",
        default=os.getenv("TALKINGBOATS_EDGE_UPLOAD_BITRATE", "64k"),
    )
    parser.add_argument(
        "--ffmpeg-path",
        default=os.getenv("TALKINGBOATS_EDGE_UPLOAD_FFMPEG_PATH", "ffmpeg"),
    )
    failed_root = os.getenv("TALKINGBOATS_SPOOL_FAILED_ROOT")
    parser.add_argument(
        "--failed-root",
        type=Path,
        default=Path(failed_root) if failed_root else None,
    )
    parser.add_argument(
        "--max-files-per-poll",
        type=int,
        default=int(os.getenv("TALKINGBOATS_SPOOL_MAX_FILES_PER_POLL", "100")),
    )
    parser.add_argument(
        "--max-retained-files",
        type=_nonnegative_int,
        default=os.getenv("TALKINGBOATS_SPOOL_MAX_RETAINED_FILES") or None,
        help="Keep only this many completed source clips while the uploader is offline.",
    )
    parser.add_argument("--delete-after-upload", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if not args.api_url:
        parser.error("--api-url or TALKINGBOATS_PRIVATE_API is required")
    if not args.ingest_token:
        parser.error("--ingest-token or TALKINGBOATS_INGEST_TOKEN is required")

    while True:
        try:
            uploaded = process_spool_once(
                spool_root=args.spool_root,
                api_url=args.api_url,
                ingest_token=args.ingest_token,
                min_age_seconds=args.min_age_seconds,
                min_duration_seconds=args.min_duration_seconds,
                max_synchronous_channels=args.max_synchronous_channels,
                delete_after_upload=args.delete_after_upload,
                mp3_bitrate=args.mp3_bitrate,
                ffmpeg_path=args.ffmpeg_path,
                failed_root=args.failed_root,
                max_files=args.max_files_per_poll,
                max_retained_files=args.max_retained_files,
            )
            _log_event("spool_uploader_poll", uploaded=uploaded)
        except Exception as exc:  # noqa: BLE001 - keep daemon retrying.
            _log_event("spool_uploader_error", error=f"{type(exc).__name__}: {exc}")
        if args.once:
            break
        time.sleep(args.poll_seconds)


def _started_at_from_filename(path: Path) -> datetime | None:
    tokens = path.stem.replace("-", "_").split("_")
    for index, token in enumerate(tokens):
        if len(token) == 16 and token.endswith("Z") and "T" in token:
            try:
                return datetime.strptime(token, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            except ValueError:
                return None
        if (
            len(token) == 8
            and token.isdigit()
            and index + 1 < len(tokens)
            and len(tokens[index + 1]) == 6
            and tokens[index + 1].isdigit()
        ):
            try:
                return datetime.strptime(
                    f"{token}{tokens[index + 1]}",
                    "%Y%m%d%H%M%S",
                ).replace(tzinfo=UTC)
            except ValueError:
                return None
    return None


def _idempotency_key(*, channel: str, started_at: datetime, path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"spool-v1:{channel}:{_format_utc(started_at)}:{digest}"


def _optional_audio_filter(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.lower() in {"0", "false", "no", "none", "off", "disabled"}:
        return None
    return stripped


def _clip_available_for_fallback(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _env_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    stripped = value.strip().lower()
    if not stripped:
        return default
    if stripped in {"1", "true", "yes", "on", "enabled"}:
        return True
    if stripped in {"0", "false", "no", "off", "disabled"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return parsed


def _nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return parsed


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return parsed.astimezone(UTC)


def quarantine_spooled_clip(
    *,
    clip: SpooledAudioClip,
    spool_root: Path,
    failed_root: Path,
    error: BaseException,
) -> Path:
    try:
        relative_path = clip.audio_path.relative_to(spool_root)
    except ValueError:
        relative_path = Path(clip.audio_path.name)
    failed_path = _unique_failed_path(failed_root / relative_path)
    failed_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(clip.audio_path), str(failed_path))
    sidecar = failed_path.with_suffix(f"{failed_path.suffix}.error.json")
    sidecar.write_text(
        json.dumps(
            {
                "channel": clip.channel,
                "error": f"{type(error.__cause__ or error).__name__}: {error.__cause__ or error}",
                "failed_at": _format_utc(datetime.now(UTC)),
                "source": str(relative_path),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return failed_path


def _discard_spooled_clip(audio_path: Path) -> None:
    audio_path.unlink(missing_ok=True)
    for metadata_path in (
        audio_path.with_suffix(".json"),
        audio_path.with_name(f"{audio_path.name}.json"),
    ):
        metadata_path.unlink(missing_ok=True)


def _unique_failed_path(path: Path) -> Path:
    if not path.exists():
        return path
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return path.with_name(f"{path.stem}-{digest}{path.suffix}")


def _normalize_spool_channel(value: str) -> Channel | None:
    channel = value.strip().upper()
    if channel in ALLOWED_CHANNELS:
        return channel  # type: ignore[return-value]
    if (channel.isdigit() and len(channel) == 1) or (
        len(channel) == 2 and channel[0].isdigit() and channel[1].isalpha()
    ):
        channel = f"0{channel}"
    if channel in ALLOWED_CHANNELS:
        return channel  # type: ignore[return-value]
    return None


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _log_event(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
