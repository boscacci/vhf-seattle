from __future__ import annotations

import argparse
import json
import math
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class AudioAnalysisReport:
    duration_seconds: float
    sample_rate_hz: int
    rms_dbfs: float
    peak_dbfs: float
    noise_floor_dbfs: float
    loud_frame_dbfs: float
    speech_contrast_db: float
    spectral_centroid_hz: float
    spectral_rolloff_95_hz: float
    warmth_band_ratio: float
    voice_band_ratio: float
    presence_band_ratio: float
    hiss_band_ratio: float
    rumble_band_ratio: float
    clipped_sample_ratio: float
    zero_crossing_rate: float


def decode_audio_file(
    path: Path,
    *,
    ffmpeg_path: str = "ffmpeg",
    sample_rate_hz: int = 16_000,
    max_seconds: float = 30,
) -> np.ndarray:
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-t",
        str(max_seconds),
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate_hz),
        "-f",
        "f32le",
        "pipe:1",
    ]
    result = subprocess.run(command, capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype=np.float32)


def analyze_audio_file(
    path: Path,
    *,
    ffmpeg_path: str = "ffmpeg",
    sample_rate_hz: int = 16_000,
    max_seconds: float = 30,
) -> AudioAnalysisReport:
    samples = decode_audio_file(
        path,
        ffmpeg_path=ffmpeg_path,
        sample_rate_hz=sample_rate_hz,
        max_seconds=max_seconds,
    )
    return analyze_samples(samples, sample_rate_hz)


def analyze_samples(samples: np.ndarray, sample_rate_hz: int) -> AudioAnalysisReport:
    samples = np.asarray(samples, dtype=np.float64)
    if samples.size == 0:
        raise ValueError("audio samples are empty")
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")
    samples = np.nan_to_num(np.clip(samples, -1.0, 1.0))
    frame_length = max(256, round(sample_rate_hz * 0.04))
    frames = _framed(samples, frame_length)
    window = np.hanning(frame_length)
    spectra = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
    frequencies = np.fft.rfftfreq(frame_length, d=1 / sample_rate_hz)
    spectral_power = spectra.mean(axis=0)
    total_power = float(np.sum(spectral_power)) or 1.0
    frame_rms = np.sqrt(np.mean(frames * frames, axis=1))
    quiet_floor = float(np.percentile(frame_rms, 20))
    loud_level = float(np.percentile(frame_rms, 80))

    return AudioAnalysisReport(
        duration_seconds=round(samples.size / sample_rate_hz, 3),
        sample_rate_hz=sample_rate_hz,
        rms_dbfs=round(_dbfs(float(np.sqrt(np.mean(samples * samples)))), 3),
        peak_dbfs=round(_dbfs(float(np.max(np.abs(samples)))), 3),
        noise_floor_dbfs=round(_dbfs(quiet_floor), 3),
        loud_frame_dbfs=round(_dbfs(loud_level), 3),
        speech_contrast_db=round(_dbfs(loud_level) - _dbfs(quiet_floor), 3),
        spectral_centroid_hz=round(_spectral_centroid(frequencies, spectral_power), 3),
        spectral_rolloff_95_hz=round(_spectral_rolloff(frequencies, spectral_power, 0.95), 3),
        warmth_band_ratio=round(_band_ratio(frequencies, spectral_power, 180, 450, total_power), 6),
        voice_band_ratio=round(_band_ratio(frequencies, spectral_power, 300, 3400, total_power), 6),
        presence_band_ratio=round(
            _band_ratio(frequencies, spectral_power, 1800, 3400, total_power),
            6,
        ),
        hiss_band_ratio=round(_band_ratio(frequencies, spectral_power, 4000, 8000, total_power), 6),
        rumble_band_ratio=round(_band_ratio(frequencies, spectral_power, 0, 180, total_power), 6),
        clipped_sample_ratio=round(float(np.mean(np.abs(samples) >= 0.98)), 6),
        zero_crossing_rate=round(_zero_crossing_rate(samples), 6),
    )


def _framed(samples: np.ndarray, frame_length: int) -> np.ndarray:
    if samples.size < frame_length:
        padded = np.pad(samples, (0, frame_length - samples.size))
        return padded.reshape(1, frame_length)
    frame_count = samples.size // frame_length
    trimmed = samples[: frame_count * frame_length]
    return trimmed.reshape(frame_count, frame_length)


def _dbfs(value: float) -> float:
    if value <= 0:
        return -120.0
    return 20 * math.log10(min(value, 1.0))


def _band_ratio(
    frequencies: np.ndarray,
    power: np.ndarray,
    low_hz: float,
    high_hz: float,
    total_power: float,
) -> float:
    mask = (frequencies >= low_hz) & (frequencies < high_hz)
    return float(np.sum(power[mask]) / total_power)


def _spectral_centroid(frequencies: np.ndarray, power: np.ndarray) -> float:
    total_power = float(np.sum(power))
    if total_power <= 0:
        return 0.0
    return float(np.sum(frequencies * power) / total_power)


def _spectral_rolloff(frequencies: np.ndarray, power: np.ndarray, threshold: float) -> float:
    cumulative = np.cumsum(power)
    if cumulative.size == 0 or cumulative[-1] <= 0:
        return 0.0
    index = int(np.searchsorted(cumulative, cumulative[-1] * threshold))
    return float(frequencies[min(index, frequencies.size - 1)])


def _zero_crossing_rate(samples: np.ndarray) -> float:
    if samples.size < 2:
        return 0.0
    signs = np.signbit(samples)
    return float(np.mean(signs[1:] != signs[:-1]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze voice-band quality in audio clips.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--ffmpeg-path", default="ffmpeg")
    parser.add_argument("--sample-rate-hz", type=int, default=16_000)
    parser.add_argument("--max-seconds", type=float, default=30)
    args = parser.parse_args()
    reports = {
        str(path): asdict(
            analyze_audio_file(
                path,
                ffmpeg_path=args.ffmpeg_path,
                sample_rate_hz=args.sample_rate_hz,
                max_seconds=args.max_seconds,
            )
        )
        for path in args.paths
    }
    print(json.dumps(reports, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
