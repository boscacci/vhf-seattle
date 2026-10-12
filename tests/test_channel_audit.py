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


def test_explicit_turbo_upgrade_allows_peak_backlog_with_overnight_recovery():
    import json
    from pathlib import Path

    from talkingboats.channel_audit import recovery_forecast

    selection = json.loads(Path('config/channel-selection.json').read_text())
    forecast = recovery_forecast(selection)
    assert selection['serving_model'] == 'large-v3-turbo'
    assert selection['activation_policy'] == 'allow_peak_backlog_overnight_recovery'
    assert forecast['max_daily_processing_seconds'] < 86400
    assert forecast['peak_hour_processing_seconds'] > 3600
    assert forecast['end_backlog_processing_seconds'] == 0
    assert forecast == selection['recovery_forecast']


def test_recovery_forecast_reports_sustained_overload():
    from talkingboats.channel_audit import recovery_forecast

    selection = {
        'active_channels': ['14'],
        'benchmark': {'samples': {'14': {'elapsed_seconds': 2, 'audio_seconds': 1}}},
        'channels': [{'channel': '14', 'hourly_audio_seconds': {
            '2026-10-05T07': 3600, '2026-10-05T08': 3600,
        }}],
        'window_start': '2026-10-05T07:00:00+00:00',
        'window_end': '2026-10-05T09:00:00+00:00',
    }
    forecast = recovery_forecast(selection)
    assert forecast['end_backlog_processing_seconds'] == 7200
    assert forecast['max_backlog_processing_seconds'] == 7200
