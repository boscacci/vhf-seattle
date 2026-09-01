from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_pi_deploy_files_use_lf_line_endings() -> None:
    deploy_paths = [
        Path("deploy/pi/install_live_radio.sh"),
        Path("deploy/pi/live-radio/talkingboats-profile-capture"),
        Path("deploy/pi/live-radio/talkingboats-pi-boot-recovery"),
        Path("deploy/systemd/talkingboats-live-radio-web.service.example"),
    ]

    for path in deploy_paths:
        assert b"\r\n" not in path.read_bytes(), str(path)


def test_pi_deploy_installs_status_web_without_reintroducing_gui_assets() -> None:
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    status_unit = Path("deploy/systemd/talkingboats-live-radio-web.service.example")

    assert not Path("deploy/pi/live-radio/index.html").exists()
    assert not Path("deploy/pi/live-radio/app.js").exists()
    assert not Path("deploy/pi/live-radio/styles.css").exists()
    assert status_unit.exists()
    assert "talkingboats-live-radio-web.service" in installer
    assert "systemctl enable talkingboats-live-radio-web.service" in installer
    assert "systemctl restart talkingboats-live-radio-web.service" in installer
    assert "/opt/talkingboats/live-radio" in installer
    assert "deploy/pi/live-radio/config.js" not in installer
    assert "rm -f" in installer
    assert "/opt/talkingboats/live-radio/index.html" in installer


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
    stream_unit = Path("deploy/systemd/talkingboats-live-radio-stream.service.example").read_text(
        encoding="utf-8"
    )
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
    assert "RuntimeMaxSec=24h" in profile_unit
    assert "CPUQuota=85%" in profile_unit
    assert "talkingboats.spool_uploader" in uploader_unit
    assert "EnvironmentFile=/etc/talkingboats/live-radio.env" in uploader_unit
    assert "--min-duration-seconds 1" in uploader_unit
    assert "--max-synchronous-channels 3" in uploader_unit
    assert "--max-files-per-poll 20" in uploader_unit
    assert "--max-retained-files 300" in uploader_unit


def test_pi_units_do_not_give_up_during_blackout_boot_races() -> None:
    unit_names = [
        "talkingboats-ais-catcher.service.example",
        "talkingboats-ais-forwarder.service.example",
        "talkingboats-edge-live-radio-stream.service.example",
        "talkingboats-live-hls-relay.service.example",
        "talkingboats-live-radio-stream.service.example",
        "talkingboats-live-radio-web.service.example",
        "talkingboats-profile-capture.service.example",
        "talkingboats-spool-uploader.service.example",
    ]

    for unit_name in unit_names:
        unit = Path("deploy/systemd", unit_name).read_text(encoding="utf-8")
        assert "StartLimitIntervalSec=0" in unit, unit_name
        assert "Restart=" in unit, unit_name


def test_pi_installer_installs_blackout_boot_recovery_service() -> None:
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    recovery_unit = Path("deploy/systemd/talkingboats-pi-boot-recovery.service.example").read_text(
        encoding="utf-8"
    )
    recovery_script = Path("deploy/pi/live-radio/talkingboats-pi-boot-recovery").read_text(
        encoding="utf-8"
    )

    assert "talkingboats-pi-boot-recovery" in installer
    assert "talkingboats-pi-boot-recovery.service" in installer
    assert "systemctl enable talkingboats-pi-boot-recovery.service" in installer
    assert "systemctl restart talkingboats-pi-boot-recovery.service" in installer
    assert "After=network-online.target" in recovery_unit
    assert "ExecStart=/opt/talkingboats/bin/talkingboats-pi-boot-recovery" in recovery_unit
    assert "WantedBy=multi-user.target" in recovery_unit
    assert "systemctl reset-failed" in recovery_script
    assert "systemctl is-enabled" in recovery_script
    assert "icecast2.service" in recovery_script
    assert "talkingboats-live-radio-web.service" in recovery_script
    assert "talkingboats-spool-uploader.service" in recovery_script


def test_pi_recurring_healthcheck_recovers_local_receiver_dependencies() -> None:
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    service = Path("deploy/systemd/talkingboats-pi-healthcheck.service.example").read_text(
        encoding="utf-8"
    )
    timer = Path("deploy/systemd/talkingboats-pi-healthcheck.timer.example").read_text(
        encoding="utf-8"
    )
    script = Path("deploy/pi/live-radio/talkingboats-pi-healthcheck").read_text(encoding="utf-8")

    assert "ExecStart=/opt/talkingboats/bin/talkingboats-pi-healthcheck" in service
    assert "TimeoutStartSec=2min" in service
    assert "OnBootSec=3min" in timer
    assert "OnUnitActiveSec=2min" in timer
    assert "Persistent=true" in timer
    assert "Unit=talkingboats-pi-healthcheck.service" in timer
    assert "talkingboats-ais-catcher.service" in script
    assert "talkingboats-profile-capture.service" in script
    assert "talkingboats-spool-uploader.service" in script
    assert "ais_forwarder_configured" in script
    assert 'ensure_active "talkingboats-ais-forwarder.service"' in script
    assert "127.0.0.1:8100/api/stat.json" in script
    assert "127.0.0.1:8000/status-json.xsl" in script
    assert "talkingboats-pi-healthcheck.timer" in installer
    assert "systemctl enable talkingboats-pi-healthcheck.timer" in installer


def test_pi_healthcheck_detects_an_unreachable_private_api_without_a_restart_loop() -> None:
    service = Path("deploy/systemd/talkingboats-pi-healthcheck.service.example").read_text(
        encoding="utf-8"
    )
    script = Path("deploy/pi/live-radio/talkingboats-pi-healthcheck").read_text(encoding="utf-8")

    assert "TALKINGBOATS_PRIVATE_API" in script
    assert "private_api_unreachable" in script
    assert "/healthz" in script
    assert "talkingboats-spool-uploader.service" in script
    assert "Restart=on-failure" not in service


def test_pi_healthcheck_recovers_an_sdr_clip_flood_without_a_restart_loop() -> None:
    script = Path("deploy/pi/live-radio/talkingboats-pi-healthcheck").read_text(encoding="utf-8")

    assert "TALKINGBOATS_PI_SPOOL_FLOOD_WINDOW_MINUTES" in script
    assert "TALKINGBOATS_PI_SPOOL_FLOOD_MAX_FILES" in script
    assert "TALKINGBOATS_PI_SPOOL_FLOOD_COOLDOWN_MINUTES" in script
    assert "ensure_capture_rate_healthy" in script
    assert "spool_flood_" in script
    assert "spool_flood_recovery_cooldown" in script
    assert 'systemctl restart "${capture_service}"' in script


def test_profile_capture_resets_only_the_pinned_voice_sdr_before_start() -> None:
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    unit = Path("deploy/systemd/talkingboats-profile-capture.service.example").read_text(
        encoding="utf-8"
    )
    reset_script = Path("deploy/pi/live-radio/talkingboats-reset-voice-sdr").read_text(
        encoding="utf-8"
    )

    assert "ExecStartPre=/opt/talkingboats/bin/talkingboats-reset-voice-sdr" in unit
    assert "talkingboats-reset-voice-sdr" in installer
    assert "TALKINGBOATS_VOICE_SDR_SERIAL" in reset_script
    assert "TALKINGBOATS_VOICE_SDR_USB_VENDOR_ID" in reset_script
    assert "TALKINGBOATS_VOICE_SDR_USB_PRODUCT_ID" in reset_script
    assert "voice_sdr_reset_ambiguous" in reset_script
    assert "voice_sdr_reset_cooldown" in reset_script


def test_voice_sdr_reset_uses_the_exact_serial_and_observes_cooldown(
    tmp_path: Path,
) -> None:
    sysfs_root = tmp_path / "sys" / "bus" / "usb"
    devices_root = sysfs_root / "devices"
    driver_root = sysfs_root / "drivers" / "usb"
    voice_device = devices_root / "1-1.1"
    ais_device = devices_root / "1-1.2"
    for device, vendor, product, serial in (
        (voice_device, "0bda", "2838", "VOICE123"),
        (ais_device, "2e8a", "0009", "AIS456"),
    ):
        device.mkdir(parents=True)
        (device / "idVendor").write_text(vendor, encoding="utf-8")
        (device / "idProduct").write_text(product, encoding="utf-8")
        (device / "serial").write_text(serial, encoding="utf-8")
    driver_root.mkdir(parents=True)
    (driver_root / "unbind").touch()
    (driver_root / "bind").touch()
    runtime_root = tmp_path / "run"

    env = {
        **os.environ,
        "TALKINGBOATS_VOICE_SDR_SERIAL": "VOICE123",
        "TALKINGBOATS_VOICE_SDR_SYSFS_ROOT": str(devices_root),
        "TALKINGBOATS_VOICE_SDR_USB_DRIVER_ROOT": str(driver_root),
        "TALKINGBOATS_VOICE_SDR_RESET_RUNTIME_ROOT": str(runtime_root),
        "TALKINGBOATS_VOICE_SDR_RESET_SETTLE_SECONDS": "0",
    }
    first = subprocess.run(
        ["bash", "deploy/pi/live-radio/talkingboats-reset-voice-sdr"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
    second = subprocess.run(
        ["bash", "deploy/pi/live-radio/talkingboats-reset-voice-sdr"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert (driver_root / "unbind").read_text(encoding="utf-8") == "1-1.1"
    assert (driver_root / "bind").read_text(encoding="utf-8") == "1-1.1"
    assert "voice_sdr_reset_complete" in first.stdout
    assert second.returncode == 0, second.stdout + second.stderr
    assert "voice_sdr_reset_cooldown" in second.stdout


def test_pi_healthcheck_recovers_connected_but_stalled_capture(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture_restarted = tmp_path / "capture-restarted"
    spool_root = tmp_path / "spool"
    spool_root.mkdir()
    env_file = tmp_path / "live-radio.env"
    env_file.write_text("TALKINGBOATS_PRIVATE_API=http://private.test\n", encoding="utf-8")
    proc_root = tmp_path / "proc"
    proc_pid = proc_root / "4242"
    proc_pid.mkdir(parents=True)
    proc_stat = proc_pid / "stat"
    proc_stat.write_text(
        "4242 (rtl_airband) S 1 1 1 0 0 0 0 0 0 0 10 0 0 0 0 0 0\n",
        encoding="utf-8",
    )
    uptime_path = tmp_path / "uptime"
    uptime_path.write_text("100.00 50.00\n", encoding="utf-8")
    fresh_start = tmp_path / "fresh-start"
    force_pid_change = tmp_path / "force-pid-change"
    pid_changed = tmp_path / "pid-changed"
    changed_proc_pid = proc_root / "4343"
    changed_proc_pid.mkdir()
    (changed_proc_pid / "stat").write_text(
        "4343 (rtl_airband) S 1 1 1 0 0 0 0 0 0 0 5 0 0 0 0 0 0\n",
        encoding="utf-8",
    )

    commands = {
        "curl": """#!/usr/bin/env bash
if [[ " $* " == *" http://icecast.test/status-json.xsl "* ]]; then
  printf '%s\n' '{"icestats":{"source":{"listenurl":"http://pi.test:8000/talkingboats-live.mp3"}}}'
fi
exit 0
""",
        "systemctl": f"""#!/usr/bin/env bash
if [[ " $* " == *" show -p MainPID --value talkingboats-profile-capture.service "* ]]; then
  if [[ -f "{pid_changed}" ]]; then printf '4343\n'; else printf '4242\n'; fi
elif [[ " $* " == *" ActiveEnterTimestampMonotonic "* ]]; then
  if [[ -f "{fresh_start}" ]]; then printf '99000000\n'; else printf '0\n'; fi
elif [[ " $* " == *" restart talkingboats-profile-capture.service "* ]]; then
  touch "{capture_restarted}"
fi
exit 0
""",
        "sleep": f"""#!/usr/bin/env bash
if [[ -f "{force_pid_change}" ]]; then
  touch "{pid_changed}"
  exit 0
fi
current=$(awk '{{print $14}}' "{proc_stat}")
increment=1
[[ -f "{capture_restarted}" ]] && increment=20
next=$((current + increment))
printf '4242 (rtl_airband) S 1 1 1 0 0 0 0 0 0 0 %s 0 0 0 0 0 0\n' "$next" > "{proc_stat}"
""",
    }
    for name, contents in commands.items():
        executable = bin_dir / name
        executable.write_text(contents, encoding="utf-8")
        executable.chmod(0o755)

    result = subprocess.run(
        ["bash", "deploy/pi/live-radio/talkingboats-pi-healthcheck"],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TALKINGBOATS_PI_ENV_FILE": str(env_file),
            "TALKINGBOATS_PI_ICECAST_STATUS_URL": "http://icecast.test/status-json.xsl",
            "TALKINGBOATS_PI_SPOOL_ROOT": str(spool_root),
            "TALKINGBOATS_PI_PROC_ROOT": str(proc_root),
            "TALKINGBOATS_PI_UPTIME_PATH": str(uptime_path),
            "TALKINGBOATS_PI_CAPTURE_PROGRESS_SECONDS": "1",
            "TALKINGBOATS_PI_CAPTURE_MIN_CPU_TICKS": "10",
            "TALKINGBOATS_PI_CAPTURE_STARTUP_GRACE_SECONDS": "60",
            "TALKINGBOATS_PI_HEALTHCHECK_ATTEMPTS": "1",
            "TALKINGBOATS_PI_HEALTHCHECK_RESTART_WAIT_SECONDS": "1",
        },
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert capture_restarted.exists()
    assert "capture_cpu_stalled" in result.stdout
    assert "capture_cpu_recovered" in result.stdout

    capture_restarted.unlink()
    fresh_start.touch()
    proc_stat.write_text(
        "4242 (rtl_airband) S 1 1 1 0 0 0 0 0 0 0 10 0 0 0 0 0 0\n",
        encoding="utf-8",
    )
    startup_result = subprocess.run(
        ["bash", "deploy/pi/live-radio/talkingboats-pi-healthcheck"],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TALKINGBOATS_PI_ENV_FILE": str(env_file),
            "TALKINGBOATS_PI_ICECAST_STATUS_URL": "http://icecast.test/status-json.xsl",
            "TALKINGBOATS_PI_SPOOL_ROOT": str(spool_root),
            "TALKINGBOATS_PI_PROC_ROOT": str(proc_root),
            "TALKINGBOATS_PI_UPTIME_PATH": str(uptime_path),
            "TALKINGBOATS_PI_CAPTURE_PROGRESS_SECONDS": "1",
            "TALKINGBOATS_PI_CAPTURE_MIN_CPU_TICKS": "10",
            "TALKINGBOATS_PI_CAPTURE_STARTUP_GRACE_SECONDS": "60",
            "TALKINGBOATS_PI_HEALTHCHECK_ATTEMPTS": "1",
            "TALKINGBOATS_PI_HEALTHCHECK_RESTART_WAIT_SECONDS": "1",
        },
        capture_output=True,
        check=False,
        text=True,
    )

    assert startup_result.returncode == 0, startup_result.stdout + startup_result.stderr
    assert not capture_restarted.exists()
    assert "capture_progress_startup_grace" in startup_result.stdout

    fresh_start.unlink()
    force_pid_change.touch()
    pid_changed.unlink(missing_ok=True)
    process_change_result = subprocess.run(
        ["bash", "deploy/pi/live-radio/talkingboats-pi-healthcheck"],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TALKINGBOATS_PI_ENV_FILE": str(env_file),
            "TALKINGBOATS_PI_ICECAST_STATUS_URL": "http://icecast.test/status-json.xsl",
            "TALKINGBOATS_PI_SPOOL_ROOT": str(spool_root),
            "TALKINGBOATS_PI_PROC_ROOT": str(proc_root),
            "TALKINGBOATS_PI_UPTIME_PATH": str(uptime_path),
            "TALKINGBOATS_PI_CAPTURE_PROGRESS_SECONDS": "1",
            "TALKINGBOATS_PI_CAPTURE_MIN_CPU_TICKS": "10",
            "TALKINGBOATS_PI_CAPTURE_STARTUP_GRACE_SECONDS": "60",
            "TALKINGBOATS_PI_HEALTHCHECK_ATTEMPTS": "1",
            "TALKINGBOATS_PI_HEALTHCHECK_RESTART_WAIT_SECONDS": "1",
        },
        capture_output=True,
        check=False,
        text=True,
    )

    assert process_change_result.returncode == 0, (
        process_change_result.stdout + process_change_result.stderr
    )
    assert not capture_restarted.exists()
    assert "capture_process_changed_during_probe" in process_change_result.stdout


def test_pi_healthcheck_recovers_active_capture_with_missing_icecast_source(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture_restarted = tmp_path / "capture-restarted"
    spool_root = tmp_path / "spool"
    spool_root.mkdir()
    env_file = tmp_path / "live-radio.env"
    env_file.write_text("TALKINGBOATS_PRIVATE_API=http://private.test\n", encoding="utf-8")

    commands = {
        "curl": f"""#!/usr/bin/env bash
if [[ " $* " == *" http://icecast.test/status-json.xsl "* ]]; then
  if [[ -f "{capture_restarted}" ]]; then
    printf '%s\n' '{{"icestats":{{"source":{{"listenurl":"http://pi.test:8000/talkingboats-live.mp3"}}}}}}'
  else
    printf '%s\n' '{{"icestats":{{"source":[]}}}}'
  fi
fi
exit 0
""",
        "systemctl": f"""#!/usr/bin/env bash
if [[ " $* " == *" restart talkingboats-profile-capture.service "* ]]; then
  touch "{capture_restarted}"
fi
exit 0
""",
        "sleep": """#!/usr/bin/env bash
exit 0
""",
    }
    for name, contents in commands.items():
        executable = bin_dir / name
        executable.write_text(contents, encoding="utf-8")
        executable.chmod(0o755)

    result = subprocess.run(
        ["bash", "deploy/pi/live-radio/talkingboats-pi-healthcheck"],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TALKINGBOATS_PI_ENV_FILE": str(env_file),
            "TALKINGBOATS_PI_ICECAST_STATUS_URL": "http://icecast.test/status-json.xsl",
            "TALKINGBOATS_PI_SPOOL_ROOT": str(spool_root),
            "TALKINGBOATS_PI_CAPTURE_PROGRESS_ENABLED": "false",
            "TALKINGBOATS_PI_HEALTHCHECK_ATTEMPTS": "1",
            "TALKINGBOATS_PI_HEALTHCHECK_RESTART_WAIT_SECONDS": "1",
        },
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert capture_restarted.exists()
    assert "icecast_source_missing" in result.stdout
    assert "icecast_source_recovered" in result.stdout


def test_pi_icecast_source_timeout_outlives_the_daily_capture_restart() -> None:
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    capture_unit = Path(
        "deploy/systemd/talkingboats-profile-capture.service.example"
    ).read_text(encoding="utf-8")

    assert "RuntimeMaxSec=24h" in capture_unit
    assert 'append_env_if_missing TALKINGBOATS_ICECAST_SOURCE_TIMEOUT_SECONDS "90000"' in installer
    assert (
        "<source-timeout>${TALKINGBOATS_ICECAST_SOURCE_TIMEOUT_SECONDS:-90000}</source-timeout>"
        in installer
    )


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
    assert "sed 's/^/[ffmpeg-pcm] /" in wrapper
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
    assert "TALKINGBOATS_EDGE_PRE_ROLL_SECONDS:-0.5" in wrapper
    assert "TALKINGBOATS_EDGE_POST_ROLL_SECONDS:-0.7" in wrapper
    assert "TALKINGBOATS_EDGE_RECORD_ENABLED" in wrapper
    assert "TALKINGBOATS_EDGE_RECORD_UPLOAD_ENABLED" in wrapper
    assert "TALKINGBOATS_EDGE_UPLOAD_ENABLED" in wrapper
    assert "TALKINGBOATS_EDGE_UPLOAD_AUDIO_FILTER" not in wrapper
    assert "--mp3-audio-filter" not in wrapper
    assert "--record-dir" in wrapper
    assert "--record-upload" in wrapper
    assert "--upload" in wrapper
    assert "--ingest-token" not in wrapper
    assert "--record-retention-seconds" in wrapper
    assert "TALKINGBOATS_EDGE_RECORD_ENABLED" in installer
    assert 'append_env_if_missing TALKINGBOATS_LIVE_AUDIO_SQUELCH_ENABLED "true"' in installer
    assert 'append_env_if_missing TALKINGBOATS_LIVE_SQUELCH_LOOKAHEAD_SECONDS "1.0"' in installer
    assert (
        'append_env_if_missing TALKINGBOATS_LIVE_OUTPUT_FILTER "alimiter=limit=0.55"' in installer
    )
    assert 'append_env_if_missing TALKINGBOATS_EDGE_RECORD_ENABLED "true"' in installer
    assert 'append_env_if_missing TALKINGBOATS_EDGE_RECORD_UPLOAD_ENABLED "false"' in installer
    assert 'append_env_if_missing TALKINGBOATS_EDGE_UPLOAD_ENABLED "false"' in installer
    assert "TALKINGBOATS_EDGE_UPLOAD_AUDIO_FILTER" not in installer
    assert 'append_env_if_missing TALKINGBOATS_EDGE_PRE_ROLL_SECONDS "0"' in installer
    assert 'append_env_if_missing TALKINGBOATS_EDGE_POST_ROLL_SECONDS "0.3"' in installer
    assert "talkingboats-profile-capture.service" in installer
    assert "talkingboats-spool-uploader.service" in installer
    assert "systemctl disable --now talkingboats-live-radio-stream.service" in installer
    assert "systemctl disable --now talkingboats-edge-live-radio-stream.service" in installer
    assert 'talkingboats-edge-capture = "talkingboats.edge_capture:main"' in pyproject


def test_profile_capture_wrapper_supports_debug_and_elliott_bay_profiles() -> None:
    wrapper = Path("deploy/pi/live-radio/talkingboats-profile-capture").read_text(encoding="utf-8")
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "TALKINGBOATS_CAPTURE_PROFILE" in wrapper
    assert "run_debug_profile" in wrapper
    assert "162550000" not in wrapper
    assert "156700000" in wrapper
    assert "current-status.json" in wrapper
    assert "TALKINGBOATS_CAPTURE_STATUS_CHANNEL:-14" in wrapper
    assert "TALKINGBOATS_CAPTURE_STATUS_FREQUENCY_HZ:-156700000" in wrapper
    assert "TALKINGBOATS_CAPTURE_STATUS_LABEL:-VTS / Seattle Traffic" in wrapper
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
        'append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_14_POST_ROLL_SECONDS "0.4"' in installer
    )
    assert (
        'replace_env_if_value TALKINGBOATS_CAPTURE_DEBUG_14_THRESHOLD_RMS "3600" "5000"'
        in installer
    )
    assert (
        'replace_env_if_value TALKINGBOATS_AIS_STATION_NAME "Elliott Bay VHF" '
        '"Elliott Bay VHF"' in installer
    )
    assert (
        'replace_env_if_value TALKINGBOATS_CAPTURE_PROFILE "debug" "voice_net_balanced"'
        in installer
    )
    assert "TALKINGBOATS_CAPTURE_DEBUG_WX" not in installer
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_SLOT_COOLDOWN_SECONDS "5"' in installer
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_STATUS_CHANNEL "14"' in installer
    assert 'append_env_if_missing TALKINGBOATS_CAPTURE_STATUS_FREQUENCY_HZ "156700000"' in installer
    assert (
        'append_env_if_missing TALKINGBOATS_CAPTURE_STATUS_LABEL "VTS / Seattle Traffic"'
        in installer
    )
    assert "talkingboats.capture_profiles" in installer
    assert (
        'squelch_args+=(--squelch-threshold "${TALKINGBOATS_VOICE_SQUELCH_THRESHOLD}")' in installer
    )
    assert (
        "squelch_args+=(--squelch-snr-threshold "
        '"${TALKINGBOATS_VOICE_SQUELCH_SNR_THRESHOLD}")' in installer
    )
    assert "printf 'TALKINGBOATS_VOICE_SQUELCH_THRESHOLD=%q\\n' \"-35\"" in installer
    assert "printf 'TALKINGBOATS_VOICE_SQUELCH_SNR_THRESHOLD=%q\\n' \"\"" in installer
    assert "printf 'TALKINGBOATS_VOICE_CHANNEL_SQUELCH_THRESHOLDS=%q\\n' \"\"" in installer
    assert "printf 'TALKINGBOATS_VOICE_CHANNEL_SQUELCH_SNR_THRESHOLDS=%q\\n' \"\"" in installer
    assert 'append_env_if_missing TALKINGBOATS_VOICE_SQUELCH_THRESHOLD "-35"' in installer
    assert 'append_env_if_missing TALKINGBOATS_VOICE_SQUELCH_SNR_THRESHOLD ""' in installer
    assert 'append_env_if_missing TALKINGBOATS_VOICE_CHANNEL_SQUELCH_THRESHOLDS ""' in installer
    assert 'append_env_if_missing TALKINGBOATS_VOICE_CHANNEL_SQUELCH_SNR_THRESHOLDS ""' in installer
    assert 'squelch_args+=(--channel-squelch-threshold "${spec}")' in installer
    assert 'squelch_args+=(--channel-squelch-snr-threshold "${spec}")' in installer
    assert 'replace_env_if_value TALKINGBOATS_VOICE_SQUELCH_SNR_THRESHOLD "20" ""' in installer
    assert "Set only one of TALKINGBOATS_VOICE_SQUELCH_THRESHOLD or" in installer
    assert '--icecast-output "13:/talkingboats-13.mp3:Talking Boats Bridge-to-bridge"' in installer
    assert (
        '--icecast-output "14:${TALKINGBOATS_ICECAST_MOUNT:-/talkingboats-live.mp3}:'
        'Talking Boats VTS / Seattle Traffic"' in installer
    )
    assert '--icecast-output "68:/talkingboats-68.mp3:Talking Boats Recreational"' in installer
    assert "--icecast-source-password" in installer
    assert "<clients>48</clients>" in installer
    assert "<sources>24</sources>" in installer
    assert (
        "<source-timeout>${TALKINGBOATS_ICECAST_SOURCE_TIMEOUT_SECONDS:-90000}</source-timeout>"
        in installer
    )
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
    ais_catcher_unit = Path("deploy/systemd/talkingboats-ais-catcher.service.example").read_text(
        encoding="utf-8"
    )
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
    assert '-N "${TALKINGBOATS_AIS_WEB_PORT:-8100}"' in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_COMMUNITY_FEED" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_SHARING_KEY" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_STATION_NAME:-Elliott Bay VHF" in ais_catcher_wrapper
    assert "TALKINGBOATS_AIS_STATION_LINK:-https://seattleboatradio.com" in ais_catcher_wrapper
    assert 'station "${TALKINGBOATS_AIS_STATION_NAME:-Elliott Bay VHF}"' in ais_catcher_wrapper
    assert (
        "station_link "
        '"${TALKINGBOATS_AIS_STATION_LINK:-https://seattleboatradio.com}"' in ais_catcher_wrapper
    )
    assert 'lat "${TALKINGBOATS_AIS_LAT:-47.6190158}"' in ais_catcher_wrapper
    assert 'lon "${TALKINGBOATS_AIS_LON:--122.3595353}"' in ais_catcher_wrapper
    assert 'share_loc "${TALKINGBOATS_AIS_SHARE_LOC:-on}"' in ais_catcher_wrapper
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
    env_example = Path("deploy/pi/talkingboats-capture.env.example").read_text(encoding="utf-8")
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
    assert (
        'http_args=(-H "http://${forwarder_host}:${forwarder_port}/" '
        'interval "${TALKINGBOATS_AIS_HTTP_INTERVAL_SECONDS:-1}" response off)'
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
        '05A,06,09,10,13,14,16,22A,65A,66A,67,68,69,71,72,73,74,77,78A}"' in hls_wrapper
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
                f"{channel}) printf '%s\\n' \"/talkingboats-{mount_channel}.mp3\" ;;" in hls_wrapper
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
    assert "TALKINGBOATS_TRANSCRIBE_TRUST_EDGE_PREPROCESSED_AUDIO" not in readme
    assert "dynaudnorm" not in readme


def test_multichannel_capture_uses_ranked_busy_channels_and_buffered_boundaries() -> None:
    from talkingboats.capture_profiles import CAPTURE_PROFILES, render_rtlsdr_airband_config

    profile = CAPTURE_PROFILES["voice_net_balanced"]
    assert [channel.channel for channel in profile.channels] == [
        "14",
        "13",
        "66A",
        "67",
        "77",
        "68",
        "74",
        "73",
        "71",
        "78A",
        "69",
        "72",
    ]
    rendered = render_rtlsdr_airband_config(profile, output_root="/tmp/spool")
    assert rendered.count("pre_roll_seconds = 0.50;") == 12
    assert rendered.count("post_roll_seconds = 0.75;") == 12
    assert rendered.count("attack_confirmation_batches = 2;") == 12
    assert rendered.count("minimum_active_batches = 3;") == 12
    assert rendered.count("maximum_transmission_seconds = 45;") == 12


def test_rtlsdr_airband_installer_pins_and_applies_repo_patch() -> None:
    installer = Path("scripts/install_rtlsdr_airband_pi.sh").read_text(encoding="utf-8")
    assert "RTLSDR_AIRBAND_VERSION:-v5.2.0" in installer
    assert "rtl-airband-buffered-clips-v5.2.0.patch" in installer
    assert 'apply --check "${buffered_clip_patch}"' in installer


def test_uploaded_clip_transcriber_has_no_second_audio_processing_switch() -> None:
    unit = Path("deploy/systemd/talkingboats-uploaded-clip-transcriber.service.example").read_text(
        encoding="utf-8"
    )
    compose = Path("compose.yaml").read_text(encoding="utf-8")

    assert "TALKINGBOATS_TRANSCRIBE_TRUST_EDGE_PREPROCESSED_AUDIO" not in unit
    assert "TALKINGBOATS_TRANSCRIBE_TRUST_EDGE_PREPROCESSED_AUDIO" not in compose
