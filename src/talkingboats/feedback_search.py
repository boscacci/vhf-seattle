"""Correction delta index shared through DynamoDB; no full index rebuild on edits."""

from __future__ import annotations

import threading

from talkingboats.asr_feedback import DynamoCorrections
from talkingboats.clip_search import (
    DEFAULT_SEARCH_EMBEDDING_MODEL,
    MINIMUM_SEARCH_SCORE,
    _recency_cutoff,
    _search_result,
    cosine_similarity,
    embed_query,
    search_clips,
)

_CACHE: dict[str, tuple[int, list[dict]]] = {}
_LOCK = threading.Lock()


def corrected_search(store, payload, index, *, query, limit, recency):
    from datetime import datetime

    if isinstance(store, DynamoCorrections):
        revision = (
            store.table.get_item(Key={"pk": "asr#revision", "sk": "current"}, ConsistentRead=True)
            .get("Item", {})
            .get("revision", 0)
        )
        with _LOCK:
            cached = _CACHE.get(store.table_name)
            if cached is None or cached[0] != revision:
                cached = (int(revision), store.list())
                _CACHE[store.table_name] = cached
            labels = cached[1]
    else:
        labels = store.list()
    changed = {(r["channel"], r["started_at"]): r for r in labels}
    embedding = (
        embed_query(query, index.get("embedding_model") or DEFAULT_SEARCH_EMBEDDING_MODEL)
        if changed
        else []
    )
    times = [
        datetime.fromisoformat(r["started_at"].replace("Z", "+00:00")) for r in changed.values()
    ]
    if payload.get("reference_started_at"):
        times.append(datetime.fromisoformat(payload["reference_started_at"].replace("Z", "+00:00")))
    reference = max(times) if times else None
    if changed:
        payload = search_clips(
            index,
            query=query,
            limit=limit,
            recency=recency,
            query_vector=embedding,
            excluded_clips=set(changed),
            reference_time_override=reference,
        )
    results = payload["results"]
    cutoff = _recency_cutoff(reference, recency)
    for row in changed.values():
        if row["channel"] == "74" or (
            cutoff and datetime.fromisoformat(row["started_at"].replace("Z", "+00:00")) < cutoff
        ):
            continue
        score = cosine_similarity(
            embedding,
            row.get("original_embedding") if row.get("reverted") else row.get("embedding"),
        )
        if score >= MINIMUM_SEARCH_SCORE:
            results.append(
                _search_result(
                    {**row, "transcript": row["original"] if row.get("reverted") else row["text"]},
                    score,
                )
            )
    results.sort(key=lambda r: (r["score"], r["started_at"]), reverse=True)
    payload["results"] = results[:limit]
    payload["count"] = len(payload["results"])
    return payload
