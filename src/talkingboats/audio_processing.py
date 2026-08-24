from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

CANONICAL_AUDIO_PROFILE = "canonical-v1"
CANONICAL_TARGET_PEAK_DB = -0.2
# MP3 synthesis filters can attenuate an otherwise peak-maxed PCM source by a
# few tenths of a decibel. Keep the hard ceiling at -0.2 dB and accept that
# codec-safe headroom while recording the measured decoded peak.
CANONICAL_MIN_DECODED_PEAK_DB = -0.75
CANONICAL_MIN_INPUT_PEAK_DB = -50.0
CANONICAL_PASSBAND_FILTER = "highpass=f=150,lowpass=f=3400"
CANONICAL_COMPRESSOR_FILTER = (
    "acompressor=threshold=0.1258925:ratio=2:attack=10:release=180:"
    "knee=2.828427:makeup=1:detection=rms"
)
# The limiter is a final safety rail at digital full scale. The measured
# compensation pass below sets the decoded MP3 peak to -0.2 dB; using -0.2 dB
# as the limiter ceiling itself would double-attenuate lossy encodes.
CANONICAL_LIMITER_FILTER = "alimiter=limit=1:level=false:latency=true"

DEFAULT_SPEECH_AUDIO_FILTER = None
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


@dataclass(frozen=True)
class CanonicalAudioResult:
    audio_profile: str
    source_peak_db: float
    normalized_gain_db: float
    compressed_peak_db: float
    compensation_gain_db: float
    decoded_peak_db: float
    duration_seconds: float | None


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


def process_public_clip_audio(
    source_path: Path,
    output_path: Path,
    *,
    ffmpeg_path: str | None = None,
    runner: Runner = subprocess.run,
) -> None:
    del ffmpeg_path, runner
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, output_path)


def process_canonical_clip_audio(
    source_path: Path,
    output_path: Path,
    *,
    bitrate: str = "64k",
    ffmpeg_path: str | None = None,
    ffprobe_path: str | None = None,
    runner: Runner = subprocess.run,
) -> CanonicalAudioResult:
    """Render one canonical clip artifact for upload, playback, and ASR.

    The source is band-limited before its peak is measured. It is then
    peak-normalized, lightly compressed, compensated for compressor gain
    reduction, limited, encoded once, and decode-checked. A single corrective
    rerender from the lossless compressed intermediate handles MP3 overshoot.
    """

    resolved_ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    resolved_ffprobe = ffprobe_path or shutil.which("ffprobe")
    if not resolved_ffmpeg or not resolved_ffprobe:
        raise RuntimeError("ffmpeg and ffprobe are required for canonical clip processing")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="talkingboats-canonical-") as tempdir:
        temp_root = Path(tempdir)
        bandpassed_path = temp_root / "bandpassed.wav"
        compressed_path = temp_root / "compressed.wav"
        encoded_path = temp_root / "canonical.mp3"

        runner(
            [
                resolved_ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_path),
                "-vn",
                "-af",
                CANONICAL_PASSBAND_FILTER,
                "-ac",
                "1",
                "-c:a",
                "pcm_f32le",
                str(bandpassed_path),
            ],
            check=True,
        )
        source_probe = probe_public_clip_audio(
            bandpassed_path,
            ffprobe_path=resolved_ffprobe,
            ffmpeg_path=resolved_ffmpeg,
            runner=runner,
        )
        source_peak_db = source_probe.max_volume_db
        if source_peak_db is None or source_peak_db == float("-inf"):
            raise PublicClipAudioRejected("canonical source peak is unavailable")
        if source_peak_db < CANONICAL_MIN_INPUT_PEAK_DB:
            raise PublicClipAudioRejected(
                f"canonical source peak {source_peak_db:.1f} dB is below "
                f"{CANONICAL_MIN_INPUT_PEAK_DB:.1f} dB"
            )
        normalized_gain_db = CANONICAL_TARGET_PEAK_DB - source_peak_db
        runner(
            [
                resolved_ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(bandpassed_path),
                "-vn",
                "-af",
                f"volume={normalized_gain_db:.6f}dB,{CANONICAL_COMPRESSOR_FILTER}",
                "-ac",
                "1",
                "-c:a",
                "pcm_f32le",
                str(compressed_path),
            ],
            check=True,
        )
        compressed_probe = probe_public_clip_audio(
            compressed_path,
            ffprobe_path=resolved_ffprobe,
            ffmpeg_path=resolved_ffmpeg,
            runner=runner,
        )
        compressed_peak_db = compressed_probe.max_volume_db
        if compressed_peak_db is None or compressed_peak_db == float("-inf"):
            raise PublicClipAudioRejected("canonical compressed peak is unavailable")

        compensation_gain_db = CANONICAL_TARGET_PEAK_DB - compressed_peak_db
        decoded_peak_db = _render_and_probe_canonical_mp3(
            compressed_path=compressed_path,
            encoded_path=encoded_path,
            compensation_gain_db=compensation_gain_db,
            bitrate=bitrate,
            ffmpeg_path=resolved_ffmpeg,
            ffprobe_path=resolved_ffprobe,
            runner=runner,
        )
        if not (CANONICAL_MIN_DECODED_PEAK_DB <= decoded_peak_db <= CANONICAL_TARGET_PEAK_DB):
            correction_db = CANONICAL_TARGET_PEAK_DB - decoded_peak_db
            if decoded_peak_db > CANONICAL_TARGET_PEAK_DB:
                correction_db -= 0.02
            compensation_gain_db += correction_db
            decoded_peak_db = _render_and_probe_canonical_mp3(
                compressed_path=compressed_path,
                encoded_path=encoded_path,
                compensation_gain_db=compensation_gain_db,
                bitrate=bitrate,
                ffmpeg_path=resolved_ffmpeg,
                ffprobe_path=resolved_ffprobe,
                runner=runner,
            )
        if decoded_peak_db > CANONICAL_TARGET_PEAK_DB:
            raise PublicClipAudioRejected(
                f"decoded canonical peak {decoded_peak_db:.2f} dB exceeds "
                f"{CANONICAL_TARGET_PEAK_DB:.2f} dB"
            )
        if decoded_peak_db < CANONICAL_MIN_DECODED_PEAK_DB:
            raise PublicClipAudioRejected(
                f"decoded canonical peak {decoded_peak_db:.2f} dB is below "
                f"{CANONICAL_MIN_DECODED_PEAK_DB:.2f} dB"
            )
        encoded_path.replace(output_path)
        return CanonicalAudioResult(
            audio_profile=CANONICAL_AUDIO_PROFILE,
            source_peak_db=source_peak_db,
            normalized_gain_db=normalized_gain_db,
            compressed_peak_db=compressed_peak_db,
            compensation_gain_db=compensation_gain_db,
            decoded_peak_db=decoded_peak_db,
            duration_seconds=source_probe.duration_seconds,
        )


def _render_and_probe_canonical_mp3(
    *,
    compressed_path: Path,
    encoded_path: Path,
    compensation_gain_db: float,
    bitrate: str,
    ffmpeg_path: str,
    ffprobe_path: str,
    runner: Runner,
) -> float:
    runner(
        [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(compressed_path),
            "-vn",
            "-af",
            f"volume={compensation_gain_db:.6f}dB,{CANONICAL_LIMITER_FILTER}",
            "-ac",
            "1",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            bitrate,
            "-map_metadata",
            "-1",
            str(encoded_path),
        ],
        check=True,
    )
    encoded_probe = probe_public_clip_audio(
        encoded_path,
        ffprobe_path=ffprobe_path,
        ffmpeg_path=ffmpeg_path,
        runner=runner,
    )
    if encoded_probe.max_volume_db is None or encoded_probe.max_volume_db == float("-inf"):
        raise PublicClipAudioRejected("decoded canonical peak is unavailable")
    return encoded_probe.max_volume_db


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
    audio_filter: str | None = None,
    ffmpeg_path: str | None = None,
    runner: Runner = subprocess.run,
) -> Iterator[Path]:
    if audio_filter:
        raise ValueError("canonical clips must not receive a second transcription filter")
    del sample_rate_hz, ffmpeg_path, runner
    # The uploader has already created the canonical artifact. Faster Whisper
    # decodes MP3 directly, so transcription must consume that exact saved file
    # instead of producing a second, independently processed derivative.
    yield source_path
