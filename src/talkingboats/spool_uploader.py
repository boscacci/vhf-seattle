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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from talkingboats.audio_processing import build_ffmpeg_upload_mp3_command

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


@dataclass(frozen=True)
class UploadResult:
    bucket: str
    key: str
    bytes_uploaded: int


UploadFunc = Callable[..., UploadResult]
Runner = Callable[..., object]


class ClipPreparationError(Exception):
    """Raised when local clip preparation fails before any upload attempt."""


def infer_spool_channel(path: Path) -> Channel:
    for part in reversed(path.parts):
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
    return sorted(clips, key=lambda clip: clip.started_at, reverse=True)


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
    now: datetime | None = None,
    stat_func=None,
    upload_func: UploadFunc = upload_spooled_clip,
    audio_filter: str | None = None,
    mp3_bitrate: str = "64k",
    ffmpeg_path: str = "ffmpeg",
    runner: Runner = subprocess.run,
    failed_root: Path | None = None,
    max_files: int | None = 100,
) -> int:
    uploaded = 0
    now = now or datetime.now(UTC)
    failed_root = failed_root or spool_root.parent / f"{spool_root.name}-failed"
    clips = discover_completed_audio_files(
        spool_root=spool_root,
        now=now,
        min_age_seconds=min_age_seconds,
        stat_func=stat_func,
    )
    if max_files is not None:
        clips = clips[: max(0, max_files)]
    for clip in clips:
        try:
            with prepared_spooled_clip_for_upload(
                clip,
                audio_filter=audio_filter,
                mp3_bitrate=mp3_bitrate,
                ffmpeg_path=ffmpeg_path,
                runner=runner,
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


@contextmanager
def prepared_spooled_clip_for_upload(
    clip: SpooledAudioClip,
    *,
    audio_filter: str | None,
    mp3_bitrate: str = "64k",
    ffmpeg_path: str = "ffmpeg",
    runner: Runner = subprocess.run,
) -> Iterator[SpooledAudioClip]:
    resolved_filter = _optional_audio_filter(audio_filter)
    if resolved_filter is None:
        yield clip
        return

    with tempfile.TemporaryDirectory(prefix="talkingboats-spool-upload-") as tempdir:
        upload_path = Path(tempdir) / f"{clip.audio_path.stem}-edge.mp3"
        try:
            runner(
                build_ffmpeg_upload_mp3_command(
                    clip.audio_path,
                    upload_path,
                    bitrate=mp3_bitrate,
                    audio_filter=resolved_filter,
                    ffmpeg_path=ffmpeg_path,
                ),
                check=True,
            )
        except Exception as exc:  # noqa: BLE001 - daemon quarantines this local input.
            raise ClipPreparationError(f"{type(exc).__name__}: {exc}") from exc
        yield replace(
            clip,
            audio_path=upload_path,
            content_type="audio/mpeg",
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
    parser.add_argument("--poll-seconds", type=float, default=20.0)
    parser.add_argument(
        "--audio-filter",
        default=os.getenv("TALKINGBOATS_EDGE_UPLOAD_AUDIO_FILTER"),
    )
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
                audio_filter=args.audio_filter,
                mp3_bitrate=args.mp3_bitrate,
                ffmpeg_path=args.ffmpeg_path,
                failed_root=args.failed_root,
                max_files=args.max_files_per_poll,
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
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _log_event(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
