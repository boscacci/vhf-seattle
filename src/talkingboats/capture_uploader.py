from __future__ import annotations

import argparse
import hashlib
import json
import os
import wave
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from talkingboats.schemas import Channel, ClipPresignRequest, ClipPresignResponse

CONTENT_TYPES_BY_SUFFIX = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}


@dataclass(frozen=True)
class ClipUploadRequest:
    channel: Channel
    audio_path: Path
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    content_type: str | None = None
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if self.channel not in ("68", "14"):
            raise ValueError("channel must be 68 or 14")
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must include a timezone")
        if self.ended_at is not None and self.ended_at.tzinfo is None:
            raise ValueError("ended_at must include a timezone")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")


@dataclass(frozen=True)
class ClipUploadResult:
    bucket: str
    key: str
    bytes_uploaded: int
    content_type: str
    idempotency_key: str


def upload_clip(
    api_base_url: str,
    ingest_token: str,
    request: ClipUploadRequest,
    *,
    client: httpx.Client | None = None,
) -> ClipUploadResult:
    if not ingest_token:
        raise ValueError("ingest_token is required")

    presign_request = build_presign_request(request)
    api_base_url = api_base_url.rstrip("/")
    owns_client = client is None
    http_client = client or httpx.Client(timeout=httpx.Timeout(30.0, read=120.0))
    audio_bytes = request.audio_path.read_bytes()

    try:
        presign_response = http_client.post(
            f"{api_base_url}/api/ingest/clips/presign",
            headers={"X-TalkingBoats-Ingest-Token": ingest_token},
            json=presign_request.model_dump(mode="json", exclude_none=True),
        )
        presign_response.raise_for_status()
        upload = ClipPresignResponse.model_validate(presign_response.json())

        put_response = http_client.put(
            upload.upload_url,
            headers=upload.required_headers,
            content=audio_bytes,
        )
        put_response.raise_for_status()
    finally:
        if owns_client:
            http_client.close()

    return ClipUploadResult(
        bucket=upload.bucket,
        key=upload.key,
        bytes_uploaded=len(audio_bytes),
        content_type=presign_request.content_type,
        idempotency_key=presign_request.idempotency_key,
    )


def build_presign_request(request: ClipUploadRequest) -> ClipPresignRequest:
    if not request.audio_path.is_file():
        raise FileNotFoundError(request.audio_path)

    content_type = request.content_type or infer_audio_content_type(request.audio_path)
    duration_seconds = request.duration_seconds
    if duration_seconds is None and content_type in {"audio/wav", "audio/x-wav"}:
        duration_seconds = _try_wav_duration_seconds(request.audio_path)

    return ClipPresignRequest(
        channel=request.channel,
        started_at=request.started_at.astimezone(UTC),
        ended_at=request.ended_at.astimezone(UTC) if request.ended_at else None,
        content_type=content_type,
        idempotency_key=request.idempotency_key or build_idempotency_key(request),
        duration_seconds=duration_seconds,
    )


def infer_audio_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in CONTENT_TYPES_BY_SUFFIX:
        raise ValueError(f"unsupported audio extension: {suffix or '<none>'}")
    return CONTENT_TYPES_BY_SUFFIX[suffix]


def build_idempotency_key(request: ClipUploadRequest) -> str:
    stamp = _format_utc(request.started_at)
    digest = _file_sha256(request.audio_path)
    return f"clip-v1:{request.channel}:{stamp}:{digest}"


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _try_wav_duration_seconds(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wav:
            frame_rate = wav.getframerate()
            if frame_rate <= 0:
                return None
            return round(wav.getnframes() / frame_rate, 3)
    except (OSError, EOFError, wave.Error):
        return None


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("datetime must include a timezone")
    return parsed.astimezone(UTC)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a captured Talking Boats audio clip.")
    parser.add_argument("--api-url", default=os.getenv("TALKINGBOATS_PRIVATE_API"))
    parser.add_argument("--ingest-token", default=os.getenv("TALKINGBOATS_INGEST_TOKEN"))
    parser.add_argument("--channel", choices=["68", "14"], required=True)
    parser.add_argument("--audio-path", type=Path, required=True)
    parser.add_argument("--started-at", type=_parse_datetime)
    parser.add_argument("--ended-at", type=_parse_datetime)
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--content-type")
    parser.add_argument("--idempotency-key")
    args = parser.parse_args()

    if not args.api_url:
        parser.error("--api-url or TALKINGBOATS_PRIVATE_API is required")
    if not args.ingest_token:
        parser.error("--ingest-token or TALKINGBOATS_INGEST_TOKEN is required")

    started_at = args.started_at
    if started_at is None:
        started_at = datetime.fromtimestamp(args.audio_path.stat().st_mtime, UTC)

    result = upload_clip(
        api_base_url=args.api_url,
        ingest_token=args.ingest_token,
        request=ClipUploadRequest(
            channel=args.channel,
            audio_path=args.audio_path,
            started_at=started_at,
            ended_at=args.ended_at,
            duration_seconds=args.duration_seconds,
            content_type=args.content_type,
            idempotency_key=args.idempotency_key,
        ),
    )
    print(json.dumps(result.__dict__, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
