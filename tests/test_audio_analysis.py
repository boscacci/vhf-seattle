import numpy as np

from talkingboats.audio_analysis import analyze_samples


def test_analyze_samples_reports_voice_band_and_noise_metrics() -> None:
    sample_rate = 16_000
    t = np.arange(sample_rate, dtype=np.float64) / sample_rate
    voice = 0.18 * np.sin(2 * np.pi * 900 * t)
    warmth = 0.08 * np.sin(2 * np.pi * 220 * t)
    hiss = 0.015 * np.sin(2 * np.pi * 6_000 * t)
    samples = voice + warmth + hiss

    report = analyze_samples(samples, sample_rate)

    assert report.duration_seconds == 1.0
    assert report.rms_dbfs < -10
    assert report.voice_band_ratio > 0.75
    assert report.hiss_band_ratio < 0.03
    assert report.warmth_band_ratio > 0.1
    assert report.noise_floor_dbfs < report.loud_frame_dbfs


def test_analyze_samples_rejects_empty_audio() -> None:
    try:
        analyze_samples(np.array([], dtype=np.float32), 16_000)
    except ValueError as exc:
        assert "audio samples are empty" in str(exc)
    else:
        raise AssertionError("empty audio should fail fast")
