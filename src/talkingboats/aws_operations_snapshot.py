from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

import boto3


@dataclass(frozen=True)
class OperationsSnapshotConfig:
    region: str = "us-west-2"
    monthly_budget_usd: float = 35.0


LAMBDA_METRICS = (
    ("lambda_ais_ingest", "AIS ingestion", "talkingboats-talkingboats-ais-ingest"),
    (
        "lambda_clip_aggregator",
        "Clip count aggregation",
        "talkingboats-dev-talkingboats-clip-count-aggregator",
    ),
    ("lambda_ais_websocket", "AIS WebSocket", "talkingboats-talkingboats-ais-websocket"),
    (
        "lambda_freshness_monitor",
        "Freshness monitoring",
        "talkingboats-talkingboats-prod-clip-freshness",
    ),
)

DYNAMODB_METRICS = (
    ("ddb_clip_events", "Clip event store", "talkingboats-dev-talkingboats-events"),
    ("ddb_ais_connections", "AIS connection store", "talkingboats-talkingboats-ais-connections"),
    ("ddb_public_events", "Public event store", "talkingboats-talkingboats-events"),
)


def collect_operations_snapshot(
    *,
    config: OperationsSnapshotConfig,
    manifest: dict[str, Any],
    cloudwatch: Any,
    cost_explorer: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = _utc(now or datetime.now(UTC))
    window_end = datetime.combine(generated_at.date(), time.min, tzinfo=UTC)
    window_start = window_end - timedelta(days=7)
    metric_results = cloudwatch.get_metric_data(
        MetricDataQueries=_metric_queries(),
        StartTime=window_start,
        EndTime=window_end,
        ScanBy="TimestampAscending",
    ).get("MetricDataResults", [])
    totals = {
        str(result.get("Id")): sum(float(value) for value in result.get("Values", []))
        for result in metric_results
    }

    lambda_functions = [
        {"label": label, "invocations": round(totals.get(metric_id, 0))}
        for metric_id, label, _function_name in LAMBDA_METRICS
    ]
    table_totals = [
        {
            "label": label,
            "readCapacityUnits": round(totals.get(f"{metric_id}_read", 0), 1),
            "writeCapacityUnits": round(totals.get(f"{metric_id}_write", 0), 1),
        }
        for metric_id, label, _table_name in DYNAMODB_METRICS
    ]
    read_units = sum(item["readCapacityUnits"] for item in table_totals)
    write_units = sum(
        item["writeCapacityUnits"] for item in table_totals
    )

    month_start = generated_at.date().replace(day=1)
    cost_end = generated_at.date() + timedelta(days=1)
    cost_response = cost_explorer.get_cost_and_usage(
        TimePeriod={"Start": month_start.isoformat(), "End": cost_end.isoformat()},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )
    cost_result = (cost_response.get("ResultsByTime") or [{}])[0]
    cost_total = cost_result.get("Total", {}).get("UnblendedCost", {})
    month_to_date = round(float(cost_total.get("Amount") or 0), 2)
    budget_limit = round(config.monthly_budget_usd, 2)

    stats = manifest.get("stats") if isinstance(manifest.get("stats"), dict) else {}
    received = _nonnegative_int(stats.get("received_clip_count"))
    analyzed = _nonnegative_int(stats.get("analyzed_clip_count"))
    pending = max(0, received - analyzed)
    completion = round(analyzed / received * 100, 2) if received else 0.0

    return {
        "generatedAt": generated_at.isoformat().replace("+00:00", "Z"),
        "window": {
            "start": window_start.date().isoformat(),
            "end": window_end.date().isoformat(),
            "completeDays": 7,
        },
        "budget": {
            "month": month_start.isoformat(),
            "monthToDateUsd": month_to_date,
            "limitUsd": budget_limit,
            "remainingUsd": round(max(0.0, budget_limit - month_to_date), 2),
            "usedPercent": round(month_to_date / budget_limit * 100, 2)
            if budget_limit
            else 0.0,
            "estimated": bool(cost_result.get("Estimated", True)),
        },
        "lambda": {
            "invocations": sum(item["invocations"] for item in lambda_functions),
            "functions": lambda_functions,
        },
        "dynamodb": {
            "readCapacityUnits": round(read_units, 1),
            "writeCapacityUnits": round(write_units, 1),
            "tables": table_totals,
        },
        "transcription": {
            "receivedClips": received,
            "analyzedClips": analyzed,
            "pendingClips": pending,
            "completionPercent": completion,
            "publishedClips": len(manifest.get("clips") or []),
        },
    }


def refresh_operations_snapshot(
    *,
    manifest_path: Path,
    cache_path: Path,
    output_path: Path,
    max_age_seconds: int,
    config: OperationsSnapshotConfig | None = None,
    now: datetime | None = None,
    cloudwatch: Any | None = None,
    cost_explorer: Any | None = None,
) -> dict[str, Any]:
    observed_at = _utc(now or datetime.now(UTC))
    if cache_path.is_file():
        cache_age = observed_at.timestamp() - cache_path.stat().st_mtime
        if 0 <= cache_age < max_age_seconds:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            _write_json_atomic(output_path, payload)
            return payload

    selected_config = config or OperationsSnapshotConfig(
        region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-west-2",
        monthly_budget_usd=float(os.environ.get("TALKINGBOATS_MONTHLY_BUDGET_USD", "35")),
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    session = boto3.session.Session(region_name=selected_config.region)
    payload = collect_operations_snapshot(
        config=selected_config,
        manifest=manifest,
        cloudwatch=cloudwatch or session.client("cloudwatch"),
        cost_explorer=cost_explorer or session.client("ce", region_name="us-east-1"),
        now=observed_at,
    )
    _write_json_atomic(cache_path, payload)
    _write_json_atomic(output_path, payload)
    return payload


def _metric_queries() -> list[dict[str, Any]]:
    queries = [
        _metric_query(metric_id, "AWS/Lambda", "Invocations", "FunctionName", function_name)
        for metric_id, _label, function_name in LAMBDA_METRICS
    ]
    for metric_id, _label, table_name in DYNAMODB_METRICS:
        queries.append(
            _metric_query(
                f"{metric_id}_read",
                "AWS/DynamoDB",
                "ConsumedReadCapacityUnits",
                "TableName",
                table_name,
            )
        )
        queries.append(
            _metric_query(
                f"{metric_id}_write",
                "AWS/DynamoDB",
                "ConsumedWriteCapacityUnits",
                "TableName",
                table_name,
            )
        )
    return queries


def _metric_query(
    metric_id: str,
    namespace: str,
    metric_name: str,
    dimension_name: str,
    dimension_value: str,
) -> dict[str, Any]:
    return {
        "Id": metric_id,
        "MetricStat": {
            "Metric": {
                "Namespace": namespace,
                "MetricName": metric_name,
                "Dimensions": [{"Name": dimension_name, "Value": dimension_value}],
            },
            "Period": 3600,
            "Stat": "Sum",
        },
        "ReturnData": True,
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("now must include a timezone")
    return value.astimezone(UTC)


def _nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export public-safe AWS operations metrics")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-age-seconds", type=int, default=86_400)
    args = parser.parse_args(argv)
    try:
        payload = refresh_operations_snapshot(
            manifest_path=args.manifest,
            cache_path=args.cache,
            output_path=args.output,
            max_age_seconds=args.max_age_seconds,
        )
    except Exception as exc:
        if not args.cache.is_file():
            raise
        cached_payload = json.loads(args.cache.read_text(encoding="utf-8"))
        _write_json_atomic(args.output, cached_payload)
        print(
            f"event=talkingboats_operations_snapshot_stale reason={type(exc).__name__}",
            file=sys.stderr,
        )
        return 0
    print(
        "event=talkingboats_operations_snapshot_ready "
        f"generated_at={payload.get('generatedAt', 'unknown')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
