from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import talkingboats.lexical_analysis as lexical_analysis
from talkingboats.clip_transcriber import RecentTranscribedClip, UploadedClipStore
from talkingboats.config import DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT
from talkingboats.lexical_analysis import (
    TranscriptClip,
    generate_lexical_analysis,
    generate_lexical_analysis_from_public_manifest,
    generate_lexical_analysis_from_store,
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


def test_generate_lexical_analysis_can_use_cloud_clip_store(tmp_path: Path) -> None:
    store = FakeAnalysisClipStore(
        [
            TranscriptClip(
                key="raw/channel=14/date=2026-05-25/cloud.mp3",
                channel="14",
                started_at="2026-05-25T22:10:00Z",
                ended_at="2026-05-25T22:10:08Z",
                duration_seconds=8.0,
                content_type="audio/mpeg",
                transcript="Seattle Traffic cloud backed transcript.",
            )
        ]
    )

    payload = generate_lexical_analysis_from_store(
        clip_store=store,
        output_dir=tmp_path / "site",
        generated_at=datetime(2026, 5, 26, 1, 2, 3, tzinfo=UTC),
    )

    assert payload["source_clip_count"] == 1
    assert payload["channels"] == {"14": 1}
    assert ("seattle traffic", 1) in _term_pairs(payload["terms"]["bigrams"])
    assert store.calls == [{"limit": 500, "excluded_channels": ("WX",), "offset": 0}]


def test_generate_lexical_analysis_from_store_excludes_clips_hidden_by_quality_gate(
    tmp_path: Path,
) -> None:
    store = StreamingAnalysisClipStore(
        [
            _recent_analysis_clip(
                key="raw/channel=14/date=2026-05-25/clear.mp3",
                channel="14",
                started_at="2026-05-25T22:10:00Z",
                transcript="Seattle Traffic clear radio report.",
                quality_status="ok",
                quality_score=96.0,
            ),
            _recent_analysis_clip(
                key="raw/channel=06/date=2026-05-25/legacy-low-score.mp3",
                channel="06",
                started_at="2026-05-25T22:11:00Z",
                transcript="Static should stay out of the analysis corpus.",
                quality_status="ok",
                quality_score=89.9,
            ),
            _recent_analysis_clip(
                key="raw/channel=74/date=2026-05-25/quarantined.mp3",
                channel="74",
                started_at="2026-05-25T22:12:00Z",
                transcript="Quarantined noise should stay out too.",
                quality_status="quarantined",
                quality_score=100.0,
            ),
        ]
    )

    payload = generate_lexical_analysis_from_store(
        clip_store=store,
        output_dir=tmp_path / "site",
        generated_at=datetime(2026, 5, 26, 1, 2, 3, tzinfo=UTC),
    )

    assert payload["source_clip_count"] == 1
    assert payload["channels"] == {"14": 1}
    assert "Static should stay out" not in json.dumps(payload)
    assert "Quarantined noise" not in json.dumps(payload)


def test_generate_lexical_analysis_from_sqlite_excludes_low_quality_legacy_records(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-25/clear.mp3",
        channel="14",
        started_at="2026-05-25T22:10:00Z",
        text="Seattle Traffic clear radio report.",
    )
    _transcribe(
        store,
        key="raw/channel=06/date=2026-05-25/legacy-low-score.mp3",
        channel="06",
        started_at="2026-05-25T22:11:00Z",
        text="Static legacy record should stay out of analysis.",
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE uploaded_clips SET quality_status = 'ok', quality_score = 96.0 "
            "WHERE channel = '14'"
        )
        connection.execute(
            "UPDATE uploaded_clips SET quality_status = 'ok', quality_score = 89.9 "
            "WHERE channel = '06'"
        )

    payload = generate_lexical_analysis(
        db_path=db_path,
        output_dir=tmp_path / "site",
        generated_at=datetime(2026, 5, 26, 1, 2, 3, tzinfo=UTC),
    )

    assert payload["source_clip_count"] == 1
    assert payload["channels"] == {"14": 1}
    assert "Static legacy record" not in json.dumps(payload)


def test_generate_lexical_analysis_from_store_counts_all_transcripts_and_marks_public_audio(
    tmp_path: Path,
) -> None:
    public_clip_key = "raw/channel=14/date=2026-05-25/playable.mp3"
    store = FakeAnalysisClipStore(
        [
            TranscriptClip(
                key=public_clip_key,
                channel="14",
                started_at="2026-05-25T22:10:00Z",
                ended_at="2026-05-25T22:10:08Z",
                duration_seconds=8.0,
                content_type="audio/mpeg",
                transcript="Seattle Traffic, Tug Osprey northbound.",
            ),
            TranscriptClip(
                key="raw/channel=13/date=2026-05-25/archive-only.mp3",
                channel="13",
                started_at="2026-05-25T22:20:00Z",
                ended_at="2026-05-25T22:20:08Z",
                duration_seconds=8.0,
                content_type="audio/mpeg",
                transcript="Cape San Juan archive only transcript.",
            ),
        ]
    )
    public_manifest_path = tmp_path / "public_manifest.json"
    public_manifest_path.write_text(
        json.dumps(
            {
                "clips": [
                    {
                        "id": f"clip-{hashlib.sha256(public_clip_key.encode()).hexdigest()[:16]}",
                        "channel": "14",
                        "started_at": "2026-05-25T22:10:00Z",
                        "audio_public_filename": "20260525T221000Z-vhf-14-playable.mp3",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = generate_lexical_analysis_from_store(
        clip_store=store,
        output_dir=tmp_path / "site",
        public_manifest_path=public_manifest_path,
        generated_at=datetime(2026, 5, 26, 1, 2, 3, tzinfo=UTC),
    )

    assert payload["source_clip_count"] == 2
    assert payload["channels"] == {"13": 1, "14": 1}
    assert ("archive only", 1) in _term_pairs(payload["terms"]["bigrams"])
    examples_by_name = {
        entity["name"]: entity["examples"][0]
        for entity in payload["entities"]
        if entity["examples"]
    }
    assert examples_by_name["Tug Osprey"]["audio_public_filename"] == (
        "20260525T221000Z-vhf-14-playable.mp3"
    )
    assert "audio_public_filename" not in examples_by_name["Cape San Juan"]


def test_generate_lexical_analysis_uses_only_public_playable_manifest_clips(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "site"
    public_manifest_path = tmp_path / "public_manifest.json"
    public_manifest_path.write_text(
        json.dumps(
            {
                "clips": [
                    {
                        "id": "clip-public-good",
                        "channel": "14",
                        "started_at": "2026-06-04T20:00:00Z",
                        "ended_at": "2026-06-04T20:00:08Z",
                        "duration_seconds": 8.0,
                        "transcript_public": "Seattle Traffic, tug Osprey northbound.",
                        "audio_public_filename": "20260604T200000Z-vhf-14-good.mp3",
                    },
                    {
                        "id": "clip-no-audio",
                        "channel": "14",
                        "started_at": "2026-06-04T20:01:00Z",
                        "transcript_public": "Seattle Traffic should not count.",
                    },
                    {
                        "id": "clip-ellipsis",
                        "channel": "14",
                        "started_at": "2026-06-04T20:02:00Z",
                        "transcript_public": "... ... ...",
                        "audio_public_filename": "20260604T200200Z-vhf-14-ellipsis.mp3",
                    },
                    {
                        "id": "clip-low-score",
                        "channel": "06",
                        "started_at": "2026-06-04T20:02:30Z",
                        "transcript_public": "Crackly low-score radio should not count.",
                        "audio_public_filename": "20260604T200230Z-vhf-06-low-score.mp3",
                        "quality_status": "ok",
                        "quality_score": 89.9,
                    },
                    {
                        "id": "clip-quarantined",
                        "channel": "74",
                        "started_at": "2026-06-04T20:02:45Z",
                        "transcript_public": "Quarantined radio should not count.",
                        "audio_public_filename": "20260604T200245Z-vhf-74-quarantined.mp3",
                        "quality_status": "quarantined",
                        "quality_score": 100.0,
                    },
                    {
                        "id": "clip-weather",
                        "channel": "WX",
                        "started_at": "2026-06-04T20:03:00Z",
                        "transcript_public": "Seattle Traffic weather should not count.",
                        "audio_public_filename": "20260604T200300Z-vhf-wx.mp3",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = generate_lexical_analysis_from_public_manifest(
        public_manifest_path=public_manifest_path,
        output_dir=output_dir,
        generated_at=datetime(2026, 6, 4, 21, 0, 0, tzinfo=UTC),
    )

    assert payload["source_clip_count"] == 1
    assert payload["channels"] == {"14": 1}
    assert ("seattle traffic", 1) in _term_pairs(payload["terms"]["bigrams"])
    rendered = json.dumps(payload)
    assert "should not count" not in rendered
    assert "Crackly low-score" not in rendered
    assert "Quarantined radio" not in rendered
    assert "... ... ..." not in rendered
    assert payload["entities"][0]["examples"][0]["audio_public_filename"] == (
        "20260604T200000Z-vhf-14-good.mp3"
    )


def test_generate_lexical_analysis_streams_cloud_clip_store_when_available(
    tmp_path: Path,
) -> None:
    clips = [
        TranscriptClip(
            key=f"raw/channel=14/date=2026-05-25/cloud-{index}.mp3",
            channel="14",
            started_at=f"2026-05-25T22:1{index}:00Z",
            ended_at=f"2026-05-25T22:1{index}:08Z",
            duration_seconds=8.0,
            content_type="audio/mpeg",
            transcript=f"Seattle Traffic streamed transcript {index}.",
        )
        for index in range(3)
    ]
    store = StreamingAnalysisClipStore(clips)

    payload = generate_lexical_analysis_from_store(
        clip_store=store,
        output_dir=tmp_path / "site",
        page_size=2,
        limit=2,
        generated_at=datetime(2026, 5, 26, 1, 2, 3, tzinfo=UTC),
    )

    assert payload["source_clip_count"] == 2
    assert store.iter_calls == [{"page_size": 2, "excluded_channels": ("WX",)}]
    assert store.recent_calls == []


def test_generate_lexical_analysis_skips_legacy_ellipsis_transcripts(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    output_dir = tmp_path / "site"
    store = UploadedClipStore(db_path)
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-25/good.mp3",
        channel="14",
        started_at="2026-05-25T22:10:00Z",
        text="Seattle Traffic roger.",
    )
    ellipsis_key = "raw/channel=14/date=2026-05-25/ellipsis.mp3"
    store.record_presigned_upload(
        key=ellipsis_key,
        request=ClipPresignRequest(
            channel="14",
            started_at="2026-05-25T22:20:00Z",
            ended_at="2026-05-25T22:20:08Z",
            content_type="audio/mpeg",
            idempotency_key="radio-event-14-ellipsis",
            duration_seconds=8.0,
        ),
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE uploaded_clips
            SET status = 'transcribed',
                transcript = '... ... ...',
                error = NULL
            WHERE key = ?
            """,
            (ellipsis_key,),
        )

    payload = generate_lexical_analysis(
        db_path=db_path,
        output_dir=output_dir,
        generated_at=datetime(2026, 5, 26, 1, 2, 3, tzinfo=UTC),
    )

    assert payload["source_clip_count"] == 1
    assert "... ... ..." not in json.dumps(payload)


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


def test_entity_examples_prefer_recent_audio_over_stale_short_clips(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    _transcribe(
        store,
        key="raw/channel=14/date=2026-05-26/stale-short.mp3",
        channel="14",
        started_at="2026-05-26T02:00:00Z",
        text="Seattle Traffic stale short example.",
        duration_seconds=5.0,
    )
    _transcribe(
        store,
        key="raw/channel=14/date=2026-06-04/recent-long.mp3",
        channel="14",
        started_at="2026-06-04T13:00:00Z",
        text="Seattle Traffic recent improved-audio example.",
        duration_seconds=31.0,
    )

    payload = generate_lexical_analysis(
        db_path=db_path,
        output_dir=tmp_path / "site",
        generated_at=datetime(2026, 6, 4, 14, 0, 0, tzinfo=UTC),
    )

    example = _entity(payload, "Seattle Traffic")["examples"][0]
    assert example["started_at"] == "2026-06-04T13:00:00Z"
    assert example["audio_public_filename"].startswith("20260604T130000Z")


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
                "--clip-store-backend",
                "sqlite",
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

    result = main(
        [
            "--clip-store-backend",
            "sqlite",
            "--db-path",
            str(db_path),
            "--output-dir",
            str(tmp_path / "site"),
        ]
    )

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


def test_topic_cluster_plot_excludes_outlier_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeSentenceTransformer:
        def __init__(self, _model_name: str) -> None:
            pass

        def encode(
            self,
            documents: list[str],
            *,
            show_progress_bar: bool,
        ) -> list[tuple[float, float, float]]:
            return [
                (float(index), float(index + 1), float(index + 2))
                for index, _document in enumerate(documents)
            ]

    class _Coordinates:
        def __init__(self, row_count: int) -> None:
            self.row_count = row_count

        def __getitem__(self, key: tuple[slice | list[int], int]) -> list[float]:
            rows, column = key
            values = [float(index + column) for index in range(self.row_count)]
            if isinstance(rows, list):
                return [values[index] for index in rows]
            return values

    class FakeUMAP:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def fit_transform(self, embeddings: list[tuple[float, float, float]]) -> _Coordinates:
            return _Coordinates(len(embeddings))

    class FakeBERTopic:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def fit_transform(
            self,
            documents: list[str],
            *,
            embeddings: list[tuple[float, float, float]],
        ) -> tuple[list[int], None]:
            return [-1, 0, 0, 1, -1, 1], None

        def get_topic(self, topic_id: int) -> list[tuple[str, float]]:
            return {
                0: [("seattle traffic", 1.0), ("roger", 0.9)],
                1: [("tug barge", 1.0), ("southbound", 0.9)],
            }[topic_id]

    class FakeScatter3d:
        def __init__(self, **kwargs: object) -> None:
            captured["scatter_kwargs"] = kwargs

    class FakeFigure:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def to_html(
            self,
            *,
            full_html: bool,
            include_plotlyjs: str,
            config: dict[str, object] | None = None,
        ) -> str:
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
            started_at=f"2026-05-26T00:0{index}:00Z",
            ended_at=None,
            duration_seconds=None,
            content_type="audio/mpeg",
            transcript=transcript,
        )
        for index, transcript in enumerate(
            [
                "Outlier zero should stay out of the topic map.",
                "Seattle Traffic regular cluster point one.",
                "Seattle Traffic regular cluster point two.",
                "Tug barge southbound cluster point one.",
                "Outlier four should stay out of the topic map.",
                "Tug barge southbound cluster point two.",
            ]
        )
    ]

    payload = lexical_analysis._build_topics(
        clips,
        html_output_path=tmp_path / "topic_clusters.html",
        min_topic_documents=6,
    )

    scatter_kwargs = captured["scatter_kwargs"]
    assert isinstance(scatter_kwargs, dict)
    assert scatter_kwargs["x"] == [1.0, 2.0, 3.0, 5.0]
    assert scatter_kwargs["y"] == [2.0, 3.0, 4.0, 6.0]
    assert scatter_kwargs["z"] == [3.0, 4.0, 5.0, 7.0]
    assert len(scatter_kwargs["text"]) == 4
    assert all("Outlier" not in text for text in scatter_kwargs["text"])
    assert "Outliers" not in scatter_kwargs["customdata"]
    assert lexical_analysis.TOPIC_OUTLIER_COLOR not in scatter_kwargs["marker"]["color"]
    assert any(item["id"] == -1 for item in payload["items"])


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
    assert "talkingboats-topic-plot-rotation" in topic_html
    assert 'window.addEventListener("message"' in topic_html
    assert "rotationRequested" in topic_html
    assert "prefers-reduced-motion" in topic_html
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


def test_topic_items_include_clip_metadata_for_reviewable_examples() -> None:
    class FakeTopicModel:
        def get_topic(self, _topic_id: int) -> list[tuple[str, float]]:
            return [("seattle traffic", 1.0), ("west waterway", 0.9)]

    clips = [
        lexical_analysis.TranscriptClip(
            key="clip-1",
            channel="14",
            started_at="2026-06-04T15:00:00Z",
            ended_at="2026-06-04T15:00:06Z",
            duration_seconds=6.0,
            content_type="audio/wav",
            transcript="Seattle Traffic, west waterway test.",
        )
    ]

    items = lexical_analysis._topic_items(
        FakeTopicModel(),
        topics=[0],
        documents=[clips[0].transcript],
        clips=clips,
        public_audio_keys={"clip-1"},
    )

    assert items[0]["examples"] == [
        {
            "channel": "14",
            "started_at": "2026-06-04T15:00:00Z",
            "duration_seconds": 6.0,
            "text": "Seattle Traffic, west waterway test.",
            "audio_public_filename": lexical_analysis._public_audio_filename(clips[0]),
        }
    ]


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


def _recent_analysis_clip(
    *,
    key: str,
    channel: str,
    started_at: str,
    transcript: str,
    quality_status: str,
    quality_score: float,
) -> RecentTranscribedClip:
    return RecentTranscribedClip(
        key=key,
        channel=channel,
        started_at=started_at,
        ended_at=None,
        duration_seconds=8.0,
        content_type="audio/mpeg",
        transcript=transcript,
        segments=[],
        quality_status=quality_status,
        quality_score=quality_score,
    )


class FakeAnalysisClipStore:
    def __init__(self, clips: list[TranscriptClip]) -> None:
        self.clips = clips
        self.calls: list[dict[str, object]] = []

    def recent_transcribed(
        self,
        *,
        limit: int,
        offset: int = 0,
        excluded_channels: tuple[str, ...] = (),
    ):
        self.calls.append(
            {
                "limit": limit,
                "excluded_channels": excluded_channels,
                "offset": offset,
            }
        )
        return self.clips[offset : offset + limit]


class StreamingAnalysisClipStore:
    def __init__(self, clips: list[TranscriptClip]) -> None:
        self.clips = clips
        self.iter_calls: list[dict[str, object]] = []
        self.recent_calls: list[dict[str, object]] = []

    def iter_recent_transcribed(
        self,
        *,
        page_size: int,
        excluded_channels: tuple[str, ...] = (),
    ):
        self.iter_calls.append(
            {"page_size": page_size, "excluded_channels": excluded_channels}
        )
        yield from self.clips

    def recent_transcribed(self, **kwargs):
        self.recent_calls.append(kwargs)
        raise AssertionError("offset pagination should not be used")


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
