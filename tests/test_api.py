from pathlib import Path

from fastapi.testclient import TestClient

from talkingboats.api import app, get_settings, get_storage
from talkingboats.config import LiveChannel, Settings


class FakeStorage:
    def presign_raw_upload(self, request):
        return (
            f"raw/channel={request.channel}/date=2026-05-20/fake.mp3",
            "https://s3.example.test/upload",
        )

    def presign_playback(self, key):
        if not key.startswith(("raw/", "hall-of-fame/")):
            raise ValueError("playback key must be in raw/ or hall-of-fame/")
        return "https://s3.example.test/playback"


def test_ingest_presign_requires_ingest_token() -> None:
    client = _client()

    response = client.post("/api/ingest/clips/presign", json=_clip_request())

    assert response.status_code == 401


def test_ingest_presign_returns_short_lived_upload_url() -> None:
    client = _client()

    response = client.post(
        "/api/ingest/clips/presign",
        headers={"X-TalkingBoats-Ingest-Token": "ingest-token"},
        json=_clip_request(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["bucket"] == "raw-bucket"
    assert body["key"].startswith("raw/channel=68/")
    assert body["upload_url"] == "https://s3.example.test/upload"
    assert body["expires_in_seconds"] == 900


def test_operator_live_channels_do_not_expose_upstream_urls() -> None:
    client = _client()

    response = client.get(
        "/api/live/channels",
        headers={"X-TalkingBoats-Operator-Token": "operator-token"},
    )

    assert response.status_code == 200
    rendered = response.text
    assert "127.0.0.1" not in rendered
    assert "vhf-68.mp3" not in rendered
    assert response.json()["channels"][0]["enabled"] is True


def test_operator_session_cookie_can_auth_live_channels() -> None:
    client = _client()

    session_response = client.post(
        "/api/operator/session",
        headers={"X-TalkingBoats-Operator-Token": "operator-token"},
    )
    channels_response = client.get("/api/live/channels")

    assert session_response.status_code == 200
    assert "talkingboats_operator_token" in session_response.headers["set-cookie"]
    assert channels_response.status_code == 200


def test_playback_presign_rejects_public_prefix() -> None:
    client = _client()

    response = client.post(
        "/api/clips/playback-url",
        headers={"X-TalkingBoats-Operator-Token": "operator-token"},
        json={"key": "public/file.mp3"},
    )

    assert response.status_code == 400


def _client() -> TestClient:
    app.dependency_overrides[get_settings] = lambda: Settings(
        aws_region="us-west-2",
        raw_bucket="raw-bucket",
        public_bucket="public-bucket",
        operator_token="operator-token",
        ingest_token="ingest-token",
        raw_presign_seconds=900,
        playback_presign_seconds=300,
        public_site_dir=Path("outputs/public-site"),
        public_base_url="https://talkingboats.robertboscacci.com",
        live_channels={
            "68": LiveChannel(
                channel="68",
                label="Fun Channel",
                frequency_mhz=156.425,
                stream_url="http://127.0.0.1:8040/vhf-68.mp3",
            ),
            "14": LiveChannel(
                channel="14",
                label="Super Business Channel",
                frequency_mhz=156.700,
                stream_url=None,
            ),
        },
    )
    app.dependency_overrides[get_storage] = lambda: FakeStorage()
    return TestClient(app)


def _clip_request() -> dict[str, object]:
    return {
        "channel": "68",
        "started_at": "2026-05-20T19:12:00Z",
        "content_type": "audio/mpeg",
        "idempotency_key": "unique-radio-event",
        "duration_seconds": 12.5,
    }
