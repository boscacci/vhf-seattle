"""Low-cost, stream-maintained counters for the DynamoDB clip read model.

The public API used to count every indexed clip whenever it needed dashboard
totals.  This module instead materializes just those totals in the existing
event table.  The counter is deliberately based on the serving indexes rather
than clip-state rows, so its semantics stay aligned with the queries it
replaces and it never stores clip text or object keys in aggregate items.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

LOGGER = logging.getLogger(__name__)

TRANSCRIBED_PK = "clips#transcribed"
FEATURED_PK = "clips#featured"
STATUS_PREFIX = "clip_status#"
BACKLOG_STATUSES = ("pending", "processing", "waiting_upload", "error")

CLIP_COUNT_SUMMARY_PK = "clip_count#summary"
CLIP_COUNT_SUMMARY_SK = "current"
CLIP_COUNT_MEMBERSHIP_PK = "clip_count#membership"
CLIP_COUNT_SCHEMA_VERSION = 1

CHANNEL_COUNTER_ROOTS = {
    ("all", False): "channel_counts_all",
    ("visible", False): "channel_counts_visible",
    ("quarantined", False): "channel_counts_quarantined",
    ("all", True): "featured_channel_counts_all",
    ("visible", True): "featured_channel_counts_visible",
    ("quarantined", True): "featured_channel_counts_quarantined",
}
COUNTER_ROOTS = ("backlog_counts", *CHANNEL_COUNTER_ROOTS.values())
QualityFilter = Literal["visible", "quarantined", "all"]


class ClipCountAggregateUnavailable(RuntimeError):
    """Raised when aggregate-only reads are enabled before their backfill exists."""


@dataclass(frozen=True)
class ClipCountSnapshot:
    """A validated view of the compact aggregate item."""

    backlog_counts: dict[str, int]
    channel_counts: dict[tuple[str, bool], dict[str, int]]
    updated_at: str | None

    @classmethod
    def from_item(cls, item: Mapping[str, object] | None) -> ClipCountSnapshot | None:
        if not item or int(item.get("schema_version") or 0) != CLIP_COUNT_SCHEMA_VERSION:
            return None
        if item.get("entity_type") != "clip_count_summary":
            return None
        channel_counts = {
            key: _positive_count_map(item.get(root))
            for key, root in CHANNEL_COUNTER_ROOTS.items()
        }
        return cls(
            backlog_counts=_positive_count_map(item.get("backlog_counts")),
            channel_counts=channel_counts,
            updated_at=_optional_text(item.get("updated_at")),
        )

    def counts_for(
        self,
        *,
        quality: QualityFilter = "visible",
        featured_only: bool = False,
        excluded_channels: Iterable[str] = (),
    ) -> dict[str, int]:
        normalized_quality = _normalize_quality(quality)
        excluded = {str(channel).upper() for channel in excluded_channels}
        counts = self.channel_counts[(normalized_quality, featured_only)]
        return {
            channel: count
            for channel, count in sorted(
                counts.items(),
                key=lambda item: _channel_sort_key(item[0]),
            )
            if count > 0 and channel.upper() not in excluded
        }

    def transcribed_count(
        self,
        *,
        quality: QualityFilter = "visible",
        featured_only: bool = False,
        channels: Iterable[str] | None = None,
        excluded_channels: Iterable[str] = (),
    ) -> int:
        counts = self.counts_for(
            quality=quality,
            featured_only=featured_only,
            excluded_channels=excluded_channels,
        )
        if channels is None:
            return sum(counts.values())
        selected = {str(channel) for channel in channels}
        return sum(count for channel, count in counts.items() if channel in selected)

    def non_transcribed_count(self) -> int:
        return sum(self.backlog_counts.get(status, 0) for status in BACKLOG_STATUSES)

    def received_count(self, *, excluded_channels: Iterable[str] = ()) -> int:
        return self.transcribed_count(
            quality="visible",
            excluded_channels=excluded_channels,
        ) + self.non_transcribed_count()

    def operator_counts(self) -> dict[str, int]:
        counts = dict(self.backlog_counts)
        counts["transcribed"] = self.transcribed_count(quality="all")
        return {status: count for status, count in sorted(counts.items()) if count > 0}


@dataclass(frozen=True)
class ClipCountBackfillSummary:
    scanned: int
    applied: int
    skipped: int
    dry_run: bool


def clip_count_summary_item() -> dict[str, object]:
    return {
        "pk": CLIP_COUNT_SUMMARY_PK,
        "sk": CLIP_COUNT_SUMMARY_SK,
        "entity_type": "clip_count_summary",
        "schema_version": CLIP_COUNT_SCHEMA_VERSION,
        "revision": 0,
        "backlog_counts": {},
        **{root: {} for root in CHANNEL_COUNTER_ROOTS.values()},
        "updated_at": _utc_now_text(),
    }


def _summary_item(
    roots: Mapping[str, Mapping[str, int]], *, revision: int
) -> dict[str, object]:
    item = clip_count_summary_item()
    item["revision"] = revision
    item["updated_at"] = _utc_now_text()
    item.update({root: dict(roots.get(root, {})) for root in COUNTER_ROOTS})
    return item


def contribution_for_index(item: Mapping[str, object] | None) -> dict[str, dict[str, int]]:
    """Return the count contribution for one serving-index item.

    The transcribed and featured index entries already encode the same
    displayability boundary used by the public API.  Rechecking it here keeps
    legacy malformed index rows from inflating the aggregate.
    """

    if not item:
        return {}
    pk = str(item.get("pk") or "")
    if pk.startswith(STATUS_PREFIX):
        status = pk.removeprefix(STATUS_PREFIX)
        if status in BACKLOG_STATUSES:
            return {"backlog_counts": {status: 1}}
        return {}
    if pk not in {TRANSCRIBED_PK, FEATURED_PK}:
        return {}
    if not _is_displayable_index_item(item):
        return {}
    channel = str(item.get("channel") or "?")
    quality = _quality_for_index(item.get("quality_status"))
    featured = pk == FEATURED_PK
    contribution = {
        CHANNEL_COUNTER_ROOTS[("all", featured)]: {channel: 1},
    }
    if quality == "quarantined":
        contribution[CHANNEL_COUNTER_ROOTS[("quarantined", featured)]] = {channel: 1}
    else:
        contribution[CHANNEL_COUNTER_ROOTS[("visible", featured)]] = {channel: 1}
    return contribution


def is_counted_index_key(key: Mapping[str, object]) -> bool:
    pk = str(key.get("pk") or "")
    return pk in {TRANSCRIBED_PK, FEATURED_PK} or pk in {
        f"{STATUS_PREFIX}{status}" for status in BACKLOG_STATUSES
    }


class DynamoClipCountAggregator:
    """Transactionally reconcile one index item into the compact summary.

    A membership item holds only the prior count contribution and a hashed
    source identifier.  Each retry reads the current source index row, so
    duplicate, delayed, and interleaved DynamoDB Stream records converge on
    the current value rather than replaying a stale event image.
    """

    def __init__(
        self,
        *,
        table_name: str,
        aws_region: str,
        table: Any | None = None,
        client: Any | None = None,
    ) -> None:
        self.table_name = table_name
        self.aws_region = aws_region
        if table is None:
            resource = boto3.resource("dynamodb", region_name=aws_region)
            table = resource.Table(table_name)
        self.table = table
        if client is None:
            # DynamoDB resources marshal native Python values for Table methods.
            # Their meta client applies that same marshalling, which would turn
            # an already-serialized transaction key into a map. Transactions
            # therefore always use an explicit low-level client.
            client = boto3.client("dynamodb", region_name=aws_region)
        self.client = client
        self._summary_initialized = False
        self._last_retry_reason: tuple[str, ...] = ()

    def ensure_summary(self) -> None:
        if self._summary_initialized:
            return
        summary_key = {"pk": CLIP_COUNT_SUMMARY_PK, "sk": CLIP_COUNT_SUMMARY_SK}
        for attempt in range(4):
            response = self.table.get_item(Key=summary_key, ConsistentRead=True)
            if response.get("Item") is not None:
                self._summary_initialized = True
                return
            try:
                self.table.put_item(
                    Item=clip_count_summary_item(),
                    ConditionExpression="attribute_not_exists(pk)",
                )
            except Exception as exc:
                if _error_code(exc) == "ConditionalCheckFailedException":
                    self._summary_initialized = True
                    return
                if _error_code(exc) == "TransactionConflictException" and attempt < 3:
                    time.sleep(min(0.25, 0.02 * (2**attempt)))
                    continue
                raise
            self._summary_initialized = True
            return
        raise RuntimeError("clip count summary initialization did not converge")

    def snapshot(self) -> ClipCountSnapshot | None:
        response = self.table.get_item(
            Key={"pk": CLIP_COUNT_SUMMARY_PK, "sk": CLIP_COUNT_SUMMARY_SK},
            ConsistentRead=True,
        )
        return ClipCountSnapshot.from_item(response.get("Item"))

    def reconcile_key(self, key: Mapping[str, object], *, max_attempts: int = 8) -> str:
        normalized_key = {"pk": str(key["pk"]), "sk": str(key["sk"])}
        last_retry_reason: tuple[str, ...] = ()
        for attempt in range(max_attempts):
            response = self.table.get_item(Key=normalized_key, ConsistentRead=True)
            result = self._reconcile_contribution(
                normalized_key,
                contribution_for_index(response.get("Item")),
            )
            if result != "retry":
                return result
            last_retry_reason = self._last_retry_reason
            if attempt + 1 < max_attempts:
                time.sleep(min(0.25, 0.02 * (2**attempt)))
        reason_text = ", ".join(last_retry_reason) or "unknown"
        raise RuntimeError(f"clip count aggregate membership did not converge ({reason_text})")

    def reconcile_item(self, item: Mapping[str, object], *, max_attempts: int = 8) -> str:
        key = {"pk": str(item["pk"]), "sk": str(item["sk"])}
        result = self._reconcile_contribution(key, contribution_for_index(item))
        if result != "retry":
            return result
        return self.reconcile_key(key, max_attempts=max_attempts)

    def _reconcile_contribution(
        self,
        source_key: Mapping[str, str],
        desired: Mapping[str, Mapping[str, int]],
    ) -> str:
        self.ensure_summary()
        membership_key = _membership_key(source_key)
        response = self.table.get_item(Key=membership_key, ConsistentRead=True)
        membership = response.get("Item")
        previous = _normalize_contribution(
            membership.get("contribution") if isinstance(membership, Mapping) else None
        )
        desired_normalized = _normalize_contribution(desired)
        if previous == desired_normalized:
            return "skipped"

        summary_response = self.table.get_item(
            Key={"pk": CLIP_COUNT_SUMMARY_PK, "sk": CLIP_COUNT_SUMMARY_SK},
            ConsistentRead=True,
        )
        summary_item = summary_response.get("Item")
        if not isinstance(summary_item, Mapping):
            self._last_retry_reason = ("summary_missing",)
            return "retry"
        current_revision = _as_int(summary_item.get("revision"))
        updated_roots = {
            root: _positive_count_map(summary_item.get(root)) for root in COUNTER_ROOTS
        }
        changes = _contribution_delta(previous, desired_normalized)
        for (root, key), delta in changes:
            updated_value = updated_roots[root].get(key, 0) + delta
            if updated_value > 0:
                updated_roots[root][key] = updated_value
            else:
                updated_roots[root].pop(key, None)

        summary_item = _summary_item(updated_roots, revision=current_revision + 1)
        summary_put_request = {
            "TableName": self.table_name,
            "Item": _serialize_item(summary_item),
            "ConditionExpression": "attribute_not_exists(pk) OR #revision = :previous_revision",
            "ExpressionAttributeNames": {"#revision": "revision"},
            "ExpressionAttributeValues": {":previous_revision": _serialize_value(current_revision)},
        }

        membership_item = _membership_item(source_key, desired_normalized)
        put_request: dict[str, object] = {
            "TableName": self.table_name,
            "Item": _serialize_item(membership_item),
        }
        if membership is None:
            put_request["ConditionExpression"] = "attribute_not_exists(pk)"
        else:
            put_request["ConditionExpression"] = "#contribution_hash = :previous_hash"
            put_request["ExpressionAttributeNames"] = {"#contribution_hash": "contribution_hash"}
            put_request["ExpressionAttributeValues"] = {
                ":previous_hash": _serialize_value(_contribution_hash(previous))
            }

        try:
            self.client.transact_write_items(
                TransactItems=[
                    {"Put": summary_put_request},
                    {"Put": put_request},
                ]
            )
        except Exception as exc:
            if _error_code(exc) in {
                "ConditionalCheckFailedException",
                "TransactionCanceledException",
            }:
                self._last_retry_reason = _cancellation_reason_codes(exc)
                return "retry"
            raise
        return "applied"


def backfill_clip_count_aggregates(
    *,
    table_name: str,
    aws_region: str,
    page_size: int = 100,
    dry_run: bool = False,
    bulk: bool = False,
    table: Any | None = None,
    client: Any | None = None,
) -> ClipCountBackfillSummary:
    """Seed aggregate membership from the existing, narrow serving indexes.

    It only queries the indexes whose rows feed the public counters; it does
    not scan clip-state, transcript, or event records.  A running stream
    consumer is safe during this operation because both paths reconcile the
    current source row through the same membership transaction.
    """

    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if bulk:
        return _bulk_backfill_clip_count_aggregates(
            table_name=table_name,
            aws_region=aws_region,
            page_size=page_size,
            dry_run=dry_run,
            table=table,
            client=client,
        )
    aggregator = DynamoClipCountAggregator(
        table_name=table_name,
        aws_region=aws_region,
        table=table,
        client=client,
    )
    if not dry_run:
        aggregator.ensure_summary()
    scanned = 0
    applied = 0
    skipped = 0
    for item in _serving_index_items(aggregator, page_size=page_size):
        scanned += 1
        if dry_run:
            continue
        result = aggregator.reconcile_item(item)
        if result == "applied":
            applied += 1
        else:
            skipped += 1
    return ClipCountBackfillSummary(
        scanned=scanned,
        applied=applied,
        skipped=skipped,
        dry_run=dry_run,
    )


def _bulk_backfill_clip_count_aggregates(
    *,
    table_name: str,
    aws_region: str,
    page_size: int,
    dry_run: bool,
    table: Any | None,
    client: Any | None,
) -> ClipCountBackfillSummary:
    """Seed membership in batches, then atomically publish one summary.

    This deliberately trades per-row transactionality for a short initial
    migration.  It must run only while the aggregate's stream mapping is
    disabled; after it is re-enabled, stream records reconcile any source rows
    that changed while the seed was running.
    """

    aggregator = DynamoClipCountAggregator(
        table_name=table_name,
        aws_region=aws_region,
        table=table,
        client=client,
    )
    scanned = 0
    if dry_run:
        for _ in _serving_index_items(aggregator, page_size=page_size):
            scanned += 1
        return ClipCountBackfillSummary(scanned=scanned, applied=0, skipped=0, dry_run=True)

    aggregator.ensure_summary()
    roots: dict[str, dict[str, int]] = {root: {} for root in COUNTER_ROOTS}
    with aggregator.table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
        for item in _serving_index_items(aggregator, page_size=page_size):
            contribution = _normalize_contribution(contribution_for_index(item))
            _add_contribution(roots, contribution)
            batch.put_item(
                Item=_membership_item(
                    {"pk": str(item["pk"]), "sk": str(item["sk"])},
                    contribution,
                )
            )
            scanned += 1

    summary_response = aggregator.table.get_item(
        Key={"pk": CLIP_COUNT_SUMMARY_PK, "sk": CLIP_COUNT_SUMMARY_SK},
        ConsistentRead=True,
    )
    current_summary = summary_response.get("Item")
    if not isinstance(current_summary, Mapping):
        raise RuntimeError("clip count summary disappeared during bulk backfill")
    current_revision = _as_int(current_summary.get("revision"))
    aggregator.table.put_item(
        Item=_summary_item(roots, revision=current_revision + 1),
        ConditionExpression="#revision = :previous_revision",
        ExpressionAttributeNames={"#revision": "revision"},
        ExpressionAttributeValues={":previous_revision": current_revision},
    )
    return ClipCountBackfillSummary(
        scanned=scanned,
        applied=scanned,
        skipped=0,
        dry_run=False,
    )


def _serving_index_items(
    aggregator: DynamoClipCountAggregator, *, page_size: int
) -> Iterable[Mapping[str, object]]:
    source_pks = [
        TRANSCRIBED_PK,
        FEATURED_PK,
        *[f"{STATUS_PREFIX}{status}" for status in BACKLOG_STATUSES],
    ]
    projection_expression = "pk, sk, #channel, display_transcript, transcript, quality_status"
    for source_pk in source_pks:
        start_key: dict[str, object] | None = None
        while True:
            kwargs: dict[str, object] = {
                "KeyConditionExpression": "pk = :pk",
                "ExpressionAttributeValues": {":pk": source_pk},
                "ProjectionExpression": projection_expression,
                "ExpressionAttributeNames": {"#channel": "channel"},
                "Limit": page_size,
            }
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            response = aggregator.table.query(**kwargs)
            items = response.get("Items", [])
            for item in items:
                if not isinstance(item, Mapping):
                    raise ValueError("DynamoDB query returned a non-mapping item")
                yield item
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break


def lambda_handler(
    event: Mapping[str, object],
    context: object,
    *,
    env: Mapping[str, str] | None = None,
    table: Any | None = None,
    client: Any | None = None,
) -> dict[str, object]:
    """DynamoDB Stream handler with partial-batch retry support."""

    del context
    settings = os.environ if env is None else env
    table_name = _required_env(settings, "TALKINGBOATS_CLIP_COUNT_TABLE")
    aws_region = settings.get("AWS_REGION") or settings.get("TALKINGBOATS_AWS_REGION", "us-west-2")
    aggregator = DynamoClipCountAggregator(
        table_name=table_name,
        aws_region=aws_region,
        table=table,
        client=client,
    )
    records = event.get("Records", [])
    if not isinstance(records, list):
        raise ValueError("DynamoDB Stream Records must be a list")

    applied = 0
    skipped = 0
    ignored = 0
    failures: list[dict[str, str]] = []
    for record in records:
        if not isinstance(record, Mapping):
            ignored += 1
            continue
        key = _stream_key(record)
        if key is None or not is_counted_index_key(key):
            ignored += 1
            continue
        try:
            result = aggregator.reconcile_key(key)
        except Exception:
            event_id = str(record.get("eventID") or "")
            if event_id:
                failures.append({"itemIdentifier": event_id})
            else:
                raise
            LOGGER.exception("clip count aggregate reconciliation failed")
            continue
        if result == "applied":
            applied += 1
        else:
            skipped += 1

    LOGGER.info(
        json.dumps(
            {
                "event": "clip_count_aggregate_stream",
                "records": len(records),
                "applied": applied,
                "skipped": skipped,
                "ignored": ignored,
                "failures": len(failures),
            },
            sort_keys=True,
        )
    )
    return {"batchItemFailures": failures}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill DynamoDB clip count aggregates")
    parser.add_argument("--table", default=os.getenv("TALKINGBOATS_DURABLE_EVENTS_TABLE"))
    parser.add_argument("--region", default=os.getenv("TALKINGBOATS_AWS_REGION", "us-west-2"))
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--bulk",
        action="store_true",
        help="batch seed membership; requires the aggregate stream mapping to be disabled",
    )
    args = parser.parse_args(argv)
    if not args.table:
        parser.error("--table or TALKINGBOATS_DURABLE_EVENTS_TABLE is required")
    summary = backfill_clip_count_aggregates(
        table_name=args.table,
        aws_region=args.region,
        page_size=args.page_size,
        dry_run=args.dry_run,
        bulk=args.bulk,
    )
    print(
        json.dumps(
            {
                "event": "clip_count_aggregate_backfill",
                "scanned": summary.scanned,
                "applied": summary.applied,
                "skipped": summary.skipped,
                "dry_run": summary.dry_run,
                "bulk": args.bulk,
            },
            sort_keys=True,
        )
    )
    return 0


def _contribution_delta(
    previous: Mapping[str, Mapping[str, int]], desired: Mapping[str, Mapping[str, int]]
) -> list[tuple[tuple[str, str], int]]:
    changes: list[tuple[tuple[str, str], int]] = []
    for root in COUNTER_ROOTS:
        before = previous.get(root, {})
        after = desired.get(root, {})
        for key in sorted(set(before) | set(after)):
            delta = int(after.get(key, 0)) - int(before.get(key, 0))
            if delta:
                changes.append(((root, key), delta))
    return changes


def _normalize_contribution(value: object) -> dict[str, dict[str, int]]:
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, dict[str, int]] = {}
    for root in COUNTER_ROOTS:
        counts = _positive_count_map(value.get(root))
        if counts:
            normalized[root] = counts
    return normalized


def _positive_count_map(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for raw_key, raw_count in value.items():
        count = _as_int(raw_count)
        if count > 0:
            result[str(raw_key)] = count
    return result


def _as_int(value: object) -> int:
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _membership_key(source_key: Mapping[str, str]) -> dict[str, str]:
    stable_source = f"{source_key['pk']}\0{source_key['sk']}"
    digest = hashlib.sha256(stable_source.encode("utf-8")).hexdigest()
    return {"pk": CLIP_COUNT_MEMBERSHIP_PK, "sk": digest}


def _membership_item(
    source_key: Mapping[str, str], contribution: Mapping[str, Mapping[str, int]]
) -> dict[str, object]:
    normalized = _normalize_contribution(contribution)
    return {
        **_membership_key(source_key),
        "entity_type": "clip_count_membership",
        "schema_version": CLIP_COUNT_SCHEMA_VERSION,
        "contribution": normalized,
        "contribution_hash": _contribution_hash(normalized),
        "updated_at": _utc_now_text(),
    }


def _add_contribution(
    target: dict[str, dict[str, int]], contribution: Mapping[str, Mapping[str, int]]
) -> None:
    for root, counts in contribution.items():
        root_counts = target[root]
        for key, count in counts.items():
            root_counts[key] = root_counts.get(key, 0) + count


def _contribution_hash(value: Mapping[str, Mapping[str, int]]) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _serialize_item(value: Mapping[str, object]) -> dict[str, object]:
    serializer = TypeSerializer()
    return {key: serializer.serialize(item) for key, item in value.items()}


def _serialize_value(value: object) -> object:
    return TypeSerializer().serialize(value)


def _stream_key(record: Mapping[str, object]) -> dict[str, str] | None:
    dynamodb = record.get("dynamodb")
    if not isinstance(dynamodb, Mapping):
        return None
    keys = dynamodb.get("Keys")
    if not isinstance(keys, Mapping):
        return None
    deserializer = TypeDeserializer()
    try:
        pk = deserializer.deserialize(keys["pk"])
        sk = deserializer.deserialize(keys["sk"])
    except (KeyError, TypeError, ValueError):
        return None
    return {"pk": str(pk), "sk": str(sk)}


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return None
    error = response.get("Error")
    if not isinstance(error, Mapping):
        return None
    code = error.get("Code")
    return str(code) if code else None


def _cancellation_reason_codes(exc: Exception) -> tuple[str, ...]:
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return (_error_code(exc) or "unknown",)
    reasons = response.get("CancellationReasons")
    if not isinstance(reasons, list):
        return (_error_code(exc) or "unknown",)
    details: set[str] = set()
    for reason in reasons:
        if not isinstance(reason, Mapping):
            continue
        code = reason.get("Code")
        if code in {None, "None"}:
            continue
        message = " ".join(str(reason.get("Message") or "").split())[:160]
        details.add(f"{code}: {message}" if message else str(code))
    return tuple(sorted(details)) or (_error_code(exc) or "unknown",)


def _utc_now_text() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _normalize_quality(value: object) -> QualityFilter:
    normalized = str(value or "visible").strip().lower()
    if normalized not in {"visible", "quarantined", "all"}:
        raise ValueError(f"unsupported quality filter: {normalized}")
    return normalized  # type: ignore[return-value]


def _quality_for_index(value: object) -> str:
    normalized = str(value or "unknown").strip().lower()
    return normalized if normalized in {"unknown", "ok", "marginal", "quarantined"} else "unknown"


def _is_displayable_index_item(item: Mapping[str, object]) -> bool:
    rendered = " ".join(str(item.get("display_transcript") or item.get("transcript") or "").split())
    if re.search(r"[a-z0-9]", rendered, flags=re.IGNORECASE) is None:
        return False
    normalized = re.sub(r"[^a-z0-9]+", " ", rendered.lower()).strip()
    if normalized in {
        "i love you",
        "lets go",
        "subs by www zeoranger co uk",
        "thank you",
        "thanks for watching",
        "we ll be right back",
        "well be right back",
    }:
        return False
    if normalized.startswith("subtitles by ") or normalized.startswith("subs by "):
        return False
    tokens = re.findall(r"[a-z0-9]+", normalized)
    if len(tokens) >= 6 and not any(len(token) > 3 for token in tokens):
        most_common = max(tokens.count(token) for token in set(tokens))
        if most_common / len(tokens) >= 0.75:
            return False
    return True


def _channel_sort_key(channel: str) -> tuple[int, int | str]:
    value = channel.strip().upper()
    return (0, int(value)) if value.isdigit() else (1, value)


if __name__ == "__main__":
    raise SystemExit(main())
