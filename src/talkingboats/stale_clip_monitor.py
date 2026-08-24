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


@dataclass(frozen=True)
class ManifestFreshness:
    generated_at: datetime
    age_seconds: float


@dataclass(frozen=True)
class AisFreshness:
    latest_message_at: datetime
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


def evaluate_manifest_generation(
    manifest: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> ManifestFreshness:
    observed_at = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    observed_at = observed_at.astimezone(UTC)

    generated_at = _parse_timestamp(manifest.get("generated_at"))
    if generated_at is None:
        raise ValueError("public manifest does not contain a valid generation timestamp")

    age_seconds = max(0.0, (observed_at - generated_at).total_seconds())
    return ManifestFreshness(generated_at=generated_at, age_seconds=age_seconds)


def evaluate_ais_snapshot(
    snapshot: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> AisFreshness:
    observed_at = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    observed_at = observed_at.astimezone(UTC)

    timestamps: list[datetime] = []
    generated_at = _parse_timestamp(snapshot.get("generated_at"))
    if generated_at is not None:
        timestamps.append(generated_at)

    vessels = snapshot.get("vessels")
    if isinstance(vessels, list):
        for vessel in vessels:
            if not isinstance(vessel, Mapping):
                continue
            timestamp = _parse_timestamp(vessel.get("last_seen"))
            if timestamp is not None:
                timestamps.append(timestamp)

    if not timestamps:
        raise ValueError("AIS snapshot does not contain a valid AIS timestamp")

    latest_message_at = max(timestamps)
    age_seconds = max(0.0, (observed_at - latest_message_at).total_seconds())
    return AisFreshness(latest_message_at=latest_message_at, age_seconds=age_seconds)


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
    ais_key = settings.get("TALKINGBOATS_MONITOR_AIS_KEY", "ais/latest.json").strip()
    namespace = settings.get("TALKINGBOATS_MONITOR_NAMESPACE", "ElliottBayVHF").strip()
    site = settings.get("TALKINGBOATS_MONITOR_SITE", "seattleboatradio.com").strip()
    stale_after_seconds = float(settings.get("TALKINGBOATS_MONITOR_STALE_AFTER_SECONDS", "3600"))
    if not key or not ais_key or not namespace or not site:
        raise ValueError("monitor keys, namespace, and site must not be empty")
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
    manifest_freshness = evaluate_manifest_generation(manifest, now=observed_at)
    manifest_status = (
        "stale" if manifest_freshness.age_seconds >= stale_after_seconds else "ok"
    )

    ais_response = s3_client.get_object(Bucket=bucket, Key=ais_key)
    ais_snapshot = json.loads(ais_response["Body"].read())
    if not isinstance(ais_snapshot, dict):
        raise ValueError("AIS snapshot must be a JSON object")
    ais_freshness = evaluate_ais_snapshot(ais_snapshot, now=observed_at)
    ais_status = "stale" if ais_freshness.age_seconds >= stale_after_seconds else "ok"

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
            },
            {
                "MetricName": "PublicManifestAgeSeconds",
                "Dimensions": [
                    {"Name": "Environment", "Value": "prod"},
                    {"Name": "Site", "Value": site},
                ],
                "Timestamp": observed_at,
                "Unit": "Seconds",
                "Value": manifest_freshness.age_seconds,
            },
            {
                "MetricName": "LatestAisMessageAgeSeconds",
                "Dimensions": [
                    {"Name": "Environment", "Value": "prod"},
                    {"Name": "Site", "Value": site},
                ],
                "Timestamp": observed_at,
                "Unit": "Seconds",
                "Value": ais_freshness.age_seconds,
            },
        ],
    )

    result: dict[str, object] = {
        "age_seconds": freshness.age_seconds,
        "ais_age_seconds": ais_freshness.age_seconds,
        "ais_status": ais_status,
        "latest_clip_at": _utc_text(freshness.latest_clip_at),
        "latest_ais_at": _utc_text(ais_freshness.latest_message_at),
        "manifest_age_seconds": manifest_freshness.age_seconds,
        "manifest_generated_at": _utc_text(manifest_freshness.generated_at),
        "manifest_status": manifest_status,
        "status": status,
    }
    print(
        json.dumps(
            {
                "event": "edge_freshness_observed",
                **result,
                "site": site,
                "stale_after_seconds": stale_after_seconds,
            },
            sort_keys=True,
        )
    )
    return result
