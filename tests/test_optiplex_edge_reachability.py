from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def test_optiplex_healthcheck_fails_when_the_pi_receiver_is_unreachable() -> None:
    script = Path("scripts/talkingboats_optiplex_healthcheck.sh").read_text(encoding="utf-8")

    assert "TALKINGBOATS_OPTIPLEX_PI_STATUS_URL" in script
    assert "http://192.168.1.114:8050/current-status.json" in script
    assert "ensure_edge_receiver_reachable" in script
    assert "edge_receiver_unreachable" in script
    assert "failures=$((failures + 1))" in script


@pytest.mark.parametrize("launch_method", ["bash", "systemd"])
@pytest.mark.parametrize(
    "journal_event", ["uploaded_clip_transcriber_poll", "uploaded_clip_transcriber_progress"]
)
def test_optiplex_healthcheck_reports_degraded_when_only_the_pi_probe_fails(
    tmp_path: Path,
    journal_event: str,
    launch_method: str,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    commands = {
        "curl": """#!/usr/bin/env bash
case " $* " in
  *" http://pi.invalid:8050/current-status.json "*) exit 22 ;;
  *) exit 0 ;;
esac
""",
        "journalctl": """#!/usr/bin/env bash
echo "$JOURNAL_EVENT"
""",
        "seq": """#!/usr/bin/env bash
echo 1
""",
        "sleep": """#!/usr/bin/env bash
exit 0
""",
        "systemctl": """#!/usr/bin/env bash
if [[ " $* " == *" show "* ]]; then
  echo active
fi
exit 0
""",
    }
    for name, contents in commands.items():
        executable = bin_dir / name
        executable.write_text(contents, encoding="utf-8")
        executable.chmod(0o755)

    command = ["bash", "scripts/talkingboats_optiplex_healthcheck.sh"]
    if launch_method == "systemd":
        import shlex

        service = Path(
            "deploy/systemd/talkingboats-optiplex-healthcheck.service.example"
        ).read_text(encoding="utf-8")
        exec_start = next(
            line.removeprefix("ExecStart=")
            for line in service.splitlines()
            if line.startswith("ExecStart=")
        )
        command = shlex.split(
            exec_start.replace("%h/repos/elliott-bay-vhf/.runtime/live-ais-deploy", str(Path.cwd()))
        )

    result = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "JOURNAL_EVENT": journal_event,
            "TALKINGBOATS_OPTIPLEX_PI_STATUS_URL": ("http://pi.invalid:8050/current-status.json"),
            "TALKINGBOATS_OPTIPLEX_HEALTHCHECK_ATTEMPTS": "1",
        },
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 1
    assert "poll_stale" not in result.stdout
    assert "unit=raspberry-pi-edge detail=edge_receiver_unreachable" in result.stdout
    assert "event=talkingboats_optiplex_health_degraded" in result.stdout


def test_pi_installer_enables_a_hardware_watchdog_for_host_level_hangs() -> None:
    watchdog = Path("deploy/systemd/talkingboats-system-watchdog.conf.example").read_text(
        encoding="utf-8"
    )
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")

    assert "[Manager]" in watchdog
    assert "RuntimeWatchdogSec=60s" in watchdog
    assert "RebootWatchdogSec=5min" in watchdog
    assert "talkingboats-system-watchdog.conf.example" in installer
    assert "/etc/systemd/system.conf.d/90-talkingboats-hardware-watchdog.conf" in installer
    assert "systemctl daemon-reexec" in installer


def test_pi_capture_services_are_bounded_against_memory_exhaustion() -> None:
    service_names = [
        "talkingboats-ais-catcher.service.example",
        "talkingboats-profile-capture.service.example",
        "talkingboats-spool-uploader.service.example",
    ]

    for service_name in service_names:
        service = Path("deploy/systemd", service_name).read_text(encoding="utf-8")
        assert "MemoryHigh=" in service, service_name
        assert "MemoryMax=" in service, service_name
        assert "OOMPolicy=stop" in service, service_name


@pytest.mark.parametrize(
    "script_name",
    [
        "talkingboats_optiplex_boot_recovery.sh",
        "talkingboats_optiplex_healthcheck.sh",
    ],
)
def test_optiplex_systemd_entrypoints_have_execute_permission(script_name: str) -> None:
    assert os.access(Path("scripts") / script_name, os.X_OK), (
        f"systemd cannot directly execute {script_name} without execute permission"
    )
