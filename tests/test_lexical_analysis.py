from __future__ import annotations

import json
import sqlite3
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import talkingboats.lexical_analysis as lexical_analysis
from talkingboats.clip_transcriber import UploadedClipStore
from talkingboats.config import DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT
from talkingboats.lexical_analysis import (
    generate_lexical_analysis,
    main,
    missing_lexical_analysis,
    read_cached_lexical_analysis,
    read_published_lexical_analysis,
)
from talkingboats.schemas import ClipPresignRequest
from talkingboats.security import assert_public_safe


def test_generate_lexical_analysis_counts_terms_entities_and_writes_cache(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    output_dir = tmp_path / "site"
    store = UploadedClipStore(db_path)
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-25/msc.mp3",
        channel="14",
        started_at="2026-05-25T22:10:00Z",
        text=(
            "PON PON, all stations. Seattle Traffic, container ship MSC Gabriella "
            "northbound Elliott Bay "
            "making 10 knots for Pier 91, roger thank you."
        ),
    )
    _transcribe(
        store,
        key="raw/channel=13/date=2026-05-25/tug.mp3",
        channel="13",
        started_at="2026-05-25T22:20:00Z",
        text="Tug Osprey to Emerald Clipper, we are crossing the West Waterway on one whistle.",
    )
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-25/cape.mp3",
        channel="14",
        started_at="2026-05-25T23:20:00Z",
        text="Seattle Traffic, Cape San Juan departing Pier 91 southbound.",
    )

    payload = generate_lexical_analysis(
        db_path=db_path,
        output_dir=output_dir,
        generated_at=datetime(2026, 5, 26, 1, 2, 3, tzinfo=UTC),
    )

    assert payload["status"] == "ok"
    assert payload["source_clip_count"] == 3
    assert payload["channels"] == {"13": 1, "14": 2}
    assert payload["source_min_started_at"] == "2026-05-25T22:10:00Z"
    assert payload["source_max_started_at"] == "2026-05-25T23:20:00Z"
    assert payload["frequency"]["by_channel"] == {"13": 1, "14": 2}
    assert payload["frequency"]["by_hour_pacific"]["15:00"] == 2
    assert payload["frequency"]["by_hour_pacific"]["16:00"] == 1
    assert ("seattle traffic", 2) in _term_pairs(payload["terms"]["bigrams"])
    assert ("elliott bay", 1) in _term_pairs(payload["terms"]["semantic_buckets"]["places"])
    assert ("west waterway", 1) in _term_pairs(payload["terms"]["semantic_buckets"]["places"])
    assert ("roger", 1) in _term_pairs(
        payload["terms"]["semantic_buckets"]["communication_markers"]
    )
    assert ("pon pon", 1) in _term_pairs(
        payload["terms"]["semantic_buckets"]["communication_markers"]
    )
    assert _entity(payload, "Seattle Traffic")["kind"] == "shore_station"
    assert _entity(payload, "MSC Gabriella")["kind"] == "vessel"
    assert _entity(payload, "Tug Osprey")["channels"] == {"13": 1}
    assert _entity(payload, "Cape San Juan")["examples"][0]["text"].startswith("Seattle Traffic")
    msc_example = _entity(payload, "MSC Gabriella")["examples"][0]
    assert msc_example["audio_public_filename"].endswith(".mp3")
    assert msc_example["duration_seconds"] == 8.0
    assert "raw/channel" not in json.dumps(msc_example)
    assert payload["topics"]["status"] == "skipped"
    assert payload["topics"]["reason"] == "not enough documents for BERTopic"
    assert payload["topics"]["plot_url"] == "/analysis/topic_clusters.html"
    assert (output_dir / "analysis" / "search_index.json").exists()
    search_index = json.loads((output_dir / "analysis" / "search_index.json").read_text())
    assert search_index["status"] == "skipped"
    assert search_index["source_clip_count"] == 0
    assert payload["education_guide"][0]["title"] == "Seattle Traffic is the coordinator"
    assert "VHF 14" in payload["education_guide"][0]["why_it_matters"]
    assert "sail plan" in payload["education_guide"][0]["what_it_explains"].lower()
    assert any(
        section["title"] == "PAN-PAN means urgent, not mayday"
        for section in payload["education_guide"]
    )
    assert any("West Waterway" in section["signals"] for section in payload["education_guide"])
    assert any(
        "pilot" in section["what_it_explains"].lower()
        for section in payload["education_guide"]
    )
    assert payload["education"][0]["url"].startswith("https://")
    assert (output_dir / "analysis" / "lexical.json").exists()
    assert (output_dir / "analysis" / "topic_clusters.html").exists()
    assert json.loads((output_dir / "analysis" / "lexical.json").read_text()) == payload
    assert read_cached_lexical_analysis(db_path) == payload
    assert read_published_lexical_analysis(output_dir / "analysis" / "lexical.json") == payload
    assert_public_safe(payload)


def test_generate_lexical_analysis_uses_corrected_transcripts(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    output_dir = tmp_path / "site"
    store = UploadedClipStore(db_path)
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-25/pan.mp3",
        channel="14",
        started_at="2026-05-25T22:10:00Z",
        text="PON PON all stations",
    )
    store.correct_transcript(
        channel="14",
        started_at="2026-05-25T22:10:00Z",
        corrected_transcript="PAN-PAN, all stations.",
        reviewer="rob",
    )

    payload = generate_lexical_analysis(
        db_path=db_path,
        output_dir=output_dir,
        generated_at=datetime(2026, 5, 26, 1, 2, 3, tzinfo=UTC),
    )

    assert ("pan-pan", 1) in _term_pairs(
        payload["terms"]["semantic_buckets"]["communication_markers"]
    )
    assert ("pon pon", 1) not in _term_pairs(
        payload["terms"]["semantic_buckets"]["communication_markers"]
    )


def test_generate_lexical_analysis_cache_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-25/one.mp3",
        channel="14",
        started_at="2026-05-25T22:10:00Z",
        text="Seattle Traffic roger.",
    )

    generate_lexical_analysis(
        db_path=db_path,
        output_dir=tmp_path / "site",
        generated_at=datetime(2026, 5, 26, 1, 2, 3, tzinfo=UTC),
    )
    generate_lexical_analysis(
        db_path=db_path,
        output_dir=tmp_path / "site",
        generated_at=datetime(2026, 5, 26, 1, 2, 3, tzinfo=UTC),
    )

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT cache_key, payload_json FROM lexical_analysis_cache"
        ).fetchall()

    assert [row[0] for row in rows] == ["latest"]
    assert json.loads(rows[0][1])["source_clip_count"] == 1


def test_entity_examples_prefer_recent_playable_clips(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-25/old.mp3",
        channel="14",
        started_at="2026-05-25T12:00:00Z",
        text="Seattle Traffic old example.",
    )
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-26/recent.mp3",
        channel="14",
        started_at="2026-05-26T02:00:00Z",
        text="Seattle Traffic recent example.",
    )

    payload = generate_lexical_analysis(
        db_path=db_path,
        output_dir=tmp_path / "site",
        generated_at=datetime(2026, 5, 26, 3, 0, 0, tzinfo=UTC),
    )

    example = _entity(payload, "Seattle Traffic")["examples"][0]
    assert example["started_at"] == "2026-05-26T02:00:00Z"
    assert example["audio_public_filename"].startswith("20260526T020000Z")


def test_entity_examples_only_mark_public_export_window_as_playable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lexical_analysis, "PUBLIC_AUDIO_EXAMPLE_LIMIT", 1)
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-25/old-match.mp3",
        channel="14",
        started_at="2026-05-25T12:00:00Z",
        text="Seattle Traffic old example.",
    )
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-26/newer.mp3",
        channel="14",
        started_at="2026-05-26T01:00:00Z",
        text="routine radio check",
    )

    payload = generate_lexical_analysis(
        db_path=db_path,
        output_dir=tmp_path / "site",
        generated_at=datetime(2026, 5, 26, 3, 0, 0, tzinfo=UTC),
    )

    example = _entity(payload, "Seattle Traffic")["examples"][0]
    assert example["started_at"] == "2026-05-25T12:00:00Z"
    assert "audio_public_filename" not in example


def test_entity_examples_prefer_short_analysis_clips(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-26/long.mp3",
        channel="14",
        started_at="2026-05-26T03:00:00Z",
        text="Seattle Traffic long but recent example.",
        duration_seconds=31.0,
    )
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-26/short.mp3",
        channel="14",
        started_at="2026-05-26T02:00:00Z",
        text="Seattle Traffic short useful example.",
        duration_seconds=5.0,
    )

    payload = generate_lexical_analysis(
        db_path=db_path,
        output_dir=tmp_path / "site",
        generated_at=datetime(2026, 5, 26, 3, 30, 0, tzinfo=UTC),
    )

    examples = _entity(payload, "Seattle Traffic")["examples"]
    assert examples[0]["started_at"] == "2026-05-26T02:00:00Z"
    assert examples[0]["duration_seconds"] == 5.0
    assert all(example["duration_seconds"] <= 12.0 for example in examples)


def test_entity_examples_keep_playable_fallback_for_long_clips(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-26/long-msc.mp3",
        channel="14",
        started_at="2026-05-26T03:00:00Z",
        text="Seattle Traffic, MSC Gabriella northbound past Elliott Bay Marina.",
        duration_seconds=31.0,
    )

    payload = generate_lexical_analysis(
        db_path=db_path,
        output_dir=tmp_path / "site",
        generated_at=datetime(2026, 5, 26, 3, 30, 0, tzinfo=UTC),
    )

    example = _entity(payload, "MSC Gabriella")["examples"][0]
    assert example["started_at"] == "2026-05-26T03:00:00Z"
    assert example["duration_seconds"] == 31.0
    assert example["audio_public_filename"].endswith(".mp3")


def test_analysis_audio_example_window_matches_public_export_default() -> None:
    assert lexical_analysis.PUBLIC_AUDIO_EXAMPLE_LIMIT == DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT
    assert DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT >= 3000


def test_missing_cache_returns_valid_empty_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    UploadedClipStore(db_path)

    payload = read_cached_lexical_analysis(db_path)

    assert payload == missing_lexical_analysis()
    assert payload["education_guide"][0]["title"] == "Seattle Traffic is the coordinator"
    assert_public_safe(payload)


def test_cli_rejects_missing_database(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--db-path",
                str(tmp_path / "missing.sqlite3"),
                "--output-dir",
                str(tmp_path / "site"),
            ]
        )

    assert exc.value.code == 2
    assert "database does not exist" in capsys.readouterr().err


def test_cli_writes_summary_and_returns_none(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-25/one.mp3",
        channel="14",
        started_at="2026-05-25T22:10:00Z",
        text="Seattle Traffic roger.",
    )

    result = main(["--db-path", str(db_path), "--output-dir", str(tmp_path / "site")])

    assert result is None
    assert json.loads(capsys.readouterr().out) == {"status": "ok", "source_clip_count": 1}


def test_generate_lexical_analysis_rejects_nonpositive_page_size(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    UploadedClipStore(db_path)

    with pytest.raises(ValueError, match="page_size must be positive"):
        generate_lexical_analysis(db_path=db_path, output_dir=tmp_path / "site", page_size=0)


def test_bertopic_model_is_configured_for_condensed_topic_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeSentenceTransformer:
        def __init__(self, model_name: str) -> None:
            captured["model_name"] = model_name

        def encode(
            self,
            documents: list[str],
            *,
            show_progress_bar: bool,
        ) -> list[tuple[float, float, float]]:
            captured["show_progress_bar"] = show_progress_bar
            return [
                (float(index), float(index + 1), float(index + 2))
                for index, _ in enumerate(documents)
            ]

    class _Coordinates:
        def __init__(self, row_count: int) -> None:
            self.row_count = row_count

        def __getitem__(self, key: tuple[slice, int]) -> list[float]:
            _rows, column = key
            return [float(index + column) for index in range(self.row_count)]

    class FakeUMAP:
        def __init__(self, **kwargs: object) -> None:
            captured["umap_kwargs"] = kwargs

        def fit_transform(self, embeddings: list[tuple[float, float, float]]) -> _Coordinates:
            return _Coordinates(len(embeddings))

    class FakeBERTopic:
        def __init__(self, **kwargs: object) -> None:
            captured["bertopic_kwargs"] = kwargs

        def fit_transform(
            self,
            documents: list[str],
            *,
            embeddings: list[tuple[float, float, float]],
        ) -> tuple[list[int], None]:
            bertopic_kwargs = captured["bertopic_kwargs"]
            assert isinstance(bertopic_kwargs, dict)
            topic_count = int(bertopic_kwargs.get("nr_topics", 25))
            return [index % topic_count for index, _ in enumerate(documents)], None

        def get_topic(self, topic_id: int) -> list[tuple[str, float]]:
            return [(f"word-{topic_id}", 1.0)]

    class FakeScatter3d:
        def __init__(self, **kwargs: object) -> None:
            captured["scatter_kwargs"] = kwargs

    class FakeFigure:
        def __init__(self, **kwargs: object) -> None:
            captured["figure_kwargs"] = kwargs

        def to_html(
            self,
            *,
            full_html: bool,
            include_plotlyjs: str,
            config: dict[str, object] | None = None,
        ) -> str:
            captured["html_options"] = {
                "full_html": full_html,
                "include_plotlyjs": include_plotlyjs,
                "config": config,
            }
            return "<html>topics</html>"

    monkeypatch.setitem(sys.modules, "bertopic", types.SimpleNamespace(BERTopic=FakeBERTopic))
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    monkeypatch.setitem(sys.modules, "umap", types.SimpleNamespace(UMAP=FakeUMAP))
    monkeypatch.setitem(
        sys.modules,
        "plotly",
        types.SimpleNamespace(
            graph_objects=types.SimpleNamespace(
                Figure=FakeFigure,
                Scatter3d=FakeScatter3d,
            )
        ),
    )

    clips = [
        lexical_analysis.TranscriptClip(
            key=f"clip-{index}.mp3",
            channel="14",
            started_at=f"2026-05-26T00:{index:02d}:00Z",
            ended_at=None,
            duration_seconds=None,
            content_type="audio/mpeg",
            transcript=f"Seattle Traffic routine movement report {index}",
        )
        for index in range(40)
    ]

    search_index_path = tmp_path / "search_index.json"
    payload = lexical_analysis._build_topics(
        clips,
        html_output_path=tmp_path / "topic_clusters.html",
        search_index_output_path=search_index_path,
    )

    bertopic_kwargs = captured["bertopic_kwargs"]
    scatter_kwargs = captured["scatter_kwargs"]
    figure_kwargs = captured["figure_kwargs"]
    html_options = captured["html_options"]
    assert isinstance(bertopic_kwargs, dict)
    assert isinstance(scatter_kwargs, dict)
    assert isinstance(figure_kwargs, dict)
    assert isinstance(html_options, dict)
    assert bertopic_kwargs["nr_topics"] == lexical_analysis.MAX_BERTOPIC_TOPICS
    assert lexical_analysis.MAX_BERTOPIC_TOPICS < 20
    assert len(set(scatter_kwargs["marker"]["color"])) > 6
    assert scatter_kwargs["marker"]["colorscale"] != "Viridis"
    assert figure_kwargs["layout"]["dragmode"] == "orbit"
    assert figure_kwargs["layout"]["scene"]["camera"]
    assert html_options["config"]["scrollZoom"] is True
    assert html_options["config"]["responsive"] is True
    assert html_options["config"]["displayModeBar"] is True
    search_index = json.loads(search_index_path.read_text(encoding="utf-8"))
    assert search_index["status"] == "ok"
    assert search_index["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert search_index["vector_dimension"] == 3
    assert search_index["source_clip_count"] == 40
    assert search_index["clips"][0]["channel"] == "14"
    assert search_index["clips"][0]["started_at"] == "2026-05-26T00:00:00Z"
    assert search_index["clips"][0]["embedding"] == [0.0, 1.0, 2.0]
    assert "raw/channel" not in search_index_path.read_text(encoding="utf-8")
    assert html_options["config"]["doubleClick"] == "reset"
    assert payload["status"] == "ok"
    assert len(payload["items"]) <= lexical_analysis.MAX_BERTOPIC_TOPICS
    assert lexical_analysis.MAX_BERTOPIC_TOPICS == 18
    assert all(not item["label"].startswith("Topic ") for item in payload["items"])


def test_mobile_topic_plot_html_supports_two_finger_camera_zoom() -> None:
    base_html = "<html><head><title>Topics</title></head><body><div>plot</div></body></html>"

    topic_html = lexical_analysis._mobile_topic_plot_html(base_html)
    repeated_html = lexical_analysis._mobile_topic_plot_html(topic_html)

    assert 'name="viewport"' in topic_html
    assert "topic-mobile-tools" in topic_html
    assert 'aria-label="Zoom topic clusters in"' in topic_html
    assert 'aria-label="Reset topic cluster view"' in topic_html
    assert "touches.length !== 2" in topic_html
    assert "event.preventDefault()" in topic_html
    assert "Plotly.relayout" in topic_html
    assert '"scene.camera.eye"' in topic_html
    assert "requestAnimationFrame" in topic_html
    assert repeated_html.count("topic-map-mobile-enhancements") == 1


def test_topic_items_label_topics_with_keywords_not_numeric_ids() -> None:
    class FakeTopicModel:
        def get_topic(self, topic_id: int) -> list[tuple[str, float]]:
            return {
                0: [
                    ("roger", 1.0),
                    ("seattle traffic", 0.9),
                    ("traffic", 0.8),
                    ("mariners", 0.7),
                    ("calling", 0.6),
                ],
                1: [("container ship", 1.0), ("cosco jetta", 0.9), ("ship", 0.8)],
            }[topic_id]

    items = lexical_analysis._topic_items(
        FakeTopicModel(),
        topics=[0, 0, 1, -1],
        documents=["a", "b", "c", "d"],
    )

    assert items[0]["label"] == "seattle traffic / mariners / calling"
    assert items[0]["top_words"] == ["seattle traffic", "mariners", "calling"]
    assert items[1]["label"] == "container ship / cosco jetta"
    assert items[2]["label"] == "Outliers"


def test_topic_items_fall_back_to_document_keywords_when_model_words_are_empty() -> None:
    class FakeTopicModel:
        def get_topic(self, _topic_id: int) -> list[tuple[str, float]]:
            return []

    items = lexical_analysis._topic_items(
        FakeTopicModel(),
        topics=[0, 0, 1],
        documents=[
            "Seattle Traffic, tug assist in the West Waterway.",
            "Seattle Traffic, pilot station entering the West Waterway.",
            "Cape San Juan departing Colman Dock.",
        ],
    )

    assert items[0]["label"] == "seattle traffic / west waterway / pilot station"
    assert items[0]["top_words"][:3] == [
        "seattle traffic",
        "west waterway",
        "pilot station",
    ]
    assert items[1]["label"] == "colman dock / cape san juan / departing"


def test_topic_display_words_filter_radio_filler_contractions() -> None:
    assert lexical_analysis._topic_display_words(
        ["we'll", "i'll", "that's", "seattle traffic", "wind direction"],
        limit=3,
    ) == ["seattle traffic", "wind direction"]


def _transcribe(
    store: UploadedClipStore,
    *,
    key: str,
    channel: str,
    started_at: str,
    text: str,
    duration_seconds: float = 8.0,
) -> None:
    start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    ended_at = (start + timedelta(seconds=duration_seconds)).isoformat().replace("+00:00", "Z")
    store.record_presigned_upload(
        key=key,
        request=ClipPresignRequest(
            channel=channel,
            started_at=started_at,
            ended_at=ended_at,
            content_type="audio/mpeg",
            idempotency_key=f"radio-event-{channel}-{started_at}-{key}",
            duration_seconds=duration_seconds,
        ),
    )
    store.mark_transcribed(
        key,
        [
            _Segment(
                text=text,
                started_at=started_at,
                ended_at=ended_at,
                relative_start_seconds=0.0,
                relative_end_seconds=8.0,
            )
        ],
    )


class _Segment:
    def __init__(
        self,
        *,
        text: str,
        started_at: str,
        ended_at: str,
        relative_start_seconds: float,
        relative_end_seconds: float,
    ) -> None:
        self.text = text
        self.started_at = started_at
        self.ended_at = ended_at
        self.relative_start_seconds = relative_start_seconds
        self.relative_end_seconds = relative_end_seconds


def _term_pairs(items: list[dict[str, object]]) -> set[tuple[str, int]]:
    return {(str(item["term"]), int(item["count"])) for item in items}


def _entity(payload: dict[str, object], name: str) -> dict[str, object]:
    for entity in payload["entities"]:  # type: ignore[index]
        if entity["name"] == name:
            return entity
    raise AssertionError(f"missing entity {name}")
