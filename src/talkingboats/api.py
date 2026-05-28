from __future__ import annotations

import argparse
from collections.abc import AsyncIterator
from pathlib import Path as FilePath
from typing import Annotated

import httpx
import uvicorn
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Path, Query, Response, status
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from talkingboats.channel_metadata import channel_label, public_monitored_channel_labels
from talkingboats.clip_transcriber import UploadedClipStore
from talkingboats.config import Settings
from talkingboats.lexical_analysis import read_cached_lexical_analysis
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


async def get_settings() -> Settings:
    return Settings.from_env()


async def get_storage(settings: Annotated[Settings, Depends(get_settings)]) -> S3AudioStorage:
    return S3AudioStorage(settings)


async def get_clip_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> UploadedClipStore | None:
    if settings.clip_db_path is None:
        return None
    return UploadedClipStore(settings.clip_db_path)


async def require_ingest_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_talkingboats_ingest_token: Annotated[str | None, Header()] = None,
) -> None:
    require_token(
        x_talkingboats_ingest_token,
        settings.ingest_token,
        "TALKINGBOATS_INGEST_TOKEN",
    )


async def require_operator_token(
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

SHARED_UI_DIR = FilePath(__file__).resolve().parents[2] / "public-site"
PUBLIC_EXCLUDED_CHANNELS = ("WX",)
if SHARED_UI_DIR.exists():
    app.mount("/operator", StaticFiles(directory=SHARED_UI_DIR, html=True), name="operator")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/operator/session",
)
async def create_operator_session(
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
async def clear_operator_session(response: Response) -> dict[str, str]:
    response.delete_cookie("talkingboats_operator_token")
    return {"status": "ok"}


@app.post(
    "/api/ingest/clips/presign",
    response_model=ClipPresignResponse,
    dependencies=[Depends(require_ingest_token)],
)
async def presign_clip_upload(
    request: ClipPresignRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[S3AudioStorage, Depends(get_storage)],
    clip_store: Annotated[UploadedClipStore | None, Depends(get_clip_store)],
) -> ClipPresignResponse:
    try:
        key, upload_url = storage.presign_raw_upload(request)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if clip_store is not None:
        clip_store.record_presigned_upload(key=key, request=request)
    return ClipPresignResponse(
        bucket=settings.raw_bucket,
        key=key,
        upload_url=upload_url,
        expires_in_seconds=settings.raw_presign_seconds,
        required_headers={"Content-Type": request.content_type},
    )


@app.get(
    "/api/ingest/clips/stats",
    dependencies=[Depends(require_operator_token)],
)
async def ingest_clip_stats(
    clip_store: Annotated[UploadedClipStore | None, Depends(get_clip_store)],
) -> dict[str, object]:
    if clip_store is None:
        return {"persisted": False, "counts": {}, "recent": []}
    return {"persisted": True, **clip_store.stats()}


@app.get(
    "/api/clips/recent",
)
async def recent_clips(
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[S3AudioStorage, Depends(get_storage)],
    clip_store: Annotated[UploadedClipStore | None, Depends(get_clip_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
    channel: Annotated[str | None, Query(min_length=1, max_length=8)] = None,
) -> dict[str, object]:
    if clip_store is None:
        return {
            "clips": [],
            "clip_count": 0,
            "filtered_clip_count": 0,
            "limit": limit,
            "offset": offset,
            "channel_counts": {},
            "channel_labels": public_monitored_channel_labels(),
        }
    channel_counts = clip_store.transcribed_channel_counts(
        excluded_channels=PUBLIC_EXCLUDED_CHANNELS,
    )
    clip_count = sum(channel_counts.values())
    filtered_clip_count = channel_counts.get(channel, clip_count) if channel else clip_count
    if channel and channel.upper() in PUBLIC_EXCLUDED_CHANNELS:
        return {
            "clips": [],
            "clip_count": clip_count,
            "filtered_clip_count": 0,
            "limit": limit,
            "offset": offset,
            "channel_counts": channel_counts,
            "channel_labels": public_monitored_channel_labels(channel_counts),
        }
    clips = []
    for clip in clip_store.recent_transcribed(
        limit=limit,
        offset=offset,
        channel=channel,
        excluded_channels=PUBLIC_EXCLUDED_CHANNELS,
    ):
        try:
            playback_url = storage.presign_playback(clip.key)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        clips.append(
            {
                "channel": clip.channel,
                "channel_label": channel_label(clip.channel),
                "started_at": clip.started_at,
                "ended_at": clip.ended_at,
                "duration_seconds": clip.duration_seconds,
                "content_type": clip.content_type,
                "transcript": clip.transcript,
                "segments": clip.segments,
                "playback_url": playback_url,
                "playback_expires_in_seconds": settings.playback_presign_seconds,
            }
        )
    return {
        "clips": clips,
        "clip_count": clip_count,
        "filtered_clip_count": filtered_clip_count,
        "limit": limit,
        "offset": offset,
        "channel_counts": channel_counts,
        "channel_labels": public_monitored_channel_labels(channel_counts),
    }


@app.get(
    "/api/analysis/lexical",
)
async def lexical_analysis(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    try:
        return read_cached_lexical_analysis(settings.clip_db_path)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/clips/playback-url",
    response_model=PlaybackUrlResponse,
    dependencies=[Depends(require_operator_token)],
)
async def presign_clip_playback(
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
async def list_live_channels(
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
