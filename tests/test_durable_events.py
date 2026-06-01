from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from talkingboats.durable_events import DynamoDurableEventStore


def test_dynamo_event_store_writes_idempotent_clip_event_shape() -> None:
    table = FakeDynamoTable()
    store = DynamoDurableEventStore(
        table_name="talkingboats-dev-events",
        aws_region="us-west-2",
        environment="dev",
        table=table,
    )

    store.record_clip_event(
        "clip.transcribed",
        key="raw/channel=14/date=2026-06-01/example.mp3",
        observed_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        idempotency_key="transcript-v1",
        payload={
            "channel": "14",
            "duration_seconds": 4.5,
            "segments": [
                {
                    "text": "Seattle Traffic",
                    "relative_start_seconds": 0.0,
                    "relative_end_seconds": 4.5,
                }
            ],
        },
    )

    assert table.items == [
        {
            "pk": "clip#raw/channel=14/date=2026-06-01/example.mp3",
            "sk": "event#clip.transcribed#transcript-v1",
            "event_type": "clip.transcribed",
            "environment": "dev",
            "observed_at": "2026-06-01T12:00:00Z",
            "key": "raw/channel=14/date=2026-06-01/example.mp3",
            "channel": "14",
            "duration_seconds": Decimal("4.5"),
            "segments": [
                {
                    "text": "Seattle Traffic",
                    "relative_start_seconds": Decimal("0.0"),
                    "relative_end_seconds": Decimal("4.5"),
                }
            ],
        }
    ]
    assert table.condition_expressions == [
        "attribute_not_exists(pk) AND attribute_not_exists(sk)"
    ]


def test_dynamo_event_store_treats_duplicate_event_as_success() -> None:
    table = FakeDynamoTable(duplicate=True)
    store = DynamoDurableEventStore(
        table_name="talkingboats-dev-events",
        aws_region="us-west-2",
        environment="dev",
        table=table,
    )

    store.record_clip_event(
        "clip.presigned",
        key="raw/channel=68/date=2026-06-01/example.mp3",
        observed_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        idempotency_key="edge-upload-1",
        payload={"channel": "68"},
    )

    assert table.items == []


def test_dynamo_event_store_can_require_success() -> None:
    table = FakeDynamoTable(fail=True)
    store = DynamoDurableEventStore(
        table_name="talkingboats-dev-events",
        aws_region="us-west-2",
        environment="dev",
        table=table,
        required=True,
    )

    with pytest.raises(RuntimeError, match="failed to write durable event"):
        store.record_clip_event(
            "clip.presigned",
            key="raw/channel=68/date=2026-06-01/example.mp3",
            observed_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            idempotency_key="edge-upload-1",
            payload={"channel": "68"},
        )


class FakeDynamoTable:
    def __init__(self, *, duplicate: bool = False, fail: bool = False) -> None:
        self.duplicate = duplicate
        self.fail = fail
        self.items: list[dict[str, object]] = []
        self.condition_expressions: list[str] = []

    def put_item(self, *, Item, ConditionExpression):
        if self.duplicate:
            raise FakeClientError("ConditionalCheckFailedException")
        if self.fail:
            raise FakeClientError("InternalServerError")
        self.items.append(Item)
        self.condition_expressions.append(ConditionExpression)


class FakeClientError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}
