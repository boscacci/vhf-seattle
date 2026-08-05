from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import wave
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from talkingboats.audio_processing import (
    DEFAULT_SPEECH_AUDIO_FILTER,
    DEFAULT_TRANSCRIBE_BEAM_SIZE,
    DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ,
)
from talkingboats.durable_events import to_dynamodb_item

DEFAULT_AUDIO_FILTER = DEFAULT_SPEECH_AUDIO_FILTER
DEFAULT_TRANSCRIBE_MODEL = "base.en"


class TranscriptStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def add_entry(self, *, text: str, started_at: str, ended_at: str, received_at: str) -> bool:
        with self._lock, sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO transcript_entries
                    (text, started_at, ended_at, received_at)
                VALUES (?, ?, ?, ?)
                """,
                (text, started_at, ended_at, received_at),
            )
            return cursor.rowcount > 0

    def recent_entries(self, *, limit: int) -> list[dict[str, str]]:
        with self._lock, sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT text, started_at, ended_at
                FROM transcript_entries
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {"text": text, "started_at": started_at, "ended_at": ended_at}
            for text, started_at, ended_at in reversed(rows)
        ]

    def count_entries(self) -> int:
        with self._lock, sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT count(*) FROM transcript_entries").fetchone()
        return int(row[0])

    def _init_schema(self) -> None:
        with self._lock, sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS transcript_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    UNIQUE(text, started_at, ended_at)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_transcript_entries_started_at
                ON transcript_entries(started_at)
                """
            )


class DynamoTranscriptStore:
    def __init__(
        self,
        *,
        table_name: str,
        aws_region: str,
        environment: str = "dev",
        table: Any | None = None,
    ) -> None:
        self.environment = environment
        if table is None:
            import boto3

            table = boto3.resource("dynamodb", region_name=aws_region).Table(table_name)
        self.table = table

    @classmethod
    def from_env(cls) -> DynamoTranscriptStore:
        table_name = os.getenv("TALKINGBOATS_TRANSCRIPT_STORE_DYNAMO_TABLE") or os.getenv(
            "TALKINGBOATS_DURABLE_EVENTS_TABLE"
        )
        if not table_name:
            raise RuntimeError(
                "TALKINGBOATS_TRANSCRIPT_STORE_DYNAMO_TABLE or "
                "TALKINGBOATS_DURABLE_EVENTS_TABLE is required"
            )
        return cls(
            table_name=table_name,
            aws_region=os.getenv("TALKINGBOATS_AWS_REGION", "us-west-2"),
            environment=os.getenv("TALKINGBOATS_DURABLE_EVENTS_ENVIRONMENT", "dev"),
        )

    def add_entry(self, *, text: str, started_at: str, ended_at: str, received_at: str) -> bool:
        self.table.put_item(
            Item=to_dynamodb_item(
                {
                    "pk": self._pk(),
                    "sk": _transcript_entry_sk(
                        text=text,
                        started_at=started_at,
                        ended_at=ended_at,
                    ),
                    "entity_type": "live_transcript_entry",
                    "text": text,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "received_at": received_at,
                }
            )
        )
        return True

    def recent_entries(self, *, limit: int) -> list[dict[str, str]]:
        rows = self._query_items(limit=limit, scan_forward=False)
        return [
            {
                "text": str(item["text"]),
                "started_at": str(item["started_at"]),
                "ended_at": str(item["ended_at"]),
            }
            for item in reversed(rows)
        ]

    def count_entries(self) -> int:
        total = 0
        start_key: dict[str, Any] | None = None
        while True:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": "pk = :pk",
                "ExpressionAttributeValues": {":pk": self._pk()},
                "Select": "COUNT",
            }
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            response = self.table.query(**kwargs)
            total += int(response.get("Count", 0))
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return total

    def _query_items(self, *, limit: int, scan_forward: bool) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        remaining = limit
        start_key: dict[str, Any] | None = None
        while remaining > 0:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": "pk = :pk",
                "ExpressionAttributeValues": {":pk": self._pk()},
                "ScanIndexForward": scan_forward,
                "Limit": remaining,
            }
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            response = self.table.query(**kwargs)
            items.extend(response.get("Items", []))
            remaining = limit - len(items)
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return items[:limit]

    def _pk(self) -> str:
        return f"live_transcripts#{self.environment}"


def _transcript_entry_sk(*, text: str, started_at: str, ended_at: str) -> str:
    digest = hashlib.sha256(f"{text}\0{started_at}\0{ended_at}".encode()).hexdigest()[:16]
    return f"{started_at}#{digest}"


@dataclass
class TranscriptState:
    max_entries: int = 30
    store: TranscriptStore | DynamoTranscriptStore | None = None
    status: str = "running"
    updated_at: str | None = None
    error: str | None = None
    entries: deque[dict[str, str]] = field(default_factory=deque)

    def add_entry(self, *, text: str, started_at: str, ended_at: str) -> None:
        cleaned = " ".join(text.split())
        if not cleaned:
            return
        received_at = _format_utc(datetime.now(UTC))
        entry = {
            "text": cleaned,
            "started_at": started_at,
            "ended_at": ended_at,
        }
        if self.store is not None:
            self.store.add_entry(
                text=cleaned,
                started_at=started_at,
                ended_at=ended_at,
                received_at=received_at,
            )
        self.entries.append(entry)
        while len(self.entries) > self.max_entries:
            self.entries.popleft()
        self.updated_at = received_at
        self.error = None

    def mark_running(self) -> None:
        self.status = "running"
        self.error = None
        self.updated_at = _format_utc(datetime.now(UTC))

    def set_error(self, error: str) -> None:
        self.status = "error"
        self.error = error
        self.updated_at = _format_utc(datetime.now(UTC))

    def payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "updated_at": self.updated_at,
            "error": self.error,
            "entries": list(self.entries),
        }


def create_app(state: TranscriptState) -> FastAPI:
    app = FastAPI(title="Talking Boats Live Transcriber", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": state.status}

    @app.get("/api/live-transcript")
    def live_transcript() -> dict[str, Any]:
        return state.payload()

    @app.get("/api/transcripts/recent")
    def recent_transcripts(limit: int = 50) -> dict[str, Any]:
        bounded_limit = min(max(limit, 1), 500)
        if state.store is None:
            return {"entries": list(state.entries)[-bounded_limit:]}
        return {"entries": state.store.recent_entries(limit=bounded_limit)}

    @app.get("/api/transcripts/stats")
    def transcript_stats() -> dict[str, Any]:
        entry_count = (
            state.store.count_entries() if state.store is not None else len(state.entries)
        )
        return {
            "persisted": state.store is not None,
            "entries": entry_count,
            "updated_at": state.updated_at,
        }

    return app


def build_ffmpeg_pcm_command(
    stream_url: str,
    *,
    sample_rate_hz: int,
    audio_filter: str | None = None,
) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-i",
        stream_url,
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate_hz),
    ]
    if audio_filter:
        command.extend(["-af", audio_filter])
    command.extend(["-f", "s16le", "pipe:1"])
    return command


def iter_pcm_chunks(
    stream_url: str,
    *,
    sample_rate_hz: int,
    chunk_seconds: float,
    audio_filter: str | None,
) -> Iterator[tuple[datetime, bytes]]:
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be positive")
    chunk_bytes = int(sample_rate_hz * chunk_seconds) * 2
    command = build_ffmpeg_pcm_command(
        stream_url,
        sample_rate_hz=sample_rate_hz,
        audio_filter=audio_filter,
    )
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    try:
        if process.stdout is None:
            raise RuntimeError("ffmpeg stdout pipe was not created")
        while True:
            started_at = datetime.now(UTC)
            chunk = process.stdout.read(chunk_bytes)
            if not chunk:
                break
            yield started_at, chunk
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def iter_encoded_audio_chunks(
    stream_url: str,
    *,
    chunk_seconds: float,
) -> Iterator[tuple[datetime, bytes]]:
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be positive")
    timeout = httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)
    with httpx.stream("GET", stream_url, timeout=timeout, follow_redirects=False) as response:
        response.raise_for_status()
        chunk_started = datetime.now(UTC)
        deadline = time.monotonic() + chunk_seconds
        chunks: list[bytes] = []
        for data in response.iter_bytes():
            if not data:
                continue
            chunks.append(data)
            if time.monotonic() >= deadline:
                yield chunk_started, b"".join(chunks)
                chunk_started = datetime.now(UTC)
                deadline = time.monotonic() + chunk_seconds
                chunks = []


def append_transcript_segments(
    state: TranscriptState,
    segments: Iterable[Any],
    *,
    chunk_started: datetime,
) -> None:
    for segment in segments:
        text = getattr(segment, "text", "")
        if not text.strip():
            continue
        started_at = chunk_started + timedelta(seconds=float(getattr(segment, "start", 0.0)))
        ended_at = chunk_started + timedelta(seconds=float(getattr(segment, "end", 0.0)))
        state.add_entry(
            text=text,
            started_at=_format_utc(started_at),
            ended_at=_format_utc(ended_at),
        )


def run_transcription_loop(
    *,
    state: TranscriptState,
    stream_url: str,
    model_size: str,
    device: str,
    compute_type: str,
    sample_rate_hz: int,
    chunk_seconds: float,
    audio_filter: str | None,
    beam_size: int,
    hotwords: str | None,
) -> None:
    model = _load_faster_whisper_model(
        model_size=model_size,
        device=device,
        compute_type=compute_type,
    )
    state.status = "running"
    while True:
        try:
            if shutil.which("ffmpeg"):
                chunks = iter_pcm_chunks(
                    stream_url,
                    sample_rate_hz=sample_rate_hz,
                    chunk_seconds=chunk_seconds,
                    audio_filter=audio_filter,
                )
                suffix = ".wav"
            else:
                chunks = iter_encoded_audio_chunks(stream_url, chunk_seconds=chunk_seconds)
                suffix = ".mp3"
            for chunk_started, audio_bytes in chunks:
                state.mark_running()
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                    audio_path = Path(handle.name)
                try:
                    if suffix == ".wav":
                        write_pcm_wav(audio_path, audio_bytes, sample_rate_hz=sample_rate_hz)
                    else:
                        audio_path.write_bytes(audio_bytes)
                    segments = transcribe_audio_file(
                        model=model,
                        audio_path=audio_path,
                        beam_size=beam_size,
                        vad_filter=True,
                        hotwords=hotwords,
                    )
                    append_transcript_segments(state, segments, chunk_started=chunk_started)
                except Exception as exc:  # noqa: BLE001 - keep service alive and expose state.
                    state.set_error(f"{type(exc).__name__}: {exc}")
                    time.sleep(2)
                finally:
                    audio_path.unlink(missing_ok=True)
            state.set_error("stream ended; reconnecting")
        except Exception as exc:  # noqa: BLE001 - live stream may vanish while moving the Pi.
            state.set_error(f"{type(exc).__name__}: {exc}; reconnecting")
        time.sleep(5)


def write_pcm_wav(path: Path, pcm: bytes, *, sample_rate_hz: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate_hz)
        wav.writeframes(pcm)


def transcribe_audio_file(
    *,
    model: Any,
    audio_path: Path,
    beam_size: int = DEFAULT_TRANSCRIBE_BEAM_SIZE,
    vad_filter: bool = True,
    hotwords: str | None = None,
) -> Iterable[Any]:
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
    return segments


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live open-source captions for Talking Boats.")
    parser.add_argument("--stream-url", default=os.getenv("TALKINGBOATS_TRANSCRIBE_STREAM_URL"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8055)
    parser.add_argument(
        "--model-size",
        default=os.getenv("TALKINGBOATS_TRANSCRIBE_MODEL", DEFAULT_TRANSCRIBE_MODEL),
    )
    parser.add_argument("--device", default=os.getenv("TALKINGBOATS_TRANSCRIBE_DEVICE", "cpu"))
    parser.add_argument(
        "--compute-type",
        default=os.getenv("TALKINGBOATS_TRANSCRIBE_COMPUTE_TYPE", "int8"),
    )
    parser.add_argument("--sample-rate-hz", type=int, default=DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ)
    parser.add_argument("--chunk-seconds", type=float, default=12.0)
    parser.add_argument("--max-entries", type=int, default=30)
    parser.add_argument("--audio-filter", default=os.getenv("TALKINGBOATS_TRANSCRIBE_AUDIO_FILTER"))
    parser.add_argument("--no-audio-filter", action="store_true")
    parser.add_argument(
        "--beam-size",
        type=int,
        default=int(os.getenv("TALKINGBOATS_TRANSCRIBE_BEAM_SIZE", DEFAULT_TRANSCRIBE_BEAM_SIZE)),
    )
    parser.add_argument("--hotwords", default=os.getenv("TALKINGBOATS_TRANSCRIBE_HOTWORDS"))
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=Path(os.environ["TALKINGBOATS_TRANSCRIBE_SQLITE_PATH"])
        if os.getenv("TALKINGBOATS_TRANSCRIBE_SQLITE_PATH")
        else None,
    )
    args = parser.parse_args()

    if not args.stream_url:
        parser.error("--stream-url or TALKINGBOATS_TRANSCRIBE_STREAM_URL is required")
    if args.beam_size <= 0:
        parser.error("--beam-size must be positive")

    state = TranscriptState(
        max_entries=args.max_entries,
        store=_transcript_store_from_env(args.sqlite_path),
    )
    audio_filter = None if args.no_audio_filter else (args.audio_filter or DEFAULT_AUDIO_FILTER)
    worker = threading.Thread(
        target=run_transcription_loop,
        kwargs={
            "state": state,
            "stream_url": args.stream_url,
            "model_size": args.model_size,
            "device": args.device,
            "compute_type": args.compute_type,
            "sample_rate_hz": args.sample_rate_hz,
            "chunk_seconds": args.chunk_seconds,
            "audio_filter": audio_filter,
            "beam_size": args.beam_size,
            "hotwords": args.hotwords,
        },
        daemon=True,
    )
    worker.start()
    uvicorn.run(create_app(state), host=args.host, port=args.port)


def _load_faster_whisper_model(*, model_size: str, device: str, compute_type: str) -> Any:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Install with: "
            'conda run -n dell python -m pip install -e ".[transcribe]"'
        ) from exc
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _transcript_store_from_env(
    sqlite_path: Path | None,
) -> TranscriptStore | DynamoTranscriptStore | None:
    backend = os.getenv("TALKINGBOATS_TRANSCRIPT_STORE_BACKEND") or os.getenv(
        "TALKINGBOATS_CLIP_STORE_BACKEND",
        "dynamodb",
    )
    if backend == "dynamodb":
        return DynamoTranscriptStore.from_env()
    if backend == "sqlite":
        return TranscriptStore(sqlite_path) if sqlite_path else None
    raise RuntimeError(f"unsupported transcript store backend: {backend}")


if __name__ == "__main__":
    main()
