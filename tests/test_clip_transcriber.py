from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from talkingboats.clip_transcriber import (
    ClipNotAvailable,
    UploadedClipStore,
    process_pending_uploads_once,
)
from talkingboats.schemas import ClipPresignRequest


def test_uploaded_clip_transcriber_persists_clip_segments(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    store.record_presigned_upload(
        key="raw/channel=68/date=2026-05-24/20260524T210000Z-test.mp3",
        request=_clip_request(),
    )

    summary = process_pending_uploads_once(
        store=store,
        clip_reader=WritingClipReader(),
        model=FakeSpeechModel(),
        limit=10,
    )

    clip = store.get_clip("raw/channel=68/date=2026-05-24/20260524T210000Z-test.mp3")
    assert summary.transcribed == 1
    assert clip is not None
    assert clip.status == "transcribed"
    assert clip.transcript == "Seattle traffic inbound for the locks"
    assert store.segments_for_clip(clip.key) == [
        {
            "text": "Seattle traffic inbound for the locks",
            "started_at": "2026-05-24T21:00:00Z",
            "ended_at": "2026-05-24T21:00:03Z",
        }
    ]
    assert FakeSpeechModel.last_kwargs["vad_filter"] is False


def test_uploaded_clip_transcriber_leaves_missing_objects_retryable(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    key = "raw/channel=68/date=2026-05-24/20260524T210000Z-test.mp3"
    store.record_presigned_upload(key=key, request=_clip_request())

    summary = process_pending_uploads_once(
        store=store,
        clip_reader=MissingClipReader(),
        model=FakeSpeechModel(),
        limit=10,
    )

    clip = store.get_clip(key)
    assert summary.waiting_upload == 1
    assert clip is not None
    assert clip.status == "waiting_upload"
    assert "not available" in (clip.error or "")


def test_uploaded_clip_transcriber_marks_low_confidence_segments_empty(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    key = "raw/channel=14/date=2026-05-24/20260524T210000Z-static.mp3"
    store.record_presigned_upload(key=key, request=_clip_request(channel="14"))

    summary = process_pending_uploads_once(
        store=store,
        clip_reader=WritingClipReader(expected_channel="14"),
        model=LowConfidenceSpeechModel(),
        limit=10,
        min_segment_avg_logprob=-0.6,
    )

    clip = store.get_clip(key)
    assert summary.empty == 1
    assert clip is not None
    assert clip.status == "empty"
    assert clip.transcript == ""
    assert store.segments_for_clip(clip.key) == []


def test_uploaded_clip_transcriber_marks_known_static_hallucinations_empty(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    key = "raw/channel=14/date=2026-05-24/20260524T210000Z-static.mp3"
    store.record_presigned_upload(key=key, request=_clip_request(channel="14"))

    summary = process_pending_uploads_once(
        store=store,
        clip_reader=WritingClipReader(expected_channel="14"),
        model=KnownStaticHallucinationSpeechModel(),
        limit=10,
    )

    clip = store.get_clip(key)
    assert summary.empty == 1
    assert clip is not None
    assert clip.status == "empty"
    assert clip.transcript == ""
    assert store.segments_for_clip(clip.key) == []


def test_uploaded_clip_transcriber_retries_interrupted_processing_rows(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    key = "raw/channel=68/date=2026-05-24/20260524T210000Z-test.mp3"
    store.record_presigned_upload(key=key, request=_clip_request())
    store.mark_processing(key)

    summary = process_pending_uploads_once(
        store=store,
        clip_reader=WritingClipReader(),
        model=FakeSpeechModel(),
        limit=10,
    )

    clip = store.get_clip(key)
    assert summary.transcribed == 1
    assert clip is not None
    assert clip.status == "transcribed"


def test_recent_transcribed_clips_returns_newest_with_segments(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    older_key = "raw/channel=14/date=2026-05-24/20260524T210000Z-older.mp3"
    newer_key = "raw/channel=13/date=2026-05-24/20260524T213000Z-newer.mp3"
    pending_key = "raw/channel=16/date=2026-05-24/20260524T214000Z-pending.mp3"
    store.record_presigned_upload(key=older_key, request=_clip_request(channel="14"))
    store.record_presigned_upload(
        key=newer_key,
        request=_clip_request(channel="13", started_at="2026-05-24T21:30:00Z"),
    )
    store.record_presigned_upload(
        key=pending_key,
        request=_clip_request(channel="16", started_at="2026-05-24T21:40:00Z"),
    )
    store.mark_transcribed(
        older_key,
        [
            _segment("Older traffic", "2026-05-24T21:00:00Z", "2026-05-24T21:00:03Z"),
        ],
    )
    store.mark_transcribed(
        newer_key,
        [
            _segment("First segment", "2026-05-24T21:30:00Z", "2026-05-24T21:30:02Z"),
            _segment("Second segment", "2026-05-24T21:30:02Z", "2026-05-24T21:30:04Z"),
        ],
    )

    clips = store.recent_transcribed(limit=10)

    assert [clip.key for clip in clips] == [newer_key, older_key]
    assert clips[0].channel == "13"
    assert clips[0].transcript == "First segment Second segment"
    assert [segment["text"] for segment in clips[0].segments] == ["First segment", "Second segment"]

    channel_14_clips = store.recent_transcribed(limit=10, channel="14")

    assert [clip.key for clip in channel_14_clips] == [older_key]


def _clip_request(
    *,
    channel: str = "68",
    started_at: str = "2026-05-24T21:00:00Z",
) -> ClipPresignRequest:
    ended_at = (datetime.fromisoformat(started_at.replace("Z", "+00:00")) + timedelta(seconds=5))
    ended_at_text = ended_at.isoformat().replace("+00:00", "Z")
    return ClipPresignRequest(
        channel=channel,
        started_at=started_at,
        ended_at=ended_at_text,
        content_type="audio/mpeg",
        idempotency_key=f"radio-event-{channel}-{started_at}",
        duration_seconds=5.0,
    )


def _segment(text: str, started_at: str, ended_at: str):
    return SimpleNamespace(
        text=text,
        started_at=started_at,
        ended_at=ended_at,
        relative_start_seconds=0.0,
        relative_end_seconds=3.0,
    )


class WritingClipReader:
    def __init__(self, *, expected_channel: str = "68") -> None:
        self.expected_channel = expected_channel

    def download(self, key: str, output_path) -> None:
        assert key.startswith(f"raw/channel={self.expected_channel}/")
        output_path.write_bytes(b"fake mp3")


class MissingClipReader:
    def download(self, key: str, output_path) -> None:
        raise ClipNotAvailable(f"{key} not available yet")


class FakeSpeechModel:
    last_kwargs = {}

    def transcribe(self, path: str, **kwargs):
        FakeSpeechModel.last_kwargs = kwargs
        return (
            [
                SimpleNamespace(
                    start=0.0,
                    end=3.0,
                    text=" Seattle traffic inbound for the locks ",
                )
            ],
            None,
        )


class LowConfidenceSpeechModel:
    def transcribe(self, path: str, **kwargs):
        return (
            [
                SimpleNamespace(
                    start=0.0,
                    end=30.0,
                    text=" Thank you. ",
                    avg_logprob=-0.95,
                )
            ],
            None,
        )


class KnownStaticHallucinationSpeechModel:
    def transcribe(self, path: str, **kwargs):
        return (
            [
                SimpleNamespace(
                    start=0.0,
                    end=30.0,
                    text=" Thank you. ",
                    avg_logprob=-0.2,
                )
            ],
            None,
        )
