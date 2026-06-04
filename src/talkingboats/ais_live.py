from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from talkingboats.ais_history import VESSEL_TYPES

DEFAULT_AIS_MIN_LAT = 47.45
DEFAULT_AIS_MAX_LAT = 47.85
DEFAULT_AIS_MIN_LON = -122.55
DEFAULT_AIS_MAX_LON = -122.15
DEFAULT_AIS_MAX_STALENESS_SECONDS = 10 * 60
DEFAULT_AIS_MAX_VESSELS = 250


@dataclass(frozen=True)
class AisLiveConfig:
    station: str = "Elliott Bay VHF"
    generated_at: datetime | None = None
    min_lat: float = DEFAULT_AIS_MIN_LAT
    max_lat: float = DEFAULT_AIS_MAX_LAT
    min_lon: float = DEFAULT_AIS_MIN_LON
    max_lon: float = DEFAULT_AIS_MAX_LON
    max_staleness_seconds: int = DEFAULT_AIS_MAX_STALENESS_SECONDS
    max_vessels: int = DEFAULT_AIS_MAX_VESSELS

    def now(self) -> datetime:
        return (self.generated_at or datetime.now(UTC)).astimezone(UTC)


def public_ais_snapshot(payload: object, *, config: AisLiveConfig | None = None) -> dict[str, Any]:
    config = config or AisLiveConfig()
    generated_at = config.now()
    vessels = []
    seen_mmsi: set[str] = set()
    for item in _candidate_vessels(payload):
        vessel = _sanitize_vessel(item, config=config, generated_at=generated_at)
        if not vessel:
            continue
        mmsi = str(vessel["mmsi"])
        if mmsi in seen_mmsi:
            continue
        seen_mmsi.add(mmsi)
        vessels.append(vessel)

    vessels.sort(key=lambda vessel: (str(vessel["last_seen"]), str(vessel["mmsi"])), reverse=True)
    snapshot = {
        "type": "ais_snapshot",
        "generated_at": _format_utc(generated_at),
        "station": config.station,
        "sequence": generated_at.strftime("%Y%m%dT%H%M%SZ"),
        "vessels": vessels[: config.max_vessels],
    }
    assert_public_safe(snapshot)
    return snapshot


def ais_http_ingest_handler(
    event: Mapping[str, Any],
    _context: object,
    *,
    env: Mapping[str, str] | None = None,
    s3_client: Any | None = None,
    websocket_client: Any | None = None,
    websocket_connection_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    env = env or os.environ
    if not _request_token_is_valid(event, env):
        return _lambda_response(401, {"status": "unauthorized"})

    payload = _event_json_body(event)
    config = AisLiveConfig(
        station=env.get("TALKINGBOATS_AIS_STATION", "Elliott Bay VHF"),
        generated_at=_fixed_now(env),
    )
    snapshot = public_ais_snapshot(payload, config=config)
    body = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")

    bucket = env.get("TALKINGBOATS_AIS_SNAPSHOT_BUCKET")
    key = env.get("TALKINGBOATS_AIS_SNAPSHOT_KEY", "ais/latest.json")
    if bucket:
        client = s3_client or _boto3_client("s3")
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body + b"\n",
            ContentType="application/json",
            CacheControl="no-store",
        )

    posted = 0
    connection_ids = list(websocket_connection_ids or ())
    if not connection_ids and env.get("TALKINGBOATS_AIS_CONNECTIONS_TABLE"):
        connection_ids = _connection_ids_from_table(env)
    if websocket_client is None and env.get("TALKINGBOATS_AIS_WEBSOCKET_ENDPOINT"):
        websocket_client = _boto3_client(
            "apigatewaymanagementapi",
            endpoint_url=env["TALKINGBOATS_AIS_WEBSOCKET_ENDPOINT"],
        )
    if websocket_client is not None:
        for connection_id in connection_ids:
            websocket_client.post_to_connection(ConnectionId=connection_id, Data=body)
            posted += 1

    return _lambda_response(
        202,
        {
            "status": "accepted",
            "vessel_count": len(snapshot["vessels"]),
            "connections_notified": posted,
        },
    )


def ais_lambda_handler(event: Mapping[str, Any], context: object) -> dict[str, Any]:
    return ais_http_ingest_handler(event, context)


def ais_websocket_handler(
    event: Mapping[str, Any],
    _context: object,
    *,
    env: Mapping[str, str] | None = None,
    table: Any | None = None,
) -> dict[str, Any]:
    env = env or os.environ
    request_context = event.get("requestContext") or {}
    route_key = str(request_context.get("routeKey") or "")
    connection_id = str(request_context.get("connectionId") or "")
    if not connection_id:
        return _lambda_response(400, {"status": "missing_connection"})
    table_name = env.get("TALKINGBOATS_AIS_CONNECTIONS_TABLE", "")
    if not table_name and table is None:
        return _lambda_response(500, {"status": "connections_table_not_configured"})
    table = table or _dynamodb_table(table_name)
    if route_key == "$connect":
        connected_at = datetime.now(UTC)
        ttl_seconds = _positive_int(env.get("TALKINGBOATS_AIS_CONNECTION_TTL_SECONDS"), 3600)
        table.put_item(
            Item={
                "connection_id": connection_id,
                "connected_at": _format_utc(connected_at),
                "expires_at": int(connected_at.timestamp()) + ttl_seconds,
            }
        )
        return _lambda_response(200, {"status": "connected"})
    if route_key == "$disconnect":
        table.delete_item(Key={"connection_id": connection_id})
        return _lambda_response(200, {"status": "disconnected"})
    return _lambda_response(200, {"status": "ignored"})


def _candidate_vessels(payload: object) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("vessels", "ships", "ais", "messages", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    if _first_present(payload, ("mmsi", "MMSI")) and _first_present(payload, ("lat", "Lat")):
        return [payload]
    return []


def _sanitize_vessel(
    item: Mapping[str, Any],
    *,
    config: AisLiveConfig,
    generated_at: datetime,
) -> dict[str, Any] | None:
    mmsi = _clean_mmsi(_first_present(item, ("mmsi", "MMSI", "Mmsi")))
    lat = _optional_float(_first_present(item, ("lat", "Lat", "latitude", "Latitude")))
    lon = _optional_float(_first_present(item, ("lon", "Lon", "lng", "longitude", "Longitude")))
    if not mmsi or lat is None or lon is None:
        return None
    if not (config.min_lat <= lat <= config.max_lat and config.min_lon <= lon <= config.max_lon):
        return None

    last_seen = _parse_time(
        _first_present(
            item,
            ("last_seen", "lastSeen", "observed_at", "time", "Time", "timestamp", "Timestamp"),
        ),
        default=generated_at,
    )
    if generated_at - last_seen > timedelta(seconds=config.max_staleness_seconds):
        return None

    vessel: dict[str, Any] = {
        "mmsi": mmsi,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "last_seen": _format_utc(last_seen),
    }
    name = _clean_text(_first_present(item, ("name", "Name", "VesselName", "shipname")))
    if name:
        vessel["name"] = name
    vessel_type = _vessel_type(_first_present(item, ("type", "Type", "VesselType", "shiptype")))
    if vessel_type:
        vessel["type"] = vessel_type
    for output_name, keys in {
        "sog": ("sog", "SOG", "speed", "speed_knots"),
        "cog": ("cog", "COG", "course", "course_degrees"),
        "heading": ("heading", "Heading", "hdg", "HDG"),
    }.items():
        value = _optional_float(_first_present(item, keys))
        if value is not None:
            vessel[output_name] = round(value, 3)
    return vessel


def _first_present(item: Mapping[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


def _clean_mmsi(value: object) -> str:
    text = str(value or "").strip()
    return text if text.isdigit() and 7 <= len(text) <= 9 else ""


def _clean_text(value: object) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:80]


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _vessel_type(value: object) -> str:
    text = str(value or "").strip()
    if text in VESSEL_TYPES:
        return VESSEL_TYPES[text]
    return _clean_text(text).lower().replace(" ", "-") if text and not text.isdigit() else ""


def _parse_time(value: object, *, default: datetime) -> datetime:
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), UTC)
    text = str(value).strip()
    if text.isdigit():
        return datetime.fromtimestamp(float(text), UTC)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return default


def _request_token(event: Mapping[str, Any]) -> str:
    headers = event.get("headers") or {}
    lowered = {str(key).lower(): str(value) for key, value in dict(headers).items()}
    auth = lowered.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]
    return lowered.get("x-talkingboats-ais-ingest-token", "")


def _request_token_is_valid(event: Mapping[str, Any], env: Mapping[str, str]) -> bool:
    token = _request_token(event)
    expected_hash = env.get("TALKINGBOATS_AIS_INGEST_TOKEN_SHA256", "")
    if expected_hash:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return digest == expected_hash
    expected_token = env.get("TALKINGBOATS_AIS_INGEST_TOKEN", "")
    return bool(expected_token) and token == expected_token


def _event_json_body(event: Mapping[str, Any]) -> object:
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(str(body)).decode("utf-8")
    return json.loads(str(body))


def _fixed_now(env: Mapping[str, str]) -> datetime | None:
    value = env.get("TALKINGBOATS_AIS_FIXED_NOW")
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _lambda_response(status_code: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, sort_keys=True),
    }


def _boto3_client(name: str, **kwargs: Any) -> Any:
    import boto3

    return boto3.client(name, **kwargs)


def _dynamodb_table(table_name: str) -> Any:
    import boto3

    return boto3.resource("dynamodb").Table(table_name)


def _connection_ids_from_table(env: Mapping[str, str]) -> list[str]:
    table = _dynamodb_table(env["TALKINGBOATS_AIS_CONNECTIONS_TABLE"])
    response = table.scan(ProjectionExpression="connection_id")
    return [
        str(item["connection_id"])
        for item in response.get("Items", [])
        if item.get("connection_id")
    ]


def assert_public_safe(value: object) -> None:
    rendered = json.dumps(value, sort_keys=True, default=str)
    forbidden = ("192.168.", "10.", "172.16.", ".tail", "s3://", "raw_nmea", "token")
    for marker in forbidden:
        if marker.lower() in rendered.lower():
            raise ValueError(f"forbidden public AIS value: {marker}")
