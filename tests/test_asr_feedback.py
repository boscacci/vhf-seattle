import pytest

from talkingboats.asr_feedback import Correction, MemoryCorrections, RevisionConflict, split_day


def label(**kwargs):
    return Correction(
        channel="14",
        started_at="2026-10-05T12:00:00Z",
        text="Tug Osprey northbound",
        request_id="request-0001",
        expected_revision=0,
        **kwargs,
    )


def test_correction_preserves_original_retries_and_overlays_both_text_fields():
    store = MemoryCorrections()
    saved = store.save(label(), original="Tug spray northbound", key="raw/clip.mp3", duration=5)
    assert store.save(label(), original="new machine text", key="raw/clip.mp3", duration=5) == saved
    clips = [
        {
            "channel": "14",
            "started_at": label().started_at,
            "transcript": "Tug spray northbound",
            "segments": [{"text": "Tug spray"}],
        }
    ]
    out = store.overlay(clips)[0]
    assert out["transcript"] == "Tug Osprey northbound"
    assert out["segments"] == []
    assert saved["original"] == "Tug spray northbound"
    with pytest.raises(RevisionConflict):
        store.save(
            Correction(**{**label().model_dump(), "text": "different text"}),
            original="",
            key="",
            duration=5,
        )


def test_stale_edit_conflicts_and_revert_retains_revision_history():
    store = MemoryCorrections()
    store.save(label(), original="original", key="raw/clip.mp3", duration=5)
    changed = label()
    changed.request_id = "request-0002"
    with pytest.raises(RevisionConflict):
        store.save(changed, original="original", key="raw/clip.mp3", duration=5)
    changed.expected_revision = 1
    changed.reverted = True
    store.save(changed, original="original", key="raw/clip.mp3", duration=5)
    assert (
        store.overlay(
            [{"channel": "14", "started_at": changed.started_at, "transcript": "original"}]
        )[0]["transcript"]
        == "original"
    )
    assert len(store.history) == 2


def test_partial_labels_and_invalid_ranges_never_enter_training():
    with pytest.raises(ValueError):
        label(reviewed=True).validate(duration=60)
    with pytest.raises(ValueError):
        label(reviewed=True, start_seconds=4, end_seconds=2).validate(duration=5)
    assert label(reviewed=False).validate(duration=60) is None
    assert (
        label(
            reviewed=True, start_seconds=0, end_seconds=20, training_text="Tug Osprey northbound"
        ).validate(duration=60)
        is None
    )


def test_day_assignment_keeps_channels_and_related_calls_together():
    assert split_day("2026-10-05T12:00:00Z") == split_day("2026-10-05T22:00:00Z")
    assert split_day("2026-10-05T12:00:00Z") in ("train", "validation", "test")
