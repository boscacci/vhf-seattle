from datetime import UTC, datetime

import httpx
import pytest

from talkingboats.capture_uploader import (
    ClipUploadRequest,
    infer_audio_content_type,
    upload_clip,
)


def test_upload_clip_presigns_and_puts_audio_without_local_path_in_payload(tmp_path):
    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(b"RIFFfake-wave")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            assert request.url.path == "/api/ingest/clips/presign"
            assert request.headers["X-TalkingBoats-Ingest-Token"] == "ingest-token"
            payload = httpx.Response(200, content=request.content).json()
            assert payload["channel"] == "68"
            assert payload["content_type"] == "audio/wav"
            assert payload["started_at"] == "2026-05-20T19:12:00Z"
            assert str(audio_path) not in request.content.decode("utf-8")
            assert len(payload["idempotency_key"]) <= 200
            return httpx.Response(
                200,
                json={
                    "bucket": "raw-bucket",
                    "key": "raw/channel=68/date=2026-05-20/fake.wav",
                    "upload_url": "https://s3.example.test/upload",
                    "expires_in_seconds": 900,
                    "required_headers": {"Content-Type": "audio/wav"},
                },
            )
        if request.method == "PUT":
            assert request.url.host == "s3.example.test"
            assert request.headers["Content-Type"] == "audio/wav"
            assert request.content == b"RIFFfake-wave"
            return httpx.Response(200)
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = upload_clip(
        api_base_url="http://private-api.test:8034/",
        ingest_token="ingest-token",
        request=ClipUploadRequest(
            channel="68",
            audio_path=audio_path,
            started_at=datetime(2026, 5, 20, 19, 12, tzinfo=UTC),
            duration_seconds=4.2,
        ),
        client=client,
    )

    assert result.bucket == "raw-bucket"
    assert result.key == "raw/channel=68/date=2026-05-20/fake.wav"
    assert result.bytes_uploaded == len(b"RIFFfake-wave")
    assert [request.method for request in calls] == ["POST", "PUT"]


def test_upload_clip_uses_stable_idempotency_key_for_same_audio(tmp_path):
    audio_path = tmp_path / "same.wav"
    audio_path.write_bytes(b"same bytes")
    posted_keys = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payload = httpx.Response(200, content=request.content).json()
            posted_keys.append(payload["idempotency_key"])
            return httpx.Response(
                200,
                json={
                    "bucket": "raw-bucket",
                    "key": "raw/channel=14/date=2026-05-20/stable.wav",
                    "upload_url": "https://s3.example.test/upload",
                    "expires_in_seconds": 900,
                    "required_headers": {"Content-Type": "audio/wav"},
                },
            )
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    request = ClipUploadRequest(
        channel="14",
        audio_path=audio_path,
        started_at=datetime(2026, 5, 20, 21, 30, tzinfo=UTC),
    )

    upload_clip("http://private-api.test", "ingest-token", request, client=client)
    upload_clip("http://private-api.test", "ingest-token", request, client=client)

    assert posted_keys == [posted_keys[0], posted_keys[0]]


def test_upload_clip_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        upload_clip(
            "http://private-api.test",
            "ingest-token",
            ClipUploadRequest(
                channel="68",
                audio_path=tmp_path / "missing.wav",
                started_at=datetime(2026, 5, 20, 19, 12, tzinfo=UTC),
            ),
            client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
        )


def test_infer_audio_content_type_rejects_unknown_extensions(tmp_path):
    with pytest.raises(ValueError, match="unsupported audio extension"):
        infer_audio_content_type(tmp_path / "clip.txt")
