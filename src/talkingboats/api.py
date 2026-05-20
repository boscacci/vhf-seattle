from __future__ import annotations

import argparse
from collections.abc import AsyncIterator
from pathlib import Path as FilePath
from typing import Annotated

import httpx
import uvicorn
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Path, Response, status
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from talkingboats.config import Settings
from talkingboats.schemas import (
    ClipPresignRequest,
    ClipPresignResponse,
    LiveChannelResponse,
    LiveChannelsResponse,
    PlaybackUrlRequest,
    PlaybackUrlResponse,
)
from talkingboats.security import require_token
from talkingboats.storage import S3AudioStorage


def get_settings() -> Settings:
    return Settings.from_env()


def get_storage(settings: Annotated[Settings, Depends(get_settings)]) -> S3AudioStorage:
    return S3AudioStorage(settings)


def require_ingest_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_talkingboats_ingest_token: Annotated[str | None, Header()] = None,
) -> None:
    require_token(
        x_talkingboats_ingest_token,
        settings.ingest_token,
        "TALKINGBOATS_INGEST_TOKEN",
    )


def require_operator_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_talkingboats_operator_token: Annotated[str | None, Header()] = None,
    talkingboats_operator_token: Annotated[str | None, Cookie()] = None,
) -> None:
    require_token(
        x_talkingboats_operator_token or talkingboats_operator_token,
        settings.operator_token,
        "TALKINGBOATS_OPERATOR_TOKEN",
    )


app = FastAPI(
    title="Talking Boats Private API",
    version="0.1.0",
    description="Private ingest, playback, and live-radio proxy for Talking Boats.",
)

PRIVATE_UI_DIR = FilePath(__file__).resolve().parents[2] / "private-ui"
if PRIVATE_UI_DIR.exists():
    app.mount("/operator", StaticFiles(directory=PRIVATE_UI_DIR, html=True), name="operator")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/operator/session",
)
def create_operator_session(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    x_talkingboats_operator_token: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    require_token(
        x_talkingboats_operator_token,
        settings.operator_token,
        "TALKINGBOATS_OPERATOR_TOKEN",
    )
    response.set_cookie(
        "talkingboats_operator_token",
        x_talkingboats_operator_token or "",
        httponly=True,
        samesite="strict",
        max_age=3600,
    )
    return {"status": "ok"}


@app.post("/api/operator/session/logout")
def clear_operator_session(response: Response) -> dict[str, str]:
    response.delete_cookie("talkingboats_operator_token")
    return {"status": "ok"}


@app.post(
    "/api/ingest/clips/presign",
    response_model=ClipPresignResponse,
    dependencies=[Depends(require_ingest_token)],
)
def presign_clip_upload(
    request: ClipPresignRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[S3AudioStorage, Depends(get_storage)],
) -> ClipPresignResponse:
    try:
        key, upload_url = storage.presign_raw_upload(request)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return ClipPresignResponse(
        bucket=settings.raw_bucket,
        key=key,
        upload_url=upload_url,
        expires_in_seconds=settings.raw_presign_seconds,
        required_headers={"Content-Type": request.content_type},
    )


@app.post(
    "/api/clips/playback-url",
    response_model=PlaybackUrlResponse,
    dependencies=[Depends(require_operator_token)],
)
def presign_clip_playback(
    request: PlaybackUrlRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[S3AudioStorage, Depends(get_storage)],
) -> PlaybackUrlResponse:
    try:
        playback_url = storage.presign_playback(request.key)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PlaybackUrlResponse(
        playback_url=playback_url,
        expires_in_seconds=settings.playback_presign_seconds,
    )


@app.get(
    "/api/live/channels",
    response_model=LiveChannelsResponse,
    dependencies=[Depends(require_operator_token)],
)
def list_live_channels(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LiveChannelsResponse:
    return LiveChannelsResponse(
        channels=[
            LiveChannelResponse(
                channel=channel.channel,
                label=channel.label,
                frequency_mhz=channel.frequency_mhz,
                enabled=channel.enabled,
            )
            for channel in settings.live_channels.values()
        ]
    )


@app.get("/api/live/{channel}/stream", dependencies=[Depends(require_operator_token)])
async def live_channel_stream(
    settings: Annotated[Settings, Depends(get_settings)],
    channel: Annotated[str, Path(pattern=r"^(68|14)$")],
) -> StreamingResponse:
    live_channel = settings.live_channels[channel]
    if not live_channel.stream_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="live stream not configured",
        )

    return StreamingResponse(
        _iter_upstream_audio(live_channel.stream_url),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


async def _iter_upstream_audio(url: str) -> AsyncIterator[bytes]:
    timeout = httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
    ) as client, client.stream("GET", url) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            if chunk:
                yield chunk


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Talking Boats private API.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8034)
    args = parser.parse_args()
    uvicorn.run("talkingboats.api:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
