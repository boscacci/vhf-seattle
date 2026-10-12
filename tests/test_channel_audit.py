from datetime import UTC, datetime

import pytest

from talkingboats.channel_audit import choose_channels, pacific_window, rank_channels


def test_audit_uses_complete_pacific_days_across_dst():
    start, end = pacific_window(datetime(2026, 11, 3, 18, tzinfo=UTC))
    assert end.isoformat() == "2026-11-03T08:00:00+00:00"
    assert (end - start).total_seconds() == 7 * 86400 + 3600


def test_channel_selection_reserves_core_and_never_selects_74():
    rows = [
        {"channel": c, "audio_minutes": n, "usable_fraction": 1}
        for n, c in enumerate(["09", "65A", "66A", "67", "68", "69", "72", "73", "74"])
    ]
    selected = choose_channels(rank_channels(rows), count=8)
    assert selected[:3] == ["14", "13", "16"]
    assert "74" not in selected
    assert len(selected) == 8
    assert choose_channels(rank_channels(rows), count=6) == selected[:6]


def test_selection_requires_enough_measured_optional_channels():
    with pytest.raises(ValueError):
        choose_channels([], count=8)


def test_runtime_and_audit_selection_agree_and_turbo_stays_capacity_gated():
    import json
    from pathlib import Path

    from talkingboats.channel_metadata import ACTIVE_CAPTURE_CHANNELS

    selection = json.loads(Path("config/channel-selection.json").read_text())
    assert list(ACTIVE_CAPTURE_CHANNELS) == selection["active_channels"]
    assert selection["turbo_capacity_passed"] is any(
        c["passes"] for c in selection["benchmark"]["capacity_checks"]
    )
