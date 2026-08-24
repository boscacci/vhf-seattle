from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from talkingboats.stale_clip_monitor import (
    evaluate_ais_snapshot,
    evaluate_manifest,
    evaluate_manifest_generation,
    lambda_handler,
)


class FakeBody:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class FakeS3:
    def __init__(self, payloads: dict[str, object]) -> None:
        self.payloads = payloads
        self.requests: list[dict[str, object]] = []

    def get_object(self, **kwargs) -> dict[str, object]:
        self.requests.append(kwargs)
        payload = self.payloads[str(kwargs["Key"])]
        assert isinstance(payload, dict)
        return {"Body": FakeBody(payload)}


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


def test_evaluate_manifest_generation_tracks_the_publisher_heartbeat() -> None:
    result = evaluate_manifest_generation(
        {"generated_at": "2026-07-25T17:45:00Z"},
        now=datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
    )

    assert result.generated_at == datetime(2026, 7, 25, 17, 45, tzinfo=UTC)
    assert result.age_seconds == 15 * 60


@pytest.mark.parametrize(
    "manifest",
    [
        {},
        {"generated_at": None},
        {"generated_at": "not-a-timestamp"},
    ],
)
def test_evaluate_manifest_generation_rejects_a_missing_publisher_heartbeat(
    manifest: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="valid generation timestamp"):
        evaluate_manifest_generation(
            manifest,
            now=datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
        )


def test_evaluate_ais_snapshot_uses_ingest_generation_time() -> None:
    result = evaluate_ais_snapshot(
        {
            "generated_at": "2026-07-25T17:40:00Z",
            "vessels": [{"last_seen": "2026-07-25T17:39:50Z"}],
        },
        now=datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
    )

    assert result.latest_message_at == datetime(2026, 7, 25, 17, 40, tzinfo=UTC)
    assert result.age_seconds == 20 * 60


def test_evaluate_ais_snapshot_falls_back_to_newest_vessel_timestamp() -> None:
    result = evaluate_ais_snapshot(
        {
            "vessels": [
                {"last_seen": "2026-07-25T17:31:00Z"},
                {"last_seen": "2026-07-25T17:42:00Z"},
            ]
        },
        now=datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
    )

    assert result.latest_message_at == datetime(2026, 7, 25, 17, 42, tzinfo=UTC)
    assert result.age_seconds == 18 * 60


@pytest.mark.parametrize(
    "snapshot",
    [
        {},
        {"generated_at": "not-a-timestamp"},
        {"generated_at": None, "vessels": []},
        {"vessels": [{"last_seen": None}]},
    ],
)
def test_evaluate_ais_snapshot_rejects_missing_or_invalid_timestamps(
    snapshot: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="valid AIS timestamp"):
        evaluate_ais_snapshot(
            snapshot,
            now=datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
        )


def test_lambda_handler_reads_prod_manifest_and_emits_age_metric(capsys) -> None:
    s3 = FakeS3(
        {
            "public_manifest.json": {
                "generated_at": "2026-07-25T17:45:00Z",
                "clips": [{"ended_at": "2026-07-25T17:35:00Z"}],
            },
            "ais/latest.json": {"generated_at": "2026-07-25T17:50:00Z", "vessels": []},
        }
    )
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

    assert s3.requests == [
        {"Bucket": "prod-public", "Key": "public_manifest.json"},
        {"Bucket": "prod-public", "Key": "ais/latest.json"},
    ]
    assert result == {
        "age_seconds": 1500.0,
        "ais_age_seconds": 600.0,
        "ais_status": "ok",
        "latest_clip_at": "2026-07-25T17:35:00Z",
        "latest_ais_at": "2026-07-25T17:50:00Z",
        "manifest_age_seconds": 900.0,
        "manifest_generated_at": "2026-07-25T17:45:00Z",
        "manifest_status": "ok",
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
                },
                {
                    "MetricName": "PublicManifestAgeSeconds",
                    "Dimensions": [
                        {"Name": "Environment", "Value": "prod"},
                        {"Name": "Site", "Value": "seattleboatradio.com"},
                    ],
                    "Timestamp": datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
                    "Unit": "Seconds",
                    "Value": 900.0,
                },
                {
                    "MetricName": "LatestAisMessageAgeSeconds",
                    "Dimensions": [
                        {"Name": "Environment", "Value": "prod"},
                        {"Name": "Site", "Value": "seattleboatradio.com"},
                    ],
                    "Timestamp": datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
                    "Unit": "Seconds",
                    "Value": 600.0,
                },
            ],
        }
    ]
    log_record = json.loads(capsys.readouterr().out)
    assert log_record["event"] == "edge_freshness_observed"
    assert log_record["age_seconds"] == 1500.0
    assert log_record["manifest_age_seconds"] == 900.0
    assert log_record["ais_age_seconds"] == 600.0
    assert log_record["latest_clip_at"] == "2026-07-25T17:35:00Z"
    assert "prod-public" not in log_record


def test_lambda_handler_fails_fast_when_required_config_is_missing() -> None:
    with pytest.raises(ValueError, match="TALKINGBOATS_MONITOR_BUCKET"):
        lambda_handler(
            {},
            None,
            env={},
            s3_client=FakeS3({}),
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
    assert re.search(r'actions\s*=\s*\["s3:GetObject"\]', monitoring_tf)
    assert '"${aws_s3_bucket.public_site.arn}/ais/latest.json"' in monitoring_tf
    assert re.search(r'actions\s*=\s*\["cloudwatch:PutMetricData"\]', monitoring_tf)
    assert 'TALKINGBOATS_MONITOR_STALE_AFTER_SECONDS = "3600"' in monitoring_tf
    assert 'TALKINGBOATS_MONITOR_AIS_KEY             = "ais/latest.json"' in monitoring_tf


def test_opentofu_keeps_quiet_radio_visible_without_email_and_pages_on_pipeline_staleness() -> None:
    monitoring_tf = Path("infra/opentofu/monitoring.tf").read_text(encoding="utf-8")

    assert 'resource "aws_sns_topic" "prod_clip_freshness_alerts"' in monitoring_tf
    clip_signal = _resource_block(monitoring_tf, "prod_clip_freshness")
    assert 'metric_name         = "LatestPublicClipAgeSeconds"' in clip_signal
    assert 'comparison_operator = "GreaterThanOrEqualToThreshold"' in clip_signal
    assert "threshold           = 3600" in clip_signal
    assert 'treat_missing_data  = "breaching"' in clip_signal
    assert "actions_enabled     = false" in clip_signal
    assert "alarm_actions" not in clip_signal
    assert "ok_actions" not in clip_signal

    manifest_alarm = _resource_block(monitoring_tf, "prod_public_manifest_freshness")
    assert 'metric_name         = "PublicManifestAgeSeconds"' in manifest_alarm
    assert "threshold           = 3600" in manifest_alarm
    assert "evaluation_periods  = 3" in manifest_alarm
    assert "datapoints_to_alarm = 3" in manifest_alarm
    assert 'treat_missing_data  = "notBreaching"' in manifest_alarm
    assert "alarm_actions = [aws_sns_topic.prod_clip_freshness_alerts.arn]" in manifest_alarm
    assert "ok_actions    = [aws_sns_topic.prod_clip_freshness_alerts.arn]" in manifest_alarm

    ais_alarm = _resource_block(monitoring_tf, "prod_ais_freshness")
    assert 'metric_name         = "LatestAisMessageAgeSeconds"' in ais_alarm
    assert "threshold           = 900" in ais_alarm
    assert "evaluation_periods  = 3" in ais_alarm
    assert "datapoints_to_alarm = 3" in ais_alarm
    assert 'treat_missing_data  = "breaching"' in ais_alarm
    assert "alarm_actions = [aws_sns_topic.prod_clip_freshness_alerts.arn]" in ais_alarm
    assert "ok_actions    = [aws_sns_topic.prod_clip_freshness_alerts.arn]" in ais_alarm


def _resource_block(monitoring_tf: str, resource_name: str) -> str:
    start = monitoring_tf.index(f'resource "aws_cloudwatch_metric_alarm" "{resource_name}"')
    next_resource = monitoring_tf.find('\nresource "', start + 1)
    end = next_resource if next_resource != -1 else len(monitoring_tf)
    return monitoring_tf[start:end]
