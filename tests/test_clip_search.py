from __future__ import annotations

import json

from talkingboats.clip_search import read_search_index, search_clips


def test_read_search_index_reuses_unchanged_parsed_payload(tmp_path, monkeypatch) -> None:
    index_path = tmp_path / "search_index.json"
    index_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "embedding_model": "example/model",
                "clips": [{"transcript": "Seattle Traffic"}],
            }
        ),
        encoding="utf-8",
    )

    first = read_search_index(index_path)

    def fail_reparse(_payload: str):
        raise AssertionError("unchanged search index should be served from memory")

    monkeypatch.setattr("talkingboats.clip_search.json.loads", fail_reparse)

    second = read_search_index(index_path)

    assert second is first


def test_read_search_index_reloads_when_generated_file_changes(tmp_path) -> None:
    index_path = tmp_path / "search_index.json"
    index_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "embedding_model": "example/model",
                "clips": [{"transcript": "first"}],
            }
        ),
        encoding="utf-8",
    )
    first = read_search_index(index_path)

    index_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "embedding_model": "example/model",
                "clips": [
                    {"transcript": "second"},
                    {"transcript": "third"},
                ],
            }
        ),
        encoding="utf-8",
    )

    second = read_search_index(index_path)

    assert second is not first
    assert [clip["transcript"] for clip in second["clips"]] == ["second", "third"]


def test_search_clips_suppresses_low_relevance_top_n_fillers() -> None:
    index = {
        "status": "ok",
        "generated_at": "2026-08-02T01:00:00Z",
        "embedding_model": "example/model",
        "source_clip_count": 2,
        "clips": [
            {
                "channel": "14",
                "started_at": "2026-08-02T00:30:00Z",
                "transcript": "Unrelated recent radio traffic.",
                "embedding": [0.25, 0.97],
            },
            {
                "channel": "14",
                "started_at": "2026-07-31T00:30:00Z",
                "transcript": "Roger, Wenatchee.",
                "embedding": [0.99, 0.01],
            },
        ],
    }

    payload = search_clips(
        index,
        query="Wenatchee",
        limit=10,
        recency="24h",
        query_vector=[1.0, 0.0],
    )

    assert payload["minimum_score"] == 0.35
    assert payload["count"] == 0
    assert payload["results"] == []


def test_search_clips_builds_one_compact_vector_runtime_and_reuses_it(monkeypatch) -> None:
    index = {
        "status": "ok",
        "generated_at": "2026-08-02T01:00:00Z",
        "embedding_model": "example/model",
        "vector_dimension": 2,
        "source_clip_count": 2,
        "clips": [
            {
                "channel": "14",
                "started_at": "2026-08-02T00:30:00Z",
                "transcript": "Roger, Wenatchee.",
                "embedding": [0.99, 0.01],
            },
            {
                "channel": "13",
                "started_at": "2026-08-01T23:30:00Z",
                "transcript": "Bridge arrangement.",
                "embedding": [0.1, 0.99],
            },
        ],
    }

    first = search_clips(
        index,
        query="Wenatchee",
        limit=10,
        recency="24h",
        query_vector=[1.0, 0.0],
    )

    assert first["count"] == 1
    assert first["results"][0]["transcript"] == "Roger, Wenatchee."
    assert all("embedding" not in clip for clip in index["clips"])
    assert "_vector_search_runtime" in index

    monkeypatch.setattr(
        "talkingboats.clip_search._build_vector_search_runtime",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("vector runtime should be reused")
        ),
    )

    second = search_clips(
        index,
        query="Wenatchee",
        limit=10,
        recency="24h",
        query_vector=[1.0, 0.0],
    )

    assert second["results"] == first["results"]
