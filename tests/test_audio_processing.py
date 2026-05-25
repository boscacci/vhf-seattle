from __future__ import annotations

from pathlib import Path

from talkingboats.audio_processing import (
    DEFAULT_SPEECH_AUDIO_FILTER,
    DEFAULT_TRANSCRIBE_BEAM_SIZE,
    DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ,
    build_ffmpeg_transcription_command,
    prepared_transcription_audio,
)


def test_default_transcription_audio_settings_match_edge_speech_cleanup() -> None:
    assert DEFAULT_SPEECH_AUDIO_FILTER == "highpass=f=250,lowpass=f=3200,afftdn=nf=-28"
    assert DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ == 16_000
    assert DEFAULT_TRANSCRIBE_BEAM_SIZE == 5


def test_ffmpeg_transcription_command_resamples_mono_and_applies_filter(tmp_path) -> None:
    source = tmp_path / "clip.mp3"
    output = tmp_path / "clip-prepared.wav"

    command = build_ffmpeg_transcription_command(
        source,
        output,
        sample_rate_hz=16_000,
        audio_filter=DEFAULT_SPEECH_AUDIO_FILTER,
    )

    assert command == [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-af",
        DEFAULT_SPEECH_AUDIO_FILTER,
        "-f",
        "wav",
        str(output),
    ]


def test_prepared_transcription_audio_cleans_temp_wav(tmp_path) -> None:
    source = tmp_path / "clip.mp3"
    source.write_bytes(b"fake mp3")
    calls = []

    def fake_run(command, *, check):
        calls.append((command, check))
        output = Path(command[-1])
        output.write_bytes(b"RIFFfake wav")

    with prepared_transcription_audio(
        source,
        sample_rate_hz=16_000,
        audio_filter=DEFAULT_SPEECH_AUDIO_FILTER,
        ffmpeg_path="ffmpeg",
        runner=fake_run,
    ) as prepared:
        assert prepared != source
        assert prepared.suffix == ".wav"
        assert prepared.read_bytes() == b"RIFFfake wav"

    assert calls
    assert calls[0][1] is True
    assert not prepared.exists()


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
