from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from talkingboats.durable_events import (
    DurableEventStore,
    DynamoDurableEventStore,
    NullDurableEventStore,
    stable_event_id,
    to_dynamodb_item,
)
from talkingboats.dynamo_clip_store import (
    CLIP_STATE_SK,
    CORRECTIONS_PK,
    TRANSCRIBED_PK,
    DynamoClipStoreConfig,
    DynamoUploadedClipStore,
    _channel_transcribed_pk,
    _clip_pk,
    _index_item,
    _index_sk,
    _status_pk,
)
from talkingboats.schemas import ClipPresignRequest


@dataclass(frozen=True)
class BackfillSummary:
    clip_count: int
    correction_count: int
    event_count: int
    read_model_count: int = 0


def backfill_clip_events(
    *,
    db_path: Path,
    event_store: DurableEventStore,
    limit: int | None = None,
    show_progress: bool = False,
) -> BackfillSummary:
    clips = _clip_rows(db_path, limit=limit)
    event_count = 0
    for index, clip in enumerate(clips, start=1):
        _maybe_print_progress(index, len(clips), show_progress=show_progress)
        event_count += _record_presigned_event(event_store, clip)
        status_event = _current_status_event_type(str(clip["status"]))
        if status_event is not None:
            event_count += _record_status_event(
                event_store,
                clip,
                status_event,
                segments=_segment_rows(db_path, key=str(clip["key"])),
            )
    corrections = _correction_rows(db_path, limit=limit)
    for correction in corrections:
        event_count += _record_correction_event(event_store, correction)
    if show_progress and clips:
        print(f"backfilled {len(clips)} clips and {len(corrections)} corrections", flush=True)
    return BackfillSummary(
        clip_count=len(clips),
        correction_count=len(corrections),
        event_count=event_count,
    )


def backfill_clip_read_model(
    *,
    db_path: Path,
    clip_store: DynamoUploadedClipStore,
    limit: int | None = None,
    show_progress: bool = False,
) -> BackfillSummary:
    clips = _clip_rows(db_path, limit=limit)
    segments_by_clip = _segment_rows_by_clip(db_path)
    corrections = _correction_rows(db_path, limit=limit)
    read_model_count = 0
    state_by_key: dict[str, dict[str, object]] = {}
    with clip_store.table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
        for index, clip in enumerate(clips, start=1):
            _maybe_print_progress(index, len(clips), show_progress=show_progress)
            key = str(clip["key"])
            state = _state_item_from_clip_row(clip, segments_by_clip.get(key, []))
            state_by_key[key] = state
            read_model_count += _batch_replace_clip_read_model(batch, state)
        for correction in corrections:
            key = str(correction["key"])
            state = state_by_key.get(key)
            if state is None:
                raise LookupError(f"correction references clip outside read-model backfill: {key}")
            _apply_correction_to_state(state, correction)
            read_model_count += _batch_replace_clip_read_model(batch, state)
            _batch_put_item(batch, _correction_item(correction))
            read_model_count += 1
    if show_progress and clips:
        print(
            f"backfilled read model for {len(clips)} clips and {len(corrections)} corrections",
            flush=True,
        )
    return BackfillSummary(
        clip_count=len(clips),
        correction_count=len(corrections),
        event_count=0,
        read_model_count=read_model_count,
    )


def _record_presigned_event(event_store: DurableEventStore, clip: sqlite3.Row) -> int:
    event_store.record_clip_event(
        "clip.presigned",
        key=str(clip["key"]),
        observed_at=_parse_utc(str(clip["started_at"])),
        idempotency_key=str(clip["idempotency_key"]),
        payload={
            "channel": clip["channel"],
            "started_at": clip["started_at"],
            "ended_at": clip["ended_at"],
            "duration_seconds": clip["duration_seconds"],
            "content_type": clip["content_type"],
            "idempotency_key": clip["idempotency_key"],
            "status": clip["status"],
        },
    )
    return 1


def _record_status_event(
    event_store: DurableEventStore,
    clip: sqlite3.Row,
    event_type: str,
    *,
    segments: list[dict[str, object]],
) -> int:
    key = str(clip["key"])
    payload: dict[str, Any] = {
        "channel": clip["channel"],
        "started_at": clip["started_at"],
        "ended_at": clip["ended_at"],
        "duration_seconds": clip["duration_seconds"],
        "content_type": clip["content_type"],
        "idempotency_key": clip["idempotency_key"],
        "status": clip["status"],
        "error": clip["error"],
    }
    if event_type == "clip.transcribed":
        payload["transcript"] = clip["transcript"]
        payload["segments"] = segments
        payload["segment_count"] = len(segments)
        idempotency_seed = stable_event_id(clip["transcript"], segments)
    elif event_type == "clip.empty":
        payload["transcript"] = ""
        idempotency_seed = "empty"
    else:
        idempotency_seed = stable_event_id(clip["status"], clip["error"])
    event_store.record_clip_event(
        event_type,
        key=key,
        observed_at=_parse_utc(str(clip["started_at"])),
        idempotency_key=f"{key}:{event_type}:{idempotency_seed}",
        payload=payload,
    )
    return 1


def _record_correction_event(event_store: DurableEventStore, correction: sqlite3.Row) -> int:
    key = str(correction["key"])
    correction_event_id = stable_event_id(
        correction["corrected_transcript"],
        correction["reviewer"],
        correction["note"],
    )
    event_store.record_clip_event(
        "clip.transcript_corrected",
        key=key,
        observed_at=_parse_utc(str(correction["started_at"])),
        idempotency_key=f"{key}:clip.transcript_corrected:{correction_event_id}",
        payload={
            "channel": correction["channel"],
            "started_at": correction["started_at"],
            "ended_at": correction["ended_at"],
            "duration_seconds": correction["duration_seconds"],
            "content_type": correction["content_type"],
            "original_transcript": correction["original_transcript"],
            "corrected_transcript": correction["corrected_transcript"],
            "reviewer": correction["reviewer"],
            "note": correction["note"],
        },
    )
    return 1


def _current_status_event_type(status: str) -> str | None:
    return {
        "pending": None,
        "processing": "clip.processing",
        "waiting_upload": "clip.waiting_upload",
        "error": "clip.failed",
        "empty": "clip.empty",
        "transcribed": "clip.transcribed",
    }.get(status, "clip.status")


def _clip_rows(db_path: Path, *, limit: int | None) -> list[sqlite3.Row]:
    query = """
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
        ORDER BY started_at ASC, id ASC
    """
    params: tuple[object, ...] = ()
    if limit is not None:
        query += "\nLIMIT ?"
        params = (limit,)
    with _connect(db_path) as connection:
        return list(connection.execute(query, params).fetchall())


def _segment_rows(db_path: Path, *, key: str) -> list[dict[str, object]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT text, started_at, ended_at, relative_start_seconds, relative_end_seconds
            FROM uploaded_clip_segments
            WHERE clip_key = ?
            ORDER BY relative_start_seconds ASC, id ASC
            """,
            (key,),
        ).fetchall()
    return [
        {
            "text": row["text"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "relative_start_seconds": row["relative_start_seconds"],
            "relative_end_seconds": row["relative_end_seconds"],
        }
        for row in rows
    ]


def _segment_rows_by_clip(db_path: Path) -> dict[str, list[dict[str, object]]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT clip_key, text, started_at, ended_at,
                relative_start_seconds, relative_end_seconds
            FROM uploaded_clip_segments
            ORDER BY clip_key ASC, relative_start_seconds ASC, id ASC
            """
        ).fetchall()
    segments: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        segments.setdefault(str(row["clip_key"]), []).append(
            {
                "text": row["text"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "relative_start_seconds": row["relative_start_seconds"],
                "relative_end_seconds": row["relative_end_seconds"],
            }
        )
    return segments


def _correction_rows(db_path: Path, *, limit: int | None) -> list[sqlite3.Row]:
    query = """
        SELECT
            uploaded_clips.key,
            uploaded_clips.channel,
            uploaded_clips.started_at,
            uploaded_clips.ended_at,
            uploaded_clips.duration_seconds,
            uploaded_clips.content_type,
            uploaded_clip_transcript_corrections.original_transcript,
            uploaded_clip_transcript_corrections.corrected_transcript,
            uploaded_clip_transcript_corrections.reviewer,
            uploaded_clip_transcript_corrections.note
        FROM uploaded_clip_transcript_corrections
        JOIN uploaded_clips
            ON uploaded_clips.key = uploaded_clip_transcript_corrections.clip_key
        ORDER BY uploaded_clip_transcript_corrections.updated_at ASC,
            uploaded_clip_transcript_corrections.id ASC
    """
    params: tuple[object, ...] = ()
    if limit is not None:
        query += "\nLIMIT ?"
        params = (limit,)
    with _connect(db_path) as connection:
        return list(connection.execute(query, params).fetchall())


def _clip_request_from_row(row: sqlite3.Row) -> ClipPresignRequest:
    return ClipPresignRequest(
        channel=row["channel"],
        started_at=_parse_utc(str(row["started_at"])),
        ended_at=_parse_utc(str(row["ended_at"])) if row["ended_at"] else None,
        duration_seconds=row["duration_seconds"],
        content_type=row["content_type"],
        idempotency_key=row["idempotency_key"],
    )


def _segment_object(row: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        text=row["text"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        relative_start_seconds=row["relative_start_seconds"],
        relative_end_seconds=row["relative_end_seconds"],
    )


def _state_item_from_clip_row(
    row: sqlite3.Row,
    segments: list[dict[str, object]],
) -> dict[str, object]:
    key = str(row["key"])
    status = str(row["status"])
    transcript = row["transcript"] if status == "transcribed" else None
    if status == "empty":
        transcript = ""
    return {
        "pk": _clip_pk(key),
        "sk": CLIP_STATE_SK,
        "entity_type": "clip_state",
        "key": key,
        "channel": row["channel"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "duration_seconds": row["duration_seconds"],
        "content_type": row["content_type"],
        "idempotency_key": row["idempotency_key"],
        "status": status,
        "transcript": transcript,
        "display_transcript": transcript,
        "error": row["error"],
        "transcript_reviewed": False,
        "segments": segments if status == "transcribed" else [],
        "segment_count": len(segments) if status == "transcribed" else 0,
    }


def _apply_correction_to_state(
    state: dict[str, object],
    correction: sqlite3.Row,
) -> None:
    corrected = " ".join(str(correction["corrected_transcript"]).split())
    original = correction["original_transcript"] or state.get("transcript")
    state.update(
        {
            "original_transcript": original,
            "corrected_transcript": corrected,
            "display_transcript": corrected,
            "transcript_reviewed": True,
            "reviewer": correction["reviewer"],
            "note": correction["note"],
        }
    )


def _batch_replace_clip_read_model(batch: object, state: dict[str, object]) -> int:
    key = str(state["key"])
    channel = str(state["channel"])
    started_at = str(state["started_at"])
    status = str(state["status"])
    index_sk = _index_sk(started_at, key)

    for indexed_status in ("pending", "processing", "waiting_upload", "error"):
        if indexed_status != status:
            batch.delete_item(Key={"pk": _status_pk(indexed_status), "sk": index_sk})
    if status != "transcribed":
        batch.delete_item(Key={"pk": TRANSCRIBED_PK, "sk": index_sk})
        batch.delete_item(Key={"pk": _channel_transcribed_pk(channel), "sk": index_sk})

    item_count = 1
    _batch_put_item(batch, state)
    if status in {"pending", "processing", "waiting_upload", "error"}:
        _batch_put_item(batch, _index_item(_status_pk(status), state))
        item_count += 1
    if status == "transcribed":
        _batch_put_item(batch, _index_item(TRANSCRIBED_PK, state))
        _batch_put_item(batch, _index_item(_channel_transcribed_pk(channel), state))
        item_count += 2
    return item_count


def _correction_item(correction: sqlite3.Row) -> dict[str, object]:
    return {
        "pk": CORRECTIONS_PK,
        "sk": f"{correction['started_at']}#{correction['key']}",
        "entity_type": "clip_correction",
        "key": correction["key"],
        "channel": correction["channel"],
        "started_at": correction["started_at"],
        "ended_at": correction["ended_at"],
        "duration_seconds": correction["duration_seconds"],
        "content_type": correction["content_type"],
        "original_transcript": correction["original_transcript"],
        "corrected_transcript": correction["corrected_transcript"],
        "reviewer": correction["reviewer"],
        "note": correction["note"],
    }


def _batch_put_item(batch: object, item: dict[str, object]) -> None:
    batch.put_item(Item=to_dynamodb_item(item))


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return parsed.astimezone(UTC)


def _maybe_print_progress(index: int, total: int, *, show_progress: bool) -> None:
    if not show_progress:
        return
    if index == 1 or index == total or index % 250 == 0:
        print(f"backfilling clips {index}/{total}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill SQLite clip metadata into DynamoDB.")
    parser.add_argument("--db-path", type=Path, default=_default_db_path())
    parser.add_argument("--table", default=os.getenv("TALKINGBOATS_DURABLE_EVENTS_TABLE"))
    parser.add_argument(
        "--environment",
        default=os.getenv("TALKINGBOATS_DURABLE_EVENTS_ENVIRONMENT", "dev"),
    )
    parser.add_argument("--aws-region", default=os.getenv("TALKINGBOATS_AWS_REGION", "us-west-2"))
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--mode",
        choices=("events", "read-model", "both"),
        default="both",
        help="Backfill durable event items, DynamoDB read-model items, or both.",
    )
    args = parser.parse_args()

    if args.db_path is None:
        parser.error("--db-path or TALKINGBOATS_CLIP_DB_PATH is required")
    if not args.table:
        parser.error("--table or TALKINGBOATS_DURABLE_EVENTS_TABLE is required")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")

    event_store = DynamoDurableEventStore(
        table_name=args.table,
        aws_region=args.aws_region,
        environment=args.environment,
        required=True,
    )
    summary = BackfillSummary(clip_count=0, correction_count=0, event_count=0, read_model_count=0)
    if args.mode in {"events", "both"}:
        summary = backfill_clip_events(
            db_path=args.db_path,
            event_store=event_store,
            limit=args.limit,
            show_progress=True,
        )
    if args.mode in {"read-model", "both"}:
        read_model_summary = backfill_clip_read_model(
            db_path=args.db_path,
            clip_store=DynamoUploadedClipStore(
                DynamoClipStoreConfig(
                    table_name=args.table,
                    aws_region=args.aws_region,
                    environment=args.environment,
                ),
                event_store=NullDurableEventStore(),
            ),
            limit=args.limit,
            show_progress=True,
        )
        summary = BackfillSummary(
            clip_count=max(summary.clip_count, read_model_summary.clip_count),
            correction_count=max(summary.correction_count, read_model_summary.correction_count),
            event_count=summary.event_count,
            read_model_count=read_model_summary.read_model_count,
        )
    print(json.dumps(asdict(summary), sort_keys=True), flush=True)


def _default_db_path() -> Path | None:
    value = os.getenv("TALKINGBOATS_CLIP_DB_PATH")
    return Path(value) if value else None


if __name__ == "__main__":
    main()
