import os
import subprocess
from pathlib import Path


def test_optiplex_ci_runs_only_trusted_repository_code() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "self-hosted" in workflow
    assert "optiplex" in workflow
    assert "vhf-seattle" in workflow
    assert "github.event.pull_request.head.repo.full_name == github.repository" in workflow
    assert "ref: ${{ github.event.pull_request.head.sha || github.sha }}" in workflow
    assert "conda run --no-capture-output -n dell pytest -q" in workflow
    assert "conda run --no-capture-output -n dell ruff check ." in workflow


def test_break_glass_workflow_deploys_the_checked_out_commit() -> None:
    workflow = Path(".github/workflows/deploy-pi-break-glass.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "confirm_break_glass" in workflow
    assert "production-break-glass" in workflow
    assert "github.sha" in workflow
    assert "scripts/deploy_pi_capture_health.sh" in workflow
    assert "TALKINGBOATS_RELEASE_COMMIT" in workflow


def test_pi_capture_health_deploy_is_scoped_and_records_release_identity() -> None:
    deploy = Path("scripts/deploy_pi_capture_health.sh").read_text(encoding="utf-8")
    apply_release = Path("scripts/apply_pi_capture_health_release.sh").read_text(
        encoding="utf-8"
    )

    assert "deploy/pi/live-radio/talkingboats-pi-healthcheck" in deploy
    assert "deploy/pi/live-radio/talkingboats-reset-voice-sdr" in deploy
    assert "deploy/systemd/talkingboats-profile-capture.service.example" in deploy
    assert "scripts/apply_pi_capture_health_release.sh" in deploy
    assert "TALKINGBOATS_RELEASE_COMMIT" in deploy
    assert "talkingboats-profile-capture.service" in apply_release
    assert "talkingboats-reset-voice-sdr" in apply_release
    assert "talkingboats-profile-capture.service.example" in apply_release
    assert "talkingboats-ais-catcher.service" not in apply_release
    assert "talkingboats-ais-forwarder.service" not in apply_release
    assert "release-commit" in apply_release
    assert ".break-glass-${release_commit}" in apply_release


def test_pi_capture_health_release_updates_only_scoped_runtime(tmp_path: Path) -> None:
    release_root = tmp_path / "artifact"
    healthcheck_source = (
        release_root / "deploy" / "pi" / "live-radio" / "talkingboats-pi-healthcheck"
    )
    healthcheck_source.parent.mkdir(parents=True)
    healthcheck_source.write_text("#!/usr/bin/env bash\necho new-healthcheck\n", encoding="utf-8")
    reset_source = (
        release_root / "deploy" / "pi" / "live-radio" / "talkingboats-reset-voice-sdr"
    )
    reset_source.write_text("#!/usr/bin/env bash\necho reset-voice-sdr\n", encoding="utf-8")
    capture_unit_source = (
        release_root / "deploy" / "systemd" / "talkingboats-profile-capture.service.example"
    )
    capture_unit_source.parent.mkdir(parents=True)
    capture_unit_source.write_text("[Service]\nExecStart=/new-capture\n", encoding="utf-8")

    target_healthcheck = tmp_path / "opt" / "talkingboats-pi-healthcheck"
    target_healthcheck.parent.mkdir(parents=True)
    target_healthcheck.write_text("#!/usr/bin/env bash\necho old-healthcheck\n", encoding="utf-8")
    target_reset = tmp_path / "opt" / "talkingboats-reset-voice-sdr"
    target_reset.write_text("#!/usr/bin/env bash\necho old-reset\n", encoding="utf-8")
    target_capture_unit = tmp_path / "etc" / "talkingboats-profile-capture.service"
    target_capture_unit.parent.mkdir(parents=True)
    target_capture_unit.write_text("[Service]\nExecStart=/old-capture\n", encoding="utf-8")
    icecast_config = tmp_path / "etc" / "icecast.xml"
    icecast_config.parent.mkdir(parents=True, exist_ok=True)
    icecast_config.write_text(
        "<icecast><limits><source-timeout>300</source-timeout></limits></icecast>\n",
        encoding="utf-8",
    )
    release_base = tmp_path / "releases"
    command_log = tmp_path / "systemctl.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "id").write_text(
        "#!/usr/bin/env bash\n"
        "[[ \"${1:-}\" == -u ]] && { echo 0; exit 0; }\n"
        "exec /usr/bin/id \"$@\"\n",
        encoding="utf-8",
    )
    (bin_dir / "systemctl").write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {command_log}\nexit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "id").chmod(0o755)
    (bin_dir / "systemctl").chmod(0o755)

    commit = "a" * 40
    result = subprocess.run(
        ["bash", "scripts/apply_pi_capture_health_release.sh", str(release_root)],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TALKINGBOATS_RELEASE_COMMIT": commit,
            "TALKINGBOATS_RELEASE_SHA256": "b" * 64,
            "TALKINGBOATS_PI_HEALTHCHECK_PATH": str(target_healthcheck),
            "TALKINGBOATS_PI_RESET_VOICE_SDR_PATH": str(target_reset),
            "TALKINGBOATS_PI_CAPTURE_UNIT_PATH": str(target_capture_unit),
            "TALKINGBOATS_ICECAST_CONFIG_PATH": str(icecast_config),
            "TALKINGBOATS_PI_RELEASE_ROOT": str(release_base),
        },
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "<source-timeout>90000</source-timeout>" in icecast_config.read_text()
    assert "new-healthcheck" in target_healthcheck.read_text()
    assert "reset-voice-sdr" in target_reset.read_text()
    assert "ExecStart=/new-capture" in target_capture_unit.read_text()
    assert (release_base / commit / "release-commit").read_text().strip() == commit
    commands = command_log.read_text(encoding="utf-8")
    assert "reload icecast2.service" in commands
    assert "restart talkingboats-profile-capture.service" in commands
    assert "talkingboats-ais" not in commands
