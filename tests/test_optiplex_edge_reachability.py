from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_optiplex_healthcheck_fails_when_the_pi_receiver_is_unreachable() -> None:
    script = Path("scripts/talkingboats_optiplex_healthcheck.sh").read_text(encoding="utf-8")

    assert "TALKINGBOATS_OPTIPLEX_PI_STATUS_URL" in script
    assert "http://192.168.1.114:8050/current-status.json" in script
    assert "ensure_edge_receiver_reachable" in script
    assert "edge_receiver_unreachable" in script
    assert 'failures=$((failures + 1))' in script


def test_optiplex_healthcheck_reports_degraded_when_only_the_pi_probe_fails(
    tmp_path: Path,
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
echo 'uploaded_clip_transcriber_poll'
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

    result = subprocess.run(
        ["bash", "scripts/talkingboats_optiplex_healthcheck.sh"],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TALKINGBOATS_OPTIPLEX_PI_STATUS_URL": (
                "http://pi.invalid:8050/current-status.json"
            ),
            "TALKINGBOATS_OPTIPLEX_HEALTHCHECK_ATTEMPTS": "1",
        },
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 1
    assert "unit=raspberry-pi-edge detail=edge_receiver_unreachable" in result.stdout
    assert "event=talkingboats_optiplex_health_degraded" in result.stdout


def test_pi_installer_enables_a_hardware_watchdog_for_host_level_hangs() -> None:
    watchdog = Path(
        "deploy/systemd/talkingboats-system-watchdog.conf.example"
    ).read_text(encoding="utf-8")
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
