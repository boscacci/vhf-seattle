from __future__ import annotations

import json
import os
import wave
from array import array
from datetime import UTC, datetime, timedelta

from talkingboats.edge_capture import (
    ContinuousWavRecorder,
    EdgeCaptureConfig,
    EdgeClip,
    SegmentUploadRequest,
    SegmentUploadWorker,
    ThermalPolicy,
    build_activity_upload_request,
    detect_activity_clips,
    infer_audio_content_type,
    should_pause_processing,
    squelched_pcm_chunks,
    write_spooled_clip,
)


def test_detect_activity_keeps_pre_and_post_roll_and_ignores_silence() -> None:
    started_at = datetime(2026, 5, 24, 13, 30, tzinfo=UTC)
    config = EdgeCaptureConfig(
        channel="68",
        sample_rate_hz=1_000,
        frame_ms=100,
        threshold_rms=1_000,
        min_clip_seconds=0.2,
        max_clip_seconds=10,
        pre_roll_seconds=0.2,
        post_roll_seconds=0.2,
    )
    pcm = b"".join(
        [
            _pcm(amplitude=0, seconds=0.3, sample_rate_hz=config.sample_rate_hz),
            _pcm(amplitude=5_000, seconds=0.5, sample_rate_hz=config.sample_rate_hz),
            _pcm(amplitude=0, seconds=0.4, sample_rate_hz=config.sample_rate_hz),
        ]
    )

    clips = list(detect_activity_clips([pcm], started_at=started_at, config=config))

    assert len(clips) == 1
    clip = clips[0]
    assert clip.started_at == started_at + timedelta(seconds=0.1)
    assert clip.ended_at == started_at + timedelta(seconds=1.0)
    assert clip.duration_seconds == 0.9
    assert clip.peak_amplitude == 5_000
    assert clip.rms_amplitude > config.threshold_rms


def test_detect_activity_splits_long_transmissions_at_max_clip_seconds() -> None:
    started_at = datetime(2026, 5, 24, 13, 30, tzinfo=UTC)
    config = EdgeCaptureConfig(
        channel="14",
        sample_rate_hz=1_000,
        frame_ms=100,
        threshold_rms=1_000,
        min_clip_seconds=0.1,
        max_clip_seconds=0.5,
        pre_roll_seconds=0,
        post_roll_seconds=0.1,
    )

    clips = list(
        detect_activity_clips(
            [_pcm(amplitude=4_000, seconds=1.2, sample_rate_hz=config.sample_rate_hz)],
            started_at=started_at,
            config=config,
        )
    )

    assert len(clips) >= 2
    assert all(clip.duration_seconds <= config.max_clip_seconds for clip in clips)


def test_squelched_pcm_chunks_mutes_inactive_frames_but_preserves_active_audio() -> None:
    config = EdgeCaptureConfig(
        channel="14",
        sample_rate_hz=1_000,
        frame_ms=100,
        threshold_rms=1_000,
        post_roll_seconds=0.1,
    )
    silent_frame = _pcm(amplitude=0, seconds=0.1, sample_rate_hz=config.sample_rate_hz)
    active_frame = _pcm(amplitude=4_000, seconds=0.1, sample_rate_hz=config.sample_rate_hz)
    quiet_frame = _pcm(amplitude=100, seconds=0.1, sample_rate_hz=config.sample_rate_hz)

    rendered = b"".join(
        squelched_pcm_chunks(
            [silent_frame + active_frame + quiet_frame + silent_frame],
            config=config,
        )
    )

    assert rendered == (b"\0" * len(silent_frame)) + active_frame + quiet_frame + (
        b"\0" * len(silent_frame)
    )


def test_thermal_policy_uses_hysteresis_for_cooling_down() -> None:
    policy = ThermalPolicy(max_temp_c=70.0, resume_temp_c=64.0, max_load_per_cpu=0.8)

    assert should_pause_processing(
        temp_c=71.0,
        load_1m=0.5,
        cpu_count=4,
        policy=policy,
        already_paused=False,
    )
    assert should_pause_processing(
        temp_c=66.0,
        load_1m=0.5,
        cpu_count=4,
        policy=policy,
        already_paused=True,
    )
    assert not should_pause_processing(
        temp_c=63.5,
        load_1m=0.5,
        cpu_count=4,
        policy=policy,
        already_paused=True,
    )
    assert should_pause_processing(
        temp_c=63.0,
        load_1m=4.0,
        cpu_count=4,
        policy=policy,
        already_paused=False,
    )


def test_write_spooled_clip_creates_audio_and_metadata(tmp_path) -> None:
    started_at = datetime(2026, 5, 24, 13, 30, tzinfo=UTC)
    clip = EdgeClip(
        channel="68",
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=0.2),
        sample_rate_hz=1_000,
        pcm_i16le=_pcm(amplitude=2_000, seconds=0.2, sample_rate_hz=1_000),
        peak_amplitude=2_000,
        rms_amplitude=2_000.0,
    )

    result = write_spooled_clip(clip, tmp_path)

    assert result.audio_path.suffix == ".wav"
    assert result.metadata_path.suffix == ".json"
    with wave.open(str(result.audio_path), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 1_000
        assert wav.getnframes() == 200
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["channel"] == "68"
    assert metadata["duration_seconds"] == 0.2
    assert metadata["audio_file"] == result.audio_path.name
    assert str(tmp_path) not in result.metadata_path.read_text(encoding="utf-8")


def test_continuous_wav_recorder_writes_fixed_segments_with_metadata(tmp_path) -> None:
    started_at = datetime(2026, 5, 24, 13, 30, tzinfo=UTC)
    recorder = ContinuousWavRecorder(
        output_dir=tmp_path,
        channel="14",
        stream_started_at=started_at,
        sample_rate_hz=1_000,
        segment_seconds=1,
        retention_seconds=60,
    )

    recorder.write(_pcm(amplitude=900, seconds=2.2, sample_rate_hz=1_000))
    recorder.close()

    audio_files = sorted(tmp_path.glob("continuous-channel-14-*.wav"))
    metadata_files = sorted(tmp_path.glob("continuous-channel-14-*.json"))
    assert len(audio_files) == 3
    assert len(metadata_files) == 3
    with wave.open(str(audio_files[0]), "rb") as wav:
        assert wav.getframerate() == 1_000
        assert wav.getnframes() == 1_000
    first_metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert first_metadata["channel"] == "14"
    assert first_metadata["started_at"] == "2026-05-24T13:30:00Z"
    assert first_metadata["ended_at"] == "2026-05-24T13:30:01Z"
    assert first_metadata["duration_seconds"] == 1.0
    assert first_metadata["recording_kind"] == "continuous"


def test_continuous_wav_recorder_expires_old_segments(tmp_path) -> None:
    old_audio = tmp_path / "continuous-channel-14-20260524T132000000000Z-old.wav"
    old_metadata = old_audio.with_suffix(".json")
    old_audio.write_bytes(b"old")
    old_metadata.write_text("{}\n", encoding="utf-8")
    now = datetime(2026, 5, 24, 13, 30, tzinfo=UTC)
    old_timestamp = (now - timedelta(seconds=120)).timestamp()
    for path in (old_audio, old_metadata):
        path.touch()
        os.utime(path, (old_timestamp, old_timestamp))

    recorder = ContinuousWavRecorder(
        output_dir=tmp_path,
        channel="14",
        stream_started_at=now,
        sample_rate_hz=1_000,
        segment_seconds=1,
        retention_seconds=60,
    )
    recorder.write(_pcm(amplitude=900, seconds=1, sample_rate_hz=1_000))
    recorder.close()

    assert not old_audio.exists()
    assert not old_metadata.exists()
    assert sorted(tmp_path.glob("continuous-channel-14-*.wav"))


def test_segment_upload_worker_uploads_continuous_segment_metadata(tmp_path) -> None:
    audio_path = tmp_path / "continuous-channel-68-20260524T133000000000Z.wav"
    metadata_path = audio_path.with_suffix(".json")
    audio_path.write_bytes(b"RIFFfake-wave")
    metadata_path.write_text(
        json.dumps(
            {
                "channel": "68",
                "started_at": "2026-05-24T13:30:00Z",
                "ended_at": "2026-05-24T13:31:00Z",
                "duration_seconds": 60.0,
                "content_type": "audio/wav",
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def uploader(api_base_url, ingest_token, request):
        calls.append((api_base_url, ingest_token, request))
        return type(
            "UploadResult",
            (),
            {
                "key": "raw/channel=68/date=2026-05-24/fake.wav",
                "bytes_uploaded": 13,
                "content_type": "audio/wav",
            },
        )()

    worker = SegmentUploadWorker(
        api_url="http://private-api.test",
        ingest_token="ingest-token",
        uploader=uploader,
    )

    worker.upload(audio_path, metadata_path)

    assert len(calls) == 1
    assert calls[0][0] == "http://private-api.test"
    assert calls[0][1] == "ingest-token"
    request = calls[0][2]
    assert request.channel == "68"
    assert request.audio_path == audio_path
    assert request.duration_seconds == 60.0
    assert request.content_type == "audio/wav"
    assert request.idempotency_key.startswith("continuous-v1:68:2026-05-24T13:30:00Z:")


def test_segment_upload_worker_uploads_activity_clip_without_httpx_dependency(tmp_path) -> None:
    audio_path = tmp_path / "activity.mp3"
    audio_path.write_bytes(b"fake mp3")
    calls = []
    started_at = datetime(2026, 5, 24, 13, 30, tzinfo=UTC)

    def uploader(api_base_url, ingest_token, request):
        calls.append((api_base_url, ingest_token, request))
        return type(
            "UploadResult",
            (),
            {
                "key": "raw/channel=68/date=2026-05-24/fake.mp3",
                "bytes_uploaded": 8,
                "content_type": "audio/mpeg",
            },
        )()

    worker = SegmentUploadWorker(
        api_url="http://private-api.test",
        ingest_token="ingest-token",
        uploader=uploader,
    )
    request = SegmentUploadRequest(
        channel="68",
        audio_path=audio_path,
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=2),
        duration_seconds=2.0,
        content_type=infer_audio_content_type(audio_path),
        idempotency_key="activity-v1:68:2026-05-24T13:30:00Z:test",
    )

    worker.upload_request(request)

    assert len(calls) == 1
    assert calls[0][2].content_type == "audio/mpeg"


def test_build_activity_upload_request_sets_idempotency_key(tmp_path) -> None:
    started_at = datetime(2026, 5, 24, 13, 30, tzinfo=UTC)
    audio_path = tmp_path / "activity.mp3"
    audio_path.write_bytes(b"fake mp3")
    clip = EdgeClip(
        channel="WX",
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=2),
        sample_rate_hz=1_000,
        pcm_i16le=_pcm(amplitude=2_000, seconds=2, sample_rate_hz=1_000),
        peak_amplitude=2_000,
        rms_amplitude=2_000,
    )

    request = build_activity_upload_request(clip, audio_path)

    assert request.channel == "WX"
    assert request.audio_path == audio_path
    assert request.content_type == "audio/mpeg"
    assert request.idempotency_key.startswith("activity-v1:WX:2026-05-24T13:30:00Z:")


def test_edge_capture_accepts_weather_and_harbor_channel_metadata() -> None:
    weather = EdgeCaptureConfig(channel="WX")
    harbor = EdgeCaptureConfig(channel="05A")

    assert weather.channel == "WX"
    assert harbor.channel == "05A"


def _pcm(*, amplitude: int, seconds: float, sample_rate_hz: int) -> bytes:
    sample_count = round(seconds * sample_rate_hz)
    values = array(
        "h",
        [amplitude if index % 2 == 0 else -amplitude for index in range(sample_count)],
    )
    return values.tobytes()
