from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from talkingboats.durable_backfill import backfill_clip_read_model
from talkingboats.dynamo_clip_store import DynamoClipStoreConfig, DynamoUploadedClipStore
from talkingboats.schemas import ClipPresignRequest


def test_dynamo_clip_store_serves_recent_counts_pending_and_corrections() -> None:
    table = FakeDynamoTable()
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2"),
        event_store=CapturingEventStore(),
        table=table,
    )
    key = "raw/channel=14/date=2026-06-01/example.mp3"

    store.record_presigned_upload(key=key, request=_request(channel="14"))
    assert [record.key for record in store.pending_uploads(limit=5)] == [key]

    store.mark_processing(key)
    assert store.pending_uploads(limit=5)[0].status == "processing"
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

    assert store.transcribed_channel_counts() == {"14": 1}
    assert [clip.transcript for clip in store.recent_transcribed(limit=5)] == [
        "PON PON all stations"
    ]
    correction = store.correct_transcript(
        channel="14",
        started_at="2026-06-01T12:00:00Z",
        corrected_transcript="PAN-PAN, all stations.",
        reviewer="rob",
        note="urgency",
    )

    assert correction.original_transcript == "PON PON all stations"
    assert store.recent_transcribed(limit=5)[0].transcript == "PAN-PAN, all stations."
    assert store.recent_transcribed(limit=5)[0].transcript_reviewed is True
    assert store.transcript_corrections_for_training()[0]["corrected_transcript"] == (
        "PAN-PAN, all stations."
    )

    feature = store.set_clip_featured(
        channel="14",
        started_at="2026-06-01T12:00:00Z",
        featured=True,
        featured_by="operator-ui",
    )

    assert feature.key == key
    assert feature.featured is True
    assert store.recent_transcribed(limit=5)[0].featured is True
    assert [clip.key for clip in store.recent_transcribed(limit=5, featured_only=True)] == [key]
    assert store.transcribed_clip_count(featured_only=True) == 1

    store.set_clip_featured(
        channel="14",
        started_at="2026-06-01T12:00:00Z",
        featured=False,
        featured_by="operator-ui",
    )

    assert store.recent_transcribed(limit=5)[0].featured is False
    assert store.recent_transcribed(limit=5, featured_only=True) == []


def test_backfill_clip_read_model_replays_sqlite_into_dynamo(tmp_path: Path) -> None:
    from talkingboats.clip_transcriber import UploadedClipStore

    db_path = tmp_path / "clips.sqlite3"
    sqlite_store = UploadedClipStore(db_path)
    key = "raw/channel=68/date=2026-06-01/example.mp3"
    sqlite_store.record_presigned_upload(key=key, request=_request(channel="68"))
    sqlite_store.mark_transcribed(
        key,
        [
            SimpleNamespace(
                text="Seattle Traffic roger",
                started_at="2026-06-01T12:00:00Z",
                ended_at="2026-06-01T12:00:02Z",
                relative_start_seconds=0.0,
                relative_end_seconds=2.0,
            )
        ],
    )
    table = FakeDynamoTable()
    dynamo_store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2"),
        table=table,
    )

    summary = backfill_clip_read_model(db_path=db_path, clip_store=dynamo_store)

    assert summary.clip_count == 1
    assert summary.read_model_count == 3
    assert dynamo_store.transcribed_channel_counts() == {"68": 1}
    assert dynamo_store.recent_transcribed(limit=5)[0].transcript == "Seattle Traffic roger"


def test_dynamo_clip_store_paginates_counts_and_stats() -> None:
    table = FakeDynamoTable(page_size=2)
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2"),
        table=table,
    )
    for index in range(3):
        key = f"raw/channel=14/date=2026-06-01/example-{index}.mp3"
        store.record_presigned_upload(key=key, request=_request(channel="14"))
        store.mark_transcribed(
            key,
            [
                SimpleNamespace(
                    text=f"Seattle Traffic {index}",
                    started_at=f"2026-06-01T12:00:0{index}Z",
                    ended_at=f"2026-06-01T12:00:0{index + 1}Z",
                    relative_start_seconds=0.0,
                    relative_end_seconds=1.0,
                )
            ],
        )

    assert store.transcribed_channel_counts() == {"14": 3}
    stats = store.stats()
    assert stats["counts"] == {"transcribed": 3}
    assert len(stats["recent"]) == 3


def _request(*, channel: str) -> ClipPresignRequest:
    return ClipPresignRequest(
        channel=channel,
        started_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 1, 12, 0, 5, tzinfo=UTC),
        duration_seconds=5.0,
        content_type="audio/mpeg",
        idempotency_key=f"edge-upload-{channel}",
    )


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


class FakeDynamoTable:
    def __init__(self, *, page_size: int | None = None) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {}
        self.page_size = page_size

    def put_item(self, *, Item, **kwargs):
        self.items[(Item["pk"], Item["sk"])] = Item

    def delete_item(self, *, Key):
        self.items.pop((Key["pk"], Key["sk"]), None)

    def get_item(self, *, Key):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": item} if item else {}

    def query(self, **kwargs):
        values = kwargs["ExpressionAttributeValues"]
        pk = values[":pk"]
        sk_prefix = values.get(":sk_prefix")
        rows = [
            item
            for (item_pk, item_sk), item in self.items.items()
            if item_pk == pk and (sk_prefix is None or item_sk.startswith(sk_prefix))
        ]
        rows.sort(key=lambda item: item["sk"], reverse=not kwargs.get("ScanIndexForward", True))
        rows = self._after_exclusive_start(rows, kwargs.get("ExclusiveStartKey"))
        page_limit = kwargs.get("Limit")
        if self.page_size is not None:
            page_limit = min(int(page_limit), self.page_size) if page_limit else self.page_size
        page_rows = rows[: int(page_limit)] if page_limit is not None else rows
        response = {}
        if len(page_rows) < len(rows) and page_rows:
            response["LastEvaluatedKey"] = {
                "pk": page_rows[-1]["pk"],
                "sk": page_rows[-1]["sk"],
            }
        if kwargs.get("Select") == "COUNT":
            return {"Count": len(page_rows), **response}
        return {"Items": page_rows, **response}

    def scan(self, **kwargs):
        rows = list(self.items.values())
        rows.sort(key=lambda item: (item["pk"], item["sk"]))
        rows = self._after_exclusive_start(rows, kwargs.get("ExclusiveStartKey"))
        page_rows = rows[: self.page_size] if self.page_size is not None else rows
        response = {}
        if len(page_rows) < len(rows) and page_rows:
            response["LastEvaluatedKey"] = {
                "pk": page_rows[-1]["pk"],
                "sk": page_rows[-1]["sk"],
            }
        return {"Items": page_rows, **response}

    def batch_writer(self, **kwargs):
        return FakeBatchWriter(self)

    def _after_exclusive_start(self, rows, exclusive_start_key):
        if not exclusive_start_key:
            return rows
        for index, item in enumerate(rows):
            if item["pk"] == exclusive_start_key["pk"] and item["sk"] == exclusive_start_key["sk"]:
                return rows[index + 1 :]
        return rows


class FakeBatchWriter:
    def __init__(self, table: FakeDynamoTable) -> None:
        self.table = table

    def __enter__(self) -> FakeBatchWriter:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def put_item(self, *, Item):
        self.table.put_item(Item=Item)

    def delete_item(self, *, Key):
        self.table.delete_item(Key=Key)
