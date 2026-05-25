from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_SPEECH_AUDIO_FILTER = "highpass=f=250,lowpass=f=3200,afftdn=nf=-28"
DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ = 16_000
DEFAULT_TRANSCRIBE_BEAM_SIZE = 5

Runner = Callable[..., object]


def build_ffmpeg_transcription_command(
    source_path: Path,
    output_path: Path,
    *,
    sample_rate_hz: int,
    audio_filter: str | None,
    ffmpeg_path: str = "ffmpeg",
) -> list[str]:
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate_hz),
    ]
    if audio_filter:
        command.extend(["-af", audio_filter])
    command.extend(["-f", "wav", str(output_path)])
    return command


@contextmanager
def prepared_transcription_audio(
    source_path: Path,
    *,
    sample_rate_hz: int = DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ,
    audio_filter: str | None = DEFAULT_SPEECH_AUDIO_FILTER,
    ffmpeg_path: str | None = None,
    runner: Runner = subprocess.run,
) -> Iterator[Path]:
    if audio_filter is None:
        yield source_path
        return

    resolved_ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not resolved_ffmpeg:
        raise RuntimeError(
            "ffmpeg is required for transcription audio preparation; "
            "install ffmpeg or pass --no-audio-filter"
        )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        prepared_path = Path(handle.name)
    try:
        command = build_ffmpeg_transcription_command(
            source_path,
            prepared_path,
            sample_rate_hz=sample_rate_hz,
            audio_filter=audio_filter,
            ffmpeg_path=resolved_ffmpeg,
        )
        runner(command, check=True)
        yield prepared_path
    finally:
        prepared_path.unlink(missing_ok=True)
