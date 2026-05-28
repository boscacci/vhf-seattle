from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SPEECH_AUDIO_FILTER = "highpass=f=250,lowpass=f=3200,afftdn=nf=-28"
DEFAULT_PUBLIC_CLIP_AUDIO_FILTER = ",".join(
    (
        "acompressor=threshold=0.06:ratio=3:attack=8:release=180:makeup=4",
        "loudnorm=I=-16:LRA=8:TP=-6",
    )
)
DEFAULT_EDGE_UPLOAD_AUDIO_FILTER = ",".join(
    (
        DEFAULT_SPEECH_AUDIO_FILTER,
        DEFAULT_PUBLIC_CLIP_AUDIO_FILTER,
    )
)
DEFAULT_PUBLIC_CLIP_MIN_DURATION_SECONDS = 1.0
DEFAULT_PUBLIC_CLIP_MIN_PEAK_DB = -50.0
DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ = 16_000
DEFAULT_TRANSCRIBE_BEAM_SIZE = 5

Runner = Callable[..., object]
MAX_VOLUME_PATTERN = re.compile(r"max_volume:\s+(-?inf|-?\d+(?:\.\d+)?) dB")


class PublicClipAudioRejected(ValueError):
    pass


@dataclass(frozen=True)
class PublicClipAudioProbe:
    duration_seconds: float | None
    max_volume_db: float | None


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


def build_ffmpeg_public_clip_command(
    source_path: Path,
    output_path: Path,
    *,
    audio_filter: str = DEFAULT_PUBLIC_CLIP_AUDIO_FILTER,
    ffmpeg_path: str = "ffmpeg",
) -> list[str]:
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-af",
        audio_filter,
        "-map_metadata",
        "-1",
        str(output_path),
    ]
    return command


def build_ffmpeg_upload_mp3_command(
    source_path: Path,
    output_path: Path,
    *,
    bitrate: str,
    audio_filter: str | None = DEFAULT_EDGE_UPLOAD_AUDIO_FILTER,
    ffmpeg_path: str = "ffmpeg",
) -> list[str]:
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-vn",
    ]
    if audio_filter:
        command.extend(["-af", audio_filter])
    command.extend(
        [
            "-codec:a",
            "libmp3lame",
            "-b:a",
            bitrate,
            "-map_metadata",
            "-1",
            str(output_path),
        ]
    )
    return command


def process_public_clip_audio(
    source_path: Path,
    output_path: Path,
    *,
    audio_filter: str = DEFAULT_PUBLIC_CLIP_AUDIO_FILTER,
    ffmpeg_path: str | None = None,
    runner: Runner = subprocess.run,
) -> None:
    resolved_ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not resolved_ffmpeg:
        raise RuntimeError(
            "ffmpeg is required for public clip audio processing; "
            "install ffmpeg or disable public audio processing"
        )
    command = build_ffmpeg_public_clip_command(
        source_path,
        output_path,
        audio_filter=audio_filter,
        ffmpeg_path=resolved_ffmpeg,
    )
    runner(command, check=True)


def assert_publishable_public_clip_audio(
    source_path: Path,
    *,
    min_duration_seconds: float = DEFAULT_PUBLIC_CLIP_MIN_DURATION_SECONDS,
    min_peak_db: float = DEFAULT_PUBLIC_CLIP_MIN_PEAK_DB,
    ffprobe_path: str | None = None,
    ffmpeg_path: str | None = None,
    runner: Runner = subprocess.run,
) -> None:
    report = probe_public_clip_audio(
        source_path,
        ffprobe_path=ffprobe_path,
        ffmpeg_path=ffmpeg_path,
        runner=runner,
    )
    if report.duration_seconds is None:
        raise PublicClipAudioRejected("duration is unavailable")
    if report.duration_seconds < min_duration_seconds:
        raise PublicClipAudioRejected(
            f"duration {report.duration_seconds:.3f}s is below {min_duration_seconds:.3f}s"
        )
    if report.max_volume_db is None:
        raise PublicClipAudioRejected("max volume is unavailable")
    if report.max_volume_db < min_peak_db:
        raise PublicClipAudioRejected(
            f"max volume {report.max_volume_db:.1f} dB is below {min_peak_db:.1f} dB"
        )


def probe_public_clip_audio(
    source_path: Path,
    *,
    ffprobe_path: str | None = None,
    ffmpeg_path: str | None = None,
    runner: Runner = subprocess.run,
) -> PublicClipAudioProbe:
    resolved_ffprobe = ffprobe_path or shutil.which("ffprobe")
    if not resolved_ffprobe:
        raise RuntimeError(
            "ffprobe is required for public clip audio quality checks; "
            "install ffprobe or disable the public audio quality gate"
        )
    resolved_ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not resolved_ffmpeg:
        raise RuntimeError(
            "ffmpeg is required for public clip audio quality checks; "
            "install ffmpeg or disable the public audio quality gate"
        )

    duration_result = runner(
        [
            resolved_ffprobe,
            "-hide_banner",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    volume_result = runner(
        [
            resolved_ffmpeg,
            "-hide_banner",
            "-i",
            str(source_path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return PublicClipAudioProbe(
        duration_seconds=_parse_probe_float(getattr(duration_result, "stdout", "")),
        max_volume_db=_parse_max_volume_db(getattr(volume_result, "stderr", "")),
    )


def _parse_probe_float(value: str) -> float | None:
    value = value.strip()
    if not value or value.upper() == "N/A":
        return None
    try:
        return float(value.splitlines()[-1])
    except ValueError:
        return None


def _parse_max_volume_db(stderr: str) -> float | None:
    match = MAX_VOLUME_PATTERN.search(stderr)
    if not match:
        return None
    value = match.group(1)
    if value == "-inf":
        return float("-inf")
    return float(value)


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
