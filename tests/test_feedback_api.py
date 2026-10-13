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


def test_archived_experiment_audio_uses_immutable_dataset_and_stays_operator_only(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from test_api import _client

    import talkingboats.api as api
    from talkingboats.asr_experiments import atomic_json, run_directory

    monkeypatch.setenv("TALKINGBOATS_ASR_OUTPUT_DIR", str(tmp_path / "private-training"))
    run_id = "c" * 32
    clip_id = "d" * 64
    archived_key = "asr-feedback/audio/" + "e" * 64 + ".mp3"
    dataset = run_directory(run_id) / "dataset.json"
    atomic_json(
        dataset,
        [
            {
                "id": clip_id,
                "channel": "14",
                "archive_key": archived_key,
                "archive_status": "ready",
                "revision": 1,
            }
        ],
    )
    seen = []

    class S3:
        def head_object(self, **kwargs):
            seen.append(kwargs["Key"])
            return {}

        def generate_presigned_url(self, operation, **kwargs):
            assert operation == "get_object"
            assert kwargs["Params"] == {"Bucket": "raw-bucket", "Key": archived_key}
            return "https://example.test/private-reviewed-audio"

    client = _client()
    app.dependency_overrides[api.get_storage] = lambda: SimpleNamespace(client=S3())
    path = f"/api/asr-feedback/runs/{run_id}/audio?clip_id={clip_id}"
    try:
        assert client.get(path).status_code in (401, 503)
        app.dependency_overrides[api.require_feedback_operator] = lambda: None
        response = client.get(path)
        assert response.status_code == 307
        assert response.headers["location"] == "https://example.test/private-reviewed-audio"
        assert "no-store" in response.headers["cache-control"]
        assert seen == [archived_key]
        assert client.get(path.replace(clip_id, "missing")).status_code == 404
        atomic_json(
            dataset,
            [
                {
                    "id": clip_id,
                    "channel": "74",
                    "archive_key": archived_key,
                    "archive_status": "ready",
                }
            ],
        )
        assert client.get(path).status_code == 404
        atomic_json(
            dataset,
            [
                {
                    "id": clip_id,
                    "channel": "14",
                    "archive_key": "raw/forbidden.mp3",
                    "archive_status": "ready",
                }
            ],
        )
        assert client.get(path).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_missing_archived_audio_returns_a_safe_storage_error(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from botocore.exceptions import NoCredentialsError
    from test_api import _client

    import talkingboats.api as api
    from talkingboats.asr_experiments import atomic_json, run_directory

    monkeypatch.setenv("TALKINGBOATS_ASR_OUTPUT_DIR", str(tmp_path))
    run_id = "a" * 32
    atomic_json(
        run_directory(run_id) / "dataset.json",
        [
            dict(
                id="fixture",
                channel="14",
                archive_status="ready",
                archive_key="asr-feedback/audio/" + "b" * 64 + ".mp3",
            )
        ],
    )

    class Storage:
        def head_object(self, **kwargs):
            raise NoCredentialsError()

    client = _client()
    app.dependency_overrides[api.require_feedback_operator] = lambda: None
    app.dependency_overrides[api.get_storage] = lambda: SimpleNamespace(client=Storage())
    try:
        response = client.get(f"/api/asr-feedback/runs/{run_id}/audio?clip_id=fixture")
        assert response.status_code == 503
        assert response.json() == {"detail": "reviewed audio storage unavailable"}
    finally:
        app.dependency_overrides.clear()


def test_operator_status_reports_turbo_recovery_policy(tmp_path, monkeypatch):
    from test_api import _client

    import talkingboats.api as api
    from talkingboats.asr_feedback import MemoryCorrections

    monkeypatch.setenv('TALKINGBOATS_ASR_OUTPUT_DIR', str(tmp_path / 'feedback'))
    monkeypatch.setenv('TALKINGBOATS_ACTIVE_ASR_MODEL', 'large-v3-turbo')
    client = _client(clip_db_path=tmp_path / 'clips.sqlite3')
    app.dependency_overrides[api.get_feedback_store] = lambda: MemoryCorrections()
    app.dependency_overrides[api.require_feedback_operator] = lambda: None
    try:
        response = client.get('/api/asr-feedback/status')
        assert response.status_code == 200
        status = response.json()
        assert status['selected_model'] == 'large-v3-turbo'
        assert status['serving_model'] is None
        assert status['shared_worker_release_active'] is False
        assert status['activation_policy'] == 'allow_peak_backlog_overnight_recovery'
        assert status['recovery_forecast']['max_daily_processing_seconds'] < 86400
        import json
        proof = tmp_path / 'feedback/production-overlay.json'
        proof.parent.mkdir(parents=True, exist_ok=True)
        proof.write_text(json.dumps({'commit': 'released', 'serving_model': 'large-v3-turbo'}))
        activated = client.get('/api/asr-feedback/status').json()
        assert activated['serving_model'] == 'large-v3-turbo'
        assert activated['shared_worker_release_active'] is True
    finally:
        app.dependency_overrides.clear()
