from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ClipFreshness:
    latest_clip_at: datetime
    age_seconds: float


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


def evaluate_manifest(
    manifest: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> ClipFreshness:
    observed_at = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    observed_at = observed_at.astimezone(UTC)

    clips = manifest.get("clips")
    timestamps: list[datetime] = []
    if isinstance(clips, list):
        for clip in clips:
            if not isinstance(clip, Mapping):
                continue
            timestamp = _parse_timestamp(clip.get("ended_at")) or _parse_timestamp(
                clip.get("started_at")
            )
            if timestamp is not None:
                timestamps.append(timestamp)

    if not timestamps:
        raise ValueError("public manifest does not contain a valid clip timestamp")

    latest_clip_at = max(timestamps)
    age_seconds = max(0.0, (observed_at - latest_clip_at).total_seconds())
    return ClipFreshness(latest_clip_at=latest_clip_at, age_seconds=age_seconds)


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    env: Mapping[str, str] | None = None,
    s3_client: Any | None = None,
    cloudwatch_client: Any | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    del event, context
    settings = os.environ if env is None else env
    bucket = _required_env(settings, "TALKINGBOATS_MONITOR_BUCKET")
    key = settings.get("TALKINGBOATS_MONITOR_KEY", "public_manifest.json").strip()
    namespace = settings.get("TALKINGBOATS_MONITOR_NAMESPACE", "ElliottBayVHF").strip()
    site = settings.get("TALKINGBOATS_MONITOR_SITE", "seattleboatradio.com").strip()
    stale_after_seconds = float(settings.get("TALKINGBOATS_MONITOR_STALE_AFTER_SECONDS", "3600"))
    if not key or not namespace or not site:
        raise ValueError("monitor key, namespace, and site must not be empty")
    if stale_after_seconds <= 0:
        raise ValueError("TALKINGBOATS_MONITOR_STALE_AFTER_SECONDS must be positive")

    observed_at = now or datetime.now(UTC)
    if s3_client is None or cloudwatch_client is None:
        import boto3

        s3_client = s3_client or boto3.client("s3")
        cloudwatch_client = cloudwatch_client or boto3.client("cloudwatch")

    response = s3_client.get_object(Bucket=bucket, Key=key)
    manifest = json.loads(response["Body"].read())
    if not isinstance(manifest, dict):
        raise ValueError("public manifest must be a JSON object")
    freshness = evaluate_manifest(manifest, now=observed_at)
    status = "stale" if freshness.age_seconds >= stale_after_seconds else "ok"

    cloudwatch_client.put_metric_data(
        Namespace=namespace,
        MetricData=[
            {
                "MetricName": "LatestPublicClipAgeSeconds",
                "Dimensions": [
                    {"Name": "Environment", "Value": "prod"},
                    {"Name": "Site", "Value": site},
                ],
                "Timestamp": observed_at,
                "Unit": "Seconds",
                "Value": freshness.age_seconds,
            }
        ],
    )

    result: dict[str, object] = {
        "age_seconds": freshness.age_seconds,
        "latest_clip_at": _utc_text(freshness.latest_clip_at),
        "status": status,
    }
    print(
        json.dumps(
            {
                "event": "public_clip_freshness_observed",
                **result,
                "site": site,
                "stale_after_seconds": stale_after_seconds,
            },
            sort_keys=True,
        )
    )
    return result
