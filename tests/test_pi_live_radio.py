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


def test_pi_installer_restarts_source_loaded_services_after_code_copy() -> None:
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")

    copy_index = installer.index('cp -a "${repo_root}/src/talkingboats"')
    restart_uploader_index = installer.index(
        "systemctl restart talkingboats-spool-uploader.service"
    )
    restart_capture_index = installer.index(
        "systemctl restart talkingboats-profile-capture.service"
    )

    assert copy_index < restart_uploader_index
    assert copy_index < restart_capture_index


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
    assert "--squelch-stdout" in wrapper
    assert "TALKINGBOATS_LIVE_AUDIO_SQUELCH_ENABLED" in wrapper
    assert "TALKINGBOATS_LIVE_SQUELCH_LOOKAHEAD_SECONDS" in wrapper
    assert "--live-squelch-lookahead-seconds" in wrapper
    assert "TALKINGBOATS_LIVE_OUTPUT_FILTER" in wrapper
    assert "alimiter=limit=0.55" in wrapper
    assert "python3 -m talkingboats.icecast_source" in wrapper
    assert "--netrc-file" in wrapper
    assert "icecast://source:" not in wrapper
    assert "-f s16le" in wrapper
    assert "TALKINGBOATS_EDGE_MAX_TEMP_C" in wrapper
    assert "TALKINGBOATS_EDGE_PRE_ROLL_SECONDS:-0" in wrapper
    assert "TALKINGBOATS_EDGE_POST_ROLL_SECONDS:-0.3" in wrapper
    assert "TALKINGBOATS_EDGE_RECORD_ENABLED" in wrapper
    assert "TALKINGBOATS_EDGE_RECORD_UPLOAD_ENABLED" in wrapper
    assert "TALKINGBOATS_EDGE_UPLOAD_ENABLED" in wrapper
    assert "TALKINGBOATS_EDGE_UPLOAD_AUDIO_FILTER" in wrapper
    assert "--mp3-audio-filter" in wrapper
    assert "--record-dir" in wrapper
    assert "--record-upload" in wrapper
    assert "--upload" in wrapper
    assert "--ingest-token" not in wrapper
    assert "--record-retention-seconds" in wrapper
    assert "TALKINGBOATS_EDGE_RECORD_ENABLED" in installer
    assert 'append_env_if_missing TALKINGBOATS_LIVE_AUDIO_SQUELCH_ENABLED "true"' in installer
    assert 'append_env_if_missing TALKINGBOATS_LIVE_SQUELCH_LOOKAHEAD_SECONDS "1.0"' in installer
    assert (
        'append_env_if_missing TALKINGBOATS_LIVE_OUTPUT_FILTER "alimiter=limit=0.55"'
        in installer
    )
    assert 'append_env_if_missing TALKINGBOATS_EDGE_RECORD_ENABLED "true"' in installer
    assert 'append_env_if_missing TALKINGBOATS_EDGE_RECORD_UPLOAD_ENABLED "false"' in installer
    assert 'append_env_if_missing TALKINGBOATS_EDGE_UPLOAD_ENABLED "false"' in installer
    assert "TALKINGBOATS_EDGE_UPLOAD_AUDIO_FILTER" in installer
    assert "acompressor=threshold=0.06" in installer
    assert "loudnorm=I=-16:LRA=8:TP=-6" in installer
    assert 'append_env_if_missing TALKINGBOATS_EDGE_PRE_ROLL_SECONDS "0"' in installer
    assert 'append_env_if_missing TALKINGBOATS_EDGE_POST_ROLL_SECONDS "0.3"' in installer
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
    assert "162550000" not in wrapper
    assert "156700000" in wrapper
    assert "current-status.json" in wrapper
    assert "TALKINGBOATS_CAPTURE_LIVE_MOUNT:-/talkingboats-live.mp3" in wrapper
    assert "TALKINGBOATS_CAPTURE_DEBUG_14_THRESHOLD_RMS:-5000" in wrapper
    assert "TALKINGBOATS_CAPTURE_DEBUG_14_SECONDS:-180" in wrapper
    assert "TALKINGBOATS_CAPTURE_DEBUG_14_MIN_CLIP_SECONDS:-2.0" in wrapper
    assert "TALKINGBOATS_CAPTURE_DEBUG_14_POST_ROLL_SECONDS:-0.4" in wrapper
    assert "run_elliott_bay_profile" in wrapper
    assert "rtl_airband" in wrapper
    assert '-F -e -c "${config_path}"' in wrapper
    assert "rtl_airband-elliott-bay.conf" in wrapper
    assert "timeout --foreground" not in wrapper
    assert "timeout --kill-after=10s" in wrapper
    assert "TALKINGBOATS_CAPTURE_SLOT_COOLDOWN_SECONDS:-5" in wrapper
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_PROFILE "debug"' in installer
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_14_SECONDS "180"' in installer
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_14_THRESHOLD_RMS "5000"' in installer
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_14_MIN_CLIP_SECONDS "2.0"' in installer
    assert (
        'append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_14_POST_ROLL_SECONDS "0.4"'
        in installer
    )
    assert (
        'replace_env_if_value TALKINGBOATS_CAPTURE_DEBUG_14_THRESHOLD_RMS "3600" "5000"'
        in installer
    )
    assert (
        'replace_env_if_value TALKINGBOATS_AIS_STATION_NAME "Elliott Bay VHF" '
        '"Elliott Bay VHF"'
        in installer
    )
    assert (
        'replace_env_if_value TALKINGBOATS_CAPTURE_PROFILE "debug" "voice_net_balanced"'
        in installer
    )
    assert "TALKINGBOATS_CAPTURE_DEBUG_WX" not in installer
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_SLOT_COOLDOWN_SECONDS "5"' in installer
    assert "talkingboats.capture_profiles" in installer
    assert (
        'squelch_args+=(--squelch-threshold "${TALKINGBOATS_VOICE_SQUELCH_THRESHOLD}")'
        in installer
    )
    assert (
        'squelch_args+=(--squelch-snr-threshold '
        '"${TALKINGBOATS_VOICE_SQUELCH_SNR_THRESHOLD}")'
        in installer
    )
    assert 'elif [[ -n "${TALKINGBOATS_VOICE_SQUELCH_THRESHOLD:-}" ]]' not in installer
    assert '--icecast-output "13:/talkingboats-13.mp3:Talking Boats Bridge-to-bridge"' in installer
    assert (
        '--icecast-output "14:${TALKINGBOATS_ICECAST_MOUNT:-/talkingboats-live.mp3}:'
        'Talking Boats VTS / Seattle Traffic"'
        in installer
    )
    assert '--icecast-output "68:/talkingboats-68.mp3:Talking Boats Recreational"' in installer
    assert "--icecast-source-password" in installer
    assert "<clients>48</clients>" in installer
    assert "<sources>24</sources>" in installer
    assert "<source-timeout>300</source-timeout>" in installer
    assert "<mount-name>/talkingboats-13.mp3</mount-name>" in installer
    assert "<mount-name>/talkingboats-68.mp3</mount-name>" in installer
    assert (
        "<mount-name>${TALKINGBOATS_ICECAST_MOUNT:-/talkingboats-live.mp3}</mount-name>"
        in installer
    )
    assert "chmod 0600 /etc/talkingboats/rtl_airband-voice-net-balanced.conf" in installer
    assert 'talkingboats-upload-spooled-clips = "talkingboats.spool_uploader:main"' in pyproject


def test_pi_installer_adds_serial_pinned_voice_and_ais_catcher_service() -> None:
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    profile_unit = Path("deploy/systemd/talkingboats-profile-capture.service.example").read_text(
        encoding="utf-8"
    )
    ais_catcher_unit = Path(
        "deploy/systemd/talkingboats-ais-catcher.service.example"
    ).read_text(encoding="utf-8")
    ais_catcher_wrapper = Path("deploy/pi/live-radio/talkingboats-ais-catcher").read_text(
        encoding="utf-8"
    )
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "TALKINGBOATS_VOICE_SDR_SERIAL" in installer
    assert "TALKINGBOATS_VOICE_DEVICE_INDEX" in installer
    assert "TALKINGBOATS_AIS_SDR_SERIAL" in installer
    assert "TALKINGBOATS_AIS_DEVICE_INDEX" in installer
    assert "TALKINGBOATS_AIS_INPUT" in installer
    assert "TALKINGBOATS_AIS_SERIAL_PORT" in installer
    assert "TALKINGBOATS_AIS_SERIAL_BAUD" in installer
    assert "TALKINGBOATS_AIS_SERIAL_INIT_SEQ" in installer
    assert "TALKINGBOATS_AIS_SERIAL_AUTO_INCLUDE_GPIO" in installer
    assert "TALKINGBOATS_AIS_WEB_PORT" in installer
    assert "TALKINGBOATS_AIS_COMMUNITY_FEED" in installer
    assert "TALKINGBOATS_AIS_SHARING_KEY" in installer
    assert "TALKINGBOATS_AIS_STATION_NAME" in installer
    assert "TALKINGBOATS_AIS_STATION_LINK" in installer
    assert "TALKINGBOATS_AIS_LAT" in installer
    assert "TALKINGBOATS_AIS_LON" in installer
    assert "TALKINGBOATS_AIS_SHARE_LOC" in installer
    assert "TALKINGBOATS_AIS_FRIENDS_HOST" in installer
    assert "TALKINGBOATS_AIS_FRIENDS_UDP_PORT" in installer
    assert "talkingboats-ais-catcher.service" in installer
    assert "talkingboats-ais-uploader.service" not in installer
    assert "--profile voice_net_balanced" in installer
    assert "--device-index" in installer
    assert "--device-serial" in installer
    assert "rtl_airband-voice-net-balanced.conf" in installer
    assert "talkingboats-ais-catcher" in ais_catcher_unit
    assert not Path("deploy/systemd/talkingboats-ais-uploader.service.example").exists()
    assert not Path("deploy/pi/live-radio/talkingboats-ais-uploader").exists()
    assert "TALKINGBOATS_AIS_INPUT" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_SERIAL_PORT" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_SERIAL_BAUD:-115200" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_SERIAL_INIT_SEQ:-co2,v" in ais_catcher_wrapper
    assert "/dev/serial/by-id/*Raspberry_Pi_Pico*" in ais_catcher_wrapper
    assert 'device_args=(-e "${serial_baud}" "${serial_port}")' in ais_catcher_wrapper
    assert 'device_args+=(-ge init_seq "${serial_init_seq}")' in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_INPUT=serial" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_SERIAL_AUTO_INCLUDE_GPIO" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_SDR_SERIAL" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_DEVICE_INDEX:-1" in ais_catcher_wrapper
    assert '"-d:${TALKINGBOATS_AIS_DEVICE_INDEX:-1}"' in ais_catcher_wrapper
    assert "-N \"${TALKINGBOATS_AIS_WEB_PORT:-8100}\"" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_COMMUNITY_FEED" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_SHARING_KEY" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_STATION_NAME:-Elliott Bay VHF" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_STATION_LINK:-https://robertboscacci.com" in ais_catcher_wrapper
    assert "station \"${TALKINGBOATS_AIS_STATION_NAME:-Elliott Bay VHF}\"" in ais_catcher_wrapper
    assert (
        "station_link "
        "\"${TALKINGBOATS_AIS_STATION_LINK:-https://robertboscacci.com}\""
        in ais_catcher_wrapper
    )
    assert "lat \"${TALKINGBOATS_AIS_LAT:-47.6190158}\"" in ais_catcher_wrapper
    assert "lon \"${TALKINGBOATS_AIS_LON:--122.3595353}\"" in ais_catcher_wrapper
    assert "share_loc \"${TALKINGBOATS_AIS_SHARE_LOC:-on}\"" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_FRIENDS_UDP_PORT must be numeric" in ais_catcher_wrapper
    assert (
        'ais_friends_args=(-u "${ais_friends_host}" "${TALKINGBOATS_AIS_FRIENDS_UDP_PORT}")'
        in ais_catcher_wrapper
    )
    assert '"${ais_friends_args[@]}"' in ais_catcher_wrapper
    assert "sharing_args=(-X off)" in ais_catcher_wrapper
    assert "sharing_args=(-X)" in ais_catcher_wrapper
    assert 'sharing_args=(-X "${TALKINGBOATS_AIS_SHARING_KEY}")' in ais_catcher_wrapper
    assert "MSGFORMAT JSON_FULL" not in ais_catcher_wrapper
    assert "CPUQuota=35%" in ais_catcher_unit
    assert "talkingboats.ais_uploader" not in pyproject
    assert "EnvironmentFile=/etc/talkingboats/live-radio.env" in profile_unit


def test_pi_installer_adds_cloud_hls_and_ais_forwarder_as_gated_relays() -> None:
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    hls_unit = Path("deploy/systemd/talkingboats-live-hls-relay.service.example").read_text(
        encoding="utf-8"
    )
    ais_forwarder_unit = Path(
        "deploy/systemd/talkingboats-ais-forwarder.service.example"
    ).read_text(encoding="utf-8")
    hls_wrapper = Path("deploy/pi/live-radio/talkingboats-live-hls-relay").read_text(
        encoding="utf-8"
    )
    env_example = Path("deploy/pi/talkingboats-capture.env.example").read_text(
        encoding="utf-8"
    )
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "talkingboats-live-hls-relay" in installer
    assert "talkingboats-ais-forwarder.service" in installer
    assert 'append_env_if_missing TALKINGBOATS_CLOUD_HLS_ENABLED "false"' in installer
    assert 'append_env_if_missing TALKINGBOATS_PUBLIC_SITE_BUCKET ""' in installer
    assert "TALKINGBOATS_CLOUD_HLS_ENABLED:-false" in installer
    assert "TALKINGBOATS_PUBLIC_SITE_BUCKET:-" in installer
    assert "TALKINGBOATS_AIS_HTTP_INGEST_URL:-" in installer
    assert "TALKINGBOATS_AIS_INGEST_TOKEN:-" in installer
    assert "AIS forwarder installed but disabled" in installer
    assert "ExecStart=/opt/talkingboats/bin/talkingboats-live-hls-relay" in hls_unit
    assert "CPUQuota=65%" in hls_unit
    assert "ExecStart=/usr/bin/python3 -m talkingboats.ais_forwarder" in ais_forwarder_unit
    assert "TALKINGBOATS_CLOUD_HLS_ENABLED:-false" in hls_wrapper
    assert "python3 -m talkingboats.hls_publisher" in hls_wrapper
    assert "ffmpeg" in hls_wrapper
    assert "TALKINGBOATS_AIS_HTTP_INGEST_URL=" in env_example
    assert "TALKINGBOATS_AIS_INGEST_TOKEN=" in env_example
    assert (
        'if [[ -n "${TALKINGBOATS_AIS_HTTP_INGEST_URL:-}" && '
        '-n "${TALKINGBOATS_AIS_INGEST_TOKEN:-}" ]]; then'
        in Path("deploy/pi/live-radio/talkingboats-ais-catcher").read_text(encoding="utf-8")
    )
    assert 'talkingboats-forward-ais = "talkingboats.ais_forwarder:main"' in pyproject
    assert 'talkingboats-publish-live-hls = "talkingboats.hls_publisher:main"' in pyproject


def test_pi_installer_streams_every_balanced_voice_net_channel_to_icecast() -> None:
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    hls_wrapper = Path("deploy/pi/live-radio/talkingboats-live-hls-relay").read_text(
        encoding="utf-8"
    )
    expected_channels = (
        "05A",
        "06",
        "09",
        "10",
        "13",
        "14",
        "16",
        "22A",
        "65A",
        "66A",
        "67",
        "68",
        "69",
        "71",
        "72",
        "73",
        "74",
        "77",
        "78A",
    )

    assert "<sources>24</sources>" in installer
    assert "append_env_if_missing TALKINGBOATS_CLOUD_HLS_CHANNELS \\" in installer
    assert '"05A,06,09,10,13,14,16,22A,65A,66A,67,68,69,71,72,73,74,77,78A"' in installer
    assert (
        'channels_csv="${TALKINGBOATS_CLOUD_HLS_CHANNELS:-'
        '05A,06,09,10,13,14,16,22A,65A,66A,67,68,69,71,72,73,74,77,78A}"'
        in hls_wrapper
    )
    for channel in expected_channels:
        mount_channel = channel.lower()
        mount = (
            "${TALKINGBOATS_ICECAST_MOUNT:-/talkingboats-live.mp3}"
            if channel == "14"
            else f"/talkingboats-{mount_channel}.mp3"
        )
        assert f'--icecast-output "{channel}:' in installer
        assert f"<mount-name>{mount}</mount-name>" in installer
        if channel != "14":
            assert (
                f'{channel}) printf \'%s\\n\' "/talkingboats-{mount_channel}.mp3" ;;'
                in hls_wrapper
            )


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
    assert "TALKINGBOATS_TRANSCRIBE_SAMPLE_RATE_HZ=16000" in readme
    assert "TALKINGBOATS_TRANSCRIBE_BEAM_SIZE=5" in readme
    assert "TALKINGBOATS_TRANSCRIBE_HOTWORDS" in readme
    assert "TALKINGBOATS_TRANSCRIBE_TRUST_EDGE_PREPROCESSED_AUDIO=true" in readme
    assert "dynaudnorm" not in readme


def test_uploaded_clip_transcriber_defaults_to_edge_preprocessed_mp3s() -> None:
    unit = Path("deploy/systemd/talkingboats-uploaded-clip-transcriber.service.example").read_text(
        encoding="utf-8"
    )
    compose = Path("compose.yaml").read_text(encoding="utf-8")

    assert "TALKINGBOATS_TRANSCRIBE_TRUST_EDGE_PREPROCESSED_AUDIO=true" in unit
    assert "TALKINGBOATS_TRANSCRIBE_TRUST_EDGE_PREPROCESSED_AUDIO" in compose
