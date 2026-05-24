from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

CLIP_CONSOLE_DIR = Path(__file__).resolve().parents[2] / "private-ui"
NO_STORE_PATHS = frozenset(
    ("/", "/index.html", "/app.js", "/main.js", "/styles.css", "/config.js")
)


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
        id="noaa_seattle",
        channel="WX",
        label="NOAA Weather 162.550",
        frequency_hz=162_550_000,
        description="Continuous Seattle-area weather broadcast.",
    ),
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


@dataclass(frozen=True)
class ProxySettings:
    stream_url: str = "http://192.168.1.114:8000/talkingboats-live.mp3"
    transcript_url: str = "http://127.0.0.1:8055/api/live-transcript"
    private_api_url: str = "http://192.168.1.247:8034"
    active_channel_id: str = "noaa_seattle"
    retune_ssh_target: str = "talkingboats-pi"
    pi_env_path: str = "/etc/talkingboats/live-radio.env"
    pi_web_config_path: str = "/opt/talkingboats/live-radio/config.js"
    restart_transcriber_service: bool = True
    enable_debug_endpoints: bool = False

    @classmethod
    def from_env(cls) -> ProxySettings:
        return cls(
            stream_url=os.environ.get(
                "TALKINGBOATS_PROXY_STREAM_URL",
                cls.stream_url,
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
            restart_transcriber_service=_env_bool("TALKINGBOATS_PROXY_RESTART_TRANSCRIBER", True),
            enable_debug_endpoints=_env_bool("TALKINGBOATS_PROXY_ENABLE_DEBUG_ENDPOINTS", False),
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
    active_channel_id = settings.active_channel_id
    retune_lock = asyncio.Lock()
    app = FastAPI(title="Talking Boats Tailnet Radio Proxy", version="0.1.0")

    @app.middleware("http")
    async def no_store_shell_assets(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if request.url.path in NO_STORE_PATHS:
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/config.js")
    def config_js() -> Response:
        active_channel = _find_channel(active_channel_id)
        config = {
            "activeChannelId": active_channel.id,
            "channels": [channel.to_config() for channel in DEFAULT_CHANNELS],
            "frequencyMhz": active_channel.frequency_mhz,
            "label": active_channel.label,
            "mountPath": "/talkingboats-live.mp3",
            "retuneUrl": "/api/channel",
            "streamPort": 0,
            "streamUrl": "/talkingboats-live.mp3",
            "transcriptUrl": "/api/live-transcript",
        }
        body = "window.TALKINGBOATS_LIVE_RADIO = \n" + json.dumps(
            config,
            indent=2,
            sort_keys=True,
        )
        return Response(f"{body}\n;\n", media_type="application/javascript")

    @app.get("/api/clips/recent")
    async def recent_clips(request: Request) -> Response:
        return await _proxy_private_api(request, "/api/clips/recent", settings, client_factory)

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
            nonlocal active_channel_id
            if retune_lock.locked():
                raise HTTPException(status_code=409, detail="retune already in progress")
            preset = _find_channel(request.id)
            async with retune_lock:
                try:
                    result = await asyncio.to_thread(retuner, preset, settings)
                except subprocess.CalledProcessError as exc:
                    detail = (exc.stderr or exc.stdout or str(exc)).strip()
                    raise HTTPException(status_code=502, detail=detail or "retune failed") from exc
                except subprocess.TimeoutExpired as exc:
                    raise HTTPException(status_code=504, detail="retune timed out") from exc
                active_channel_id = preset.id
            return {
                "activeChannelId": preset.id,
                "channel": preset.channel,
                "label": preset.label,
                "frequencyMhz": preset.frequency_mhz,
                "restartedTranscriber": result.restarted_transcriber,
            }

        @app.get("/talkingboats-live.mp3")
        async def live_stream() -> StreamingResponse:
            return StreamingResponse(
                _iter_upstream_audio(settings.stream_url, client_factory),
                media_type="audio/mpeg",
                headers={"Cache-Control": "no-store"},
            )

    app.mount("/", StaticFiles(directory=CLIP_CONSOLE_DIR, html=True), name="clip-console")
    return app


def _find_channel(channel_id: str) -> ChannelPreset:
    for channel in DEFAULT_CHANNELS:
        if channel.id == channel_id:
            return channel
    raise HTTPException(status_code=404, detail="unknown channel")


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
        "web_config_path": settings.pi_web_config_path,
        "updates": {
            "TALKINGBOATS_LIVE_CHANNEL": preset.channel,
            "TALKINGBOATS_LIVE_FREQUENCY_HZ": str(preset.frequency_hz),
            "TALKINGBOATS_LIVE_LABEL": preset.label,
            "TALKINGBOATS_LIVE_SQUELCH": str(preset.squelch),
            "TALKINGBOATS_AUDIO_FILTER_ENABLED": str(preset.audio_filter_enabled).lower(),
        },
        "web_config": {
            "frequencyMhz": preset.frequency_mhz,
            "label": preset.label,
            "mountPath": "/talkingboats-live.mp3",
            "streamPort": 8000,
            "transcriptUrl": "http://192.168.1.247:8055/api/live-transcript",
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
config_path = Path(payload["web_config_path"])
config_path.write_text(
    "window.TALKINGBOATS_LIVE_RADIO = \\n"
    + json.dumps(payload["web_config"], indent=2, sort_keys=True)
    + "\\n;\\n"
)
config_path.chmod(0o644)
subprocess.run(["systemctl", "restart", "talkingboats-edge-live-radio-stream.service"], check=True)
subprocess.run(["systemctl", "restart", "talkingboats-live-radio-web.service"], check=True)
"""


async def _iter_upstream_audio(
    stream_url: str,
    client_factory: ClientFactory,
) -> AsyncIterator[bytes]:
    async with client_factory() as client, client.stream("GET", stream_url) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            if chunk:
                yield chunk


async def _proxy_private_api(
    request: Request,
    path: str,
    settings: ProxySettings,
    client_factory: ClientFactory,
) -> Response:
    target_url = f"{settings.private_api_url.rstrip('/')}{path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"
    request_headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() in {"content-type", "cookie", "x-talkingboats-operator-token"}
    }
    async with client_factory() as client:
        upstream = await client.request(
            request.method,
            target_url,
            content=await request.body(),
            headers=request_headers,
        )
    response_headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() in {"cache-control", "content-type", "set-cookie"}
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


def _default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0),
        follow_redirects=False,
    )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


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
