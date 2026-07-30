from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from talkingboats.stale_clip_monitor import evaluate_manifest, lambda_handler


class FakeBody:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class FakeS3:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.requests: list[dict[str, object]] = []

    def get_object(self, **kwargs) -> dict[str, object]:
        self.requests.append(kwargs)
        return {"Body": FakeBody(self.payload)}


class FakeCloudWatch:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def put_metric_data(self, **kwargs) -> None:
        self.requests.append(kwargs)


def test_evaluate_manifest_uses_the_newest_clip_timestamp() -> None:
    result = evaluate_manifest(
        {
            "generated_at": "2026-07-25T17:55:00Z",
            "clips": [
                {"ended_at": "2026-07-25T16:40:00Z"},
                {"ended_at": "2026-07-25T17:35:00Z"},
                {"started_at": "2026-07-25T17:10:00Z"},
            ],
        },
        now=datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
    )

    assert result.latest_clip_at == datetime(2026, 7, 25, 17, 35, tzinfo=UTC)
    assert result.age_seconds == 25 * 60


@pytest.mark.parametrize(
    "manifest",
    [
        {},
        {"clips": []},
        {"clips": [{"ended_at": None}]},
        {"clips": [{"ended_at": "not-a-timestamp"}]},
    ],
)
def test_evaluate_manifest_rejects_missing_or_invalid_clip_timestamps(
    manifest: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="valid clip timestamp"):
        evaluate_manifest(
            manifest,
            now=datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
        )


def test_evaluate_manifest_clamps_future_clock_skew_to_zero() -> None:
    result = evaluate_manifest(
        {"clips": [{"ended_at": "2026-07-25T18:01:00Z"}]},
        now=datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
    )

    assert result.age_seconds == 0


def test_lambda_handler_reads_prod_manifest_and_emits_age_metric(capsys) -> None:
    s3 = FakeS3({"clips": [{"ended_at": "2026-07-25T17:35:00Z"}]})
    cloudwatch = FakeCloudWatch()

    result = lambda_handler(
        {},
        None,
        env={
            "TALKINGBOATS_MONITOR_BUCKET": "prod-public",
            "TALKINGBOATS_MONITOR_KEY": "public_manifest.json",
            "TALKINGBOATS_MONITOR_NAMESPACE": "ElliottBayVHF",
            "TALKINGBOATS_MONITOR_SITE": "seattleboatradio.com",
        },
        s3_client=s3,
        cloudwatch_client=cloudwatch,
        now=datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
    )

    assert s3.requests == [{"Bucket": "prod-public", "Key": "public_manifest.json"}]
    assert result == {
        "age_seconds": 1500.0,
        "latest_clip_at": "2026-07-25T17:35:00Z",
        "status": "ok",
    }
    assert cloudwatch.requests == [
        {
            "Namespace": "ElliottBayVHF",
            "MetricData": [
                {
                    "MetricName": "LatestPublicClipAgeSeconds",
                    "Dimensions": [
                        {"Name": "Environment", "Value": "prod"},
                        {"Name": "Site", "Value": "seattleboatradio.com"},
                    ],
                    "Timestamp": datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
                    "Unit": "Seconds",
                    "Value": 1500.0,
                }
            ],
        }
    ]
    log_record = json.loads(capsys.readouterr().out)
    assert log_record["event"] == "public_clip_freshness_observed"
    assert log_record["age_seconds"] == 1500.0
    assert log_record["latest_clip_at"] == "2026-07-25T17:35:00Z"
    assert "prod-public" not in log_record


def test_lambda_handler_fails_fast_when_required_config_is_missing() -> None:
    with pytest.raises(ValueError, match="TALKINGBOATS_MONITOR_BUCKET"):
        lambda_handler(
            {},
            None,
            env={},
            s3_client=FakeS3({"clips": []}),
            cloudwatch_client=FakeCloudWatch(),
        )


def test_opentofu_schedules_independent_prod_clip_freshness_monitor() -> None:
    monitoring_tf = Path("infra/opentofu/monitoring.tf").read_text(encoding="utf-8")

    assert 'filename = "talkingboats/stale_clip_monitor.py"' in monitoring_tf
    assert (
        'content  = file("${path.module}/../../src/talkingboats/stale_clip_monitor.py")'
        in monitoring_tf
    )
    assert 'handler          = "talkingboats.stale_clip_monitor.lambda_handler"' in monitoring_tf
    assert 'runtime          = "python3.12"' in monitoring_tf
    assert "timeout          = 30" in monitoring_tf
    assert "memory_size      = 256" in monitoring_tf
    assert 'schedule_expression = "rate(5 minutes)"' in monitoring_tf
    assert 'principal     = "events.amazonaws.com"' in monitoring_tf
    assert 'actions   = ["s3:GetObject"]' in monitoring_tf
    assert 'actions   = ["cloudwatch:PutMetricData"]' in monitoring_tf
    assert 'TALKINGBOATS_MONITOR_STALE_AFTER_SECONDS = "3600"' in monitoring_tf


def test_opentofu_alerts_after_one_hour_and_when_monitor_data_is_missing() -> None:
    monitoring_tf = Path("infra/opentofu/monitoring.tf").read_text(encoding="utf-8")

    assert 'resource "aws_sns_topic" "prod_clip_freshness_alerts"' in monitoring_tf
    assert 'metric_name         = "LatestPublicClipAgeSeconds"' in monitoring_tf
    assert 'comparison_operator = "GreaterThanOrEqualToThreshold"' in monitoring_tf
    assert "threshold           = 3600" in monitoring_tf
    assert 'treat_missing_data  = "breaching"' in monitoring_tf
    assert "alarm_actions = [aws_sns_topic.prod_clip_freshness_alerts.arn]" in monitoring_tf
    assert "ok_actions    = [aws_sns_topic.prod_clip_freshness_alerts.arn]" in monitoring_tf
