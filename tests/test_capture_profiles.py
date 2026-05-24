from talkingboats.capture_profiles import (
    CAPTURE_PROFILES,
    render_rtlsdr_airband_config,
)


def test_debug_profile_uses_noaa_for_fast_feedback_and_vts_14() -> None:
    profile = CAPTURE_PROFILES["debug"]

    assert profile.mode == "sequential"
    assert [channel.channel for channel in profile.channels] == ["WX", "14"]
    assert profile.channels[0].frequency_hz == 162_550_000
    assert profile.channels[1].frequency_hz == 156_700_000


def test_elliott_bay_profile_monitors_two_nearby_non_noaa_channels() -> None:
    profile = CAPTURE_PROFILES["elliott_bay"]

    assert profile.mode == "multichannel"
    assert profile.center_frequency_hz == 156_675_000
    assert [channel.channel for channel in profile.channels] == ["13", "14"]
    assert all(channel.channel != "WX" for channel in profile.channels)


def test_elliott_bay_airband_config_writes_channel_spool_outputs() -> None:
    config = render_rtlsdr_airband_config(
        CAPTURE_PROFILES["elliott_bay"],
        output_root="/opt/talkingboats/spool/airband",
    )

    assert 'mode = "multichannel";' in config
    assert "centerfreq = 156675000;" in config
    assert "freq = 156650000;" in config
    assert "freq = 156700000;" in config
    assert 'label = "vhf-13";' in config
    assert 'label = "vhf-14";' in config
    assert 'type = "rawfile";' in config
    assert 'directory = "/opt/talkingboats/spool/airband/13";' in config
    assert 'directory = "/opt/talkingboats/spool/airband/14";' in config
