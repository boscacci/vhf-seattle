from pathlib import Path


def test_pi_deploy_no_longer_installs_a_separate_web_gui() -> None:
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")

    assert not Path("deploy/pi/live-radio/index.html").exists()
    assert not Path("deploy/pi/live-radio/app.js").exists()
    assert not Path("deploy/pi/live-radio/styles.css").exists()
    assert not Path("deploy/systemd/talkingboats-live-radio-web.service.example").exists()
    assert "talkingboats-live-radio-web.service" not in installer
    assert "/opt/talkingboats/live-radio" not in installer
    assert "config.js" not in installer


def test_live_radio_stream_script_requires_generated_source_password() -> None:
    stream_script = Path("deploy/pi/live-radio/talkingboats-live-radio-stream").read_text(
        encoding="utf-8"
    )
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")

    assert "python3 -m talkingboats.icecast_source" in stream_script
    assert "--netrc-file" in stream_script
    assert "icecast://source:" not in stream_script
    assert "openssl rand -base64 36" in installer
    assert "icecast.netrc" in installer
    assert "hackme" not in stream_script
    assert "hackme" not in installer


def test_live_radio_systemd_units_restart_and_stay_lan_scoped() -> None:
    stream_unit = Path(
        "deploy/systemd/talkingboats-live-radio-stream.service.example"
    ).read_text(encoding="utf-8")
    edge_unit = Path(
        "deploy/systemd/talkingboats-edge-live-radio-stream.service.example"
    ).read_text(encoding="utf-8")
    profile_unit = Path("deploy/systemd/talkingboats-profile-capture.service.example").read_text(
        encoding="utf-8"
    )
    uploader_unit = Path("deploy/systemd/talkingboats-spool-uploader.service.example").read_text(
        encoding="utf-8"
    )

    assert "Requires=icecast2.service" in stream_unit
    assert "Restart=always" in stream_unit
    assert "Requires=icecast2.service" in edge_unit
    assert "CPUQuota=85%" in edge_unit
    assert "Nice=5" in edge_unit
    assert "PYTHONPATH=/opt/talkingboats/app/src" in edge_unit
    assert "EnvironmentFile=/etc/talkingboats/live-radio.env" in stream_unit
    assert "talkingboats-profile-capture" in profile_unit
    assert "CPUQuota=85%" in profile_unit
    assert "talkingboats.spool_uploader" in uploader_unit
    assert "EnvironmentFile=/etc/talkingboats/live-radio.env" in uploader_unit


def test_edge_live_radio_stream_filters_pcm_before_detector_and_upload() -> None:
    wrapper = Path("deploy/pi/live-radio/talkingboats-edge-live-radio-stream").read_text(
        encoding="utf-8"
    )
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "rtl_fm" in wrapper
    assert "pcm_source_command=(" in wrapper
    assert "ffmpeg" in wrapper
    assert '"${pcm_source_command[@]}"' in wrapper
    assert 'sed \'s/^/[ffmpeg-pcm] /' in wrapper
    assert "python3 -m talkingboats.edge_capture" in wrapper
    assert "--tee-stdout" in wrapper
    assert "python3 -m talkingboats.icecast_source" in wrapper
    assert "--netrc-file" in wrapper
    assert "icecast://source:" not in wrapper
    assert "-f s16le" in wrapper
    assert "TALKINGBOATS_EDGE_MAX_TEMP_C" in wrapper
    assert "TALKINGBOATS_EDGE_RECORD_ENABLED" in wrapper
    assert "TALKINGBOATS_EDGE_RECORD_UPLOAD_ENABLED" in wrapper
    assert "TALKINGBOATS_EDGE_UPLOAD_ENABLED" in wrapper
    assert "--record-dir" in wrapper
    assert "--record-upload" in wrapper
    assert "--upload" in wrapper
    assert "--ingest-token" not in wrapper
    assert "--record-retention-seconds" in wrapper
    assert "TALKINGBOATS_EDGE_RECORD_ENABLED" in installer
    assert 'append_env_if_missing TALKINGBOATS_EDGE_RECORD_ENABLED "true"' in installer
    assert 'append_env_if_missing TALKINGBOATS_EDGE_RECORD_UPLOAD_ENABLED "false"' in installer
    assert 'append_env_if_missing TALKINGBOATS_EDGE_UPLOAD_ENABLED "false"' in installer
    assert "talkingboats-profile-capture.service" in installer
    assert "talkingboats-spool-uploader.service" in installer
    assert "systemctl disable --now talkingboats-live-radio-stream.service" in installer
    assert "systemctl disable --now talkingboats-edge-live-radio-stream.service" in installer
    assert 'talkingboats-edge-capture = "talkingboats.edge_capture:main"' in pyproject


def test_profile_capture_wrapper_supports_debug_and_elliott_bay_profiles() -> None:
    wrapper = Path("deploy/pi/live-radio/talkingboats-profile-capture").read_text(
        encoding="utf-8"
    )
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "TALKINGBOATS_CAPTURE_PROFILE" in wrapper
    assert "run_debug_profile" in wrapper
    assert "162550000" in wrapper
    assert "156700000" in wrapper
    assert "TALKINGBOATS_CAPTURE_DEBUG_WX_THRESHOLD_RMS:-2200" in wrapper
    assert "TALKINGBOATS_CAPTURE_DEBUG_WX_POST_ROLL_SECONDS:-4.5" in wrapper
    assert "TALKINGBOATS_CAPTURE_DEBUG_WX_MIN_CLIP_SECONDS:-4" in wrapper
    assert "TALKINGBOATS_CAPTURE_DEBUG_WX_MAX_CLIP_SECONDS:-30" in wrapper
    assert "run_elliott_bay_profile" in wrapper
    assert "rtl_airband" in wrapper
    assert "rtl_airband-elliott-bay.conf" in wrapper
    assert "timeout --foreground" not in wrapper
    assert "timeout --kill-after=10s" in wrapper
    assert "TALKINGBOATS_CAPTURE_SLOT_COOLDOWN_SECONDS:-5" in wrapper
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_PROFILE "debug"' in installer
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_WX_THRESHOLD_RMS "2200"' in installer
    assert (
        'append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_WX_POST_ROLL_SECONDS "4.5"'
        in installer
    )
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_WX_MIN_CLIP_SECONDS "4"' in installer
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_WX_MAX_CLIP_SECONDS "30"' in installer
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_SLOT_COOLDOWN_SECONDS "5"' in installer
    assert "talkingboats.capture_profiles" in installer
    assert 'talkingboats-upload-spooled-clips = "talkingboats.spool_uploader:main"' in pyproject


def test_live_radio_audio_filter_is_flagged_and_default_on() -> None:
    stream_wrapper = Path("deploy/pi/live-radio/talkingboats-live-radio-stream").read_text(
        encoding="utf-8"
    )
    edge_wrapper = Path("deploy/pi/live-radio/talkingboats-edge-live-radio-stream").read_text(
        encoding="utf-8"
    )
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    for wrapper in (stream_wrapper, edge_wrapper):
        assert "TALKINGBOATS_AUDIO_FILTER_ENABLED" in wrapper
        assert "TALKINGBOATS_AUDIO_FILTER" in wrapper
        assert "audio_filter" in wrapper

    assert "TALKINGBOATS_AUDIO_FILTER_ENABLED" in installer
    assert 'append_env_if_missing TALKINGBOATS_AUDIO_FILTER_ENABLED "true"' in installer
    assert "highpass=f=250,lowpass=f=3200,afftdn=nf=-28" in installer
    assert "TALKINGBOATS_AUDIO_FILTER_ENABLED=true" in readme
