from __future__ import annotations

from collections.abc import Iterable

TRAINING_QUALITY_VALUES = ("unknown", "excellent", "good", "usable", "poor")
TRAINING_INCLUDED_QUALITIES = {"excellent", "good", "usable"}
TRAINING_SPLIT_VALUES = ("auto", "train", "validation", "test", "holdout")
TRAINING_FLAG_VALUES = (
    "static_or_no_speech",
    "overlap",
    "truncated_start",
    "low_snr",
    "clipped_audio",
)
TRAINING_BLOCKING_FLAGS = {
    "static_or_no_speech",
    "overlap",
    "truncated_start",
    "clipped_audio",
}


def normalize_training_flags(flags: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for flag in flags or ():
        value = str(flag).strip().lower()
        if not value:
            continue
        if value not in TRAINING_FLAG_VALUES:
            raise ValueError(f"unsupported training flag: {value}")
        if value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized


def normalize_training_quality(value: object | None) -> str:
    quality = str(value or "unknown").strip().lower()
    if quality not in TRAINING_QUALITY_VALUES:
        raise ValueError(f"unsupported training quality: {quality}")
    return quality


def normalize_training_split(value: object | None) -> str:
    split = str(value or "auto").strip().lower()
    if split not in TRAINING_SPLIT_VALUES:
        raise ValueError(f"unsupported training split: {split}")
    return split


def validate_training_metadata(
    *,
    include_in_training: bool,
    training_quality: str,
    training_flags: Iterable[str],
) -> None:
    flags = set(training_flags)
    if not include_in_training:
        return
    if training_quality not in TRAINING_INCLUDED_QUALITIES:
        raise ValueError("training_quality must be excellent, good, or usable")
    blocking = sorted(flags & TRAINING_BLOCKING_FLAGS)
    if blocking:
        raise ValueError(
            "cannot include blocking training flags: " + ", ".join(blocking)
        )


def is_training_eligible(
    *,
    include_in_training: bool,
    training_quality: str,
    training_flags: Iterable[str],
) -> bool:
    if not include_in_training or training_quality not in TRAINING_INCLUDED_QUALITIES:
        return False
    return not (set(training_flags) & TRAINING_BLOCKING_FLAGS)
