from __future__ import annotations

import argparse
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path as FilePath
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Response, status
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from talkingboats.asr_feedback import (
    DEFAULT_BASE_MODEL,
    DEFAULT_MIN_CORRECTIONS,
    DEFAULT_OUTPUT_DIR,
    has_new_training_corrections,
)
from talkingboats.channel_metadata import channel_label, public_monitored_channel_labels
from talkingboats.clip_search import (
    SearchIndexUnavailable,
    read_search_index,
)
from talkingboats.clip_search import (
    search_clips as search_index_clips,
)
from talkingboats.clip_transcriber import UploadedClipStore
from talkingboats.config import Settings
from talkingboats.durable_events import (
    DurableEventStore,
    DynamoDurableEventStore,
    NullDurableEventStore,
)
from talkingboats.dynamo_clip_store import DynamoClipStoreConfig, DynamoUploadedClipStore
from talkingboats.lexical_analysis import (
    read_cached_lexical_analysis,
    read_published_lexical_analysis,
)
from talkingboats.schemas import (
    ClipPresignRequest,
    ClipPresignResponse,
    LiveChannelResponse,
    LiveChannelsResponse,
    PlaybackUrlRequest,
    PlaybackUrlResponse,
    TranscriptCorrectionRequest,
    TranscriptCorrectionResponse,
)
from talkingboats.security import require_token
from talkingboats.storage import S3AudioStorage


async def get_settings() -> Settings:
    return Settings.from_env()


async def get_storage(settings: Annotated[Settings, Depends(get_settings)]) -> S3AudioStorage:
    return S3AudioStorage(settings)


async def get_durable_event_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DurableEventStore:
    if not settings.durable_events_table:
        return NullDurableEventStore()
    return DynamoDurableEventStore(
        table_name=settings.durable_events_table,
        aws_region=settings.aws_region,
        environment=settings.durable_events_environment,
        required=settings.durable_events_required,
    )


async def get_clip_store(
    settings: Annotated[Settings, Depends(get_settings)],
    event_store: Annotated[DurableEventStore, Depends(get_durable_event_store)],
) -> UploadedClipStore | DynamoUploadedClipStore | None:
    if settings.clip_store_backend == "dynamodb":
        table_name = settings.durable_events_table
        if not table_name:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="DynamoDB clip store table is not configured",
            )
        return DynamoUploadedClipStore(
            DynamoClipStoreConfig(
                table_name=table_name,
                aws_region=settings.aws_region,
                environment=settings.durable_events_environment,
            ),
            event_store=event_store,
        )
    if settings.clip_db_path is None:
        return None
    return UploadedClipStore(settings.clip_db_path, event_store=event_store)


async def require_ingest_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_talkingboats_ingest_token: Annotated[str | None, Header()] = None,
) -> None:
    require_token(
        x_talkingboats_ingest_token,
        settings.ingest_token,
        "TALKINGBOATS_INGEST_TOKEN",
    )


app = FastAPI(
    title="Talking Boats Private API",
    version="0.1.0",
    description="Private ingest, playback, and live-radio proxy for Talking Boats.",
)

SHARED_UI_DIR = FilePath(__file__).resolve().parents[2] / "public-site"
PUBLISHED_LEXICAL_PATH = (
    FilePath(__file__).resolve().parents[2] / "outputs/public-site/analysis/lexical.json"
)
PUBLISHED_SEARCH_INDEX_PATH = (
    FilePath(__file__).resolve().parents[2] / "outputs/public-site/analysis/search_index.json"
)
PUBLIC_EXCLUDED_CHANNELS = ("WX",)
if SHARED_UI_DIR.exists():
    app.mount("/operator", StaticFiles(directory=SHARED_UI_DIR, html=True), name="operator")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
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
    event_store: Annotated[DurableEventStore, Depends(get_durable_event_store)],
    clip_store: Annotated[UploadedClipStore | None, Depends(get_clip_store)],
) -> ClipPresignResponse:
    try:
        key, upload_url = storage.presign_raw_upload(request)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    try:
        event_store.record_clip_event(
            "clip.presigned",
            key=key,
            observed_at=request.started_at,
            idempotency_key=request.idempotency_key,
            payload={
                "bucket": settings.raw_bucket,
                "channel": request.channel,
                "started_at": _format_utc(request.started_at),
                "ended_at": _format_utc(request.ended_at) if request.ended_at else None,
                "duration_seconds": request.duration_seconds,
                "content_type": request.content_type,
                "idempotency_key": request.idempotency_key,
            },
        )
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
    channels: Annotated[list[str] | None, Query()] = None,
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
    selected_channels = _requested_public_channels(channel=channel, channels=channels)
    filtered_clip_count = (
        sum(channel_counts.get(selected_channel, 0) for selected_channel in selected_channels)
        if selected_channels
        else clip_count
    )
    if (channel or channels) and not selected_channels:
        return {
            "clips": [],
            "clip_count": clip_count,
            "filtered_clip_count": 0,
            "limit": limit,
            "offset": offset,
            "channel_counts": channel_counts,
            "channel_labels": public_monitored_channel_labels(channel_counts),
        }
    clips = _recent_playable_clip_page(
        settings=settings,
        storage=storage,
        clip_store=clip_store,
        limit=limit,
        offset=offset,
        channel=channel if not channels else None,
        channels=selected_channels,
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


def _recent_playable_clip_page(
    *,
    settings: Settings,
    storage: S3AudioStorage,
    clip_store: UploadedClipStore,
    limit: int,
    offset: int,
    channel: str | None,
    channels: list[str],
) -> list[dict[str, object]]:
    clips: list[dict[str, object]] = []
    playable_seen = 0
    candidate_offset = 0
    batch_size = max(limit, 50)
    while len(clips) < limit:
        candidates = clip_store.recent_transcribed(
            limit=batch_size,
            offset=candidate_offset,
            channel=channel,
            channels=channels,
            excluded_channels=PUBLIC_EXCLUDED_CHANNELS,
        )
        if not candidates:
            break
        for clip in candidates:
            try:
                if not storage.playback_exists(clip.key):
                    continue
                playback_url = storage.presign_playback(clip.key)
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc
            except ValueError:
                continue
            if playable_seen < offset:
                playable_seen += 1
                continue
            clips.append(
                {
                    "channel": clip.channel,
                    "channel_label": channel_label(clip.channel),
                    "started_at": clip.started_at,
                    "ended_at": clip.ended_at,
                    "duration_seconds": clip.duration_seconds,
                    "content_type": clip.content_type,
                    "transcript": clip.transcript,
                    "transcript_reviewed": clip.transcript_reviewed,
                    "segments": clip.segments,
                    "playback_url": playback_url,
                    "playback_expires_in_seconds": settings.playback_presign_seconds,
                }
            )
            playable_seen += 1
            if len(clips) >= limit:
                break
        candidate_offset += len(candidates)
        if len(candidates) < batch_size:
            break
    return clips


@app.get(
    "/api/clips/playback",
)
async def public_clip_playback_url(
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[S3AudioStorage, Depends(get_storage)],
    clip_store: Annotated[UploadedClipStore | None, Depends(get_clip_store)],
    channel: Annotated[str, Query(min_length=1, max_length=8)],
    started_at: Annotated[str, Query(min_length=1, max_length=64)],
) -> dict[str, object]:
    clip = public_playback_clip(clip_store, channel=channel, started_at=started_at)
    try:
        if not storage.playback_exists(clip.key):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip not found")
        playback_url = storage.presign_playback(clip.key)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip not found") from exc
    return {
        "channel": clip.channel,
        "started_at": clip.started_at,
        "playback_url": playback_url,
        "playback_expires_in_seconds": settings.playback_presign_seconds,
    }


@app.get(
    "/api/clips/audio",
)
async def public_clip_audio(
    storage: Annotated[S3AudioStorage, Depends(get_storage)],
    clip_store: Annotated[UploadedClipStore | None, Depends(get_clip_store)],
    channel: Annotated[str, Query(min_length=1, max_length=8)],
    started_at: Annotated[str, Query(min_length=1, max_length=64)],
) -> StreamingResponse:
    clip = public_playback_clip(clip_store, channel=channel, started_at=started_at)
    try:
        body = storage.open_playback(clip.key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip not found") from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip not found") from exc
    return StreamingResponse(
        iter_playback_body(body),
        media_type=clip.content_type,
        headers={"Cache-Control": "no-store"},
    )


@app.post(
    "/api/clips/corrections",
    response_model=TranscriptCorrectionResponse,
)
async def correct_clip_transcript(
    request: TranscriptCorrectionRequest,
    clip_store: Annotated[UploadedClipStore | None, Depends(get_clip_store)],
) -> TranscriptCorrectionResponse:
    if clip_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="clip store unavailable",
        )
    try:
        correction = clip_store.correct_transcript(
            channel=request.channel,
            started_at=request.started_at,
            corrected_transcript=request.transcript,
            reviewer=request.reviewer,
            note=request.note,
            excluded_channels=PUBLIC_EXCLUDED_CHANNELS,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TranscriptCorrectionResponse(
        status="corrected",
        channel=correction.channel,
        started_at=correction.started_at,
        original_transcript=correction.original_transcript,
        corrected_transcript=correction.corrected_transcript,
        transcript_reviewed=True,
    )


@app.get(
    "/api/clips/corrections/export",
)
async def export_clip_transcript_corrections(
    clip_store: Annotated[UploadedClipStore | None, Depends(get_clip_store)],
) -> Response:
    if clip_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="clip store unavailable",
        )
    lines = [
        json.dumps(_public_training_record(correction), sort_keys=True)
        for correction in clip_store.transcript_corrections_for_training()
    ]
    content = "\n".join(lines)
    if content:
        content += "\n"
    return Response(
        content=content,
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store"},
    )


@app.get(
    "/api/asr-feedback/status",
)
async def asr_feedback_status(
    clip_store: Annotated[UploadedClipStore | None, Depends(get_clip_store)],
) -> dict[str, object]:
    if clip_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="clip store unavailable",
        )
    corrections = clip_store.transcript_corrections_for_training()
    correction_count = len(corrections)
    min_corrections = _env_positive_int(
        "TALKINGBOATS_ASR_FEEDBACK_MIN_CORRECTIONS",
        DEFAULT_MIN_CORRECTIONS,
    )
    output_dir = FilePath(
        os.getenv("TALKINGBOATS_ASR_FEEDBACK_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))
    )
    new_corrections_since_last_train = has_new_training_corrections(output_dir, corrections)
    return {
        "status": "ok",
        "reviewed_correction_count": correction_count,
        "min_corrections": min_corrections,
        "new_corrections_since_last_train": new_corrections_since_last_train,
        "ready_for_training": (
            correction_count >= min_corrections and new_corrections_since_last_train
        ),
        "base_model": os.getenv("TALKINGBOATS_ASR_FEEDBACK_BASE_MODEL", DEFAULT_BASE_MODEL),
        "nightly_schedule": "03:00 America/Los_Angeles",
        "export_url": "/api/clips/corrections/export",
        "training_status": _read_public_asr_feedback_status(),
    }


def public_playback_clip(
    clip_store: UploadedClipStore | None,
    *,
    channel: str,
    started_at: str,
):
    if clip_store is None or channel.upper() in PUBLIC_EXCLUDED_CHANNELS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip not found")
    clip = clip_store.transcribed_clip_for_public_playback(
        channel=channel,
        started_at=started_at,
        excluded_channels=PUBLIC_EXCLUDED_CHANNELS,
    )
    if clip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip not found")
    return clip


def _public_training_record(correction: dict[str, object]) -> dict[str, object]:
    channel = str(correction["channel"])
    started_at = str(correction["started_at"])
    return {
        "audio_url": "/api/clips/audio?"
        + urlencode({"channel": channel, "started_at": started_at}),
        "channel": channel,
        "started_at": started_at,
        "duration_seconds": correction["duration_seconds"],
        "content_type": correction["content_type"],
        "original_text": correction["original_transcript"],
        "text": correction["corrected_transcript"],
        "reviewer": correction["reviewer"],
        "note": correction["note"],
    }


def _read_public_asr_feedback_status() -> dict[str, object] | None:
    output_dir = FilePath(
        os.getenv("TALKINGBOATS_ASR_FEEDBACK_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))
    )
    status_path = output_dir / "training_status.json"
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return {"status": "unreadable"}
    if not isinstance(payload, dict):
        return {"status": "unreadable"}
    allowed_keys = {
        "status",
        "reason",
        "correction_count",
        "min_corrections",
        "last_trained_at",
        "generated_at",
    }
    return {key: value for key, value in payload.items() if key in allowed_keys}


def _env_positive_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def iter_playback_body(body: Any):
    try:
        for chunk in body.iter_chunks(chunk_size=64 * 1024):
            if chunk:
                yield chunk
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()


@app.get(
    "/api/analysis/lexical",
)
async def lexical_analysis(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    try:
        if settings.clip_store_backend == "dynamodb":
            return read_published_lexical_analysis(PUBLISHED_LEXICAL_PATH)
        return read_cached_lexical_analysis(settings.clip_db_path)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/clips/search",
)
async def clip_search(
    settings: Annotated[Settings, Depends(get_settings)],
    q: Annotated[str, Query(min_length=1, max_length=240)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    recency: Annotated[str, Query(min_length=1, max_length=8)] = "7d",
) -> dict[str, object]:
    index_path = _search_index_path(settings)
    try:
        return search_index_clips(
            read_search_index(index_path),
            query=q,
            limit=limit,
            recency=recency,
        )
    except SearchIndexUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="clip search index is not ready",
        ) from exc
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"clip search embedding model is unavailable: {exc.name or type(exc).__name__}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _search_index_path(settings: Settings) -> FilePath:
    if settings.clip_store_backend == "dynamodb":
        return PUBLISHED_SEARCH_INDEX_PATH
    return settings.public_site_dir / "analysis/search_index.json"


@app.post(
    "/api/clips/playback-url",
    response_model=PlaybackUrlResponse,
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


@app.get("/api/live/{channel}/stream")
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


def _requested_public_channels(
    *,
    channel: str | None,
    channels: list[str] | None,
) -> list[str]:
    excluded = {excluded_channel.upper() for excluded_channel in PUBLIC_EXCLUDED_CHANNELS}
    requested: list[str] = []
    for value in [channel, *(channels or [])]:
        if value is None:
            continue
        for part in value.split(","):
            normalized = part.strip()
            if normalized and normalized.upper() not in excluded and normalized not in requested:
                requested.append(normalized)
    return requested


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Talking Boats private API.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8034)
    args = parser.parse_args()
    uvicorn.run("talkingboats.api:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
