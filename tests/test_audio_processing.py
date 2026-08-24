from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave

import pytest

from talkingboats.audio_processing import (
    CANONICAL_AUDIO_PROFILE,
    CANONICAL_COMPRESSOR_FILTER,
    CANONICAL_MIN_DECODED_PEAK_DB,
    CANONICAL_PASSBAND_FILTER,
    CANONICAL_TARGET_PEAK_DB,
    DEFAULT_SPEECH_AUDIO_FILTER,
    DEFAULT_TRANSCRIBE_BEAM_SIZE,
    DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ,
    PublicClipAudioRejected,
    assert_publishable_public_clip_audio,
    build_ffmpeg_transcription_command,
    prepared_transcription_audio,
    process_canonical_clip_audio,
)


def test_canonical_profile_is_light_single_pass_voice_processing() -> None:
    assert CANONICAL_AUDIO_PROFILE == "canonical-v1"
    assert CANONICAL_PASSBAND_FILTER == "highpass=f=150,lowpass=f=3400"
    assert "threshold=0.1258925" in CANONICAL_COMPRESSOR_FILTER
    assert "ratio=2" in CANONICAL_COMPRESSOR_FILTER
    assert "attack=10" in CANONICAL_COMPRESSOR_FILTER
    assert "release=180" in CANONICAL_COMPRESSOR_FILTER
    assert "makeup=1" in CANONICAL_COMPRESSOR_FILTER
    assert "afftdn" not in CANONICAL_COMPRESSOR_FILTER
    assert "loudnorm" not in CANONICAL_COMPRESSOR_FILTER
    assert CANONICAL_TARGET_PEAK_DB == -0.2


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg is required for the canonical audio integration check",
)
def test_canonical_processor_normalizes_before_compression_and_decode_checks(
    tmp_path,
) -> None:
    source = tmp_path / "quiet-voice-band-tone.wav"
    output = tmp_path / "canonical.mp3"
    sample_rate_hz = 16_000
    samples = [
        round(2_000 * math.sin(2 * math.pi * 1_000 * index / sample_rate_hz))
        for index in range(sample_rate_hz * 2)
    ]
    with wave.open(str(source), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate_hz)
        handle.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    result = process_canonical_clip_audio(source, output)

    assert output.stat().st_size > 0
    assert result.normalized_gain_db == pytest.approx(
        CANONICAL_TARGET_PEAK_DB - result.source_peak_db,
        abs=0.01,
    )
    assert result.compensation_gain_db > 0
    assert CANONICAL_MIN_DECODED_PEAK_DB <= result.decoded_peak_db <= CANONICAL_TARGET_PEAK_DB


def test_default_transcription_consumes_the_saved_canonical_artifact() -> None:
    assert DEFAULT_SPEECH_AUDIO_FILTER is None
    assert DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ == 16_000
    assert DEFAULT_TRANSCRIBE_BEAM_SIZE == 5


def test_transcription_preparation_only_decodes_and_resamples(tmp_path) -> None:
    source = tmp_path / "canonical.mp3"
    output = tmp_path / "canonical.wav"

    command = build_ffmpeg_transcription_command(
        source,
        output,
        sample_rate_hz=16_000,
        audio_filter=None,
    )

    assert command[command.index("-ac") + 1] == "1"
    assert command[command.index("-ar") + 1] == "16000"
    assert "-af" not in command


def test_ffmpeg_transcription_command_does_not_apply_a_second_filter(tmp_path) -> None:
    source = tmp_path / "clip.mp3"
    output = tmp_path / "clip-prepared.wav"

    command = build_ffmpeg_transcription_command(
        source,
        output,
        sample_rate_hz=16_000,
        audio_filter=DEFAULT_SPEECH_AUDIO_FILTER,
    )

    assert "-af" not in command
    assert command[-3:] == ["-f", "wav", str(output)]


def test_public_clip_quality_gate_rejects_subsecond_near_silent_audio(tmp_path) -> None:
    source = tmp_path / "raw.mp3"
    source.write_bytes(b"fake mp3")

    def fake_run(command, *, check, capture_output, text):
        assert check is True
        assert capture_output is True
        assert text is True
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout="0.216000\n", stderr="")
        if command[0] == "ffmpeg":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr="max_volume: -54.5 dB\n",
            )
        raise AssertionError(command)

    with pytest.raises(PublicClipAudioRejected, match="0.216s is below 1.000s"):
        assert_publishable_public_clip_audio(
            source,
            ffprobe_path="ffprobe",
            ffmpeg_path="ffmpeg",
            runner=fake_run,
        )


def test_prepared_transcription_audio_rejects_a_second_filter(tmp_path) -> None:
    source = tmp_path / "clip.mp3"
    source.write_bytes(b"fake mp3")
    with (
        pytest.raises(ValueError, match="must not receive a second"),
        prepared_transcription_audio(
            source,
            sample_rate_hz=16_000,
            audio_filter="highpass=f=250",
            ffmpeg_path="ffmpeg",
        ),
    ):
        pass


def test_prepared_transcription_audio_bypasses_ffmpeg_when_filter_disabled(tmp_path) -> None:
    source = tmp_path / "clip.mp3"
    source.write_bytes(b"fake mp3")

    with prepared_transcription_audio(
        source,
        sample_rate_hz=16_000,
        audio_filter=None,
        ffmpeg_path=None,
    ) as prepared:
        assert prepared == source
