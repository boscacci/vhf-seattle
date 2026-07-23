from __future__ import annotations

from talkingboats.audio_analysis import AudioAnalysisReport
from talkingboats.clip_quality import (
    AsrQualitySummary,
    assess_clip_quality,
    summarize_asr_quality,
)


def test_clip_quality_accepts_clean_voice_band_audio() -> None:
    report = _audio_report(
        speech_contrast_db=12.0,
        voice_band_ratio=0.82,
        hiss_band_ratio=0.02,
        rumble_band_ratio=0.02,
        peak_dbfs=-8.0,
    )

    assessment = assess_clip_quality(
        audio=report,
        asr=AsrQualitySummary(mean_avg_logprob=-0.22, max_no_speech_prob=0.05),
    )

    assert assessment.quality_status == "ok"
    assert assessment.quality_score >= 80
    assert assessment.quality_reason is None
    assert assessment.quality_flags == ()


def test_clip_quality_quarantines_low_speech_contrast_static() -> None:
    report = _audio_report(
        speech_contrast_db=1.2,
        voice_band_ratio=0.34,
        hiss_band_ratio=0.41,
        rumble_band_ratio=0.03,
        peak_dbfs=-20.0,
    )

    assessment = assess_clip_quality(audio=report, asr=AsrQualitySummary())

    assert assessment.quality_status == "quarantined"
    assert assessment.quality_reason == "static_or_no_speech"
    assert "static_or_no_speech" in assessment.quality_flags


def test_clip_quality_quarantines_clipped_audio() -> None:
    report = _audio_report(
        speech_contrast_db=9.0,
        voice_band_ratio=0.7,
        hiss_band_ratio=0.02,
        rumble_band_ratio=0.02,
        clipped_sample_ratio=0.08,
        peak_dbfs=-0.2,
    )

    assessment = assess_clip_quality(audio=report, asr=AsrQualitySummary())

    assert assessment.quality_status == "quarantined"
    assert assessment.quality_reason == "clipped_audio"
    assert assessment.quality_flags == ("clipped_audio",)


def test_clip_quality_quarantines_repetitive_asr_hallucination_signal() -> None:
    assessment = assess_clip_quality(
        audio=_audio_report(speech_contrast_db=8.0, voice_band_ratio=0.72),
        asr=AsrQualitySummary(max_compression_ratio=3.1, max_no_speech_prob=0.82),
    )

    assert assessment.quality_status == "quarantined"
    assert assessment.quality_reason == "static_or_no_speech"


def test_summarize_asr_quality_reads_optional_whisper_segment_fields() -> None:
    class Segment:
        def __init__(self, avg_logprob, no_speech_prob, compression_ratio) -> None:
            self.avg_logprob = avg_logprob
            self.no_speech_prob = no_speech_prob
            self.compression_ratio = compression_ratio

    summary = summarize_asr_quality(
        [
            Segment(-0.2, 0.08, 1.2),
            Segment(-0.8, 0.42, 2.7),
        ]
    )

    assert summary.segment_count == 2
    assert summary.mean_avg_logprob == -0.5
    assert summary.min_avg_logprob == -0.8
    assert summary.max_no_speech_prob == 0.42
    assert summary.max_compression_ratio == 2.7


def _audio_report(
    *,
    speech_contrast_db: float,
    voice_band_ratio: float,
    hiss_band_ratio: float = 0.01,
    rumble_band_ratio: float = 0.01,
    peak_dbfs: float = -8.0,
    clipped_sample_ratio: float = 0.0,
) -> AudioAnalysisReport:
    return AudioAnalysisReport(
        duration_seconds=5.0,
        sample_rate_hz=16_000,
        rms_dbfs=-19.0,
        peak_dbfs=peak_dbfs,
        noise_floor_dbfs=-38.0,
        loud_frame_dbfs=-38.0 + speech_contrast_db,
        speech_contrast_db=speech_contrast_db,
        spectral_centroid_hz=1200.0,
        spectral_rolloff_95_hz=3100.0,
        warmth_band_ratio=0.12,
        voice_band_ratio=voice_band_ratio,
        presence_band_ratio=0.22,
        hiss_band_ratio=hiss_band_ratio,
        rumble_band_ratio=rumble_band_ratio,
        clipped_sample_ratio=clipped_sample_ratio,
        zero_crossing_rate=0.08,
    )
