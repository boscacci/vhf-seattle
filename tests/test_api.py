from pathlib import Path

from fastapi.testclient import TestClient

from talkingboats.api import app, get_settings, get_storage
from talkingboats.clip_transcriber import UploadedClipStore
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


def test_ingest_presign_records_upload_for_background_transcription(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)

    response = client.post(
        "/api/ingest/clips/presign",
        headers={"X-TalkingBoats-Ingest-Token": "ingest-token"},
        json=_clip_request(),
    )

    assert response.status_code == 200
    store = UploadedClipStore(db_path)
    pending = store.pending_uploads(limit=10)
    assert len(pending) == 1
    assert pending[0].key == "raw/channel=68/date=2026-05-20/fake.mp3"
    assert pending[0].channel == "68"
    assert pending[0].status == "pending"


def test_operator_can_read_ingest_clip_stats_when_db_configured(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    client.post(
        "/api/ingest/clips/presign",
        headers={"X-TalkingBoats-Ingest-Token": "ingest-token"},
        json=_clip_request(),
    )

    response = client.get(
        "/api/ingest/clips/stats",
        headers={"X-TalkingBoats-Operator-Token": "operator-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is True
    assert body["counts"] == {"pending": 1}
    assert body["recent"][0]["key"] == "raw/channel=68/date=2026-05-20/fake.mp3"


def test_recent_clips_are_public_read_only_with_playback_urls(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    key = "raw/channel=14/date=2026-05-20/fake.mp3"
    store.record_presigned_upload(key=key, request=_clip_presign(channel="14"))
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Seattle Traffic inbound for Elliott Bay",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )

    response = client.get("/api/clips/recent?limit=5")

    assert response.status_code == 200
    body = response.json()
    assert body["clips"][0]["key"] == key
    assert body["clips"][0]["channel"] == "14"
    assert body["clips"][0]["transcript"] == "Seattle Traffic inbound for Elliott Bay"
    assert body["clips"][0]["segments"][0]["text"] == "Seattle Traffic inbound for Elliott Bay"
    assert body["clips"][0]["playback_url"] == "https://s3.example.test/playback"
    assert body["clips"][0]["playback_expires_in_seconds"] == 300


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


def _client(*, clip_db_path: Path | None = None) -> TestClient:
    app.dependency_overrides.clear()
    app.dependency_overrides[get_settings] = lambda: Settings(
        aws_region="us-west-2",
        raw_bucket="raw-bucket",
        public_bucket="public-bucket",
        operator_token="operator-token",
        ingest_token="ingest-token",
        raw_presign_seconds=900,
        playback_presign_seconds=300,
        public_site_dir=Path("outputs/public-site"),
        public_base_url="https://vhf.robertboscacci.com",
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
        clip_db_path=clip_db_path,
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


def _clip_presign(*, channel: str) -> object:
    from talkingboats.schemas import ClipPresignRequest

    return ClipPresignRequest(
        channel=channel,
        started_at="2026-05-20T19:12:00Z",
        ended_at="2026-05-20T19:12:05Z",
        content_type="audio/mpeg",
        idempotency_key=f"radio-event-{channel}",
        duration_seconds=5.0,
    )


def _segment(*, text: str, started_at: str, ended_at: str) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(
        text=text,
        started_at=started_at,
        ended_at=ended_at,
        relative_start_seconds=0.0,
        relative_end_seconds=4.0,
    )
