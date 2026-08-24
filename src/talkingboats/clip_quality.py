from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

from talkingboats.audio_analysis import AudioAnalysisReport

QualityStatus = Literal["unknown", "ok", "marginal", "quarantined"]
QualityFilter = Literal["visible", "quarantined", "all"]

VISIBLE_QUALITY_STATUSES = {"unknown", "ok", "marginal"}
QUALITY_STATUS_VALUES = ("unknown", "ok", "marginal", "quarantined")
QUALITY_FILTER_VALUES = ("visible", "quarantined", "all")
MIN_CLEAR_SPEECH_CONTRAST_DB = 5.0
MIN_CLEAR_PRESENCE_BAND_RATIO = 0.12
MAX_CLEAR_NOISE_FLOOR_DBFS = -24.0
MIN_CLEAR_ASR_MEAN_AVG_LOGPROB = -0.8
# Older records predate the blocking ASR-confidence rule. Their rounded score
# is the only persisted confidence signal, so keep them out of the normal feed
# when that score is below the equivalent conservative display threshold.
MIN_VISIBLE_QUALITY_SCORE = 90.0


@dataclass(frozen=True)
class AsrQualitySummary:
    segment_count: int = 0
    mean_avg_logprob: float | None = None
    min_avg_logprob: float | None = None
    max_no_speech_prob: float | None = None
    max_compression_ratio: float | None = None


@dataclass(frozen=True)
class ClipQualityAssessment:
    quality_status: QualityStatus = "unknown"
    quality_score: float | None = None
    quality_reason: str | None = None
    quality_flags: tuple[str, ...] = ()
    audio_metrics: dict[str, float] | None = None

    def as_metadata(self) -> dict[str, object]:
        return {
            "quality_status": self.quality_status,
            "quality_score": self.quality_score,
            "quality_reason": self.quality_reason,
            "quality_flags": list(self.quality_flags),
            "audio_metrics": self.audio_metrics or {},
        }


def normalize_quality_status(value: object | None) -> QualityStatus:
    status = str(value or "unknown").strip().lower()
    if status not in QUALITY_STATUS_VALUES:
        raise ValueError(f"unsupported quality status: {status}")
    return status  # type: ignore[return-value]


def normalize_quality_filter(value: object | None) -> QualityFilter:
    quality_filter = str(value or "visible").strip().lower()
    if quality_filter not in QUALITY_FILTER_VALUES:
        raise ValueError(f"unsupported quality filter: {quality_filter}")
    return quality_filter  # type: ignore[return-value]


def is_quality_visible(
    status: object | None,
    quality_score: object | None = None,
) -> bool:
    if normalize_quality_status(status) not in VISIBLE_QUALITY_STATUSES:
        return False
    score = _optional_float(quality_score)
    return score is None or score >= MIN_VISIBLE_QUALITY_SCORE


def summarize_asr_quality(segments: Iterable[Any]) -> AsrQualitySummary:
    avg_logprobs: list[float] = []
    no_speech_probs: list[float] = []
    compression_ratios: list[float] = []
    count = 0
    for segment in segments:
        count += 1
        if (value := _optional_float(getattr(segment, "avg_logprob", None))) is not None:
            avg_logprobs.append(value)
        if (value := _optional_float(getattr(segment, "no_speech_prob", None))) is not None:
            no_speech_probs.append(value)
        if (value := _optional_float(getattr(segment, "compression_ratio", None))) is not None:
            compression_ratios.append(value)
    return AsrQualitySummary(
        segment_count=count,
        mean_avg_logprob=round(sum(avg_logprobs) / len(avg_logprobs), 3)
        if avg_logprobs
        else None,
        min_avg_logprob=round(min(avg_logprobs), 3) if avg_logprobs else None,
        max_no_speech_prob=round(max(no_speech_probs), 3) if no_speech_probs else None,
        max_compression_ratio=round(max(compression_ratios), 3) if compression_ratios else None,
    )


def assess_clip_quality(
    *,
    audio: AudioAnalysisReport | None,
    asr: AsrQualitySummary | None,
) -> ClipQualityAssessment:
    if audio is None and asr is None:
        return ClipQualityAssessment()

    flags: list[str] = []
    reason: str | None = None
    score = 100.0
    audio_metrics = _audio_metric_payload(audio) if audio is not None else {}

    if audio is not None:
        score -= max(0.0, 6.0 - audio.speech_contrast_db) * 7.0
        score -= max(0.0, 0.62 - audio.voice_band_ratio) * 60.0
        score -= max(0.0, audio.hiss_band_ratio - 0.14) * 80.0
        score -= max(0.0, audio.rumble_band_ratio - 0.18) * 70.0
        score -= min(audio.clipped_sample_ratio * 400.0, 35.0)

        if audio.clipped_sample_ratio >= 0.03 or audio.peak_dbfs >= -0.3:
            flags.append("clipped_audio")
            reason = reason or "clipped_audio"
        if audio.peak_dbfs <= -45.0:
            flags.append("static_or_no_speech")
            reason = reason or "static_or_no_speech"
        if audio.noise_floor_dbfs >= MAX_CLEAR_NOISE_FLOOR_DBFS:
            flags.append("low_snr")
            reason = reason or "low_snr"
        weak_intelligibility_band = (
            audio.presence_band_ratio < MIN_CLEAR_PRESENCE_BAND_RATIO
        )
        if audio.speech_contrast_db < 2.5 and (
            audio.voice_band_ratio < 0.5 or weak_intelligibility_band
        ):
            flags.append("static_or_no_speech")
            reason = reason or "static_or_no_speech"
        elif (
            (
                audio.speech_contrast_db < MIN_CLEAR_SPEECH_CONTRAST_DB
                and weak_intelligibility_band
            )
            or (audio.speech_contrast_db < 4.0 and audio.voice_band_ratio < 0.62)
        ):
            flags.append("low_snr")
            reason = reason or "low_snr"
        if audio.hiss_band_ratio >= 0.28 and audio.voice_band_ratio < 0.68:
            flags.append("low_snr")
            reason = reason or "low_snr"
        if audio.rumble_band_ratio >= 0.32 and audio.voice_band_ratio < 0.6:
            flags.append("low_snr")
            reason = reason or "low_snr"

    if asr is not None:
        if asr.mean_avg_logprob is not None:
            score -= max(0.0, -0.45 - asr.mean_avg_logprob) * 30.0
            if asr.mean_avg_logprob <= MIN_CLEAR_ASR_MEAN_AVG_LOGPROB:
                flags.append("static_or_no_speech")
                reason = reason or "static_or_no_speech"
        if asr.max_no_speech_prob is not None and asr.max_no_speech_prob >= 0.75:
            flags.append("static_or_no_speech")
            reason = reason or "static_or_no_speech"
        if asr.max_compression_ratio is not None and asr.max_compression_ratio >= 2.8:
            flags.append("static_or_no_speech")
            reason = reason or "static_or_no_speech"

    normalized_flags = _unique_flags(flags)
    bounded_score = round(max(0.0, min(score, 100.0)), 1)
    if _has_blocking_quality_flag(normalized_flags):
        return ClipQualityAssessment(
            quality_status="quarantined",
            quality_score=bounded_score,
            quality_reason=reason or normalized_flags[0],
            quality_flags=tuple(normalized_flags),
            audio_metrics=audio_metrics,
        )
    if bounded_score < 45.0:
        return ClipQualityAssessment(
            quality_status="quarantined",
            quality_score=bounded_score,
            quality_reason=reason or "low_snr",
            quality_flags=tuple(normalized_flags or ["low_snr"]),
            audio_metrics=audio_metrics,
        )
    return ClipQualityAssessment(
        quality_status="marginal" if bounded_score < 70.0 else "ok",
        quality_score=bounded_score,
        quality_reason=reason,
        quality_flags=tuple(normalized_flags),
        audio_metrics=audio_metrics,
    )


def coerce_quality_assessment(value: object | None) -> ClipQualityAssessment:
    if value is None:
        return ClipQualityAssessment()
    if isinstance(value, ClipQualityAssessment):
        return value
    if isinstance(value, Mapping):
        return ClipQualityAssessment(
            quality_status=normalize_quality_status(value.get("quality_status")),
            quality_score=_optional_float(value.get("quality_score")),
            quality_reason=_optional_str(value.get("quality_reason")),
            quality_flags=tuple(_unique_flags(_as_string_list(value.get("quality_flags")))),
            audio_metrics=_as_float_dict(value.get("audio_metrics")),
        )
    if hasattr(value, "__dataclass_fields__"):
        return coerce_quality_assessment(asdict(value))
    raise TypeError(f"unsupported clip quality metadata: {type(value).__name__}")


def quality_matches_filter(status: object | None, quality_filter: QualityFilter) -> bool:
    normalized = normalize_quality_status(status)
    if quality_filter == "all":
        return True
    if quality_filter == "quarantined":
        return normalized == "quarantined"
    return normalized != "quarantined"


def _audio_metric_payload(audio: AudioAnalysisReport) -> dict[str, float]:
    return {
        "rms_dbfs": audio.rms_dbfs,
        "peak_dbfs": audio.peak_dbfs,
        "noise_floor_dbfs": audio.noise_floor_dbfs,
        "loud_frame_dbfs": audio.loud_frame_dbfs,
        "speech_contrast_db": audio.speech_contrast_db,
        "voice_band_ratio": audio.voice_band_ratio,
        "presence_band_ratio": audio.presence_band_ratio,
        "hiss_band_ratio": audio.hiss_band_ratio,
        "rumble_band_ratio": audio.rumble_band_ratio,
        "clipped_sample_ratio": audio.clipped_sample_ratio,
        "zero_crossing_rate": audio.zero_crossing_rate,
    }


def _has_blocking_quality_flag(flags: Iterable[str]) -> bool:
    return bool({"static_or_no_speech", "low_snr", "clipped_audio"} & set(flags))


def _unique_flags(flags: Iterable[str]) -> list[str]:
    allowed = {"static_or_no_speech", "low_snr", "clipped_audio"}
    normalized: list[str] = []
    seen: set[str] = set()
    for flag in flags:
        value = str(flag).strip().lower()
        if value in allowed and value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized


def _optional_float(value: object | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_string_list(value: object | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return []


def _as_float_dict(value: object | None) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    metrics: dict[str, float] = {}
    for key, item in value.items():
        parsed = _optional_float(item)
        if parsed is not None:
            metrics[str(key)] = parsed
    return metrics
