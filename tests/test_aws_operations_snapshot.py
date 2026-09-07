from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from talkingboats.aws_operations_snapshot import (
    OperationsSnapshotConfig,
    collect_operations_snapshot,
    refresh_operations_snapshot,
)


class FakeCloudWatch:
    def get_metric_data(self, **kwargs):  # noqa: ANN003
        assert kwargs["StartTime"] == datetime(2026, 8, 31, tzinfo=UTC)
        assert kwargs["EndTime"] == datetime(2026, 9, 7, tzinfo=UTC)
        return {
            "MetricDataResults": [
                {"Id": "lambda_ais_ingest", "Values": [1000, 250]},
                {"Id": "lambda_clip_aggregator", "Values": [800]},
                {"Id": "lambda_ais_websocket", "Values": [12]},
                {"Id": "lambda_freshness_monitor", "Values": [2016]},
                {"Id": "ddb_clip_events_read", "Values": [120.5, 79.5]},
                {"Id": "ddb_clip_events_write", "Values": [400]},
                {"Id": "ddb_ais_connections_read", "Values": [50]},
                {"Id": "ddb_ais_connections_write", "Values": [60]},
            ]
        }


class FakeCostExplorer:
    def get_cost_and_usage(self, **kwargs):  # noqa: ANN003
        assert kwargs["TimePeriod"] == {"Start": "2026-09-01", "End": "2026-09-08"}
        return {
            "ResultsByTime": [
                {
                    "Estimated": True,
                    "Total": {"UnblendedCost": {"Amount": "22.8282591161", "Unit": "USD"}},
                }
            ]
        }


def test_operations_snapshot_summarizes_cloud_work_and_transcription() -> None:
    snapshot = collect_operations_snapshot(
        config=OperationsSnapshotConfig(monthly_budget_usd=35),
        manifest={
            "clips": [{"id": "one"}, {"id": "two"}],
            "stats": {
                "received_clip_count": 149_559,
                "analyzed_clip_count": 149_047,
                "queue_status_counts": {
                    "pending": 2,
                    "processing": 1,
                    "waiting_upload": 2,
                    "error": 507,
                },
            },
        },
        cloudwatch=FakeCloudWatch(),
        cost_explorer=FakeCostExplorer(),
        now=datetime(2026, 9, 7, 20, 30, tzinfo=UTC),
    )

    assert snapshot["window"] == {
        "start": "2026-08-31",
        "end": "2026-09-07",
        "completeDays": 7,
    }
    assert snapshot["lambda"]["invocations"] == 4078
    assert snapshot["lambda"]["functions"][0] == {
        "label": "AIS ingestion",
        "invocations": 1250,
    }
    assert snapshot["dynamodb"]["readCapacityUnits"] == 250.0
    assert snapshot["dynamodb"]["writeCapacityUnits"] == 460.0
    assert snapshot["dynamodb"]["tables"][0] == {
        "label": "Clip event store",
        "readCapacityUnits": 200.0,
        "writeCapacityUnits": 400.0,
    }
    assert snapshot["transcription"] == {
        "receivedClips": 149_559,
        "analyzedClips": 149_047,
        "pendingClips": 5,
        "completionPercent": 99.66,
        "publishedClips": 2,
    }
    assert snapshot["budget"]["monthToDateUsd"] == 22.83
    assert snapshot["budget"]["limitUsd"] == 35.0
    assert snapshot["budget"]["usedPercent"] == 65.23
    assert snapshot["budget"]["estimated"] is True
    rendered = json.dumps(snapshot)
    assert "talkingboats-dev" not in rendered
    assert "arn:aws" not in rendered


def test_operations_snapshot_reuses_daily_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "operations-cache.json"
    output_path = tmp_path / "site" / "operations.json"
    cached = {
        "generatedAt": "2026-09-07T00:00:00Z",
        "lambda": {"invocations": 5},
        "transcription": {"pendingClips": 99},
    }
    cache_path.write_text(json.dumps(cached), encoding="utf-8")
    manifest_path = tmp_path / "public_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "clips": [{"id": "one"}],
                "stats": {
                    "received_clip_count": 100,
                    "analyzed_clip_count": 90,
                    "queue_status_counts": {"pending": 2, "error": 8},
                },
            }
        ),
        encoding="utf-8",
    )

    result = refresh_operations_snapshot(
        manifest_path=manifest_path,
        cache_path=cache_path,
        output_path=output_path,
        max_age_seconds=86_400,
        now=datetime.fromtimestamp(cache_path.stat().st_mtime + 60, tz=UTC),
    )

    assert result["lambda"] == cached["lambda"]
    assert result["transcription"] == {
        "receivedClips": 100,
        "analyzedClips": 90,
        "pendingClips": 2,
        "completionPercent": 90.0,
        "publishedClips": 1,
    }
    assert json.loads(output_path.read_text(encoding="utf-8")) == result
