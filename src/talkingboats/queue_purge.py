from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

QUEUE_STATUSES = ("pending", "processing", "waiting_upload", "error")
CLIP_STATE_SK = "state"


@dataclass
class QueuePurgeSummary:
    cutoff: str
    execute: bool
    matched: dict[str, int]
    deleted_items: int = 0
    skipped_after_cutoff: int = 0


def purge_clip_queue(
    *,
    table: Any,
    cutoff: datetime,
    statuses: Iterable[str] = QUEUE_STATUSES,
    execute: bool = False,
    progress_every: int = 10_000,
    progress: Callable[[QueuePurgeSummary], None] | None = None,
) -> QueuePurgeSummary:
    if cutoff.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware")
    cutoff = cutoff.astimezone(UTC)
    cutoff_text = _utc_text(cutoff)
    selected_statuses = tuple(statuses)
    invalid_statuses = sorted(set(selected_statuses) - set(QUEUE_STATUSES))
    if invalid_statuses:
        raise ValueError(f"unsupported queue statuses: {', '.join(invalid_statuses)}")
    if progress_every <= 0:
        raise ValueError("progress_every must be positive")

    summary = QueuePurgeSummary(
        cutoff=cutoff_text,
        execute=execute,
        matched={status: 0 for status in selected_statuses},
    )
    batch_context = (
        table.batch_writer(overwrite_by_pkeys=["pk", "sk"])
        if execute
        else _NullBatchContext()
    )
    with batch_context as batch:
        for status in selected_statuses:
            for item in _iter_queue_items(table, status=status, cutoff_text=cutoff_text):
                started_at = _parse_timestamp(item.get("started_at"))
                if started_at is None:
                    raise ValueError(f"queue item has invalid started_at in {status}")
                if started_at > cutoff:
                    summary.skipped_after_cutoff += 1
                    continue
                key = item.get("key")
                pk = item.get("pk")
                sk = item.get("sk")
                if not all(isinstance(value, str) and value for value in (key, pk, sk)):
                    raise ValueError(f"queue item is missing a key in {status}")
                if item.get("status") != status or pk != _status_pk(status):
                    raise ValueError(f"queue item status mismatch in {status}")

                summary.matched[status] += 1
                if execute:
                    batch.delete_item(Key={"pk": pk, "sk": sk})
                    batch.delete_item(Key={"pk": _clip_pk(key), "sk": CLIP_STATE_SK})
                    summary.deleted_items += 2
                if progress and sum(summary.matched.values()) % progress_every == 0:
                    progress(summary)
    if progress:
        progress(summary)
    return summary


def _iter_queue_items(
    table: Any,
    *,
    status: str,
    cutoff_text: str,
) -> Iterable[dict[str, object]]:
    kwargs: dict[str, object] = {
        "KeyConditionExpression": "pk = :pk AND sk <= :cutoff_sk",
        "ExpressionAttributeValues": {
            ":pk": _status_pk(status),
            ":cutoff_sk": f"{cutoff_text}#\uffff",
        },
        "ExpressionAttributeNames": {
            "#key": "key",
            "#status": "status",
        },
        "ProjectionExpression": "pk, sk, #key, #status, started_at",
        "ConsistentRead": True,
    }
    while True:
        response = table.query(**kwargs)
        items = response.get("Items", [])
        if not isinstance(items, list):
            raise ValueError("DynamoDB query returned invalid Items")
        yield from items
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key


class _NullBatchContext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status_pk(status: str) -> str:
    return f"clip_status#{status}"


def _clip_pk(key: str) -> str:
    return f"clip#{key}"


def _print_progress(summary: QueuePurgeSummary) -> None:
    print(
        json.dumps(
            {"event": "clip_queue_purge_progress", **asdict(summary)},
            sort_keys=True,
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Purge unprocessed clip queue state up to a fixed UTC cutoff."
    )
    parser.add_argument("--table", required=True)
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-table")
    parser.add_argument("--progress-every", type=int, default=10_000)
    args = parser.parse_args()

    cutoff = _parse_timestamp(args.cutoff)
    if cutoff is None:
        parser.error("--cutoff must be an ISO-8601 timezone-aware timestamp")
    if args.execute and args.confirm_table != args.table:
        parser.error("--execute requires --confirm-table to exactly match --table")

    import boto3

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    summary = purge_clip_queue(
        table=table,
        cutoff=cutoff,
        execute=args.execute,
        progress_every=args.progress_every,
        progress=_print_progress,
    )
    print(
        json.dumps(
            {"event": "clip_queue_purge_complete", **asdict(summary)},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
