from __future__ import annotations

import json

from talkingboats.clip_search import read_search_index


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
