from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

ALLOWED_CHANNELS = {"WX", "05A", "13", "14", "16", "22A", "66A", "68", "69", "71", "72", "74"}
CONTENT_TYPES = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}
Channel = Literal["WX", "05A", "13", "14", "16", "22A", "66A", "68", "69", "71", "72", "74"]


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


@dataclass(frozen=True)
class UploadResult:
    bucket: str
    key: str
    bytes_uploaded: int


def infer_spool_channel(path: Path) -> Channel:
    for part in reversed(path.parts):
        if part in ALLOWED_CHANNELS:
            return part  # type: ignore[return-value]
    raise ValueError(f"could not infer channel from path: {path}")


def discover_completed_audio_files(
    *,
    spool_root: Path,
    now: datetime,
    min_age_seconds: float,
    stat_func=None,
) -> list[SpooledAudioClip]:
    stat_func = stat_func or (lambda path: path.stat())
    clips: list[SpooledAudioClip] = []
    if not spool_root.exists():
        return clips
    for audio_path in sorted(spool_root.rglob("*")):
        if not audio_path.is_file() or audio_path.suffix.lower() not in CONTENT_TYPES:
            continue
        stat = stat_func(audio_path)
        if stat.st_size <= 0:
            continue
        modified_at = datetime.fromtimestamp(stat.st_mtime, UTC)
        if (now - modified_at).total_seconds() < min_age_seconds:
            continue
        channel = infer_spool_channel(audio_path)
        started_at = _started_at_from_filename(audio_path) or modified_at
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
            )
        )
    return clips


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
) -> int:
    uploaded = 0
    now = datetime.now(UTC)
    for clip in discover_completed_audio_files(
        spool_root=spool_root,
        now=now,
        min_age_seconds=min_age_seconds,
    ):
        result = upload_spooled_clip(api_url=api_url, ingest_token=ingest_token, clip=clip)
        uploaded += 1
        _log_event(
            "spool_clip_uploaded",
            channel=clip.channel,
            audio_file=clip.audio_path.name,
            key=result.key,
            bytes_uploaded=result.bytes_uploaded,
        )
        if delete_after_upload:
            clip.audio_path.unlink(missing_ok=True)
    return uploaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload completed multichannel audio spool files.")
    parser.add_argument("--spool-root", type=Path, default=Path("/opt/talkingboats/spool/airband"))
    parser.add_argument("--api-url", default=os.getenv("TALKINGBOATS_PRIVATE_API", ""))
    parser.add_argument("--ingest-token", default=os.getenv("TALKINGBOATS_INGEST_TOKEN", ""))
    parser.add_argument("--min-age-seconds", type=float, default=10.0)
    parser.add_argument("--poll-seconds", type=float, default=20.0)
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
                delete_after_upload=args.delete_after_upload,
            )
            _log_event("spool_uploader_poll", uploaded=uploaded)
        except Exception as exc:  # noqa: BLE001 - keep daemon retrying.
            _log_event("spool_uploader_error", error=f"{type(exc).__name__}: {exc}")
        if args.once:
            break
        time.sleep(args.poll_seconds)


def _started_at_from_filename(path: Path) -> datetime | None:
    for token in path.stem.replace("-", "_").split("_"):
        if len(token) == 16 and token.endswith("Z") and "T" in token:
            try:
                return datetime.strptime(token, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            except ValueError:
                return None
    return None


def _idempotency_key(*, channel: str, started_at: datetime, path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"spool-v1:{channel}:{_format_utc(started_at)}:{digest}"


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _log_event(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
