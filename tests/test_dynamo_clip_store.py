from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from talkingboats.durable_backfill import backfill_clip_read_model
from talkingboats.dynamo_clip_store import DynamoClipStoreConfig, DynamoUploadedClipStore
from talkingboats.schemas import ClipPresignRequest
from talkingboats.transcript_cleanup import cleanup_noise_transcripts


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
    corrections = store.transcript_corrections(limit=5)
    assert len(corrections) == 1
    assert corrections[0]["corrected_transcript"] == "PAN-PAN, all stations."
    assert corrections[0]["include_in_training"] is True
    assert corrections[0]["training_quality"] == "good"
    assert store.transcript_corrections_for_training()[0]["corrected_transcript"] == (
        "PAN-PAN, all stations."
    )

    store.correct_transcript(
        channel="14",
        started_at="2026-06-01T12:00:00Z",
        corrected_transcript="PAN-PAN, all stations.",
        include_in_training=False,
    )
    assert store.transcript_corrections_for_training() == []

    store.correct_transcript(
        channel="14",
        started_at="2026-06-01T12:00:00Z",
        corrected_transcript="PAN-PAN, all stations.",
        reviewer="rob",
        note="urgency",
        include_in_training=True,
        training_quality="excellent",
        training_split="train",
        training_flags=[],
        training_reason="clear urgency proword",
    )
    assert store.transcript_corrections(limit=5)[0]["include_in_training"] is True
    training = store.transcript_corrections_for_training()[0]
    assert training["corrected_transcript"] == "PAN-PAN, all stations."
    assert training["include_in_training"] is True
    assert training["training_quality"] == "excellent"
    assert training["training_split"] == "train"
    assert training["training_flags"] == []
    assert training["training_reason"] == "clear urgency proword"

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


def test_dynamo_clip_store_removes_transcript_correction_from_training() -> None:
    table = FakeDynamoTable()
    event_store = CapturingEventStore()
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2"),
        event_store=event_store,
        table=table,
    )
    key = "raw/channel=14/date=2026-06-01/example.mp3"
    store.record_presigned_upload(key=key, request=_request(channel="14"))
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
    )

    removed = store.remove_transcript_correction(
        channel="14",
        started_at="2026-06-01T12:00:00Z",
    )

    assert removed.key == key
    assert removed.original_transcript == "PON PON all stations"
    assert removed.corrected_transcript == "PAN-PAN, all stations."
    assert store.transcript_corrections(limit=5) == []
    assert store.transcript_corrections_for_training() == []
    assert store.recent_transcribed(limit=5, reviewed_only=True) == []
    recent = store.recent_transcribed(limit=5)[0]
    assert recent.transcript == "PON PON all stations"
    assert recent.transcript_reviewed is False
    assert event_store.events[-1]["event_type"] == "clip.transcript_correction_removed"


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
    assert store.received_clip_count() == 3
    stats = store.stats()
    assert stats["counts"] == {"transcribed": 3}
    assert len(stats["recent"]) == 3


def test_dynamo_clip_store_hides_legacy_ellipsis_only_rows() -> None:
    table = FakeDynamoTable()
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2"),
        table=table,
    )
    good_key = "raw/channel=14/date=2026-06-01/good.mp3"
    ellipsis_key = "raw/channel=14/date=2026-06-01/ellipsis.mp3"
    store.record_presigned_upload(key=good_key, request=_request(channel="14"))
    store.record_presigned_upload(key=ellipsis_key, request=_request(channel="14"))
    store.mark_transcribed(
        good_key,
        [
            SimpleNamespace(
                text="Seattle Traffic roger",
                started_at="2026-06-01T12:00:00Z",
                ended_at="2026-06-01T12:00:01Z",
                relative_start_seconds=0.0,
                relative_end_seconds=1.0,
            )
        ],
    )
    _seed_legacy_dynamo_transcribed_clip(table, ellipsis_key, transcript="... ... ...")

    assert [clip.key for clip in store.recent_transcribed(limit=5)] == [good_key]
    assert store.transcribed_channel_counts() == {"14": 1}
    assert store.transcribed_clip_count(channel="14") == 1


def test_dynamo_clip_store_cleanup_marks_legacy_noise_transcripts_empty() -> None:
    table = FakeDynamoTable()
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2"),
        event_store=CapturingEventStore(),
        table=table,
    )
    good_key = "raw/channel=10/date=2026-06-13/good.mp3"
    noise_key = "raw/channel=10/date=2026-06-13/noise.mp3"
    store.record_presigned_upload(key=good_key, request=_request(channel="10"))
    store.record_presigned_upload(key=noise_key, request=_request(channel="10"))
    store.mark_transcribed(
        good_key,
        [
            SimpleNamespace(
                text="Do you have a channel there, Cap?",
                started_at="2026-06-13T23:29:49Z",
                ended_at="2026-06-13T23:29:53Z",
                relative_start_seconds=0.0,
                relative_end_seconds=4.0,
            )
        ],
    )
    _seed_legacy_dynamo_transcribed_clip(
        table,
        noise_key,
        transcript="Tuk, tuk, tuk, tuk, tuk, tuk, tuk, tuk, tuk.",
    )

    dry_run = cleanup_noise_transcripts(store, dry_run=True, page_size=2)
    applied = cleanup_noise_transcripts(store, dry_run=False, page_size=2)

    assert dry_run.scanned == 2
    assert dry_run.candidates == 1
    assert dry_run.cleaned == 0
    assert applied.scanned == 2
    assert applied.candidates == 1
    assert applied.cleaned == 1
    assert store.get_clip(noise_key).status == "empty"
    assert [clip.key for clip in store.recent_transcribed(limit=5)] == [good_key]
    assert store.transcribed_channel_counts() == {"10": 1}


def test_dynamo_clip_store_cleanup_does_not_skip_rows_after_mutating_pages() -> None:
    table = FakeDynamoTable(page_size=2)
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2"),
        event_store=CapturingEventStore(),
        table=table,
    )
    good_key = "raw/channel=10/date=2026-06-13/good.mp3"
    noise_keys = [
        f"raw/channel=10/date=2026-06-13/noise-{index}.mp3"
        for index in range(3)
    ]
    for key in [good_key, *noise_keys]:
        store.record_presigned_upload(key=key, request=_request(channel="10"))
    store.mark_transcribed(
        good_key,
        [
            SimpleNamespace(
                text="Do you have a channel there, Cap?",
                started_at="2026-06-13T23:29:49Z",
                ended_at="2026-06-13T23:29:53Z",
                relative_start_seconds=0.0,
                relative_end_seconds=4.0,
            )
        ],
    )
    for key in noise_keys:
        _seed_legacy_dynamo_transcribed_clip(
            table,
            key,
            transcript="Tuk, tuk, tuk, tuk, tuk, tuk, tuk, tuk, tuk.",
        )

    summary = cleanup_noise_transcripts(store, dry_run=False, page_size=2)

    assert summary.scanned == 4
    assert summary.candidates == 3
    assert summary.cleaned == 3
    assert [store.get_clip(key).status for key in noise_keys] == ["empty", "empty", "empty"]
    assert [clip.key for clip in store.recent_transcribed(limit=10)] == [good_key]


def test_dynamo_clip_store_streams_recent_transcribed_with_cursor_pages() -> None:
    table = FakeDynamoTable(page_size=2)
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2"),
        table=table,
    )
    expected_keys: list[str] = []
    for index in range(5):
        key = f"raw/channel=14/date=2026-06-01/example-{index}.mp3"
        expected_keys.insert(0, key)
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

    table.query_calls.clear()
    clips = list(store.iter_recent_transcribed(page_size=2))

    assert [clip.key for clip in clips] == expected_keys
    transcribed_queries = [
        call
        for call in table.query_calls
        if call["ExpressionAttributeValues"][":pk"] == "clips#transcribed"
    ]
    assert len(transcribed_queries) == 3
    assert [call.get("Limit") for call in transcribed_queries] == [2, 2, 2]
    assert "ExclusiveStartKey" not in transcribed_queries[0]
    assert "ExclusiveStartKey" in transcribed_queries[1]
    assert "ExclusiveStartKey" in transcribed_queries[2]


def test_dynamo_clip_store_reads_oldest_transcribed_with_forward_query() -> None:
    table = FakeDynamoTable(page_size=2)
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2"),
        table=table,
    )
    expected_keys: list[str] = []
    for index in range(5):
        key = f"raw/channel=14/date=2026-06-01/example-{index}.mp3"
        started_at = datetime(2026, 6, 1, 12, 0, index, tzinfo=UTC)
        expected_keys.append(key)
        request = _request(channel="14").model_copy(
            update={
                "started_at": started_at,
                "ended_at": datetime(2026, 6, 1, 12, 0, index + 1, tzinfo=UTC),
                "idempotency_key": f"edge-upload-oldest-{index}",
            }
        )
        store.record_presigned_upload(key=key, request=request)
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

    table.query_calls.clear()
    clips = store.recent_transcribed(limit=3, sort="oldest")

    assert [clip.key for clip in clips] == expected_keys[:3]
    transcribed_queries = [
        call
        for call in table.query_calls
        if call["ExpressionAttributeValues"][":pk"] == "clips#transcribed"
    ]
    assert len(transcribed_queries) == 2
    assert all(call["ScanIndexForward"] is True for call in transcribed_queries)


def test_dynamo_clip_store_serves_numbered_page_from_cached_index_anchor() -> None:
    table = FakeDynamoTable()
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2"),
        table=table,
    )
    expected_keys: list[str] = []
    for index in range(30):
        key = f"raw/channel=14/date=2026-06-01/example-{index}.mp3"
        started_at = datetime(2026, 6, 1, 12, 0, index, tzinfo=UTC)
        expected_keys.insert(0, key)
        request = _request(channel="14").model_copy(
            update={
                "started_at": started_at,
                "ended_at": datetime(2026, 6, 1, 12, 0, index + 1, tzinfo=UTC),
                "idempotency_key": f"edge-upload-page-anchor-{index}",
            }
        )
        store.record_presigned_upload(key=key, request=request)
        store.mark_transcribed(
            key,
            [
                SimpleNamespace(
                    text=f"Seattle Traffic {index}",
                    started_at=f"2026-06-01T12:00:{index:02d}Z",
                    ended_at=f"2026-06-01T12:00:{index + 1:02d}Z",
                    relative_start_seconds=0.0,
                    relative_end_seconds=1.0,
                )
            ],
        )

    store.transcribed_channel_counts()
    table.query_calls.clear()

    clips = store.recent_transcribed(limit=6, page=5)

    assert [clip.key for clip in clips] == expected_keys[24:30]
    transcribed_queries = [
        call
        for call in table.query_calls
        if call["ExpressionAttributeValues"][":pk"] == "clips#transcribed"
    ]
    assert len(transcribed_queries) == 1
    assert transcribed_queries[0]["Limit"] == 6
    assert "ExclusiveStartKey" in transcribed_queries[0]
    assert transcribed_queries[0]["ExclusiveStartKey"]["sk"].endswith("example-6.mp3")


def test_dynamo_clip_store_builds_numbered_page_anchor_with_bounded_query() -> None:
    table = FakeDynamoTable()
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2"),
        table=table,
    )
    expected_keys: list[str] = []
    for index in range(30):
        key = f"raw/channel=14/date=2026-06-01/example-{index}.mp3"
        started_at = datetime(2026, 6, 1, 12, 0, index, tzinfo=UTC)
        expected_keys.insert(0, key)
        request = _request(channel="14").model_copy(
            update={
                "started_at": started_at,
                "ended_at": datetime(2026, 6, 1, 12, 0, index + 1, tzinfo=UTC),
                "idempotency_key": f"edge-upload-cold-page-anchor-{index}",
            }
        )
        store.record_presigned_upload(key=key, request=request)
        store.mark_transcribed(
            key,
            [
                SimpleNamespace(
                    text=f"Seattle Traffic {index}",
                    started_at=f"2026-06-01T12:00:{index:02d}Z",
                    ended_at=f"2026-06-01T12:00:{index + 1:02d}Z",
                    relative_start_seconds=0.0,
                    relative_end_seconds=1.0,
                )
            ],
        )

    table.query_calls.clear()

    clips = store.recent_transcribed(limit=6, page=5)

    assert [clip.key for clip in clips] == expected_keys[24:30]
    transcribed_queries = [
        call
        for call in table.query_calls
        if call["ExpressionAttributeValues"][":pk"] == "clips#transcribed"
    ]
    assert [call["Limit"] for call in transcribed_queries] == [50, 6]
    assert transcribed_queries[0]["ProjectionExpression"].startswith("pk, sk")
    assert "ExclusiveStartKey" in transcribed_queries[1]


def test_dynamo_clip_store_counts_channels_with_projected_cached_global_query() -> None:
    table = FakeDynamoTable(page_size=2)
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2"),
        table=table,
    )
    for index, channel in enumerate(["14", "68", "14"]):
        key = f"raw/channel={channel}/date=2026-06-01/example-{index}.mp3"
        store.record_presigned_upload(key=key, request=_request(channel=channel))
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

    table.query_calls.clear()

    assert store.transcribed_channel_counts() == {"14": 2, "68": 1}
    assert store.transcribed_channel_counts() == {"14": 2, "68": 1}

    count_queries = [
        call
        for call in table.query_calls
        if call["ExpressionAttributeValues"][":pk"] == "clips#transcribed"
    ]
    assert len(count_queries) == 2
    assert all(
        call["ProjectionExpression"]
        == "pk, sk, #channel, display_transcript, transcript, transcript_reviewed"
        for call in count_queries
    )
    assert all(
        call["ExpressionAttributeNames"] == {"#channel": "channel"}
        for call in count_queries
    )


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


def _seed_legacy_dynamo_transcribed_clip(
    table: FakeDynamoTable,
    key: str,
    *,
    transcript: str,
) -> None:
    state_key = (f"clip#{key}", "state")
    item = dict(table.items[state_key])
    item.update(
        {
            "status": "transcribed",
            "transcript": transcript,
            "display_transcript": transcript,
            "segments": [
                {
                    "text": transcript,
                    "started_at": item["started_at"],
                    "ended_at": item["ended_at"],
                    "relative_start_seconds": 0.0,
                    "relative_end_seconds": 1.0,
                }
            ],
            "segment_count": 1,
        }
    )
    table.put_item(Item=item)
    for pk in ("clips#transcribed", f"clips#transcribed#channel#{item['channel']}"):
        table.put_item(
            Item={
                "pk": pk,
                "sk": f"{item['started_at']}#{key}",
                "entity_type": "clip_index",
                **{
                    item_key: value
                    for item_key, value in item.items()
                    if item_key not in {"pk", "sk", "entity_type"}
                },
            }
        )


class FakeDynamoTable:
    def __init__(self, *, page_size: int | None = None) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {}
        self.page_size = page_size
        self.query_calls: list[dict[str, object]] = []

    def put_item(self, *, Item, **kwargs):
        self.items[(Item["pk"], Item["sk"])] = Item

    def delete_item(self, *, Key):
        self.items.pop((Key["pk"], Key["sk"]), None)

    def get_item(self, *, Key):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": item} if item else {}

    def query(self, **kwargs):
        self.query_calls.append(dict(kwargs))
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
        return {"Items": self._project_rows(page_rows, kwargs), **response}

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

    def _project_rows(self, rows, kwargs):
        projection = kwargs.get("ProjectionExpression")
        if not projection:
            return list(rows)
        names = kwargs.get("ExpressionAttributeNames", {})
        fields = [
            names.get(field.strip(), field.strip())
            for field in str(projection).split(",")
            if field.strip()
        ]
        return [{field: item[field] for field in fields if field in item} for item in rows]


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
