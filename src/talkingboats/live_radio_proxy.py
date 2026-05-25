from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import threading
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from talkingboats.audio_dsp import build_ffmpeg_dsp_command, dsp_profile_for_name

CLIP_CONSOLE_DIR = Path(__file__).resolve().parents[2] / "public-site"
SHELL_ASSET_TYPES = {
    "index.html": "text/html",
    "assets/app.js": "application/javascript",
    "assets/styles.css": "text/css",
    "public_manifest.json": "application/json",
}
@dataclass(frozen=True)
class ChannelPreset:
    id: str
    channel: str
    label: str
    frequency_hz: int
    description: str
    squelch: int = 0
    audio_filter_enabled: bool = True

    @property
    def frequency_mhz(self) -> str:
        return f"{self.frequency_hz / 1_000_000:.3f}"

    def to_config(self) -> dict[str, str]:
        return {
            "id": self.id,
            "channel": self.channel,
            "label": self.label,
            "frequencyMhz": self.frequency_mhz,
            "description": self.description,
        }


DEFAULT_CHANNELS = (
    ChannelPreset(
        id="vts_14",
        channel="14",
        label="VTS / Seattle Traffic",
        frequency_hz=156_700_000,
        description="Vessel traffic and harbor movements.",
    ),
    ChannelPreset(
        id="vts_05a",
        channel="05A",
        label="VTS / Port Ops",
        frequency_hz=156_250_000,
        description="Puget Sound traffic and port coordination.",
    ),
    ChannelPreset(
        id="bridge_13",
        channel="13",
        label="Bridge-to-bridge",
        frequency_hz=156_650_000,
        description="Navigation safety between commercial vessels.",
    ),
    ChannelPreset(
        id="safety_16",
        channel="16",
        label="Distress / Calling",
        frequency_hz=156_800_000,
        description="Safety hailing and distress watch.",
    ),
    ChannelPreset(
        id="uscg_22a",
        channel="22A",
        label="USCG Liaison",
        frequency_hz=157_100_000,
        description="Coast Guard working broadcasts after hailing.",
    ),
    ChannelPreset(
        id="port_66a",
        channel="66A",
        label="Port Operations",
        frequency_hz=156_325_000,
        description="Harbor and commercial operations.",
    ),
    ChannelPreset(
        id="recreation_68",
        channel="68",
        label="Recreational",
        frequency_hz=156_425_000,
        description="Local recreational vessel traffic.",
    ),
)


def _default_channel_stream_urls() -> dict[str, tuple[str, ...]]:
    return {
        "13": ("http://192.168.1.114:8000/talkingboats-13.mp3",),
        "14": (
            "http://192.168.1.114:8000/talkingboats-live.mp3",
            "http://192.168.1.114:8000/talkingboats-14.mp3",
        ),
    }


@dataclass(frozen=True)
class ProxySettings:
    stream_url: str = "http://192.168.1.114:8000/talkingboats-live.mp3"
    stream_urls: tuple[str, ...] = (
        "http://192.168.1.114:8000/talkingboats-live.mp3",
        "http://192.168.1.114:8000/talkingboats-14.mp3",
    )
    channel_stream_urls: dict[str, tuple[str, ...]] = field(
        default_factory=_default_channel_stream_urls
    )
    receiver_status_url: str = "http://192.168.1.114:8050/current-status.json"
    transcript_url: str = "http://127.0.0.1:8055/api/live-transcript"
    private_api_url: str = "http://192.168.1.247:8034"
    active_channel_id: str = "recreation_68"
    retune_ssh_target: str = "talkingboats-pi"
    pi_env_path: str = "/etc/talkingboats/live-radio.env"
    ffmpeg_path: str = "ffmpeg"
    restart_transcriber_service: bool = True
    enable_debug_endpoints: bool = False
    cors_origins: tuple[str, ...] = (
        "https://vhf.robertboscacci.com",
        "https://vhf-dev.robertboscacci.com",
    )

    @classmethod
    def from_env(cls) -> ProxySettings:
        stream_url = os.environ.get("TALKINGBOATS_PROXY_STREAM_URL", cls.stream_url)
        stream_urls = _env_csv("TALKINGBOATS_PROXY_STREAM_URLS") or (stream_url, *cls.stream_urls)
        stream_urls = _dedupe(stream_urls)
        channel_stream_urls = _env_channel_stream_urls("TALKINGBOATS_PROXY_CHANNEL_STREAM_URLS")
        if not channel_stream_urls:
            channel_stream_urls = _default_channel_stream_urls()
            channel_stream_urls["14"] = stream_urls
        return cls(
            stream_url=stream_url,
            stream_urls=stream_urls,
            channel_stream_urls=channel_stream_urls,
            receiver_status_url=os.environ.get(
                "TALKINGBOATS_PROXY_RECEIVER_STATUS_URL",
                cls.receiver_status_url,
            ),
            transcript_url=os.environ.get(
                "TALKINGBOATS_PROXY_TRANSCRIPT_URL",
                cls.transcript_url,
            ),
            private_api_url=os.environ.get(
                "TALKINGBOATS_PROXY_PRIVATE_API_URL",
                cls.private_api_url,
            ),
            active_channel_id=os.environ.get(
                "TALKINGBOATS_PROXY_ACTIVE_CHANNEL_ID",
                cls.active_channel_id,
            ),
            retune_ssh_target=os.environ.get(
                "TALKINGBOATS_PROXY_RETUNE_SSH_TARGET",
                cls.retune_ssh_target,
            ),
            ffmpeg_path=os.environ.get("TALKINGBOATS_PROXY_FFMPEG_PATH", cls.ffmpeg_path),
            restart_transcriber_service=_env_bool("TALKINGBOATS_PROXY_RESTART_TRANSCRIBER", True),
            enable_debug_endpoints=_env_bool("TALKINGBOATS_PROXY_ENABLE_DEBUG_ENDPOINTS", False),
            cors_origins=_env_csv("TALKINGBOATS_PROXY_CORS_ORIGINS") or cls.cors_origins,
        )


@dataclass(frozen=True)
class RetuneResult:
    restarted_transcriber: bool = False


class RetuneRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64)


ClientFactory = Callable[[], httpx.AsyncClient]
Retuner = Callable[[ChannelPreset, ProxySettings], RetuneResult]


def create_app(
    settings: ProxySettings | None = None,
    *,
    client_factory: ClientFactory | None = None,
    retuner: Retuner | None = None,
) -> FastAPI:
    settings = settings or ProxySettings.from_env()
    client_factory = client_factory or _default_client
    retuner = retuner or retune_pi
    retune_lock = asyncio.Lock()
    app = FastAPI(title="Talking Boats Tailnet Radio Proxy", version="0.1.0")
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/clips/recent")
    async def recent_clips(request: Request) -> Response:
        return await _proxy_private_api(request, "/api/clips/recent", settings, client_factory)

    @app.get("/api/live/current.mp3")
    async def current_live_stream(dsp: str | None = None) -> StreamingResponse:
        stream_url = await _select_live_stream(settings.stream_urls, client_factory)
        return StreamingResponse(
            _audio_iterator_for_stream(stream_url, dsp, settings, client_factory),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/live/channels")
    async def live_channels() -> dict[str, object]:
        return {
            "defaultChannel": "14",
            "channels": _public_live_channels(settings),
        }

    @app.get("/api/live/{channel}/current.mp3")
    async def channel_live_stream(channel: str, dsp: str | None = None) -> StreamingResponse:
        stream_urls = _stream_urls_for_channel(settings, channel)
        stream_url = await _select_live_stream(stream_urls, client_factory)
        return StreamingResponse(
            _audio_iterator_for_stream(stream_url, dsp, settings, client_factory),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/live/status")
    async def live_status() -> dict[str, object]:
        preset = (
            await _preset_from_receiver_status(settings, client_factory)
            or await _preset_from_available_stream(settings.stream_urls, client_factory)
            or _find_channel(settings.active_channel_id)
        )
        return _live_status_payload(preset)

    @app.get("/api/live/{channel}/status")
    async def channel_live_status(channel: str) -> dict[str, object]:
        _stream_urls_for_channel(settings, channel)
        preset = _find_channel_by_number(channel)
        return _live_status_payload(preset)

    if settings.enable_debug_endpoints:

        @app.get("/api/live-transcript")
        async def live_transcript() -> dict[str, Any]:
            async with client_factory() as client:
                response = await client.get(settings.transcript_url)
            if response.status_code >= 500:
                raise HTTPException(status_code=502, detail="transcriber unavailable")
            if response.status_code >= 400:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()

        @app.post("/api/channel")
        async def retune_channel(request: RetuneRequest) -> dict[str, Any]:
            if retune_lock.locked():
                raise HTTPException(status_code=409, detail="retune already in progress")
            preset = _find_channel(request.id)
            async with retune_lock:
                try:
                    result = await _run_retuner(retuner, preset, settings)
                except subprocess.CalledProcessError as exc:
                    detail = (exc.stderr or exc.stdout or str(exc)).strip()
                    raise HTTPException(status_code=502, detail=detail or "retune failed") from exc
                except subprocess.TimeoutExpired as exc:
                    raise HTTPException(status_code=504, detail="retune timed out") from exc
            return {
                "activeChannelId": preset.id,
                "channel": preset.channel,
                "label": preset.label,
                "frequencyMhz": preset.frequency_mhz,
                "restartedTranscriber": result.restarted_transcriber,
            }

        @app.get("/talkingboats-live.mp3")
        async def live_stream() -> StreamingResponse:
            stream_url = await _select_live_stream(settings.stream_urls, client_factory)
            return StreamingResponse(
                _iter_upstream_audio(stream_url, client_factory),
                media_type="audio/mpeg",
                headers={"Cache-Control": "no-store"},
            )

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    async def clip_console_index() -> Response:
        return _shell_asset_response("index.html")

    @app.get("/assets/app.js", include_in_schema=False)
    async def clip_console_app_js() -> Response:
        return _shell_asset_response("assets/app.js")

    @app.get("/assets/styles.css", include_in_schema=False)
    async def clip_console_styles() -> Response:
        return _shell_asset_response("assets/styles.css")

    @app.get("/public_manifest.json", include_in_schema=False)
    async def clip_console_manifest() -> Response:
        return _shell_asset_response("public_manifest.json")

    app.mount("/", StaticFiles(directory=CLIP_CONSOLE_DIR, html=True), name="clip-console")
    return app


def _find_channel(channel_id: str) -> ChannelPreset:
    for channel in DEFAULT_CHANNELS:
        if channel.id == channel_id:
            return channel
    raise HTTPException(status_code=404, detail="unknown channel")


def _find_channel_by_number(channel_number: str) -> ChannelPreset:
    normalized = channel_number.upper()
    for channel in DEFAULT_CHANNELS:
        if channel.channel.upper() == normalized:
            return channel
    raise HTTPException(status_code=404, detail="unknown channel")


def _public_live_channels(settings: ProxySettings) -> list[dict[str, str]]:
    channels = []
    for channel_number in settings.channel_stream_urls:
        try:
            preset = _find_channel_by_number(channel_number)
        except HTTPException:
            continue
        channels.append(
            {
                "channel": preset.channel,
                "label": preset.label,
                "frequencyMhz": preset.frequency_mhz,
                "streamPath": f"/api/live/{preset.channel}/current.mp3",
                "statusPath": f"/api/live/{preset.channel}/status",
            }
        )
    return channels


def _stream_urls_for_channel(settings: ProxySettings, channel_number: str) -> tuple[str, ...]:
    preset = _find_channel_by_number(channel_number)
    stream_urls = settings.channel_stream_urls.get(preset.channel)
    if not stream_urls:
        raise HTTPException(status_code=404, detail="live stream not configured")
    return stream_urls


def _live_status_payload(preset: ChannelPreset) -> dict[str, object]:
    return {
        "activeChannelId": preset.id,
        "channel": preset.channel,
        "label": preset.label,
        "frequencyMhz": preset.frequency_mhz,
        "streamDelaySeconds": {"minimum": 1, "maximum": 5},
    }


def _shell_asset_response(relative_path: str) -> Response:
    path = (CLIP_CONSOLE_DIR / relative_path).resolve()
    try:
        path.relative_to(CLIP_CONSOLE_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="asset not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return Response(
        content=path.read_bytes(),
        headers={"Cache-Control": "no-store", "Pragma": "no-cache", "Expires": "0"},
        media_type=SHELL_ASSET_TYPES.get(relative_path, "application/octet-stream"),
    )


def _preset_for_stream_url(stream_url: str) -> ChannelPreset | None:
    normalized = stream_url.lower()
    stream_channel_markers = {
        "bridge_13": ("-13.", "/13.", "channel=13"),
        "vts_14": ("-14.", "/14.", "channel=14"),
        "recreation_68": ("-68.", "/68.", "channel=68"),
    }
    for channel_id, markers in stream_channel_markers.items():
        if any(marker in normalized for marker in markers):
            return _find_channel(channel_id)
    return None


def retune_pi(preset: ChannelPreset, settings: ProxySettings) -> RetuneResult:
    script = _build_pi_retune_script(preset, settings)
    subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            settings.retune_ssh_target,
            "sudo",
            "python3",
            "-",
        ],
        input=script,
        text=True,
        capture_output=True,
        timeout=45,
        check=True,
    )
    restarted = False
    if settings.restart_transcriber_service:
        subprocess.run(
            ["systemctl", "--user", "restart", "talkingboats-live-transcriber.service"],
            text=True,
            capture_output=True,
            timeout=20,
            check=True,
        )
        restarted = True
    return RetuneResult(restarted_transcriber=restarted)


def _build_pi_retune_script(preset: ChannelPreset, settings: ProxySettings) -> str:
    payload = {
        "env_path": settings.pi_env_path,
        "updates": {
            "TALKINGBOATS_LIVE_CHANNEL": preset.channel,
            "TALKINGBOATS_LIVE_FREQUENCY_HZ": str(preset.frequency_hz),
            "TALKINGBOATS_LIVE_LABEL": preset.label,
            "TALKINGBOATS_LIVE_SQUELCH": str(preset.squelch),
            "TALKINGBOATS_AUDIO_FILTER_ENABLED": str(preset.audio_filter_enabled).lower(),
        },
    }
    return f"""
import json
import subprocess
from pathlib import Path

payload = {json.dumps(payload)}
env_path = Path(payload["env_path"])
updates = payload["updates"]
lines = env_path.read_text().splitlines()
seen = set()
out = []

def quote(value):
    return "'" + value.replace("'", "'\\\\''") + "'"

for line in lines:
    if "=" not in line or line.lstrip().startswith("#"):
        out.append(line)
        continue
    key = line.split("=", 1)[0]
    if key in updates:
        out.append(f"{{key}}={{quote(updates[key])}}")
        seen.add(key)
    else:
        out.append(line)

for key, value in updates.items():
    if key not in seen:
        out.append(f"{{key}}={{quote(value)}}")

env_path.write_text("\\n".join(out) + "\\n")
env_path.chmod(0o600)
subprocess.run(["systemctl", "restart", "talkingboats-edge-live-radio-stream.service"], check=True)
"""


async def _iter_upstream_audio(
    stream_url: str,
    client_factory: ClientFactory,
) -> AsyncIterator[bytes]:
    async with client_factory() as client, client.stream("GET", stream_url) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes(chunk_size=1024):
            if chunk:
                yield chunk


def _audio_iterator_for_stream(
    stream_url: str,
    dsp: str | None,
    settings: ProxySettings,
    client_factory: ClientFactory,
) -> AsyncIterator[bytes]:
    if not dsp:
        return _iter_upstream_audio(stream_url, client_factory)
    try:
        profile = dsp_profile_for_name(dsp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _iter_dsp_audio(stream_url, settings.ffmpeg_path, profile.name)


async def _iter_dsp_audio(
    stream_url: str,
    ffmpeg_path: str,
    profile_name: str,
) -> AsyncIterator[bytes]:
    profile = dsp_profile_for_name(profile_name)
    command = build_ffmpeg_dsp_command(ffmpeg_path, stream_url, profile)
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=502, detail=f"ffmpeg not found: {ffmpeg_path}") from exc

    stderr_task = asyncio.create_task(_drain_stream(process.stderr))
    try:
        if process.stdout is None:
            raise HTTPException(status_code=502, detail="ffmpeg stdout unavailable")
        while True:
            chunk = await process.stdout.read(1024)
            if not chunk:
                break
            yield chunk
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()
        await stderr_task


async def _drain_stream(stream: asyncio.StreamReader | None) -> None:
    if stream is None:
        return
    while await stream.read(4096):
        pass


async def _select_live_stream(
    stream_urls: tuple[str, ...],
    client_factory: ClientFactory,
) -> str:
    last_error = "no live stream candidates configured"
    async with client_factory() as client:
        for url in stream_urls:
            try:
                async with client.stream("GET", url) as response:
                    if response.status_code < 400:
                        return url
                    last_error = f"{url} returned HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                last_error = f"{url} failed: {type(exc).__name__}"
    raise HTTPException(status_code=502, detail=last_error)


async def _preset_from_available_stream(
    stream_urls: tuple[str, ...],
    client_factory: ClientFactory,
) -> ChannelPreset | None:
    try:
        stream_url = await _select_live_stream(stream_urls, client_factory)
    except HTTPException:
        return None
    return _preset_for_stream_url(stream_url)


async def _preset_from_receiver_status(
    settings: ProxySettings,
    client_factory: ClientFactory,
) -> ChannelPreset | None:
    async with client_factory() as client:
        try:
            response = await client.get(settings.receiver_status_url, timeout=2)
        except httpx.HTTPError:
            return None
    if response.status_code >= 400:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None

    channel = str(payload.get("channel") or "")
    frequency_hz = _int_or_none(payload.get("frequencyHz"))
    label = str(payload.get("label") or "")
    for preset in DEFAULT_CHANNELS:
        if channel == preset.channel or frequency_hz == preset.frequency_hz:
            return preset
    if channel and frequency_hz and label:
        return ChannelPreset(
            id=f"receiver_{channel.lower()}",
            channel=channel,
            label=label,
            frequency_hz=frequency_hz,
            description="Current receiver slot.",
        )
    return None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _proxy_private_api(
    request: Request,
    path: str,
    settings: ProxySettings,
    client_factory: ClientFactory,
) -> Response:
    target_url = f"{settings.private_api_url.rstrip('/')}{path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"
    async with client_factory() as client:
        upstream = await client.request(
            request.method,
            target_url,
            content=await request.body(),
            headers={},
        )
    response_headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() in {"cache-control", "content-type"}
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


async def _run_retuner(
    retuner: Retuner,
    preset: ChannelPreset,
    settings: ProxySettings,
) -> RetuneResult:
    done = threading.Event()
    result: RetuneResult | None = None
    error: BaseException | None = None

    def run() -> None:
        nonlocal error, result
        try:
            result = retuner(preset, settings)
        except BaseException as exc:  # noqa: BLE001 - propagate operator command failures unchanged.
            error = exc
        else:
            error = None
        finally:
            done.set()

    threading.Thread(target=run, name="talkingboats-retuner", daemon=True).start()
    while not done.is_set():
        await asyncio.sleep(0.05)
    if error is not None:
        raise error
    if result is None:
        raise RuntimeError("retune finished without a result")
    return result


def _default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0),
        follow_redirects=False,
    )


def _env_channel_stream_urls(name: str) -> dict[str, tuple[str, ...]]:
    value = os.getenv(name)
    if not value:
        return {}
    channels: dict[str, tuple[str, ...]] = {}
    for entry in value.split(";"):
        channel, separator, urls = entry.partition("=")
        channel = channel.strip().upper()
        if not separator or not channel:
            continue
        stream_urls = tuple(url.strip() for url in urls.split(",") if url.strip())
        if stream_urls:
            channels[channel] = _dedupe(stream_urls)
    return channels


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen = set()
    deduped = []
    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return tuple(deduped)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Talking Boats tailnet radio proxy.")
    parser.add_argument("--host", default=os.environ.get("TALKINGBOATS_PROXY_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("TALKINGBOATS_PROXY_PORT", "8095")),
    )
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
