from __future__ import annotations

from types import SimpleNamespace

import pytest
from boto3.dynamodb.types import TypeDeserializer

from talkingboats.clip_count_aggregates import (
    DynamoClipCountAggregator,
    backfill_clip_count_aggregates,
    clip_count_summary_item,
    contribution_for_index,
    lambda_handler,
)
from talkingboats.dynamo_clip_store import DynamoClipStoreConfig, DynamoUploadedClipStore


def test_contribution_uses_only_displayable_serving_indexes() -> None:
    visible = _index_item(channel="14")
    quarantined = _index_item(channel="66A", quality_status="quarantined")
    featured = _index_item(channel="68", pk="clips#featured")

    assert contribution_for_index(visible) == {
        "channel_counts_all": {"14": 1},
        "channel_counts_visible": {"14": 1},
    }
    assert contribution_for_index(quarantined) == {
        "channel_counts_all": {"66A": 1},
        "channel_counts_quarantined": {"66A": 1},
    }
    assert contribution_for_index(featured) == {
        "featured_channel_counts_all": {"68": 1},
        "featured_channel_counts_visible": {"68": 1},
    }
    assert contribution_for_index(
        {
            "pk": "clip_status#waiting_upload",
            "sk": "2026-08-03T12:00:00Z#clip",
        }
    ) == {"backlog_counts": {"waiting_upload": 1}}
    assert contribution_for_index(_index_item(channel="14", transcript="... ... ...")) == {}


def test_aggregate_reconciles_updates_deletes_and_retries_without_double_counting() -> None:
    table = FakeDynamoTable()
    client = FakeDynamoClient(table)
    aggregator = DynamoClipCountAggregator(
        table_name="events",
        aws_region="us-west-2",
        table=table,
        client=client,
    )
    visible = _index_item(channel="14")
    table.put_item(Item=visible)

    assert aggregator.reconcile_key(_key(visible)) == "applied"
    assert aggregator.reconcile_key(_key(visible)) == "skipped"
    snapshot = aggregator.snapshot()
    assert snapshot is not None
    assert snapshot.counts_for() == {"14": 1}
    assert snapshot.received_count() == 1

    client.fail_next_transaction = True
    table.put_item(Item=_index_item(channel="14", quality_status="quarantined"))
    assert aggregator.reconcile_key(_key(visible)) == "applied"
    snapshot = aggregator.snapshot()
    assert snapshot is not None
    assert snapshot.counts_for() == {}
    assert snapshot.counts_for(quality="quarantined") == {"14": 1}
    assert snapshot.counts_for(quality="all") == {"14": 1}

    table.delete_item(Key=_key(visible))
    assert aggregator.reconcile_key(_key(visible)) == "applied"
    snapshot = aggregator.snapshot()
    assert snapshot is not None
    assert snapshot.counts_for(quality="all") == {}


def test_aggregate_replaces_counter_maps_without_a_nested_dynamodb_increment() -> None:
    table = FakeDynamoTable()
    client = FakeDynamoClient(table)
    item = _index_item(channel="14")
    table.put_item(Item=item)

    aggregator = DynamoClipCountAggregator(
        table_name="events",
        aws_region="us-west-2",
        table=table,
        client=client,
    )

    assert aggregator.reconcile_key(_key(item)) == "applied"
    summary_put = client.transactions[0]["SummaryPut"]
    summary = client._deserialize_map(summary_put["Item"])

    assert summary["channel_counts_all"] == {"14": 1}
    assert summary["channel_counts_visible"] == {"14": 1}
    assert "UpdateExpression" not in summary_put
    assert summary_put["ConditionExpression"] == (
        "attribute_not_exists(pk) OR #revision = :previous_revision"
    )


def test_aggregate_retries_transient_summary_contention_until_converged(monkeypatch) -> None:
    table = FakeDynamoTable()
    client = FakeDynamoClient(table)
    item = _index_item(channel="14")
    table.put_item(Item=item)
    client.fail_transaction_attempts = 4
    monkeypatch.setattr("talkingboats.clip_count_aggregates.time.sleep", lambda _: None)
    aggregator = DynamoClipCountAggregator(
        table_name="events",
        aws_region="us-west-2",
        table=table,
        client=client,
    )

    assert aggregator.reconcile_key(_key(item), max_attempts=5) == "applied"


def test_aggregate_reuses_existing_summary_without_a_conditional_write() -> None:
    table = FakeDynamoTable()
    client = FakeDynamoClient(table)
    table.put_item(Item=clip_count_summary_item())
    table.summary_initialization_put_attempts = 0
    aggregator = DynamoClipCountAggregator(
        table_name="events",
        aws_region="us-west-2",
        table=table,
        client=client,
    )

    aggregator.ensure_summary()

    assert table.summary_initialization_put_attempts == 0


def test_aggregate_retries_a_transient_summary_initialization_conflict(monkeypatch) -> None:
    table = FakeDynamoTable()
    client = FakeDynamoClient(table)
    table.fail_summary_initialization_attempts = 1
    monkeypatch.setattr("talkingboats.clip_count_aggregates.time.sleep", lambda _: None)
    aggregator = DynamoClipCountAggregator(
        table_name="events",
        aws_region="us-west-2",
        table=table,
        client=client,
    )

    aggregator.ensure_summary()

    assert table.summary_initialization_put_attempts == 2
    assert aggregator.snapshot() is not None


def test_aggregate_uses_a_low_level_client_for_serialized_transactions(monkeypatch) -> None:
    table = FakeDynamoTable()
    resource_client = object()
    low_level_client = FakeDynamoClient(table)
    table.meta = SimpleNamespace(client=resource_client)
    monkeypatch.setattr(
        "talkingboats.clip_count_aggregates.boto3.client",
        lambda *_args, **_kwargs: low_level_client,
    )

    aggregator = DynamoClipCountAggregator(
        table_name="events",
        aws_region="us-west-2",
        table=table,
    )

    assert aggregator.client is low_level_client


def test_aggregate_reports_the_terminal_transaction_reason(monkeypatch) -> None:
    table = FakeDynamoTable()
    client = FakeDynamoClient(table)
    item = _index_item(channel="14")
    table.put_item(Item=item)
    client.fail_transaction_attempts = 2
    monkeypatch.setattr("talkingboats.clip_count_aggregates.time.sleep", lambda _: None)
    aggregator = DynamoClipCountAggregator(
        table_name="events",
        aws_region="us-west-2",
        table=table,
        client=client,
    )

    with pytest.raises(RuntimeError, match="TransactionCanceledException"):
        aggregator.reconcile_key(_key(item), max_attempts=2)


def test_stream_reconciles_current_index_state_when_an_old_record_arrives_late() -> None:
    table = FakeDynamoTable()
    client = FakeDynamoClient(table)
    item = _index_item(channel="14")
    table.put_item(Item=item)
    event = {"Records": [_stream_record(item, event_id="first")]}
    env = {"TALKINGBOATS_CLIP_COUNT_TABLE": "events", "AWS_REGION": "us-west-2"}

    assert lambda_handler(event, object(), env=env, table=table, client=client) == {
        "batchItemFailures": []
    }
    table.put_item(Item=_index_item(channel="14", quality_status="quarantined"))
    # The new image in this delayed record is intentionally stale.  The handler
    # rereads the current index row, so it converges on the quarantine move.
    assert lambda_handler(event, object(), env=env, table=table, client=client) == {
        "batchItemFailures": []
    }

    aggregator = DynamoClipCountAggregator(
        table_name="events",
        aws_region="us-west-2",
        table=table,
        client=client,
    )
    snapshot = aggregator.snapshot()
    assert snapshot is not None
    assert snapshot.counts_for() == {}
    assert snapshot.counts_for(quality="quarantined") == {"14": 1}


def test_backfill_queries_only_the_serving_indexes() -> None:
    table = FakeDynamoTable()
    client = FakeDynamoClient(table)
    transcribed = _index_item(channel="14")
    featured = _index_item(channel="68", pk="clips#featured")
    pending = {"pk": "clip_status#pending", "sk": "2026-08-03T12:00:00Z#clip"}
    table.put_item(Item=transcribed)
    table.put_item(Item=featured)
    table.put_item(Item=pending)
    table.put_item(
        Item={
            "pk": "clip#raw/channel=14/date=2026-08-03/private.mp3",
            "sk": "state",
            "entity_type": "clip_state",
            "transcript": "Do not query this row during count backfill.",
        }
    )

    summary = backfill_clip_count_aggregates(
        table_name="events",
        aws_region="us-west-2",
        table=table,
        client=client,
        page_size=1,
    )

    assert summary.scanned == 3
    assert summary.applied == 3
    assert table.scan_calls == 0
    assert set(table.query_pks) == {
        "clips#transcribed",
        "clips#featured",
        "clip_status#pending",
        "clip_status#processing",
        "clip_status#waiting_upload",
        "clip_status#error",
    }


def test_bulk_backfill_batches_membership_then_publishes_one_summary() -> None:
    table = FakeDynamoTable()
    client = FakeDynamoClient(table)
    transcribed = _index_item(channel="14")
    featured = _index_item(channel="68", pk="clips#featured")
    pending = {"pk": "clip_status#pending", "sk": "2026-08-03T12:00:00Z#clip"}
    table.put_item(Item=transcribed)
    table.put_item(Item=featured)
    table.put_item(Item=pending)

    summary = backfill_clip_count_aggregates(
        table_name="events",
        aws_region="us-west-2",
        table=table,
        client=client,
        bulk=True,
    )

    aggregator = DynamoClipCountAggregator(
        table_name="events",
        aws_region="us-west-2",
        table=table,
        client=client,
    )
    snapshot = aggregator.snapshot()
    assert summary.scanned == 3
    assert summary.applied == 3
    assert len(table.batch_put_items) == 3
    assert client.transactions == []
    assert snapshot is not None
    assert snapshot.counts_for() == {"14": 1}
    assert snapshot.counts_for(featured_only=True) == {"68": 1}
    assert snapshot.operator_counts() == {"pending": 1, "transcribed": 1}


def test_dynamo_store_uses_the_snapshot_without_a_count_query() -> None:
    table = FakeDynamoTable()
    client = FakeDynamoClient(table)
    index = _index_item(channel="14")
    table.put_item(Item=index)
    aggregator = DynamoClipCountAggregator(
        table_name="events",
        aws_region="us-west-2",
        table=table,
        client=client,
    )
    assert aggregator.reconcile_key(_key(index)) == "applied"
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2", aggregate_counts_enabled=True),
        table=table,
    )

    assert store.transcribed_channel_counts() == {"14": 1}
    assert store.transcribed_clip_count() == 1
    assert store.received_clip_count() == 1
    assert table.query_pks == []


def test_dynamo_store_reads_oldest_pending_with_one_bounded_query() -> None:
    table = FakeDynamoTable()
    client = FakeDynamoClient(table)
    pending = {
        "pk": "clip_status#pending",
        "sk": "2026-08-03T12:00:00Z#clip",
        "started_at": "2026-08-03T12:00:00Z",
    }
    table.put_item(Item=pending)
    aggregator = DynamoClipCountAggregator(
        table_name="events",
        aws_region="us-west-2",
        table=table,
        client=client,
    )
    assert aggregator.reconcile_key(_key(pending)) == "applied"
    store = DynamoUploadedClipStore(
        DynamoClipStoreConfig("events", "us-west-2", aggregate_counts_enabled=True),
        table=table,
    )

    assert store.clip_backlog_summary() == {
        "counts": {"pending": 1},
        "oldest_pending_started_at": "2026-08-03T12:00:00Z",
    }
    assert table.query_pks == ["clip_status#pending"]


def _index_item(
    *,
    channel: str,
    pk: str = "clips#transcribed",
    quality_status: str = "ok",
    transcript: str = "Seattle Traffic, roger.",
) -> dict[str, object]:
    return {
        "pk": pk,
        "sk": "2026-08-03T12:00:00Z#clip-1",
        "entity_type": "clip_index",
        "channel": channel,
        "quality_status": quality_status,
        "display_transcript": transcript,
    }


def _key(item: dict[str, object]) -> dict[str, str]:
    return {"pk": str(item["pk"]), "sk": str(item["sk"])}


def _stream_record(item: dict[str, object], *, event_id: str) -> dict[str, object]:
    return {
        "eventID": event_id,
        "dynamodb": {
            "Keys": {
                "pk": {"S": str(item["pk"])},
                "sk": {"S": str(item["sk"])},
            }
        },
    }


class ConditionalFailure(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}
        super().__init__(code)


class FakeDynamoTable:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {}
        self.query_pks: list[str] = []
        self.batch_put_items: list[dict[str, object]] = []
        self.scan_calls = 0
        self.summary_initialization_put_attempts = 0
        self.fail_summary_initialization_attempts = 0

    def put_item(self, *, Item, ConditionExpression: str | None = None, **kwargs) -> None:
        key = (str(Item["pk"]), str(Item["sk"]))
        if (
            ConditionExpression
            and "attribute_not_exists" in ConditionExpression
            and key == ("clip_count#summary", "current")
        ):
            self.summary_initialization_put_attempts += 1
            if self.fail_summary_initialization_attempts:
                self.fail_summary_initialization_attempts -= 1
                raise ConditionalFailure("TransactionConflictException")
        if (
            ConditionExpression
            and "attribute_not_exists" in ConditionExpression
            and key in self.items
        ):
            raise ConditionalFailure("ConditionalCheckFailedException")
        self.items[key] = dict(Item)

    def delete_item(self, *, Key, **kwargs) -> None:
        self.items.pop((str(Key["pk"]), str(Key["sk"])), None)

    def get_item(self, *, Key, **kwargs) -> dict[str, object]:
        item = self.items.get((str(Key["pk"]), str(Key["sk"])))
        return {"Item": dict(item)} if item is not None else {}

    def query(self, **kwargs) -> dict[str, object]:
        pk = str(kwargs["ExpressionAttributeValues"][":pk"])
        self.query_pks.append(pk)
        rows = [
            dict(item)
            for (item_pk, _), item in sorted(self.items.items())
            if item_pk == pk
        ]
        start_key = kwargs.get("ExclusiveStartKey")
        if start_key:
            start = (str(start_key["pk"]), str(start_key["sk"]))
            rows = [item for item in rows if (str(item["pk"]), str(item["sk"])) > start]
        limit = int(kwargs.get("Limit", len(rows)))
        page = rows[:limit]
        result: dict[str, object] = {"Items": page}
        if len(rows) > len(page):
            result["LastEvaluatedKey"] = _key(page[-1])
        return result

    def scan(self, **kwargs) -> dict[str, object]:
        self.scan_calls += 1
        return {"Items": []}

    def batch_writer(self, **kwargs):
        return FakeBatchWriter(self)


class FakeBatchWriter:
    def __init__(self, table: FakeDynamoTable) -> None:
        self.table = table

    def __enter__(self) -> FakeBatchWriter:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False

    def put_item(self, *, Item) -> None:
        self.table.batch_put_items.append(dict(Item))
        self.table.put_item(Item=Item)


class FakeDynamoClient:
    def __init__(self, table: FakeDynamoTable) -> None:
        self.table = table
        self.fail_next_transaction = False
        self.fail_transaction_attempts = 0
        self.deserializer = TypeDeserializer()
        self.transactions: list[dict[str, object]] = []

    def transact_write_items(self, *, TransactItems) -> None:
        if self.fail_next_transaction or self.fail_transaction_attempts:
            self.fail_next_transaction = False
            self.fail_transaction_attempts = max(0, self.fail_transaction_attempts - 1)
            raise ConditionalFailure("TransactionCanceledException")
        summary_put_request = TransactItems[0]["Put"]
        membership_put_request = TransactItems[1]["Put"]
        self.transactions.append(
            {
                "SummaryPut": summary_put_request,
                "MembershipPut": membership_put_request,
            }
        )
        summary = self._deserialize_map(summary_put_request["Item"])
        summary_key = (str(summary["pk"]), str(summary["sk"]))
        existing_summary = self.table.items.get(summary_key)
        summary_values = self._deserialize_map(
            summary_put_request["ExpressionAttributeValues"]
        )
        expected_revision = summary_values[":previous_revision"]
        if existing_summary is not None and existing_summary.get("revision") != expected_revision:
            raise ConditionalFailure("TransactionCanceledException")

        put_request = membership_put_request
        membership = self._deserialize_map(put_request["Item"])
        membership_key = (str(membership["pk"]), str(membership["sk"]))
        existing_membership = self.table.items.get(membership_key)
        condition = str(put_request.get("ConditionExpression") or "")
        if "attribute_not_exists" in condition and existing_membership is not None:
            raise ConditionalFailure("TransactionCanceledException")
        if "contribution_hash" in condition:
            expected = self.deserializer.deserialize(
                put_request["ExpressionAttributeValues"][":previous_hash"]
            )
            if not existing_membership or existing_membership.get("contribution_hash") != expected:
                raise ConditionalFailure("TransactionCanceledException")

        self.table.items[summary_key] = summary
        self.table.items[membership_key] = membership

    def _deserialize_map(self, values: dict[str, object]) -> dict[str, object]:
        return {key: self.deserializer.deserialize(value) for key, value in values.items()}
