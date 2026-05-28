from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from talkingboats.audio_processing import (
    DEFAULT_EDGE_UPLOAD_AUDIO_FILTER,
    DEFAULT_PUBLIC_CLIP_AUDIO_FILTER,
    DEFAULT_SPEECH_AUDIO_FILTER,
    DEFAULT_TRANSCRIBE_BEAM_SIZE,
    DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ,
    PublicClipAudioRejected,
    assert_publishable_public_clip_audio,
    build_ffmpeg_public_clip_command,
    build_ffmpeg_transcription_command,
    build_ffmpeg_upload_mp3_command,
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


def test_ffmpeg_public_clip_command_compresses_and_limits_true_peak(tmp_path) -> None:
    source = tmp_path / "raw.mp3"
    output = tmp_path / "public.mp3"

    command = build_ffmpeg_public_clip_command(source, output)

    assert command[:8] == [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
    ]
    assert "-af" in command
    filter_graph = command[command.index("-af") + 1]
    assert filter_graph == DEFAULT_PUBLIC_CLIP_AUDIO_FILTER
    assert "acompressor=" in filter_graph
    assert "loudnorm=I=-16:LRA=8:TP=-6" in filter_graph
    assert "dynaudnorm" not in filter_graph
    assert command[-1] == str(output)


def test_ffmpeg_upload_mp3_command_applies_edge_speech_cleanup_and_loudness(tmp_path) -> None:
    source = tmp_path / "edge.wav"
    output = tmp_path / "edge.mp3"

    command = build_ffmpeg_upload_mp3_command(source, output, bitrate="64k")

    assert command[:8] == [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
    ]
    assert "-af" in command
    filter_graph = command[command.index("-af") + 1]
    assert filter_graph == DEFAULT_EDGE_UPLOAD_AUDIO_FILTER
    assert "highpass=f=250" in filter_graph
    assert "lowpass=f=3200" in filter_graph
    assert "afftdn=nf=-28" in filter_graph
    assert "acompressor=" in filter_graph
    assert "loudnorm=I=-16:LRA=8:TP=-6" in filter_graph
    assert "dynaudnorm" not in filter_graph
    assert "-codec:a" in command
    assert command[command.index("-codec:a") + 1] == "libmp3lame"
    assert command[command.index("-b:a") + 1] == "64k"
    assert command[-1] == str(output)


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
