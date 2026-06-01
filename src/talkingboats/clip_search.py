from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from talkingboats.channel_metadata import channel_label
from talkingboats.security import assert_public_safe

DEFAULT_SEARCH_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SEARCH_INDEX_PATH = "/analysis/search_index.json"
SEARCH_RECENCY_WINDOWS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "all": None,
}

_EMBEDDERS: dict[str, Any] = {}


class SearchIndexUnavailable(RuntimeError):
    pass


def missing_search_index(
    reason: str = "clip search index has not been generated",
) -> dict[str, Any]:
    return {
        "status": "missing",
        "reason": reason,
        "generated_at": None,
        "embedding_model": DEFAULT_SEARCH_EMBEDDING_MODEL,
        "vector_dimension": 0,
        "source_clip_count": 0,
        "clips": [],
    }


def skipped_search_index(reason: str, *, generated_at: str | None = None) -> dict[str, Any]:
    return {
        "status": "skipped",
        "reason": reason,
        "generated_at": generated_at,
        "embedding_model": DEFAULT_SEARCH_EMBEDDING_MODEL,
        "vector_dimension": 0,
        "source_clip_count": 0,
        "clips": [],
    }


def build_search_index(
    *,
    clips: list[Any],
    embeddings: Any,
    topics: list[int] | None = None,
    topic_labels: dict[int, str] | None = None,
    generated_at: str | None = None,
    embedding_model: str = DEFAULT_SEARCH_EMBEDDING_MODEL,
) -> dict[str, Any]:
    entries = []
    for index, clip in enumerate(clips):
        vector = _embedding_at(embeddings, index)
        if not vector:
            continue
        topic_id = int(topics[index]) if topics and index < len(topics) else None
        entry = {
            "channel": str(clip.channel),
            "channel_label": channel_label(str(clip.channel)),
            "started_at": str(clip.started_at),
            "ended_at": clip.ended_at,
            "duration_seconds": clip.duration_seconds,
            "content_type": str(clip.content_type),
            "transcript": str(clip.transcript),
            "embedding": vector,
        }
        if topic_id is not None:
            entry["topic_id"] = topic_id
            entry["topic_label"] = (topic_labels or {}).get(topic_id)
        entries.append(entry)
    dimension = len(entries[0]["embedding"]) if entries else 0
    payload = {
        "status": "ok" if entries else "skipped",
        "reason": None if entries else "no searchable transcript vectors were generated",
        "generated_at": generated_at,
        "embedding_model": embedding_model,
        "vector_dimension": dimension,
        "source_clip_count": len(entries),
        "clips": entries,
    }
    assert_public_safe(payload)
    return payload


def write_search_index(path: Path, payload: dict[str, Any]) -> None:
    assert_public_safe(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_search_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return missing_search_index()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert_public_safe(payload)
    return payload


def search_clips(
    index: dict[str, Any],
    *,
    query: str,
    limit: int,
    recency: str,
    query_vector: list[float] | None = None,
) -> dict[str, Any]:
    normalized_query = " ".join(query.split())
    if not normalized_query:
        raise ValueError("query must not be empty")
    if limit <= 0:
        raise ValueError("limit must be positive")
    recency_key = recency if recency in SEARCH_RECENCY_WINDOWS else "7d"
    clips = [clip for clip in index.get("clips", []) if isinstance(clip, dict)]
    if index.get("status") != "ok" or not clips:
        raise SearchIndexUnavailable("clip search index is not ready")
    embedding_model = str(index.get("embedding_model") or DEFAULT_SEARCH_EMBEDDING_MODEL)
    query_embedding = query_vector or embed_query(normalized_query, embedding_model)
    reference_time = _latest_clip_time(clips)
    cutoff = _recency_cutoff(reference_time, recency_key)
    candidates = [
        clip
        for clip in clips
        if cutoff is None or _parse_utc(str(clip.get("started_at") or "")) >= cutoff
    ]
    scored = []
    for clip in candidates:
        score = cosine_similarity(query_embedding, clip.get("embedding"))
        if not number_is_finite(score):
            continue
        scored.append((score, clip))
    scored.sort(key=lambda item: (item[0], str(item[1].get("started_at") or "")), reverse=True)
    results = [_search_result(clip, score) for score, clip in scored[:limit]]
    payload = {
        "status": "ok",
        "query": normalized_query,
        "recency": recency_key,
        "limit": limit,
        "count": len(results),
        "reference_started_at": reference_time.isoformat().replace("+00:00", "Z")
        if reference_time
        else None,
        "recency_cutoff": cutoff.isoformat().replace("+00:00", "Z") if cutoff else None,
        "index": {
            "generated_at": index.get("generated_at"),
            "source_clip_count": index.get("source_clip_count", len(clips)),
            "embedding_model": embedding_model,
        },
        "results": results,
    }
    assert_public_safe(payload)
    return payload


def embed_query(query: str, model_name: str) -> list[float]:
    if model_name not in _EMBEDDERS:
        from sentence_transformers import SentenceTransformer

        _EMBEDDERS[model_name] = SentenceTransformer(model_name)
    encoded = _EMBEDDERS[model_name].encode([query], show_progress_bar=False)
    return _embedding_at(encoded, 0)


def cosine_similarity(left: Any, right: Any) -> float:
    left_vector = _vector(left)
    right_vector = _vector(right)
    if not left_vector or not right_vector or len(left_vector) != len(right_vector):
        return math.nan
    dot = sum(a * b for a, b in zip(left_vector, right_vector, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left_vector))
    right_norm = math.sqrt(sum(value * value for value in right_vector))
    if left_norm <= 0 or right_norm <= 0:
        return math.nan
    return dot / (left_norm * right_norm)


def _search_result(clip: dict[str, Any], score: float) -> dict[str, Any]:
    channel = str(clip.get("channel") or "?")
    started_at = str(clip.get("started_at") or "")
    params = urlencode({"channel": channel, "started_at": started_at})
    return {
        "channel": channel,
        "channel_label": clip.get("channel_label") or channel_label(channel),
        "started_at": started_at,
        "ended_at": clip.get("ended_at"),
        "duration_seconds": clip.get("duration_seconds"),
        "content_type": clip.get("content_type") or "audio/mpeg",
        "transcript": str(clip.get("transcript") or ""),
        "score": round(score, 4),
        "topic_id": clip.get("topic_id"),
        "topic_label": clip.get("topic_label"),
        "audio_url": f"/api/clips/audio?{params}",
    }


def _embedding_at(embeddings: Any, index: int) -> list[float]:
    try:
        row = embeddings[index]
    except (IndexError, KeyError, TypeError):
        return []
    return _vector(row)


def _vector(value: Any) -> list[float]:
    if value is None:
        return []
    try:
        values = list(value)
    except TypeError:
        return []
    vector = []
    for item in values:
        try:
            number = float(item)
        except (TypeError, ValueError):
            return []
        if not number_is_finite(number):
            return []
        vector.append(round(number, 6))
    return vector


def _latest_clip_time(clips: list[dict[str, Any]]) -> datetime | None:
    times = []
    for clip in clips:
        try:
            times.append(_parse_utc(str(clip.get("started_at") or "")))
        except ValueError:
            continue
    return max(times) if times else None


def _recency_cutoff(reference_time: datetime | None, recency: str) -> datetime | None:
    window = SEARCH_RECENCY_WINDOWS[recency]
    if reference_time is None or window is None:
        return None
    return reference_time - window


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def number_is_finite(value: float) -> bool:
    return isinstance(value, int | float) and math.isfinite(value)
