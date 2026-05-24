from __future__ import annotations

import concurrent.futures
import subprocess
import threading

import httpx
from fastapi.testclient import TestClient

from talkingboats.live_radio_proxy import ChannelPreset, ProxySettings, RetuneResult, create_app


def test_proxy_static_shell_assets_are_not_cached() -> None:
    response = TestClient(create_app(ProxySettings())).get("/assets/app.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
    assert "/api/clips/recent" in response.text


def test_proxy_root_serves_clip_console() -> None:
    response = TestClient(create_app(ProxySettings())).get("/")

    assert response.status_code == 200
    assert "Seattle Marine Radio" in response.text
    assert "live-audio" in response.text
    assert "bay-map" not in response.text


def test_proxy_current_live_stream_uses_first_available_mount() -> None:
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == "http://pi.test/talkingboats-WX.mp3":
            return httpx.Response(404)
        if str(request.url) == "http://pi.test/talkingboats-14.mp3":
            return httpx.Response(200, content=b"mp3-data")
        raise AssertionError(f"unexpected URL: {request.url}")

    app = create_app(
        ProxySettings(
            stream_urls=(
                "http://pi.test/talkingboats-WX.mp3",
                "http://pi.test/talkingboats-14.mp3",
            )
        ),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = TestClient(app).get("/api/live/current.mp3")

    assert response.status_code == 200
    assert response.content == b"mp3-data"
    assert response.headers["cache-control"] == "no-store"
    assert requests == [
        "http://pi.test/talkingboats-WX.mp3",
        "http://pi.test/talkingboats-14.mp3",
        "http://pi.test/talkingboats-14.mp3",
    ]


def test_proxy_transcript_endpoint_forwards_json() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://transcriber.test/api/live-transcript"
        return httpx.Response(200, json={"status": "running", "entries": []})

    app = create_app(
        ProxySettings(
            transcript_url="http://transcriber.test/api/live-transcript",
            stream_url="http://pi.test:8000/talkingboats-live.mp3",
            enable_debug_endpoints=True,
        ),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = TestClient(app).get("/api/live-transcript")

    assert response.status_code == 200
    assert response.json() == {"status": "running", "entries": []}


def test_proxy_recent_clips_endpoint_is_public_read_only() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://private-api.test/api/clips/recent?limit=5"
        assert "x-talkingboats-operator-token" not in request.headers
        return httpx.Response(200, json={"clips": [{"transcript": "hello"}]})

    app = create_app(
        ProxySettings(private_api_url="http://private-api.test"),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = TestClient(app).get("/api/clips/recent?limit=5")

    assert response.status_code == 200
    assert response.json() == {"clips": [{"transcript": "hello"}]}


def test_proxy_debug_endpoints_are_disabled_by_default() -> None:
    client = TestClient(create_app(ProxySettings()))

    assert client.get("/api/live-transcript").status_code == 404
    assert client.post("/api/channel", json={"id": "vts_14"}).status_code in {404, 405}
    assert client.get("/talkingboats-live.mp3").status_code == 404


def test_proxy_retune_endpoint_validates_and_calls_retuner() -> None:
    calls: list[ChannelPreset] = []

    def retuner(preset: ChannelPreset, _settings: ProxySettings) -> RetuneResult:
        calls.append(preset)
        return RetuneResult(restarted_transcriber=True)

    app = create_app(ProxySettings(enable_debug_endpoints=True), retuner=retuner)

    response = TestClient(app).post("/api/channel", json={"id": "vts_14"})

    assert response.status_code == 200
    assert response.json()["activeChannelId"] == "vts_14"
    assert response.json()["frequencyMhz"] == "156.700"
    assert [call.id for call in calls] == ["vts_14"]


def test_proxy_retune_endpoint_rejects_unknown_channel() -> None:
    def retuner(_preset: ChannelPreset, _settings: ProxySettings) -> RetuneResult:
        raise AssertionError("retuner should not run")

    response = TestClient(
        create_app(ProxySettings(enable_debug_endpoints=True), retuner=retuner)
    ).post(
        "/api/channel",
        json={"id": "not-a-preset"},
    )

    assert response.status_code == 404


def test_proxy_retune_endpoint_maps_timeout_to_gateway_timeout() -> None:
    def retuner(_preset: ChannelPreset, _settings: ProxySettings) -> RetuneResult:
        raise subprocess.TimeoutExpired(cmd=["ssh", "talkingboats-pi"], timeout=45)

    response = TestClient(
        create_app(ProxySettings(enable_debug_endpoints=True), retuner=retuner)
    ).post(
        "/api/channel",
        json={"id": "vts_14"},
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "retune timed out"


def test_proxy_retune_endpoint_rejects_overlapping_retunes() -> None:
    started = threading.Event()
    release = threading.Event()

    def retuner(_preset: ChannelPreset, _settings: ProxySettings) -> RetuneResult:
        started.set()
        assert release.wait(timeout=3)
        return RetuneResult(restarted_transcriber=True)

    client = TestClient(create_app(ProxySettings(enable_debug_endpoints=True), retuner=retuner))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(lambda: client.post("/api/channel", json={"id": "vts_14"}))
        assert started.wait(timeout=3)

        second = client.post("/api/channel", json={"id": "bridge_13"})
        release.set()

        assert second.status_code == 409
        assert second.json()["detail"] == "retune already in progress"
        assert first.result(timeout=3).status_code == 200
