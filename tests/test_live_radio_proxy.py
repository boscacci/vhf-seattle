from __future__ import annotations

import asyncio
import subprocess
import threading

import httpx
from fastapi import HTTPException

from talkingboats.live_radio_proxy import (
    ChannelPreset,
    ProxySettings,
    RetuneRequest,
    RetuneResult,
    _audio_iterator_for_stream,
    _iter_upstream_audio,
    create_app,
)


def test_proxy_static_shell_assets_are_not_cached() -> None:
    response = _run(_asgi_get(create_app(ProxySettings()), "/assets/app.js"))

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
    assert "/api/clips/recent" in response.text
    assert "/api/live/current.mp3" in response.text


def test_proxy_root_serves_clip_console() -> None:
    response = _run(_asgi_get(create_app(ProxySettings()), "/"))

    assert response.status_code == 200
    assert "Elliott Bay VHF" in response.text
    assert "live-audio" in response.text
    assert "bay-map" not in response.text


def test_proxy_current_live_stream_uses_first_available_mount() -> None:
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == "http://pi.test/talkingboats-live.mp3":
            return httpx.Response(404)
        if str(request.url) == "http://pi.test/talkingboats-14.mp3":
            return httpx.Response(200, content=b"mp3-data")
        raise AssertionError(f"unexpected URL: {request.url}")

    app = create_app(
        ProxySettings(
            stream_urls=(
                "http://pi.test/talkingboats-live.mp3",
                "http://pi.test/talkingboats-14.mp3",
            )
        ),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = _run(_asgi_get(app, "/api/live/current.mp3"))

    assert response.status_code == 200
    assert response.content == b"mp3-data"
    assert response.headers["cache-control"] == "no-store"
    assert requests == [
        "http://pi.test/talkingboats-live.mp3",
        "http://pi.test/talkingboats-14.mp3",
        "http://pi.test/talkingboats-14.mp3",
    ]


def test_proxy_upstream_stream_yields_small_chunks_for_live_audio() -> None:
    chunk_sizes = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self, chunk_size=None):
            chunk_sizes.append(chunk_size)
            yield b"mp3-frame"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class FakeClient:
        def stream(self, method: str, url: str):
            assert method == "GET"
            assert url == "http://pi.test/talkingboats-13.mp3"
            return FakeResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    async def collect() -> list[bytes]:
        chunks = []
        async for chunk in _iter_upstream_audio(
            "http://pi.test/talkingboats-13.mp3",
            lambda: FakeClient(),
        ):
            chunks.append(chunk)
        return chunks

    assert _run(collect()) == [b"mp3-frame"]
    assert chunk_sizes == [1024]


def test_proxy_lists_live_channels_without_upstream_urls() -> None:
    app = create_app(
        ProxySettings(
            channel_stream_urls={
                "13": ("http://pi.test/talkingboats-13.mp3",),
                "14": ("http://pi.test/talkingboats-live.mp3",),
            }
        )
    )

    response = _run(_asgi_get(app, "/api/live/channels"))

    assert response.status_code == 200
    assert response.json() == {
        "defaultChannel": "14",
        "channels": [
            {
                "channel": "13",
                "label": "Bridge-to-bridge",
                "frequencyMhz": "156.650",
                "streamPath": "/api/live/13/current.mp3",
                "statusPath": "/api/live/13/status",
            },
            {
                "channel": "14",
                "label": "VTS / Seattle Traffic",
                "frequencyMhz": "156.700",
                "streamPath": "/api/live/14/current.mp3",
                "statusPath": "/api/live/14/status",
            },
        ],
    }
    assert "http://pi.test" not in response.text


def test_proxy_channel_live_stream_uses_requested_mount() -> None:
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == "http://pi.test/talkingboats-13.mp3":
            return httpx.Response(200, content=b"vhf-13-audio")
        if str(request.url) == "http://pi.test/talkingboats-live.mp3":
            return httpx.Response(200, content=b"vhf-14-audio")
        raise AssertionError(f"unexpected URL: {request.url}")

    app = create_app(
        ProxySettings(
            channel_stream_urls={
                "13": ("http://pi.test/talkingboats-13.mp3",),
                "14": ("http://pi.test/talkingboats-live.mp3",),
            }
        ),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = _run(_asgi_get(app, "/api/live/13/current.mp3"))

    assert response.status_code == 200
    assert response.content == b"vhf-13-audio"
    assert response.headers["cache-control"] == "no-store"
    assert requests == [
        "http://pi.test/talkingboats-13.mp3",
        "http://pi.test/talkingboats-13.mp3",
    ]


def test_proxy_uses_dsp_iterator_only_when_requested() -> None:
    raw = _audio_iterator_for_stream(
        "http://pi.test/talkingboats-13.mp3",
        dsp=None,
        settings=ProxySettings(),
        client_factory=lambda: None,
    )
    enhanced = _audio_iterator_for_stream(
        "http://pi.test/talkingboats-13.mp3",
        dsp="warm_voice",
        settings=ProxySettings(ffmpeg_path="ffmpeg"),
        client_factory=lambda: None,
    )

    assert raw.ag_code.co_name == "_iter_upstream_audio"
    assert enhanced.ag_code.co_name == "_iter_dsp_audio"


def test_proxy_channel_live_status_reports_requested_channel() -> None:
    app = create_app(
        ProxySettings(
            channel_stream_urls={
                "13": ("http://pi.test/talkingboats-13.mp3",),
                "14": ("http://pi.test/talkingboats-live.mp3",),
            }
        )
    )

    response = _run(_asgi_get(app, "/api/live/13/status"))

    assert response.status_code == 200
    assert response.json() == {
        "activeChannelId": "bridge_13",
        "channel": "13",
        "label": "Bridge-to-bridge",
        "frequencyMhz": "156.650",
        "streamDelaySeconds": {"minimum": 1, "maximum": 5},
    }


def test_proxy_live_status_reports_selected_stream_channel_and_allows_public_ui_origin() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "http://pi.test/talkingboats-live.mp3":
            return httpx.Response(200, content=b"mp3-data")
        if str(request.url) == "http://pi.test/current-status.json":
            return httpx.Response(
                200,
                json={
                    "channel": "14",
                    "frequencyHz": 156700000,
                    "label": "VTS / Seattle Traffic",
                },
            )
        raise AssertionError(f"unexpected URL: {request.url}")

    app = create_app(
        ProxySettings(
            stream_urls=("http://pi.test/talkingboats-live.mp3",),
            receiver_status_url="http://pi.test/current-status.json",
            cors_origins=("https://vhf.robertboscacci.com",),
        ),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = _run(
        _asgi_get(
            app,
            "/api/live/status",
            headers={"Origin": "https://vhf.robertboscacci.com"},
        )
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://vhf.robertboscacci.com"
    assert response.json() == {
        "activeChannelId": "vts_14",
        "channel": "14",
        "label": "VTS / Seattle Traffic",
        "frequencyMhz": "156.700",
        "streamDelaySeconds": {"minimum": 1, "maximum": 5},
    }


def test_proxy_live_status_uses_receiver_status_when_audio_mount_is_missing() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "http://pi.test/current-status.json":
            return httpx.Response(
                200,
                json={
                    "channel": "14",
                    "frequencyHz": 156700000,
                    "label": "VTS / Seattle Traffic",
                },
            )
        raise AssertionError(f"status endpoint should not require stream probe: {request.url}")

    app = create_app(
        ProxySettings(
            stream_urls=("http://pi.test/talkingboats-live.mp3",),
            receiver_status_url="http://pi.test/current-status.json",
        ),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = _run(_asgi_get(app, "/api/live/status"))

    assert response.status_code == 200
    assert response.json() == {
        "activeChannelId": "vts_14",
        "channel": "14",
        "label": "VTS / Seattle Traffic",
        "frequencyMhz": "156.700",
        "streamDelaySeconds": {"minimum": 1, "maximum": 5},
    }


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

    response = _run(_asgi_get(app, "/api/live-transcript"))

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

    response = _run(_asgi_get(app, "/api/clips/recent?limit=5"))

    assert response.status_code == 200
    assert response.json() == {"clips": [{"transcript": "hello"}]}


def test_proxy_lexical_analysis_endpoint_is_public_read_only() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://private-api.test/api/analysis/lexical"
        assert "x-talkingboats-operator-token" not in request.headers
        return httpx.Response(200, json={"status": "ok", "source_clip_count": 1, "entities": []})

    app = create_app(
        ProxySettings(private_api_url="http://private-api.test"),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = _run(_asgi_get(app, "/api/analysis/lexical"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "source_clip_count": 1, "entities": []}


def test_proxy_recent_clips_endpoint_strips_viewer_auth_and_upstream_cookies() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://private-api.test/api/clips/recent?limit=5"
        assert "cookie" not in request.headers
        assert "x-talkingboats-operator-token" not in request.headers
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/json",
                "Set-Cookie": "talkingboats_operator_token=private-token",
            },
            json={"clips": [{"transcript": "hello"}]},
        )

    app = create_app(
        ProxySettings(private_api_url="http://private-api.test"),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = _run(
        _asgi_get(
            app,
            "/api/clips/recent?limit=5",
            headers={
                "Cookie": "talkingboats_operator_token=viewer-token",
                "X-TalkingBoats-Operator-Token": "viewer-token",
            },
        )
    )

    assert response.status_code == 200
    assert response.json() == {"clips": [{"transcript": "hello"}]}
    assert "set-cookie" not in response.headers


def test_proxy_debug_endpoints_are_disabled_by_default() -> None:
    app = create_app(ProxySettings())
    route_paths = {getattr(route, "path", None) for route in app.routes}

    assert "/api/live-transcript" not in route_paths
    assert "/api/channel" not in route_paths
    assert "/talkingboats-live.mp3" not in route_paths


def test_proxy_retune_endpoint_validates_and_calls_retuner() -> None:
    calls: list[ChannelPreset] = []

    def retuner(preset: ChannelPreset, _settings: ProxySettings) -> RetuneResult:
        calls.append(preset)
        return RetuneResult(restarted_transcriber=True)

    app = create_app(ProxySettings(enable_debug_endpoints=True), retuner=retuner)

    response = _run(_asgi_post(app, "/api/channel", json={"id": "vts_14"}))

    assert response.status_code == 200
    assert response.json()["activeChannelId"] == "vts_14"
    assert response.json()["frequencyMhz"] == "156.700"
    assert [call.id for call in calls] == ["vts_14"]


def test_proxy_retune_endpoint_rejects_unknown_channel() -> None:
    def retuner(_preset: ChannelPreset, _settings: ProxySettings) -> RetuneResult:
        raise AssertionError("retuner should not run")

    response = _run(
        _asgi_post(
            create_app(ProxySettings(enable_debug_endpoints=True), retuner=retuner),
            "/api/channel",
            json={"id": "not-a-preset"},
        )
    )

    assert response.status_code == 404


def test_proxy_retune_endpoint_maps_timeout_to_gateway_timeout() -> None:
    def retuner(_preset: ChannelPreset, _settings: ProxySettings) -> RetuneResult:
        raise subprocess.TimeoutExpired(cmd=["ssh", "talkingboats-pi"], timeout=45)

    response = _run(
        _asgi_post(
            create_app(ProxySettings(enable_debug_endpoints=True), retuner=retuner),
            "/api/channel",
            json={"id": "vts_14"},
        )
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

    app = create_app(ProxySettings(enable_debug_endpoints=True), retuner=retuner)

    endpoint = _route_endpoint(app, "/api/channel")

    async def scenario() -> tuple[dict[str, object], HTTPException]:
        first_task = asyncio.create_task(endpoint(RetuneRequest(id="vts_14")))
        assert await _wait_for_event(started, timeout=3)
        second_task = asyncio.create_task(endpoint(RetuneRequest(id="bridge_13")))
        done, _ = await asyncio.wait({second_task}, timeout=0.2)
        release.set()
        first = await asyncio.wait_for(first_task, timeout=3)
        if not done:
            second_task.cancel()
            raise AssertionError("overlapping retune should be rejected immediately")
        try:
            second_task.result()
        except HTTPException as exc:
            second = exc
        else:
            raise AssertionError("overlapping retune should be rejected")
        return first, second

    first, second = _run(scenario())

    assert second.status_code == 409
    assert second.detail == "retune already in progress"
    assert first["activeChannelId"] == "vts_14"


async def _asgi_get(app, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path, **kwargs)


async def _asgi_post(app, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(path, **kwargs)


def _run(awaitable):
    return asyncio.run(awaitable)


def _route_endpoint(app, path: str):
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route.endpoint
    raise AssertionError(f"route not found: {path}")


async def _wait_for_event(event: threading.Event, *, timeout: float) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if event.is_set():
            return True
        await asyncio.sleep(0.01)
    return event.is_set()
