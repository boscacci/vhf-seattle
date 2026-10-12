import asyncio

import httpx

from talkingboats.api import app


def test_corrections_reject_requests_without_operator_credential():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            return await c.get("/api/clips/corrections?channel=14&started_at=2026-10-05T12:00:00Z")

    response = asyncio.run(run())
    assert response.status_code in (401, 503)
    assert response.status_code != 404


def test_saved_correction_is_visible_in_dev_and_public_reads_without_private_fields(
    tmp_path, monkeypatch
):
    from test_api import _client, _clip_presign, _segment

    import talkingboats.api as api
    from talkingboats.asr_feedback import MemoryCorrections
    from talkingboats.clip_transcriber import UploadedClipStore

    feedback = MemoryCorrections()
    original_dependency = api.get_feedback_store
    client = _client(clip_db_path=tmp_path / "clips.sqlite3")
    store = UploadedClipStore(tmp_path / "clips.sqlite3")
    key = "raw/channel=14/date=2026-05-20/correction-test.mp3"
    store.record_presigned_upload(key=key, request=_clip_presign(channel="14"))
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Tug spray northbound",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:05Z",
            )
        ],
    )
    app.dependency_overrides[original_dependency] = lambda: feedback
    app.dependency_overrides[api.require_feedback_operator] = lambda: None
    monkeypatch.setattr(api, "get_feedback_store", lambda settings: feedback)
    try:
        body = {
            "channel": "14",
            "started_at": "2026-05-20T19:12:00Z",
            "text": "Tug Osprey northbound",
            "expected_revision": 0,
            "request_id": "request-0001",
        }
        saved = client.put("/api/clips/corrections", json=body)
        assert saved.status_code == 200
        assert client.put("/api/clips/corrections", json=body).json()["revision"] == 1
        for _ in range(2):
            clips = client.get("/api/clips/recent?include_counts=false").json()["clips"]
            assert clips[0]["transcript"] == "Tug Osprey northbound"
            assert clips[0]["segments"] == []
            assert "original" not in clips[0] and "key" not in clips[0]
        body.update(request_id="request-0002", text="newer")
        assert client.put("/api/clips/corrections", json=body).status_code == 409
        body.update(expected_revision=1, text="Tug Osprey northbound", reverted=True)
        assert client.put("/api/clips/corrections", json=body).status_code == 200
        assert (
            client.get("/api/clips/recent?include_counts=false").json()["clips"][0]["transcript"]
            == "Tug spray northbound"
        )
    finally:
        app.dependency_overrides.clear()


def test_channel_74_explicit_query_is_empty_and_cannot_produce_playback(tmp_path):
    from test_api import _client

    client = _client(clip_db_path=tmp_path / "clips.sqlite3")
    assert client.get("/api/clips/recent?channels=74&quality=all").json()["clips"] == []
    assert (
        client.get("/api/clips/playback?channel=74&started_at=2026-05-20T19:12:00Z").status_code
        == 404
    )
