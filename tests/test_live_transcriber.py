from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from talkingboats.live_transcriber import (
    TranscriptState,
    TranscriptStore,
    append_transcript_segments,
    build_ffmpeg_pcm_command,
    iter_encoded_audio_chunks,
)


def test_transcript_state_keeps_latest_entries_bounded() -> None:
    state = TranscriptState(max_entries=2)

    state.add_entry(
        text="one", started_at="2026-05-24T17:00:00Z", ended_at="2026-05-24T17:00:02Z"
    )
    state.add_entry(
        text="two", started_at="2026-05-24T17:00:02Z", ended_at="2026-05-24T17:00:04Z"
    )
    state.add_entry(
        text="three", started_at="2026-05-24T17:00:04Z", ended_at="2026-05-24T17:00:06Z"
    )

    payload = state.payload()

    assert [entry["text"] for entry in payload["entries"]] == ["two", "three"]
    assert payload["status"] == "running"
    assert "updated_at" in payload


def test_transcript_state_clears_stream_error_when_audio_resumes() -> None:
    state = TranscriptState(max_entries=2)
    state.set_error("stream ended; reconnecting")

    state.mark_running()

    payload = state.payload()
    assert payload["status"] == "running"
    assert payload["error"] is None
    assert "updated_at" in payload


def test_append_transcript_segments_ignores_empty_text() -> None:
    state = TranscriptState(max_entries=10)
    chunk_started = datetime(2026, 5, 24, 17, 0, tzinfo=UTC)
    segments = [
        SimpleNamespace(start=0.0, end=1.2, text="  "),
        SimpleNamespace(start=1.2, end=2.5, text=" marine traffic radio "),
    ]

    append_transcript_segments(state, segments, chunk_started=chunk_started)

    payload = state.payload()
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["text"] == "marine traffic radio"
    assert payload["entries"][0]["started_at"] == "2026-05-24T17:00:01Z"
    assert payload["entries"][0]["ended_at"] == "2026-05-24T17:00:02Z"


def test_transcript_state_persists_entries_to_sqlite(tmp_path) -> None:
    db_path = tmp_path / "transcripts.sqlite3"
    state = TranscriptState(max_entries=10, store=TranscriptStore(db_path))

    state.add_entry(
        text="  Recreational traffic near the marina  ",
        started_at="2026-05-24T17:00:01Z",
        ended_at="2026-05-24T17:00:04Z",
    )
    state.add_entry(
        text="Recreational traffic near the marina",
        started_at="2026-05-24T17:00:01Z",
        ended_at="2026-05-24T17:00:04Z",
    )

    reopened = TranscriptStore(db_path)
    assert reopened.count_entries() == 1
    assert reopened.recent_entries(limit=5) == [
        {
            "text": "Recreational traffic near the marina",
            "started_at": "2026-05-24T17:00:01Z",
            "ended_at": "2026-05-24T17:00:04Z",
        }
    ]


def test_ffmpeg_command_downsamples_stream_and_applies_optional_filter() -> None:
    command = build_ffmpeg_pcm_command(
        "http://pi.test:8000/talkingboats-live.mp3",
        sample_rate_hz=16_000,
        audio_filter="highpass=f=250,lowpass=f=3200",
    )

    assert command[:3] == ["ffmpeg", "-hide_banner", "-loglevel"]
    assert "-i" in command
    assert "http://pi.test:8000/talkingboats-live.mp3" in command
    assert command[command.index("-af") + 1] == "highpass=f=250,lowpass=f=3200"
    assert command[-3:] == ["-f", "s16le", "pipe:1"]


def test_encoded_audio_chunking_requires_positive_window() -> None:
    try:
        next(iter_encoded_audio_chunks("http://example.test/stream.mp3", chunk_seconds=0))
    except ValueError as exc:
        assert "chunk_seconds must be positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")
