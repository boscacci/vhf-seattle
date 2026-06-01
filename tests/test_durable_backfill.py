from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from talkingboats.clip_transcriber import UploadedClipStore
from talkingboats.durable_backfill import backfill_clip_events
from talkingboats.schemas import ClipPresignRequest


def test_backfill_clip_events_exports_existing_transcript_and_correction(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    key = "raw/channel=14/date=2026-06-01/example.mp3"
    store = UploadedClipStore(db_path)
    store.record_presigned_upload(
        key=key,
        request=ClipPresignRequest(
            channel="14",
            started_at="2026-06-01T12:00:00Z",
            ended_at="2026-06-01T12:00:05Z",
            duration_seconds=5.0,
            content_type="audio/mpeg",
            idempotency_key="edge-upload-14",
        ),
    )
    store.mark_transcribed(
        key,
        [
            SimpleNamespace(
                text="PON PON all stations",
                started_at="2026-06-01T12:00:00Z",
                ended_at="2026-06-01T12:00:03Z",
                relative_start_seconds=0.0,
                relative_end_seconds=3.0,
            )
        ],
    )
    store.correct_transcript(
        channel="14",
        started_at="2026-06-01T12:00:00Z",
        corrected_transcript="PAN-PAN, all stations.",
        reviewer="rob",
        note="urgency signal",
    )
    event_store = CapturingEventStore()

    summary = backfill_clip_events(db_path=db_path, event_store=event_store)

    assert summary.clip_count == 1
    assert summary.event_count == 3
    assert [event["event_type"] for event in event_store.events] == [
        "clip.presigned",
        "clip.transcribed",
        "clip.transcript_corrected",
    ]
    assert event_store.events[0]["idempotency_key"] == "edge-upload-14"
    assert event_store.events[1]["payload"]["transcript"] == "PON PON all stations"
    assert event_store.events[1]["payload"]["segments"] == [
        {
            "text": "PON PON all stations",
            "started_at": "2026-06-01T12:00:00Z",
            "ended_at": "2026-06-01T12:00:03Z",
            "relative_start_seconds": 0.0,
            "relative_end_seconds": 3.0,
        }
    ]
    assert event_store.events[2]["payload"]["corrected_transcript"] == "PAN-PAN, all stations."


class CapturingEventStore:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def record_clip_event(
        self,
        event_type: str,
        *,
        key: str,
        payload,
        idempotency_key: str,
        observed_at=None,
    ) -> None:
        self.events.append(
            {
                "event_type": event_type,
                "key": key,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "observed_at": observed_at,
            }
        )
