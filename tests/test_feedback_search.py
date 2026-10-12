from talkingboats.feedback_search import corrected_search


def test_corrections_replace_stale_search_before_limit_and_undo_restores_original(monkeypatch):
    monkeypatch.setattr("talkingboats.feedback_search.embed_query", lambda *args: [1.0, 0.0])
    original = {
        "channel": "14",
        "started_at": "2026-10-05T12:00:00Z",
        "transcript": "Tug spray",
        "embedding": [1.0, 0.0],
    }
    index = {"status": "ok", "clips": [original], "embedding_model": "fixture"}
    row = {
        **original,
        "text": "Tug Osprey",
        "original": "Tug spray",
        "embedding": [1.0, 0.0],
        "original_embedding": [1.0, 0.0],
    }

    class Store:
        def list(self):
            return [row]

    result = corrected_search(
        Store(),
        {"results": [], "reference_started_at": original["started_at"]},
        index,
        query="Osprey",
        limit=1,
        recency="all",
    )
    assert result["count"] == 1 and result["results"][0]["transcript"] == "Tug Osprey"
    row["reverted"] = True
    result = corrected_search(
        Store(), {"results": []}, index, query="spray", limit=1, recency="all"
    )
    assert result["results"][0]["transcript"] == "Tug spray"
