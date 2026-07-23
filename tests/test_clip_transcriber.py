from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from talkingboats.clip_transcriber import (
    ClipNotAvailable,
    ClipQualityMetadata,
    UploadedClipStore,
    _transcriber_start_log_fields,
    is_displayable_transcript,
    process_pending_uploads_once,
)
from talkingboats.schemas import ClipPresignRequest
from talkingboats.transcript_cleanup import cleanup_noise_transcripts


def test_uploaded_clip_transcriber_persists_clip_segments(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    event_store = CapturingEventStore()
    store = UploadedClipStore(db_path, event_store=event_store)
    store.record_presigned_upload(
        key="raw/channel=68/date=2026-05-24/20260524T210000Z-test.mp3",
        request=_clip_request(),
    )

    summary = process_pending_uploads_once(
        store=store,
        clip_reader=WritingClipReader(),
        model=FakeSpeechModel(),
        limit=10,
        audio_filter=None,
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
    assert FakeSpeechModel.last_kwargs["vad_filter"] is True
    assert FakeSpeechModel.last_kwargs["vad_parameters"] == {
        "min_silence_duration_ms": 500,
        "speech_pad_ms": 400,
    }
    assert FakeSpeechModel.last_kwargs["beam_size"] == 5
    assert [event["event_type"] for event in event_store.events] == [
        "clip.processing",
        "clip.transcribed",
    ]
    assert event_store.events[-1]["payload"]["transcript"] == (
        "Seattle traffic inbound for the locks"
    )
    assert event_store.events[-1]["payload"]["segments"] == [
        {
            "text": "Seattle traffic inbound for the locks",
            "started_at": "2026-05-24T21:00:00Z",
            "ended_at": "2026-05-24T21:00:03Z",
            "relative_start_seconds": 0.0,
            "relative_end_seconds": 3.0,
        }
    ]


def test_uploaded_clip_transcriber_prepares_audio_before_model_transcription(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    key = "raw/channel=68/date=2026-05-24/20260524T210000Z-test.mp3"
    store.record_presigned_upload(key=key, request=_clip_request())
    model = FakeSpeechModel()
    ffmpeg_calls = []

    def fake_ffmpeg(command, *, check):
        ffmpeg_calls.append((command, check))
        output_path = command[-1]
        assert output_path.endswith(".wav")
        Path(output_path).write_bytes(b"RIFFprepared wav")

    summary = process_pending_uploads_once(
        store=store,
        clip_reader=WritingClipReader(),
        model=model,
        limit=10,
        audio_filter="highpass=f=250,lowpass=f=3200,afftdn=nf=-28",
        sample_rate_hz=16_000,
        beam_size=5,
        hotwords="Seattle Traffic, Elliott Bay, VTS",
        ffmpeg_path="ffmpeg",
        ffmpeg_runner=fake_ffmpeg,
    )

    assert summary.transcribed == 1
    assert ffmpeg_calls
    assert ffmpeg_calls[0][1] is True
    assert "-af" in ffmpeg_calls[0][0]
    assert FakeSpeechModel.last_path.endswith(".wav")
    assert FakeSpeechModel.last_path != ffmpeg_calls[0][0][ffmpeg_calls[0][0].index("-i") + 1]
    assert not Path(FakeSpeechModel.last_path).exists()
    assert FakeSpeechModel.last_kwargs["beam_size"] == 5
    assert FakeSpeechModel.last_kwargs["hotwords"] == "Seattle Traffic, Elliott Bay, VTS"


def test_uploaded_clip_transcriber_can_trust_edge_preprocessed_mp3(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    key = "raw/channel=68/date=2026-05-24/20260524T210000Z-edge.mp3"
    store.record_presigned_upload(key=key, request=_clip_request())
    ffmpeg_calls = []

    def fake_ffmpeg(command, *, check):
        ffmpeg_calls.append((command, check))
        Path(command[-1]).write_bytes(b"RIFFprepared wav")

    summary = process_pending_uploads_once(
        store=store,
        clip_reader=WritingClipReader(),
        model=FakeSpeechModel(),
        limit=10,
        audio_filter="highpass=f=250,lowpass=f=3200,afftdn=nf=-28",
        trust_edge_preprocessed_audio=True,
        ffmpeg_runner=fake_ffmpeg,
    )

    assert summary.transcribed == 1
    assert ffmpeg_calls == []
    assert FakeSpeechModel.last_path.endswith(".mp3")


def test_dynamo_transcriber_start_log_does_not_report_sqlite_path(tmp_path) -> None:
    fields = _transcriber_start_log_fields(
        bucket="raw-audio",
        db_path=tmp_path / "clips.sqlite3",
        clip_store_backend="dynamodb",
    )

    assert fields == {"bucket": "raw-audio", "clip_store_backend": "dynamodb"}


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
        audio_filter=None,
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
        audio_filter=None,
    )

    clip = store.get_clip(key)
    assert summary.empty == 1
    assert clip is not None
    assert clip.status == "empty"
    assert clip.transcript == ""
    assert store.segments_for_clip(clip.key) == []


def test_uploaded_clip_transcriber_marks_subtitle_credit_hallucinations_empty(
    tmp_path,
) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    key = "raw/channel=09/date=2026-06-02/20260602T141900Z-static.mp3"
    store.record_presigned_upload(key=key, request=_clip_request(channel="09"))

    summary = process_pending_uploads_once(
        store=store,
        clip_reader=WritingClipReader(expected_channel="09"),
        model=SubtitleCreditHallucinationSpeechModel(),
        limit=10,
        audio_filter=None,
    )

    clip = store.get_clip(key)
    assert summary.empty == 1
    assert clip is not None
    assert clip.status == "empty"
    assert clip.transcript == ""
    assert store.segments_for_clip(clip.key) == []


def test_uploaded_clip_transcriber_marks_ellipsis_only_segments_empty(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    key = "raw/channel=14/date=2026-06-02/20260602T141900Z-ellipsis.mp3"
    store.record_presigned_upload(key=key, request=_clip_request(channel="14"))

    summary = process_pending_uploads_once(
        store=store,
        clip_reader=WritingClipReader(expected_channel="14"),
        model=EllipsisOnlySpeechModel(),
        limit=10,
        audio_filter=None,
    )

    clip = store.get_clip(key)
    assert summary.empty == 1
    assert clip is not None
    assert clip.status == "empty"
    assert clip.transcript == ""
    assert store.segments_for_clip(clip.key) == []


def test_uploaded_clip_transcriber_marks_repeated_plosive_hallucinations_empty(
    tmp_path,
) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    key = "raw/channel=10/date=2026-06-13/20260613T233031Z-static.mp3"
    store.record_presigned_upload(key=key, request=_clip_request(channel="10"))

    summary = process_pending_uploads_once(
        store=store,
        clip_reader=WritingClipReader(expected_channel="10"),
        model=RepeatedPlosiveHallucinationSpeechModel(),
        limit=10,
        audio_filter=None,
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
        audio_filter=None,
    )

    clip = store.get_clip(key)
    assert summary.transcribed == 1
    assert clip is not None
    assert clip.status == "transcribed"


def test_uploaded_clip_store_ignores_duplicate_idempotency_key(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    first_key = "raw/channel=13/date=2026-05-24/20260524T210000Z-first.mp3"
    second_key = "raw/channel=13/date=2026-05-24/20260524T210030Z-second.mp3"
    first_request = _clip_request(channel="13", started_at="2026-05-24T21:00:00Z")
    second_request = _clip_request(channel="13", started_at="2026-05-24T21:00:30Z").model_copy(
        update={"idempotency_key": first_request.idempotency_key}
    )

    store.record_presigned_upload(key=first_key, request=first_request)
    store.record_presigned_upload(key=second_key, request=second_request)

    pending = store.pending_uploads(limit=10)
    assert [clip.key for clip in pending] == [first_key]


def test_uploaded_clip_store_returns_newest_pending_first(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    older_key = "raw/channel=13/date=2026-05-24/20260524T210000Z-first.mp3"
    newer_key = "raw/channel=14/date=2026-05-24/20260524T213000Z-second.mp3"
    store.record_presigned_upload(
        key=older_key,
        request=_clip_request(channel="13", started_at="2026-05-24T21:00:00Z"),
    )
    store.record_presigned_upload(
        key=newer_key,
        request=_clip_request(channel="14", started_at="2026-05-24T21:30:00Z"),
    )

    pending = store.pending_uploads(limit=1)

    assert [clip.key for clip in pending] == [newer_key]


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
    assert store.received_clip_count() == 3

    channel_14_clips = store.recent_transcribed(limit=10, channel="14")

    assert [clip.key for clip in channel_14_clips] == [older_key]


def test_recent_transcribed_clips_hide_quarantined_by_default(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    good_key = "raw/channel=14/date=2026-05-24/20260524T210000Z-good.mp3"
    noisy_key = "raw/channel=66A/date=2026-05-24/20260524T213000Z-noisy.mp3"
    store.record_presigned_upload(key=good_key, request=_clip_request(channel="14"))
    store.record_presigned_upload(
        key=noisy_key,
        request=_clip_request(channel="66A", started_at="2026-05-24T21:30:00Z"),
    )
    store.mark_transcribed(
        good_key,
        [_segment("Seattle Traffic roger", "2026-05-24T21:00:00Z", "2026-05-24T21:00:02Z")],
        quality=ClipQualityMetadata(quality_status="ok", quality_score=91.0),
    )
    store.mark_transcribed(
        noisy_key,
        [_segment("No address is moving", "2026-05-24T21:30:00Z", "2026-05-24T21:30:03Z")],
        quality=ClipQualityMetadata(
            quality_status="quarantined",
            quality_score=24.0,
            quality_reason="low_snr",
            quality_flags=("low_snr",),
            audio_metrics={"speech_contrast_db": 1.4, "hiss_band_ratio": 0.32},
        ),
    )

    visible = store.recent_transcribed(limit=10)
    quarantined = store.recent_transcribed(limit=10, quality="quarantined")
    all_clips = store.recent_transcribed(limit=10, quality="all")

    assert [clip.key for clip in visible] == [good_key]
    assert [clip.key for clip in quarantined] == [noisy_key]
    assert quarantined[0].quality_status == "quarantined"
    assert quarantined[0].quality_reason == "low_snr"
    assert quarantined[0].quality_flags == ("low_snr",)
    assert quarantined[0].audio_metrics["speech_contrast_db"] == 1.4
    assert [clip.key for clip in all_clips] == [noisy_key, good_key]
    assert store.transcribed_channel_counts() == {"14": 1}
    assert store.transcribed_channel_counts(quality="quarantined") == {"66A": 1}


def test_recent_transcribed_clips_hide_legacy_ellipsis_only_rows(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    good_key = "raw/channel=14/date=2026-05-24/20260524T210000Z-good.mp3"
    ellipsis_key = "raw/channel=14/date=2026-05-24/20260524T213000Z-ellipsis.mp3"
    store.record_presigned_upload(key=good_key, request=_clip_request(channel="14"))
    store.record_presigned_upload(
        key=ellipsis_key,
        request=_clip_request(channel="14", started_at="2026-05-24T21:30:00Z"),
    )
    store.mark_transcribed(
        good_key,
        [_segment("Seattle Traffic roger", "2026-05-24T21:00:00Z", "2026-05-24T21:00:03Z")],
    )
    _seed_legacy_transcribed_clip(db_path, ellipsis_key, transcript="... ... ...")

    clips = store.recent_transcribed(limit=10)

    assert [clip.key for clip in clips] == [good_key]
    assert store.transcribed_channel_counts() == {"14": 1}
    assert store.transcribed_clip_count(channel="14") == 1


def test_recent_transcribed_clips_hide_legacy_repeated_noise_rows(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    good_key = "raw/channel=10/date=2026-06-13/20260613T232949Z-good.mp3"
    noise_key = "raw/channel=10/date=2026-06-13/20260613T233031Z-noise.mp3"
    store.record_presigned_upload(key=good_key, request=_clip_request(channel="10"))
    store.record_presigned_upload(
        key=noise_key,
        request=_clip_request(channel="10", started_at="2026-06-13T23:30:31Z"),
    )
    store.mark_transcribed(
        good_key,
        [
            _segment(
                "Do you have a channel there, Cap?",
                "2026-06-13T21:00:00Z",
                "2026-06-13T21:00:03Z",
            )
        ],
    )
    _seed_legacy_transcribed_clip(
        db_path,
        noise_key,
        transcript="Tuk, tuk, tuk, tuk, tuk, tuk, tuk, tuk, tuk.",
    )

    clips = store.recent_transcribed(limit=10, channel="10")

    assert [clip.key for clip in clips] == [good_key]
    assert store.transcribed_channel_counts() == {"10": 1}
    assert store.transcribed_clip_count(channel="10") == 1


def test_transcript_displayability_keeps_short_real_radio_phrases() -> None:
    assert is_displayable_transcript("PAN-PAN, PAN-PAN, all stations.")
    assert is_displayable_transcript("6-7, so yeah, whenever crew's back.")
    assert not is_displayable_transcript("P-P-P-P-P-P-P-P-P-P-P-P-P-")
    assert not is_displayable_transcript("Tuk, tuk, tuk, tuk, tuk, tuk.")
    assert not is_displayable_transcript("0 0 0 0 0 0 0 0 0")


def test_cleanup_noise_transcripts_does_not_skip_rows_after_mutating_sqlite_page(
    tmp_path,
) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    good_key = "raw/channel=10/date=2026-06-13/20260613T232949Z-good.mp3"
    noise_keys = [
        f"raw/channel=10/date=2026-06-13/20260613T2330{index}1Z-noise.mp3"
        for index in range(3)
    ]
    for index, key in enumerate([good_key, *noise_keys]):
        store.record_presigned_upload(
            key=key,
            request=_clip_request(channel="10", started_at=f"2026-06-13T23:30:0{index}Z"),
        )
    store.mark_transcribed(
        good_key,
        [
            _segment(
                "Do you have a channel there, Cap?",
                "2026-06-13T23:30:00Z",
                "2026-06-13T23:30:03Z",
            )
        ],
    )
    for key in noise_keys:
        _seed_legacy_transcribed_clip(
            db_path,
            key,
            transcript="Tuk, tuk, tuk, tuk, tuk, tuk, tuk, tuk, tuk.",
        )

    summary = cleanup_noise_transcripts(store, dry_run=False, page_size=2)

    assert summary.scanned == 4
    assert summary.candidates == 3
    assert summary.cleaned == 3
    assert [store.get_clip(key).status for key in noise_keys] == ["empty", "empty", "empty"]
    assert [clip.key for clip in store.recent_transcribed(limit=10)] == [good_key]


def test_transcript_corrections_override_recent_text_and_export_training_pairs(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    key = "raw/channel=14/date=2026-05-24/20260524T213000Z-pan-pan.mp3"
    store.record_presigned_upload(
        key=key,
        request=_clip_request(channel="14", started_at="2026-05-24T21:30:00Z"),
    )
    store.mark_transcribed(
        key,
        [_segment("PON PON all stations", "2026-05-24T21:30:00Z", "2026-05-24T21:30:03Z")],
    )

    correction = store.correct_transcript(
        channel="14",
        started_at="2026-05-24T21:30:00Z",
        corrected_transcript="PAN-PAN, all stations.",
        reviewer="rob",
        note="marine urgency proword",
    )

    assert correction.key == key
    assert correction.original_transcript == "PON PON all stations"
    assert correction.corrected_transcript == "PAN-PAN, all stations."
    clips = store.recent_transcribed(limit=10, channel="14")
    assert clips[0].transcript == "PAN-PAN, all stations."
    assert clips[0].transcript_reviewed is True
    assert store.transcript_corrections(limit=10) == [
        {
            "key": key,
            "channel": "14",
            "started_at": "2026-05-24T21:30:00Z",
            "ended_at": "2026-05-24T21:30:05Z",
            "duration_seconds": 5.0,
            "content_type": "audio/mpeg",
            "original_transcript": "PON PON all stations",
            "corrected_transcript": "PAN-PAN, all stations.",
            "reviewer": "rob",
            "note": "marine urgency proword",
            "include_in_training": True,
            "training_quality": "good",
            "training_split": "auto",
            "training_flags": [],
            "training_reason": None,
        }
    ]

    updated = store.correct_transcript(
        channel="14",
        started_at="2026-05-24T21:30:00Z",
        corrected_transcript="PAN-PAN, PAN-PAN, all stations.",
    )
    assert updated.original_transcript == "PON PON all stations"
    assert updated.corrected_transcript == "PAN-PAN, PAN-PAN, all stations."
    assert store.transcript_corrections_for_training()[0]["corrected_transcript"] == (
        "PAN-PAN, PAN-PAN, all stations."
    )
    assert store.transcript_corrections(limit=10)[0]["include_in_training"] is True

    store.correct_transcript(
        channel="14",
        started_at="2026-05-24T21:30:00Z",
        corrected_transcript="PAN-PAN, PAN-PAN, all stations.",
        include_in_training=False,
    )
    assert store.transcript_corrections_for_training() == []
    assert store.transcript_corrections(limit=10)[0]["include_in_training"] is False

    store.correct_transcript(
        channel="14",
        started_at="2026-05-24T21:30:00Z",
        corrected_transcript="PAN-PAN, PAN-PAN, all stations.",
        include_in_training=True,
        training_quality="good",
        training_split="validation",
        training_flags=["low_snr"],
        training_reason="clear domain phrase despite noise",
    )
    assert store.transcript_corrections(limit=10)[0]["include_in_training"] is True
    exported = store.transcript_corrections_for_training()
    assert exported == [
        {
            "key": key,
            "channel": "14",
            "started_at": "2026-05-24T21:30:00Z",
            "ended_at": "2026-05-24T21:30:05Z",
            "duration_seconds": 5.0,
            "content_type": "audio/mpeg",
            "original_transcript": "PON PON all stations",
            "corrected_transcript": "PAN-PAN, PAN-PAN, all stations.",
            "reviewer": "rob",
            "note": None,
            "include_in_training": True,
            "training_quality": "good",
            "training_split": "validation",
            "training_flags": ["low_snr"],
            "training_reason": "clear domain phrase despite noise",
        }
    ]


def test_transcript_correction_can_be_removed_from_training_and_recent_reviewed_filter(
    tmp_path,
) -> None:
    db_path = tmp_path / "radio.sqlite3"
    event_store = CapturingEventStore()
    store = UploadedClipStore(db_path, event_store=event_store)
    key = "raw/channel=14/date=2026-05-24/20260524T213000Z-pan-pan.mp3"
    store.record_presigned_upload(
        key=key,
        request=_clip_request(channel="14", started_at="2026-05-24T21:30:00Z"),
    )
    store.mark_transcribed(
        key,
        [_segment("PON PON all stations", "2026-05-24T21:30:00Z", "2026-05-24T21:30:03Z")],
    )
    store.correct_transcript(
        channel="14",
        started_at="2026-05-24T21:30:00Z",
        corrected_transcript="PAN-PAN, all stations.",
        reviewer="rob",
    )

    removed = store.remove_transcript_correction(
        channel="14",
        started_at="2026-05-24T21:30:00Z",
    )

    assert removed.key == key
    assert removed.original_transcript == "PON PON all stations"
    assert removed.corrected_transcript == "PAN-PAN, all stations."
    assert store.transcript_corrections(limit=10) == []
    assert store.transcript_corrections_for_training() == []
    assert store.recent_transcribed(limit=10, reviewed_only=True) == []
    recent = store.recent_transcribed(limit=10, channel="14")
    assert recent[0].transcript == "PON PON all stations"
    assert recent[0].transcript_reviewed is False
    assert event_store.events[-1]["event_type"] == "clip.transcript_correction_removed"


def test_transcript_training_examples_reject_blocking_quality_flags(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    store = UploadedClipStore(db_path)
    key = "raw/channel=14/date=2026-05-24/20260524T213000Z-static.mp3"
    store.record_presigned_upload(
        key=key,
        request=_clip_request(channel="14", started_at="2026-05-24T21:30:00Z"),
    )
    store.mark_transcribed(
        key,
        [_segment("Static burst", "2026-05-24T21:30:00Z", "2026-05-24T21:30:03Z")],
    )

    try:
        store.correct_transcript(
            channel="14",
            started_at="2026-05-24T21:30:00Z",
            corrected_transcript="Static burst",
            include_in_training=True,
            training_quality="good",
            training_flags=["static_or_no_speech"],
        )
    except ValueError as exc:
        assert "cannot include blocking training flags" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_featured_clips_can_be_starred_filtered_and_unstarred(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    event_store = CapturingEventStore()
    store = UploadedClipStore(db_path, event_store=event_store)
    older_key = "raw/channel=14/date=2026-05-24/20260524T210000Z-older.mp3"
    newer_key = "raw/channel=68/date=2026-05-24/20260524T213000Z-newer.mp3"
    store.record_presigned_upload(
        key=older_key,
        request=_clip_request(channel="14", started_at="2026-05-24T21:00:00Z"),
    )
    store.record_presigned_upload(
        key=newer_key,
        request=_clip_request(channel="68", started_at="2026-05-24T21:30:00Z"),
    )
    store.mark_transcribed(
        older_key,
        [_segment("Routine traffic", "2026-05-24T21:00:00Z", "2026-05-24T21:00:03Z")],
    )
    store.mark_transcribed(
        newer_key,
        [_segment("Hall of fame audio", "2026-05-24T21:30:00Z", "2026-05-24T21:30:03Z")],
    )

    feature = store.set_clip_featured(
        channel="68",
        started_at="2026-05-24T21:30:00Z",
        featured=True,
        featured_by="operator-ui",
    )

    assert feature.key == newer_key
    assert feature.featured is True
    assert feature.featured_by == "operator-ui"
    recent = store.recent_transcribed(limit=10)
    assert [(clip.key, clip.featured) for clip in recent] == [
        (newer_key, True),
        (older_key, False),
    ]
    hall_of_fame = store.recent_transcribed(limit=10, featured_only=True)
    assert [clip.key for clip in hall_of_fame] == [newer_key]
    assert store.transcribed_clip_count(featured_only=True) == 1
    assert [event["event_type"] for event in event_store.events][-1] == "clip.featured"

    removed = store.set_clip_featured(
        channel="68",
        started_at="2026-05-24T21:30:00Z",
        featured=False,
        featured_by="operator-ui",
    )

    assert removed.featured is False
    assert store.recent_transcribed(limit=10, featured_only=True) == []
    assert store.transcribed_clip_count(featured_only=True) == 0
    assert [event["event_type"] for event in event_store.events][-1] == "clip.unfeatured"


def _clip_request(
    *,
    channel: str = "68",
    started_at: str = "2026-05-24T21:00:00Z",
) -> ClipPresignRequest:
    ended_at = datetime.fromisoformat(started_at.replace("Z", "+00:00")) + timedelta(seconds=5)
    ended_at_text = ended_at.isoformat().replace("+00:00", "Z")
    return ClipPresignRequest(
        channel=channel,
        started_at=started_at,
        ended_at=ended_at_text,
        content_type="audio/mpeg",
        idempotency_key=f"radio-event-{channel}-{started_at}",
        duration_seconds=5.0,
    )


def _seed_legacy_transcribed_clip(db_path: Path, key: str, *, transcript: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE uploaded_clips
            SET status = 'transcribed',
                transcript = ?,
                error = NULL
            WHERE key = ?
            """,
            (transcript, key),
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


class CapturingEventStore:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def record_clip_event(
        self,
        event_type: str,
        *,
        key: str,
        payload,
        idempotency_key: str,
        observed_at=None,
    ) -> None:
        self.events.append(
            {
                "event_type": event_type,
                "key": key,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "observed_at": observed_at,
            }
        )


class FakeSpeechModel:
    last_kwargs = {}
    last_path = ""

    def transcribe(self, path: str, **kwargs):
        FakeSpeechModel.last_path = path
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


class SubtitleCreditHallucinationSpeechModel:
    def transcribe(self, path: str, **kwargs):
        return (
            [
                SimpleNamespace(
                    start=0.0,
                    end=30.0,
                    text=" Subs by www.zeoranger.co.uk ",
                    avg_logprob=-0.2,
                )
            ],
            None,
        )


class EllipsisOnlySpeechModel:
    def transcribe(self, path: str, **kwargs):
        return (
            [
                SimpleNamespace(
                    start=0.0,
                    end=30.0,
                    text=" ... ... ... ",
                    avg_logprob=-0.2,
                )
            ],
            None,
        )


class RepeatedPlosiveHallucinationSpeechModel:
    def transcribe(self, path: str, **kwargs):
        return (
            [
                SimpleNamespace(
                    start=0.0,
                    end=4.0,
                    text=" Tuk, tuk, tuk, tuk, tuk, tuk, tuk, tuk, tuk. ",
                    avg_logprob=-0.2,
                )
            ],
            None,
        )
