from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import logging
import time
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from pathlib import Path as FilePath
from typing import Annotated, Any, Literal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, status
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from talkingboats.channel_metadata import channel_label, public_monitored_channel_labels
from talkingboats.clip_quality import (
    QualityFilter,
    is_quality_visible,
    normalize_quality_filter,
)
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
    ClipFeatureRequest,
    ClipFeatureResponse,
    ClipPresignRequest,
    ClipPresignResponse,
    LiveChannelResponse,
    LiveChannelsResponse,
    PlaybackUrlRequest,
    PlaybackUrlResponse,
)
from talkingboats.security import require_token
from talkingboats.storage import S3AudioStorage

logger = logging.getLogger("uvicorn.error")


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
                aggregate_counts_enabled=settings.clip_count_aggregates_enabled,
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
CLIP_NAVIGATION_TIMEZONE_NAME = "America/Los_Angeles"
CLIP_NAVIGATION_TIMEZONE = ZoneInfo(CLIP_NAVIGATION_TIMEZONE_NAME)
if SHARED_UI_DIR.exists():
    app.mount("/operator", StaticFiles(directory=SHARED_UI_DIR, html=True), name="operator")


def _published_playable_clip_summary(
    public_site_dir: FilePath,
    *,
    featured_only: bool = False,
) -> dict[str, object]:
    manifest_path = public_site_dir / "public_manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "playable_clip_count": 0,
            "playable_channel_counts": {},
            "latest_playable_started_at": None,
        }
    clips = []
    for clip in payload.get("clips", []):
        if not isinstance(clip, Mapping):
            continue
        if featured_only and not clip.get("featured"):
            continue
        if not clip.get("audio_public_filename"):
            continue
        channel = str(clip.get("channel") or "")
        if channel.upper() in PUBLIC_EXCLUDED_CHANNELS:
            continue
        clips.append(clip)
    channel_counts: dict[str, int] = {}
    started_values: list[str] = []
    for clip in clips:
        channel = str(clip.get("channel") or "?")
        channel_counts[channel] = channel_counts.get(channel, 0) + 1
        started_at = str(clip.get("started_at") or "")
        if started_at:
            started_values.append(started_at)
    return {
        "playable_clip_count": len(clips),
        "playable_channel_counts": dict(sorted(channel_counts.items(), key=lambda item: item[0])),
        "latest_playable_started_at": max(started_values) if started_values else None,
    }


def _received_clip_count(
    clip_store: UploadedClipStore | DynamoUploadedClipStore | None,
    *,
    fallback: int = 0,
) -> int:
    if clip_store is None:
        return fallback
    try:
        non_transcribed_count = int(clip_store.non_transcribed_clip_count())
    except (AttributeError, RuntimeError, TypeError, ValueError):
        pass
    else:
        return fallback + non_transcribed_count
    try:
        return int(clip_store.received_clip_count())
    except (AttributeError, RuntimeError, TypeError):
        pass
    try:
        stats = clip_store.stats()
    except (AttributeError, RuntimeError, TypeError):
        return fallback
    counts = stats.get("counts", {})
    if not isinstance(counts, Mapping):
        return fallback
    return sum(int(count or 0) for count in counts.values())


def _clip_count_snapshot(clip_store: object) -> Any | None:
    try:
        return clip_store.clip_count_snapshot()  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None


def _aggregate_counts_required(clip_store: object) -> bool:
    return bool(getattr(clip_store, "aggregate_counts_enabled", False))


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
    clip_store: Annotated[
        UploadedClipStore | DynamoUploadedClipStore | None,
        Depends(get_clip_store),
    ],
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
                "audio_profile": request.audio_profile,
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
        required_headers={
            "Content-Type": request.content_type,
            "x-amz-tagging": "talkingboats-featured=false",
        },
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
def recent_clips(
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[S3AudioStorage, Depends(get_storage)],
    clip_store: Annotated[
        UploadedClipStore | DynamoUploadedClipStore | None,
        Depends(get_clip_store),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
    page: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
    around: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    channel: Annotated[str | None, Query(min_length=1, max_length=8)] = None,
    channels: Annotated[list[str] | None, Query()] = None,
    featured: bool = False,
    quality: Annotated[QualityFilter, Query()] = "visible",
    include_playback_url: bool = True,
    verify_playback_exists: bool = True,
    include_counts: bool = True,
    exclude_channels: Annotated[list[str] | None, Query()] = None,
    sort: Annotated[Literal["newest", "oldest"], Query()] = "newest",
) -> dict[str, object]:
    quality = normalize_quality_filter(quality)
    around_utc = _clip_navigation_utc(around) if around else None
    if cursor is not None and (offset != 0 or page is not None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cursor cannot be combined with offset or page",
        )
    effective_offset = (page - 1) * limit if page is not None else offset
    effective_page = page if page is not None else (effective_offset // limit) + 1
    requested_excluded_channels = _requested_public_excluded_channels(exclude_channels)
    selected_channels = _requested_public_channels(
        channel=channel,
        channels=channels,
        excluded_channels=requested_excluded_channels,
    )
    cursor_binding = _clip_cursor_binding(
        channels=selected_channels,
        excluded_channels=requested_excluded_channels,
        featured=featured,
        quality=quality,
        sort=sort,
        around=around_utc,
    )
    cursor_anchor = _decode_clip_cursor(cursor, binding=cursor_binding) if cursor else None
    counts_deferred = not include_counts
    if include_counts:
        playable_summary = _published_playable_clip_summary(
            settings.public_site_dir,
            featured_only=featured,
        )
        playable_channel_counts = dict(playable_summary["playable_channel_counts"])
        playable_clip_count = int(playable_summary["playable_clip_count"])
        filtered_playable_clip_count = (
            sum(
                playable_channel_counts.get(selected_channel, 0)
                for selected_channel in selected_channels
            )
            if selected_channels
            else playable_clip_count
        )
    else:
        playable_summary = {"latest_playable_started_at": None}
        playable_channel_counts = {}
        playable_clip_count = 0
        filtered_playable_clip_count = 0
    if clip_store is None:
        return {
            "clips": [],
            "clip_count": 0,
            "received_clip_count": 0,
            "analyzed_clip_count": 0,
            "filtered_clip_count": 0,
            "playable_clip_count": playable_clip_count,
            "filtered_playable_clip_count": filtered_playable_clip_count,
            "playable_channel_counts": playable_channel_counts,
            "latest_playable_started_at": playable_summary["latest_playable_started_at"],
            "limit": limit,
            "offset": effective_offset,
            "page": effective_page,
            "featured": featured,
            "quality": quality,
            "channel_counts": {},
            "channel_labels": public_monitored_channel_labels(),
            "next_cursor": None,
            "counts_deferred": counts_deferred,
            **_clip_navigation_metadata(around_utc),
        }
    filtered_collection = featured or quality != "visible"
    if include_counts:
        snapshot = _clip_count_snapshot(clip_store)
        if snapshot is not None:
            all_channel_counts = snapshot.counts_for(
                excluded_channels=requested_excluded_channels,
                quality=quality,
            )
            channel_counts = (
                snapshot.counts_for(
                    excluded_channels=requested_excluded_channels,
                    featured_only=featured,
                    quality=quality,
                )
                if filtered_collection
                else all_channel_counts
            )
            clip_count = sum(all_channel_counts.values())
            received_clip_count = clip_count + snapshot.non_transcribed_count()
            analyzed_clip_count = clip_count
            filtered_clip_count = (
                sum(
                    channel_counts.get(selected_channel, 0)
                    for selected_channel in selected_channels
                )
                if selected_channels
                else sum(channel_counts.values())
            )
            if not selected_channels and requested_excluded_channels != PUBLIC_EXCLUDED_CHANNELS:
                playable_channel_counts = dict(channel_counts)
                playable_clip_count = sum(playable_channel_counts.values())
                filtered_playable_clip_count = filtered_clip_count
            if filtered_collection:
                playable_channel_counts = dict(channel_counts)
                playable_clip_count = sum(playable_channel_counts.values())
                filtered_playable_clip_count = filtered_clip_count
        elif _aggregate_counts_required(clip_store):
            # The rollout flag deliberately turns scans off.  A missing or
            # invalid snapshot must be visible to callers rather than quietly
            # recreating the high-cost query path.
            all_channel_counts = {}
            channel_counts = {}
            clip_count = 0
            received_clip_count = 0
            analyzed_clip_count = 0
            filtered_clip_count = 0
            counts_deferred = True
        else:
            all_channel_counts = clip_store.transcribed_channel_counts(
                excluded_channels=requested_excluded_channels,
                quality=quality,
            )
            channel_counts = (
                clip_store.transcribed_channel_counts(
                    excluded_channels=requested_excluded_channels,
                    featured_only=featured,
                    quality=quality,
                )
                if filtered_collection
                else all_channel_counts
            )
            clip_count = sum(all_channel_counts.values())
            received_clip_count = _received_clip_count(clip_store, fallback=clip_count)
            analyzed_clip_count = clip_count
            filtered_clip_count = (
                sum(
                    channel_counts.get(selected_channel, 0)
                    for selected_channel in selected_channels
                )
                if selected_channels
                else sum(channel_counts.values())
            )
            if not selected_channels and requested_excluded_channels != PUBLIC_EXCLUDED_CHANNELS:
                playable_channel_counts = dict(channel_counts)
                playable_clip_count = sum(playable_channel_counts.values())
                filtered_playable_clip_count = filtered_clip_count
            if filtered_collection:
                playable_channel_counts = dict(channel_counts)
                playable_clip_count = sum(playable_channel_counts.values())
                filtered_playable_clip_count = filtered_clip_count
    else:
        channel_counts = {}
        clip_count = 0
        received_clip_count = 0
        analyzed_clip_count = 0
        filtered_clip_count = 0
    if (channel or channels) and not selected_channels:
        return {
            "clips": [],
            "clip_count": clip_count,
            "received_clip_count": received_clip_count,
            "analyzed_clip_count": analyzed_clip_count,
            "filtered_clip_count": 0,
            "playable_clip_count": playable_clip_count,
            "filtered_playable_clip_count": 0,
            "playable_channel_counts": playable_channel_counts,
            "latest_playable_started_at": playable_summary["latest_playable_started_at"],
            "limit": limit,
            "offset": effective_offset,
            "page": effective_page,
            "featured": featured,
            "quality": quality,
            "channel_counts": channel_counts,
            "channel_labels": public_monitored_channel_labels(channel_counts),
            "next_cursor": None,
            "counts_deferred": counts_deferred,
            **_clip_navigation_metadata(around_utc),
        }
    clips, live_latest_playable_started_at, next_anchor = _recent_playable_clip_page(
        settings=settings,
        storage=storage,
        clip_store=clip_store,
        limit=limit,
        offset=effective_offset,
        page=page,
        channel=channel if not channels else None,
        channels=selected_channels,
        excluded_channels=requested_excluded_channels,
        featured_only=featured,
        quality=quality,
        include_playback_url=include_playback_url,
        verify_playback_exists=verify_playback_exists,
        sort=sort,
        cursor_anchor=cursor_anchor,
        starting_at=around_utc,
    )
    next_cursor = (
        _encode_clip_cursor(anchor=next_anchor, binding=cursor_binding)
        if next_anchor is not None
        else None
    )
    return {
        "clips": clips,
        "clip_count": clip_count,
        "received_clip_count": received_clip_count,
        "analyzed_clip_count": analyzed_clip_count,
        "filtered_clip_count": filtered_clip_count,
        "playable_clip_count": playable_clip_count,
        "filtered_playable_clip_count": filtered_playable_clip_count,
        "playable_channel_counts": playable_channel_counts,
        "latest_playable_started_at": (
            live_latest_playable_started_at
            if sort == "newest"
            else playable_summary["latest_playable_started_at"]
        ),
        "limit": limit,
        "offset": effective_offset,
        "page": effective_page,
        "featured": featured,
        "quality": quality,
        "sort": sort,
        "channel_counts": channel_counts,
        "channel_labels": public_monitored_channel_labels(channel_counts),
        "next_cursor": next_cursor,
        "counts_deferred": counts_deferred,
        **_clip_navigation_metadata(around_utc),
    }


def _recent_playable_clip_page(
    *,
    settings: Settings,
    storage: S3AudioStorage,
    clip_store: UploadedClipStore | DynamoUploadedClipStore,
    limit: int,
    offset: int,
    channel: str | None,
    channels: list[str],
    page: int | None = None,
    excluded_channels: tuple[str, ...] = PUBLIC_EXCLUDED_CHANNELS,
    featured_only: bool = False,
    quality: QualityFilter = "visible",
    include_playback_url: bool = True,
    verify_playback_exists: bool = True,
    sort: Literal["newest", "oldest"] = "newest",
    cursor_anchor: tuple[str, str] | None = None,
    starting_at: str | None = None,
) -> tuple[list[dict[str, object]], str | None, tuple[str, str] | None]:
    clips: list[dict[str, object]] = []
    latest_playable_started_at: str | None = None
    playable_seen = 0
    candidate_offset = 0
    indexed_page = (
        page is not None
        and not verify_playback_exists
        and quality != "visible"
    )
    batch_size = limit if indexed_page else max(limit, 50)
    playable_offset = 0 if indexed_page else offset
    target_count = limit + 1
    returned_anchors: list[tuple[str, str]] = []
    cursor_pending = cursor_anchor is not None
    while len(clips) < target_count:
        candidates = clip_store.recent_transcribed(
            limit=batch_size,
            offset=candidate_offset,
            page=page if indexed_page and candidate_offset == 0 else None,
            channel=channel,
            channels=channels,
            excluded_channels=excluded_channels,
            featured_only=featured_only,
            quality=quality,
            sort=sort,
            starting_at=starting_at,
        )
        if not candidates:
            break
        for clip in candidates:
            clip_anchor = (clip.started_at, _clip_cursor_key(clip.key))
            if cursor_pending:
                if clip_anchor == cursor_anchor:
                    cursor_pending = False
                continue
            if quality == "visible" and not is_quality_visible(
                clip.quality_status,
                clip.quality_score,
            ):
                continue
            try:
                if verify_playback_exists and not storage.playback_exists(clip.key):
                    continue
                playback_url = storage.presign_playback(clip.key) if include_playback_url else None
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc
            except ValueError:
                continue
            if latest_playable_started_at is None:
                latest_playable_started_at = clip.started_at
            if playable_seen < playable_offset:
                playable_seen += 1
                continue
            clip_payload = {
                "channel": clip.channel,
                "channel_label": channel_label(clip.channel),
                "started_at": clip.started_at,
                "ended_at": clip.ended_at,
                "duration_seconds": clip.duration_seconds,
                "content_type": clip.content_type,
                "transcript": clip.transcript,
                "quality_status": clip.quality_status,
                "quality_score": clip.quality_score,
                "quality_reason": clip.quality_reason,
                "quality_flags": list(clip.quality_flags),
                "audio_metrics": clip.audio_metrics,
                "featured": clip.featured,
                "featured_at": clip.featured_at,
                "segments": clip.segments,
            }
            if playback_url is not None:
                clip_payload["playback_url"] = playback_url
                clip_payload["playback_expires_in_seconds"] = settings.playback_presign_seconds
            else:
                clip_payload["audio_url"] = _public_clip_audio_url(
                    channel=clip.channel,
                    started_at=clip.started_at,
                )
            clips.append(clip_payload)
            returned_anchors.append(clip_anchor)
            playable_seen += 1
            if len(clips) >= target_count:
                break
        if indexed_page:
            break
        candidate_offset += len(candidates)
        if len(candidates) < batch_size:
            break
    if cursor_pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="clip cursor anchor is no longer available",
        )
    has_more = len(clips) > limit
    visible_clips = clips[:limit]
    next_anchor = returned_anchors[limit - 1] if has_more and limit > 0 else None
    return visible_clips, latest_playable_started_at, next_anchor


def _clip_cursor_binding(
    *,
    channels: list[str],
    excluded_channels: tuple[str, ...],
    featured: bool,
    quality: QualityFilter,
    sort: Literal["newest", "oldest"],
    around: str | None,
) -> str:
    payload = {
        "channels": sorted(channels),
        "excluded_channels": sorted(excluded_channels),
        "featured": featured,
        "quality": quality,
        "sort": sort,
        "around": around,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _encode_clip_cursor(*, anchor: tuple[str, str], binding: str) -> str:
    payload = json.dumps(
        {
            "v": 1,
            "started_at": anchor[0],
            "anchor": anchor[1],
            "binding": binding,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_clip_cursor(value: str, *, binding: str) -> tuple[str, str]:
    try:
        padded = value + ("=" * (-len(value) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (UnicodeEncodeError, binascii.Error, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid clip cursor",
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("v") != 1
        or not isinstance(payload.get("started_at"), str)
        or not isinstance(payload.get("anchor"), str)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid clip cursor",
        )
    if payload.get("binding") != binding:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cursor does not match the requested clip filters",
        )
    return payload["started_at"], payload["anchor"]


def _clip_cursor_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


@app.get(
    "/api/clips/playback",
)
async def public_clip_playback_url(
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[S3AudioStorage, Depends(get_storage)],
    clip_store: Annotated[
        UploadedClipStore | DynamoUploadedClipStore | None,
        Depends(get_clip_store),
    ],
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
    clip_store: Annotated[
        UploadedClipStore | DynamoUploadedClipStore | None,
        Depends(get_clip_store),
    ],
    channel: Annotated[str, Query(min_length=1, max_length=8)],
    started_at: Annotated[str, Query(min_length=1, max_length=64)],
) -> RedirectResponse:
    clip = public_playback_clip(clip_store, channel=channel, started_at=started_at)
    try:
        playback_url = storage.presign_playback(clip.key)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip not found") from exc
    return RedirectResponse(
        playback_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={"Cache-Control": "no-store"},
    )


@app.post(
    "/api/clips/features",
    response_model=ClipFeatureResponse,
)
async def feature_clip(
    request: ClipFeatureRequest,
    storage: Annotated[S3AudioStorage, Depends(get_storage)],
    clip_store: Annotated[
        UploadedClipStore | DynamoUploadedClipStore | None,
        Depends(get_clip_store),
    ],
) -> ClipFeatureResponse:
    if clip_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="clip store unavailable",
        )
    try:
        feature = clip_store.set_clip_featured(
            channel=request.channel,
            started_at=request.started_at,
            featured=request.featured,
            featured_by=request.featured_by,
            note=request.note,
            excluded_channels=PUBLIC_EXCLUDED_CHANNELS,
        )
        storage.tag_raw_clip_featured(feature.key, featured=feature.featured)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return ClipFeatureResponse(
        status="featured" if feature.featured else "unfeatured",
        channel=feature.channel,
        started_at=feature.started_at,
        featured=feature.featured,
    )


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


def _public_clip_audio_url(*, channel: str, started_at: str) -> str:
    return "/api/clips/audio?" + urlencode({"channel": channel, "started_at": started_at})


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _clip_navigation_utc(value: str) -> str:
    try:
        if "T" not in value and " " not in value:
            raise ValueError("time component is required")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="around must be an ISO 8601 date and time",
        ) from exc
    if parsed.tzinfo is None:
        local_wall_time = parsed
        parsed = local_wall_time.replace(tzinfo=CLIP_NAVIGATION_TIMEZONE)
        round_trip = parsed.astimezone(UTC).astimezone(CLIP_NAVIGATION_TIMEZONE)
        if round_trip.replace(tzinfo=None) != local_wall_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="around is not a valid Pacific date and time",
            )
    return _format_utc(parsed.replace(microsecond=0))


def _clip_navigation_metadata(around_utc: str | None) -> dict[str, str]:
    if around_utc is None:
        return {}
    return {
        "around": around_utc,
        "around_timezone": CLIP_NAVIGATION_TIMEZONE_NAME,
    }


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
    started_at = time.monotonic()
    try:
        index = await run_in_threadpool(read_search_index, index_path)
        payload = await run_in_threadpool(
            search_index_clips,
            index,
            query=q,
            limit=limit,
            recency=recency,
        )
        logger.info(
            "event=talkingboats_clip_search status=ok recency=%s limit=%s count=%s "
            "query_length=%s elapsed_ms=%s",
            payload.get("recency"),
            limit,
            payload.get("count"),
            len(q),
            round((time.monotonic() - started_at) * 1000),
        )
        return payload
    except SearchIndexUnavailable as exc:
        logger.warning(
            "event=talkingboats_clip_search status=index_unavailable recency=%s limit=%s "
            "query_length=%s elapsed_ms=%s",
            recency,
            limit,
            len(q),
            round((time.monotonic() - started_at) * 1000),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="clip search index is not ready",
        ) from exc
    except ImportError as exc:
        logger.exception(
            "event=talkingboats_clip_search status=model_unavailable recency=%s limit=%s "
            "query_length=%s elapsed_ms=%s",
            recency,
            limit,
            len(q),
            round((time.monotonic() - started_at) * 1000),
        )
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
    async with (
        httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        ) as client,
        client.stream("GET", url) as response,
    ):
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            if chunk:
                yield chunk


def _requested_public_channels(
    *,
    channel: str | None,
    channels: list[str] | None,
    excluded_channels: tuple[str, ...] = PUBLIC_EXCLUDED_CHANNELS,
) -> list[str]:
    excluded = {excluded_channel.upper() for excluded_channel in excluded_channels}
    requested: list[str] = []
    for value in [channel, *(channels or [])]:
        if value is None:
            continue
        for part in value.split(","):
            normalized = part.strip()
            if normalized and normalized.upper() not in excluded and normalized not in requested:
                requested.append(normalized)
    return requested


def _requested_public_excluded_channels(channels: list[str] | None) -> tuple[str, ...]:
    requested: list[str] = []
    for value in channels or []:
        for part in value.split(","):
            normalized = part.strip().upper()
            if normalized and normalized not in requested:
                requested.append(normalized)
    excluded = [*PUBLIC_EXCLUDED_CHANNELS]
    for requested_channel in requested:
        if requested_channel not in excluded:
            excluded.append(requested_channel)
    return tuple(excluded)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Talking Boats private API.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8034)
    args = parser.parse_args()
    uvicorn.run("talkingboats.api:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
