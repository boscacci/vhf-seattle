from talkingboats.capture_profiles import (
    CAPTURE_PROFILES,
    AirbandIcecastOutput,
    render_rtlsdr_airband_config,
)


def test_debug_profile_uses_vts_14_for_fast_feedback() -> None:
    profile = CAPTURE_PROFILES["debug"]

    assert profile.mode == "sequential"
    assert [channel.channel for channel in profile.channels] == ["14"]
    assert profile.channels[0].frequency_hz == 156_700_000


def test_elliott_bay_profile_monitors_selected_marine_voice_channels() -> None:
    profile = CAPTURE_PROFILES["elliott_bay"]

    assert profile.mode == "multichannel"
    assert profile.center_frequency_hz == 156_675_000
    assert [channel.channel for channel in profile.channels] == ["13", "14", "68"]


def test_elliott_bay_airband_config_writes_channel_mp3_spool_outputs() -> None:
    config = render_rtlsdr_airband_config(
        CAPTURE_PROFILES["elliott_bay"],
        output_root="/opt/talkingboats/spool/airband",
    )

    assert 'mode = "multichannel";' in config
    assert "centerfreq = 156675000;" in config
    assert "freq = 156425000;" in config
    assert "freq = 156650000;" in config
    assert "freq = 156700000;" in config
    assert 'label = "vhf-68";' in config
    assert 'label = "vhf-13";' in config
    assert 'label = "vhf-14";' in config
    assert 'type = "file";' in config
    assert 'split_on_transmission = true;' in config
    assert 'directory = "/opt/talkingboats/spool/airband/68";' in config
    assert 'directory = "/opt/talkingboats/spool/airband/13";' in config
    assert 'directory = "/opt/talkingboats/spool/airband/14";' in config


def test_elliott_bay_airband_config_can_keep_vhf_14_live_audio() -> None:
    config = render_rtlsdr_airband_config(
        CAPTURE_PROFILES["elliott_bay"],
        output_root="/opt/talkingboats/spool/airband",
        icecast_output=AirbandIcecastOutput(
            channel="14",
            server="127.0.0.1",
            port=8000,
            mountpoint="/talkingboats-live.mp3",
            name="Talking Boats VTS / Seattle Traffic",
            password="source-password",
        ),
    )

    assert 'label = "vhf-14";' in config
    assert 'type = "icecast";' in config
    assert 'mountpoint = "talkingboats-live.mp3";' in config
    assert 'name = "Talking Boats VTS / Seattle Traffic";' in config
    assert "continuous = true;" in config
    assert 'password = "source-password";' in config


def test_elliott_bay_airband_config_can_stream_monitored_voice_channels() -> None:
    config = render_rtlsdr_airband_config(
        CAPTURE_PROFILES["elliott_bay"],
        output_root="/opt/talkingboats/spool/airband",
        icecast_outputs=(
            AirbandIcecastOutput(
                channel="68",
                server="127.0.0.1",
                port=8000,
                mountpoint="/talkingboats-68.mp3",
                name="Talking Boats Recreational",
                password="source-password",
            ),
            AirbandIcecastOutput(
                channel="13",
                server="127.0.0.1",
                port=8000,
                mountpoint="/talkingboats-13.mp3",
                name="Talking Boats Bridge-to-bridge",
                password="source-password",
            ),
            AirbandIcecastOutput(
                channel="14",
                server="127.0.0.1",
                port=8000,
                mountpoint="/talkingboats-live.mp3",
                name="Talking Boats VTS / Seattle Traffic",
                password="source-password",
            ),
        ),
    )

    assert config.count('type = "icecast";') == 3
    assert config.count("continuous = true;") == 3
    assert 'label = "vhf-68";' in config
    assert 'mountpoint = "talkingboats-68.mp3";' in config
    assert 'name = "Talking Boats Recreational";' in config
    assert 'label = "vhf-13";' in config
    assert 'mountpoint = "talkingboats-13.mp3";' in config
    assert 'name = "Talking Boats Bridge-to-bridge";' in config
    assert 'label = "vhf-14";' in config
    assert 'mountpoint = "talkingboats-live.mp3";' in config
    assert 'name = "Talking Boats VTS / Seattle Traffic";' in config
