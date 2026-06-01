from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

import boto3

LOGGER = logging.getLogger(__name__)
IDEMPOTENCY_HASH_LENGTH = 16


class DurableEventStore(Protocol):
    def record_clip_event(
        self,
        event_type: str,
        *,
        key: str,
        payload: dict[str, Any],
        idempotency_key: str,
        observed_at: datetime | None = None,
    ) -> None: ...


class NullDurableEventStore:
    def record_clip_event(
        self,
        event_type: str,
        *,
        key: str,
        payload: dict[str, Any],
        idempotency_key: str,
        observed_at: datetime | None = None,
    ) -> None:
        return None


@dataclass
class DynamoDurableEventStore:
    table_name: str
    aws_region: str
    environment: str
    required: bool = False
    table: Any | None = None

    def __post_init__(self) -> None:
        if self.table is None:
            resource = boto3.resource("dynamodb", region_name=self.aws_region)
            self.table = resource.Table(self.table_name)

    def record_clip_event(
        self,
        event_type: str,
        *,
        key: str,
        payload: dict[str, Any],
        idempotency_key: str,
        observed_at: datetime | None = None,
    ) -> None:
        event_at = observed_at or datetime.now(UTC)
        item = _to_dynamodb_item(
            {
                "pk": f"clip#{key}",
                "sk": f"event#{event_type}#{idempotency_key}",
                "event_type": event_type,
                "environment": self.environment,
                "observed_at": _format_utc(event_at),
                "key": key,
                **payload,
            }
        )
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            )
        except Exception as exc:
            if _error_code(exc) == "ConditionalCheckFailedException":
                return
            LOGGER.warning(
                "durable event write failed",
                extra={
                    "table": self.table_name,
                    "event_type": event_type,
                    "key_hash": short_hash(key),
                    "required": self.required,
                },
            )
            if self.required:
                raise RuntimeError("failed to write durable event") from exc


def durable_event_store_from_env(*, aws_region: str | None = None) -> DurableEventStore:
    table_name = os.getenv("TALKINGBOATS_DURABLE_EVENTS_TABLE")
    if not table_name:
        return NullDurableEventStore()
    return DynamoDurableEventStore(
        table_name=table_name,
        aws_region=aws_region or os.getenv("TALKINGBOATS_AWS_REGION", "us-west-2"),
        environment=os.getenv("TALKINGBOATS_DURABLE_EVENTS_ENVIRONMENT", "dev"),
        required=_env_bool("TALKINGBOATS_DURABLE_EVENTS_REQUIRED", False),
    )


def stable_event_id(*parts: Any) -> str:
    return short_hash(_json_dumps(parts))


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:IDEMPOTENCY_HASH_LENGTH]


def _to_dynamodb_item(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _to_dynamodb_item(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_to_dynamodb_item(item) for item in value]
    return value


def to_dynamodb_item(value: Any) -> Any:
    return _to_dynamodb_item(value)


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    error = response.get("Error")
    if not isinstance(error, dict):
        return None
    code = error.get("Code")
    return str(code) if code else None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}
