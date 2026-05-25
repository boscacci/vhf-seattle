from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import tempfile
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.exceptions import ClientError

from talkingboats.audio_processing import (
    DEFAULT_SPEECH_AUDIO_FILTER,
    DEFAULT_TRANSCRIBE_BEAM_SIZE,
    DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ,
    prepared_transcription_audio,
)
from talkingboats.schemas import ClipPresignRequest


class ClipNotAvailable(RuntimeError):
    """Raised when a presigned upload has not appeared in object storage yet."""


class ClipReader(Protocol):
    def download(self, key: str, output_path: Path) -> None: ...


@dataclass(frozen=True)
class UploadedClipRecord:
    key: str
    channel: str
    started_at: str
    ended_at: str | None
    duration_seconds: float | None
    content_type: str
    idempotency_key: str
    status: str
    transcript: str | None
    error: str | None


@dataclass(frozen=True)
class RecentTranscribedClip:
    key: str
    channel: str
    started_at: str
    ended_at: str | None
    duration_seconds: float | None
    content_type: str
    transcript: str
    segments: list[dict[str, str]]


@dataclass(frozen=True)
class UploadedClipSegment:
    text: str
    started_at: str
    ended_at: str
    relative_start_seconds: float
    relative_end_seconds: float


@dataclass
class ProcessSummary:
    processed: int = 0
    transcribed: int = 0
    empty: int = 0
    waiting_upload: int = 0
    failed: int = 0


class UploadedClipStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def record_presigned_upload(self, *, key: str, request: ClipPresignRequest) -> None:
        now = _format_utc(datetime.now(UTC))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO uploaded_clips (
                    key,
                    channel,
                    started_at,
                    ended_at,
                    duration_seconds,
                    content_type,
                    idempotency_key,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    key,
                    request.channel,
                    _format_utc(request.started_at),
                    _format_utc(request.ended_at) if request.ended_at else None,
                    request.duration_seconds,
                    request.content_type,
                    request.idempotency_key,
                    now,
                    now,
                ),
            )

    def pending_uploads(
        self,
        *,
        limit: int,
        retry_errors: bool = False,
    ) -> list[UploadedClipRecord]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        statuses = ["pending", "waiting_upload", "processing"]
        if retry_errors:
            statuses.append("error")
        placeholders = ",".join("?" for _ in statuses)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    key,
                    channel,
                    started_at,
                    ended_at,
                    duration_seconds,
                    content_type,
                    idempotency_key,
                    status,
                    transcript,
                    error
                FROM uploaded_clips
                WHERE status IN ({placeholders})
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (*statuses, limit),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def get_clip(self, key: str) -> UploadedClipRecord | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                """
                SELECT
                    key,
                    channel,
                    started_at,
                    ended_at,
                    duration_seconds,
                    content_type,
                    idempotency_key,
                    status,
                    transcript,
                    error
                FROM uploaded_clips
                WHERE key = ?
                """,
                (key,),
            ).fetchone()
        return _row_to_record(row) if row else None

    def mark_processing(self, key: str) -> None:
        self._set_status(key, status="processing", error=None)

    def mark_waiting_upload(self, key: str, error: str) -> None:
        self._set_status(key, status="waiting_upload", error=error)

    def mark_failed(self, key: str, error: str) -> None:
        self._set_status(key, status="error", error=error)

    def mark_empty(self, key: str) -> None:
        now = _format_utc(datetime.now(UTC))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                UPDATE uploaded_clips
                SET status = 'empty',
                    transcript = '',
                    error = NULL,
                    processed_at = ?,
                    updated_at = ?
                WHERE key = ?
                """,
                (now, now, key),
            )
            connection.execute("DELETE FROM uploaded_clip_segments WHERE clip_key = ?", (key,))

    def mark_transcribed(self, key: str, segments: Iterable[UploadedClipSegment]) -> None:
        segment_list = list(segments)
        transcript = " ".join(segment.text for segment in segment_list)
        now = _format_utc(datetime.now(UTC))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                UPDATE uploaded_clips
                SET status = 'transcribed',
                    transcript = ?,
                    error = NULL,
                    processed_at = ?,
                    updated_at = ?
                WHERE key = ?
                """,
                (transcript, now, now, key),
            )
            connection.execute("DELETE FROM uploaded_clip_segments WHERE clip_key = ?", (key,))
            connection.executemany(
                """
                INSERT INTO uploaded_clip_segments (
                    clip_key,
                    text,
                    started_at,
                    ended_at,
                    relative_start_seconds,
                    relative_end_seconds
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        key,
                        segment.text,
                        segment.started_at,
                        segment.ended_at,
                        segment.relative_start_seconds,
                        segment.relative_end_seconds,
                    )
                    for segment in segment_list
                ],
            )

    def segments_for_clip(self, key: str) -> list[dict[str, str]]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT text, started_at, ended_at
                FROM uploaded_clip_segments
                WHERE clip_key = ?
                ORDER BY relative_start_seconds ASC, id ASC
                """,
                (key,),
            ).fetchall()
        return [
            {"text": text, "started_at": started_at, "ended_at": ended_at}
            for text, started_at, ended_at in rows
        ]

    def recent_transcribed(
        self,
        *,
        limit: int,
        offset: int = 0,
        channel: str | None = None,
        excluded_channels: tuple[str, ...] = (),
    ) -> list[RecentTranscribedClip]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        filters = [
            "status = 'transcribed'",
            "transcript IS NOT NULL",
            "trim(transcript) != ''",
        ]
        params: list[object] = []
        if channel:
            filters.append("channel = ?")
            params.append(channel)
        if excluded_channels:
            placeholders = ", ".join("?" for _ in excluded_channels)
            filters.append(f"channel NOT IN ({placeholders})")
            params.extend(excluded_channels)
        params.extend([limit, offset])
        where_clause = "\n                    AND ".join(filters)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    key,
                    channel,
                    started_at,
                    ended_at,
                    duration_seconds,
                    content_type,
                    transcript
                FROM uploaded_clips
                WHERE {where_clause}
                ORDER BY started_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                tuple(params),
            ).fetchall()
        clips = []
        for key, channel, started_at, ended_at, duration_seconds, content_type, transcript in rows:
            clips.append(
                RecentTranscribedClip(
                    key=key,
                    channel=channel,
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_seconds=duration_seconds,
                    content_type=content_type,
                    transcript=transcript,
                    segments=self.segments_for_clip(key),
                )
            )
        return clips

    def transcribed_channel_counts(
        self,
        *,
        excluded_channels: tuple[str, ...] = (),
    ) -> dict[str, int]:
        channel_filter = ""
        params: tuple[object, ...] = ()
        if excluded_channels:
            placeholders = ", ".join("?" for _ in excluded_channels)
            channel_filter = f"AND channel NOT IN ({placeholders})"
            params = tuple(excluded_channels)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                f"""
                SELECT channel, count(*)
                FROM uploaded_clips
                WHERE status = 'transcribed'
                    AND transcript IS NOT NULL
                    AND trim(transcript) != ''
                    {channel_filter}
                GROUP BY channel
                ORDER BY channel
                """,
                params,
            ).fetchall()
        return {channel: count for channel, count in rows}

    def stats(self) -> dict[str, Any]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT status, count(*) FROM uploaded_clips GROUP BY status ORDER BY status"
            ).fetchall()
            channel_rows = connection.execute(
                """
                SELECT channel, status, count(*)
                FROM uploaded_clips
                GROUP BY channel, status
                ORDER BY channel, status
                """
            ).fetchall()
            recent = connection.execute(
                """
                SELECT key, channel, started_at, status, transcript, error
                FROM uploaded_clips
                ORDER BY updated_at DESC, id DESC
                LIMIT 20
                """
            ).fetchall()
        channel_counts: dict[str, dict[str, int]] = {}
        for channel, status, count in channel_rows:
            channel_counts.setdefault(channel, {})[status] = count
        return {
            "counts": {status: count for status, count in rows},
            "channel_counts": channel_counts,
            "recent": [
                {
                    "key": key,
                    "channel": channel,
                    "started_at": started_at,
                    "status": status,
                    "transcript": transcript,
                    "error": error,
                }
                for key, channel, started_at, status, transcript, error in recent
            ],
        }

    def _set_status(self, key: str, *, status: str, error: str | None) -> None:
        now = _format_utc(datetime.now(UTC))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                UPDATE uploaded_clips
                SET status = ?,
                    error = ?,
                    updated_at = ?
                WHERE key = ?
                """,
                (status, error, now, key),
            )

    def _init_schema(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS uploaded_clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    channel TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_seconds REAL,
                    content_type TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    transcript TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    processed_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploaded_clips_status_created
                ON uploaded_clips(status, created_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploaded_clips_status_channel_started
                ON uploaded_clips(status, channel, started_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS uploaded_clip_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clip_key TEXT NOT NULL,
                    text TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    relative_start_seconds REAL NOT NULL,
                    relative_end_seconds REAL NOT NULL,
                    FOREIGN KEY(clip_key) REFERENCES uploaded_clips(key)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploaded_clip_segments_clip_key
                ON uploaded_clip_segments(clip_key)
                """
            )


class S3ClipReader:
    def __init__(self, *, bucket: str, aws_region: str, client: Any | None = None) -> None:
        if not bucket:
            raise ValueError("bucket is required")
        self.bucket = bucket
        self.client = client or boto3.client("s3", region_name=aws_region)

    def download(self, key: str, output_path: Path) -> None:
        try:
            self.client.download_file(self.bucket, key, str(output_path))
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise ClipNotAvailable(f"{key} is not available in S3 yet") from exc
            raise


def process_pending_uploads_once(
    *,
    store: UploadedClipStore,
    clip_reader: ClipReader,
    model: Any,
    limit: int,
    retry_errors: bool = False,
    vad_filter: bool = False,
    min_segment_avg_logprob: float | None = -0.6,
    audio_filter: str | None = DEFAULT_SPEECH_AUDIO_FILTER,
    sample_rate_hz: int = DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ,
    beam_size: int = DEFAULT_TRANSCRIBE_BEAM_SIZE,
    hotwords: str | None = None,
    ffmpeg_path: str | None = None,
    ffmpeg_runner: Any | None = None,
) -> ProcessSummary:
    if beam_size <= 0:
        raise ValueError("beam_size must be positive")
    summary = ProcessSummary()
    for record in store.pending_uploads(limit=limit, retry_errors=retry_errors):
        summary.processed += 1
        store.mark_processing(record.key)
        suffix = _suffix_for_content_type(record.content_type)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            audio_path = Path(handle.name)
        try:
            clip_reader.download(record.key, audio_path)
            prepare_kwargs: dict[str, Any] = {
                "sample_rate_hz": sample_rate_hz,
                "audio_filter": audio_filter,
                "ffmpeg_path": ffmpeg_path,
            }
            if ffmpeg_runner is not None:
                prepare_kwargs["runner"] = ffmpeg_runner
            with prepared_transcription_audio(audio_path, **prepare_kwargs) as prepared_audio_path:
                segments = transcribe_audio_file(
                    model=model,
                    audio_path=prepared_audio_path,
                    record=record,
                    vad_filter=vad_filter,
                    min_segment_avg_logprob=min_segment_avg_logprob,
                    beam_size=beam_size,
                    hotwords=hotwords,
                )
            if segments:
                store.mark_transcribed(record.key, segments)
                summary.transcribed += 1
            else:
                store.mark_empty(record.key)
                summary.empty += 1
        except ClipNotAvailable as exc:
            store.mark_waiting_upload(record.key, str(exc))
            summary.waiting_upload += 1
        except Exception as exc:  # noqa: BLE001 - keep background worker retryable.
            store.mark_failed(record.key, f"{type(exc).__name__}: {exc}")
            summary.failed += 1
        finally:
            audio_path.unlink(missing_ok=True)
    return summary


def transcribe_audio_file(
    *,
    model: Any,
    audio_path: Path,
    record: UploadedClipRecord,
    vad_filter: bool = False,
    min_segment_avg_logprob: float | None = -0.6,
    beam_size: int = DEFAULT_TRANSCRIBE_BEAM_SIZE,
    hotwords: str | None = None,
) -> list[UploadedClipSegment]:
    if beam_size <= 0:
        raise ValueError("beam_size must be positive")
    kwargs: dict[str, Any] = {
        "language": "en",
        "beam_size": beam_size,
        "vad_filter": vad_filter,
        "condition_on_previous_text": False,
    }
    if hotwords:
        kwargs["hotwords"] = hotwords
    segments, _ = model.transcribe(str(audio_path), **kwargs)
    clip_started = _parse_utc(record.started_at)
    rendered: list[UploadedClipSegment] = []
    for segment in segments:
        text = " ".join(str(getattr(segment, "text", "")).split())
        if not text:
            continue
        avg_logprob = getattr(segment, "avg_logprob", None)
        if (
            min_segment_avg_logprob is not None
            and avg_logprob is not None
            and float(avg_logprob) < min_segment_avg_logprob
        ):
            continue
        relative_start = float(getattr(segment, "start", 0.0))
        relative_end = float(getattr(segment, "end", relative_start))
        rendered.append(
            UploadedClipSegment(
                text=text,
                started_at=_format_utc(clip_started + timedelta(seconds=relative_start)),
                ended_at=_format_utc(clip_started + timedelta(seconds=relative_end)),
                relative_start_seconds=relative_start,
                relative_end_seconds=relative_end,
            )
        )
    if rendered and _is_likely_static_hallucination(
        " ".join(segment.text for segment in rendered)
    ):
        return []
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcribe completed Talking Boats clip uploads into SQLite."
    )
    parser.add_argument("--db-path", type=Path, default=_default_db_path())
    parser.add_argument("--bucket", default=os.getenv("TALKINGBOATS_RAW_BUCKET", ""))
    parser.add_argument("--aws-region", default=os.getenv("TALKINGBOATS_AWS_REGION", "us-west-2"))
    parser.add_argument("--model-size", default=os.getenv("TALKINGBOATS_TRANSCRIBE_MODEL", "turbo"))
    parser.add_argument("--device", default=os.getenv("TALKINGBOATS_TRANSCRIBE_DEVICE", "cpu"))
    parser.add_argument(
        "--compute-type",
        default=os.getenv("TALKINGBOATS_TRANSCRIBE_COMPUTE_TYPE", "int8"),
    )
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument(
        "--vad-filter",
        action="store_true",
        default=_env_bool("TALKINGBOATS_TRANSCRIBE_VAD_FILTER", False),
        help="Enable faster-whisper VAD. Off by default because clips are already RF-gated.",
    )
    parser.add_argument(
        "--min-segment-avg-logprob",
        type=float,
        default=_env_float("TALKINGBOATS_TRANSCRIBE_MIN_SEGMENT_AVG_LOGPROB", -0.6),
        help=(
            "Drop individual Whisper segments below this average log probability. "
            "Set very low, such as -10, to keep all segments."
        ),
    )
    parser.add_argument("--audio-filter", default=os.getenv("TALKINGBOATS_TRANSCRIBE_AUDIO_FILTER"))
    parser.add_argument("--no-audio-filter", action="store_true")
    parser.add_argument(
        "--sample-rate-hz",
        type=int,
        default=_env_int(
            "TALKINGBOATS_TRANSCRIBE_SAMPLE_RATE_HZ",
            DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ,
        ),
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=_env_int("TALKINGBOATS_TRANSCRIBE_BEAM_SIZE", DEFAULT_TRANSCRIBE_BEAM_SIZE),
    )
    parser.add_argument("--hotwords", default=os.getenv("TALKINGBOATS_TRANSCRIBE_HOTWORDS"))
    args = parser.parse_args()

    if args.db_path is None:
        parser.error("--db-path or TALKINGBOATS_CLIP_DB_PATH is required")
    if not args.bucket:
        parser.error("--bucket or TALKINGBOATS_RAW_BUCKET is required")
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    if args.sample_rate_hz <= 0:
        parser.error("--sample-rate-hz must be positive")
    if args.beam_size <= 0:
        parser.error("--beam-size must be positive")

    store = UploadedClipStore(args.db_path)
    reader = S3ClipReader(bucket=args.bucket, aws_region=args.aws_region)
    model = _load_faster_whisper_model(
        model_size=args.model_size,
        device=args.device,
        compute_type=args.compute_type,
    )

    _log_event("uploaded_clip_transcriber_start", db_path=str(args.db_path), bucket=args.bucket)
    audio_filter = None if args.no_audio_filter else (
        args.audio_filter or DEFAULT_SPEECH_AUDIO_FILTER
    )
    while True:
        summary = process_pending_uploads_once(
            store=store,
            clip_reader=reader,
            model=model,
            limit=args.limit,
            retry_errors=args.retry_errors,
            vad_filter=args.vad_filter,
            min_segment_avg_logprob=args.min_segment_avg_logprob,
            audio_filter=audio_filter,
            sample_rate_hz=args.sample_rate_hz,
            beam_size=args.beam_size,
            hotwords=args.hotwords,
        )
        _log_event("uploaded_clip_transcriber_poll", **asdict(summary))
        if args.once:
            break
        time.sleep(args.poll_seconds)


def _row_to_record(row: tuple[Any, ...]) -> UploadedClipRecord:
    return UploadedClipRecord(
        key=row[0],
        channel=row[1],
        started_at=row[2],
        ended_at=row[3],
        duration_seconds=row[4],
        content_type=row[5],
        idempotency_key=row[6],
        status=row[7],
        transcript=row[8],
        error=row[9],
    )


def _default_db_path() -> Path | None:
    value = os.getenv("TALKINGBOATS_CLIP_DB_PATH")
    return Path(value) if value else None


def _load_faster_whisper_model(*, model_size: str, device: str, compute_type: str) -> Any:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Install with: "
            'conda run -n dell python -m pip install -e ".[transcribe]"'
        ) from exc
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def _is_likely_static_hallucination(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return normalized in {
        "i love you",
        "lets go",
        "thank you",
        "thanks for watching",
        "we ll be right back",
        "well be right back",
    }


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
        raise ValueError("datetime must include a timezone")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _log_event(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
