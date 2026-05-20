from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from talkingboats.security import assert_public_safe

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
        clips.append(_sanitize_clip(clip))

    public_manifest = {
        "generated_at": private_manifest.get("generated_at"),
        "site": {
            "title": private_manifest.get("site", {}).get("title", "Talking Boats"),
            "subtitle": private_manifest.get("site", {}).get(
                "subtitle",
                "Reviewed VHF marine-radio moments from Elliott Bay.",
            ),
        },
        "stats": _copy_allowed(private_manifest.get("stats", {}), ALLOWED_STATS_FIELDS),
        "clips": clips,
    }
    public_manifest["stats"]["clip_count"] = len(clips)
    assert_public_safe(public_manifest)
    return public_manifest


def export_public_site(
    private_manifest_path: Path,
    site_source_dir: Path,
    output_dir: Path,
    audio_source_dir: Path | None = None,
) -> dict[str, Any]:
    private_manifest = json.loads(private_manifest_path.read_text(encoding="utf-8"))
    public_manifest = sanitize_public_manifest(private_manifest)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.copytree(site_source_dir, output_dir)

    clips_dir = output_dir / "clips"
    clips_dir.mkdir(exist_ok=True)
    if audio_source_dir:
        _copy_approved_audio(public_manifest, audio_source_dir, clips_dir)

    (output_dir / "public_manifest.json").write_text(
        json.dumps(public_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return public_manifest


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
) -> None:
    for clip in public_manifest["clips"]:
        filename = clip.get("audio_public_filename")
        if not filename:
            continue
        source = audio_source_dir / filename
        if not source.exists():
            raise PublicExportError(f"approved audio file does not exist: {source}")
        shutil.copy2(source, clips_dir / filename)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the sanitized Talking Boats public site.")
    parser.add_argument("--private-manifest", type=Path, required=True)
    parser.add_argument("--site-source", type=Path, default=Path("public-site"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/public-site"))
    parser.add_argument("--audio-source-dir", type=Path)
    args = parser.parse_args()

    export_public_site(
        private_manifest_path=args.private_manifest,
        site_source_dir=args.site_source,
        output_dir=args.output_dir,
        audio_source_dir=args.audio_source_dir,
    )


if __name__ == "__main__":
    main()
