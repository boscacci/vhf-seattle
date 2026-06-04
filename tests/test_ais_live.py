from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime

from talkingboats.ais_live import (
    AisLiveConfig,
    ais_http_ingest_handler,
    ais_websocket_handler,
    public_ais_snapshot,
)


class FakeS3:
    def __init__(self) -> None:
        self.objects: list[dict[str, object]] = []

    def put_object(self, **kwargs) -> None:
        self.objects.append(kwargs)


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def post_to_connection(self, **kwargs) -> None:
        self.messages.append(kwargs)


class FakeConnectionsTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}

    def put_item(self, Item) -> None:
        self.items[Item["connection_id"]] = Item

    def delete_item(self, Key) -> None:
        self.items.pop(Key["connection_id"], None)


def test_public_ais_snapshot_sanitizes_bounds_and_private_fields() -> None:
    payload = {
        "device": "rtl-sdr-serial",
        "lan_url": "http://192.168.1.114:8100",
        "ships": [
            {
                "MMSI": "367123456",
                "VesselName": "TUG EXAMPLE",
                "VesselType": "52",
                "Lat": 47.61,
                "Lon": -122.35,
                "SOG": 7.2,
                "COG": 181.4,
                "Heading": 180,
                "time": "2026-06-03T07:30:01Z",
                "raw_nmea": "!AIVDM,private",
            },
            {
                "MMSI": "999999999",
                "VesselName": "OUTSIDE",
                "Lat": 45.0,
                "Lon": -122.35,
                "time": "2026-06-03T07:30:01Z",
            },
            {"MMSI": "bad", "Lat": 47.61, "Lon": -122.35},
        ],
    }

    snapshot = public_ais_snapshot(
        payload,
        config=AisLiveConfig(
            station="Elliott Bay VHF",
            generated_at=datetime(2026, 6, 3, 7, 30, 2, tzinfo=UTC),
        ),
    )

    assert snapshot["type"] == "ais_snapshot"
    assert snapshot["station"] == "Elliott Bay VHF"
    assert snapshot["generated_at"] == "2026-06-03T07:30:02Z"
    assert snapshot["sequence"] == "20260603T073002Z"
    assert snapshot["vessels"] == [
        {
            "mmsi": "367123456",
            "name": "TUG EXAMPLE",
            "type": "tug",
            "lat": 47.61,
            "lon": -122.35,
            "sog": 7.2,
            "cog": 181.4,
            "heading": 180,
            "last_seen": "2026-06-03T07:30:01Z",
        }
    ]
    rendered = json.dumps(snapshot)
    assert "raw_nmea" not in rendered
    assert "192.168" not in rendered
    assert "rtl-sdr" not in rendered


def test_ais_http_ingest_handler_writes_s3_snapshot_and_broadcasts() -> None:
    s3 = FakeS3()
    websocket = FakeWebSocket()
    body = json.dumps(
        {
            "vessels": [
                {
                    "mmsi": "367123456",
                    "lat": 47.61,
                    "lon": -122.35,
                    "last_seen": "2026-06-03T07:30:01Z",
                }
            ]
        }
    )
    event = {
        "headers": {"x-talkingboats-ais-ingest-token": "secret-token"},
        "body": base64.b64encode(body.encode("utf-8")).decode("ascii"),
        "isBase64Encoded": True,
    }

    response = ais_http_ingest_handler(
        event,
        None,
        env={
            "TALKINGBOATS_AIS_INGEST_TOKEN": "secret-token",
            "TALKINGBOATS_AIS_SNAPSHOT_BUCKET": "public-bucket",
            "TALKINGBOATS_AIS_SNAPSHOT_KEY": "ais/latest.json",
            "TALKINGBOATS_AIS_STATION": "Elliott Bay VHF",
            "TALKINGBOATS_AIS_FIXED_NOW": "2026-06-03T07:30:02Z",
        },
        s3_client=s3,
        websocket_client=websocket,
        websocket_connection_ids=["viewer-1"],
    )

    assert response["statusCode"] == 202
    assert s3.objects[0]["Bucket"] == "public-bucket"
    assert s3.objects[0]["Key"] == "ais/latest.json"
    assert s3.objects[0]["ContentType"] == "application/json"
    assert s3.objects[0]["CacheControl"] == "no-store"
    stored_snapshot = json.loads(s3.objects[0]["Body"].decode("utf-8"))
    assert stored_snapshot["vessels"][0]["mmsi"] == "367123456"
    assert websocket.messages[0]["ConnectionId"] == "viewer-1"


def test_ais_http_ingest_handler_rejects_bad_token() -> None:
    response = ais_http_ingest_handler(
        {"headers": {"x-talkingboats-ais-ingest-token": "wrong"}, "body": "{}"},
        None,
        env={"TALKINGBOATS_AIS_INGEST_TOKEN": "secret-token"},
        s3_client=FakeS3(),
    )

    assert response["statusCode"] == 401


def test_ais_http_ingest_handler_accepts_sha256_token_digest() -> None:
    token = "secret-token"
    body = json.dumps(
        {
            "vessels": [
                {
                    "mmsi": "367123456",
                    "lat": 47.61,
                    "lon": -122.35,
                }
            ]
        }
    )
    response = ais_http_ingest_handler(
        {
            "headers": {"Authorization": f"Bearer {token}"},
            "body": body,
        },
        None,
        env={
            "TALKINGBOATS_AIS_INGEST_TOKEN_SHA256": hashlib.sha256(
                token.encode("utf-8")
            ).hexdigest(),
            "TALKINGBOATS_AIS_FIXED_NOW": "2026-06-03T07:30:02Z",
        },
        s3_client=FakeS3(),
    )

    assert response["statusCode"] == 202


def test_ais_websocket_handler_tracks_connections_and_ignores_viewer_messages() -> None:
    table = FakeConnectionsTable()
    connect = {
        "requestContext": {
            "routeKey": "$connect",
            "connectionId": "viewer-1",
        }
    }
    message = {
        "requestContext": {
            "routeKey": "publish",
            "connectionId": "viewer-1",
        },
        "body": '{"private":"ignored"}',
    }
    disconnect = {
        "requestContext": {
            "routeKey": "$disconnect",
            "connectionId": "viewer-1",
        }
    }

    assert ais_websocket_handler(connect, None, table=table)["statusCode"] == 200
    assert "viewer-1" in table.items
    assert "expires_at" in table.items["viewer-1"]
    ignored = ais_websocket_handler(message, None, table=table)
    assert ignored["statusCode"] == 200
    assert json.loads(ignored["body"])["status"] == "ignored"
    assert ais_websocket_handler(disconnect, None, table=table)["statusCode"] == 200
    assert table.items == {}
