from pathlib import Path


def test_live_radio_app_builds_stream_url_from_current_host() -> None:
    app_js = Path("deploy/pi/live-radio/app.js").read_text(encoding="utf-8")
    index_html = Path("deploy/pi/live-radio/index.html").read_text(encoding="utf-8")

    assert "config.streamUrl" in app_js
    assert "window.location.hostname" in app_js
    assert "192.168." not in app_js
    assert "talkingboats-live.mp3" in app_js
    assert '<audio id="live-player"' in index_html


def test_live_radio_app_can_poll_optional_transcript_url() -> None:
    app_js = Path("deploy/pi/live-radio/app.js").read_text(encoding="utf-8")
    index_html = Path("deploy/pi/live-radio/index.html").read_text(encoding="utf-8")
    styles_css = Path("deploy/pi/live-radio/styles.css").read_text(encoding="utf-8")

    assert "transcriptUrl" in app_js
    assert "fetch(config.transcriptUrl" in app_js
    assert "renderTranscript" in app_js
    assert "caption-panel" in index_html
    assert "caption-list" in index_html
    assert ".caption-panel" in styles_css
    assert "TALKINGBOATS_TRANSCRIPT_URL" in Path("deploy/pi/install_live_radio.sh").read_text(
        encoding="utf-8"
    )


def test_live_radio_app_can_render_channel_menu_and_retune() -> None:
    app_js = Path("deploy/pi/live-radio/app.js").read_text(encoding="utf-8")
    index_html = Path("deploy/pi/live-radio/index.html").read_text(encoding="utf-8")
    styles_css = Path("deploy/pi/live-radio/styles.css").read_text(encoding="utf-8")

    assert "channels" in app_js
    assert "retuneUrl" in app_js
    assert "retuneChannel" in app_js
    assert 'channelSelect.addEventListener("change"' in app_js
    assert "player.load()" in app_js
    assert "reloadAndPlay" in app_js
    assert "playCurrentStream" in app_js
    assert "cacheBustStreamUrl" in app_js
    assert '<select id="channel-select"' in index_html
    assert "tune-button" not in index_html
    assert "tuneButton" not in app_js
    assert "play-button" not in index_html
    assert "reload-button" not in index_html
    assert "stream-url" not in index_html
    assert "channel-menu" in styles_css
    assert "overflow-x: hidden" in styles_css
    assert "asset-version=20260524-channel-ui" in index_html


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
    web_unit = Path("deploy/systemd/talkingboats-live-radio-web.service.example").read_text(
        encoding="utf-8"
    )
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
    assert "Restart=always" in web_unit
    assert "--bind 0.0.0.0" in web_unit
    assert "8050" in web_unit
    assert "talkingboats-profile-capture" in profile_unit
    assert "CPUQuota=85%" in profile_unit
    assert "talkingboats.spool_uploader" in uploader_unit
    assert "EnvironmentFile=/etc/talkingboats/live-radio.env" in uploader_unit


def test_edge_live_radio_stream_tees_pcm_through_detector_before_icecast() -> None:
    wrapper = Path("deploy/pi/live-radio/talkingboats-edge-live-radio-stream").read_text(
        encoding="utf-8"
    )
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "rtl_fm" in wrapper
    assert "python3 -m talkingboats.edge_capture" in wrapper
    assert "--tee-stdout" in wrapper
    assert "python3 -m talkingboats.icecast_source" in wrapper
    assert "--netrc-file" in wrapper
    assert "icecast://source:" not in wrapper
    assert "ffmpeg" in wrapper
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
    assert "run_elliott_bay_profile" in wrapper
    assert "rtl_airband" in wrapper
    assert "rtl_airband-elliott-bay.conf" in wrapper
    assert "timeout --foreground" not in wrapper
    assert "timeout --kill-after=10s" in wrapper
    assert "TALKINGBOATS_CAPTURE_SLOT_COOLDOWN_SECONDS:-5" in wrapper
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_PROFILE "debug"' in installer
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_WX_THRESHOLD_RMS "2200"' in installer
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_SLOT_COOLDOWN_SECONDS "5"' in installer
    assert "talkingboats.capture_profiles" in installer
    assert 'talkingboats-upload-spooled-clips = "talkingboats.spool_uploader:main"' in pyproject


def test_live_radio_audio_filter_is_flagged_and_default_off() -> None:
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
        assert "ffmpeg_filter_args=(-af" in wrapper
        assert '"${ffmpeg_filter_args[@]}"' in wrapper

    assert "TALKINGBOATS_AUDIO_FILTER_ENABLED" in installer
    assert 'append_env_if_missing TALKINGBOATS_AUDIO_FILTER_ENABLED "false"' in installer
    assert "highpass=f=250,lowpass=f=3200,afftdn=nf=-28,dynaudnorm=f=150:g=12" in installer
    assert "TALKINGBOATS_AUDIO_FILTER_ENABLED=true" in readme
