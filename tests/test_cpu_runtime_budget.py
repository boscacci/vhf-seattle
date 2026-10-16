import os
import subprocess
from pathlib import Path


def test_gentle_cpu_runtime_survives_reload_without_restarting_worker(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    directory = runtime / "systemd/user/talkingboats-uploaded-clip-transcriber.service.d"
    directory.mkdir(parents=True)
    (directory / "50-CPUQuota.conf").write_text("[Service]\nCPUQuota=300%\n")
    (directory / "zzzz-asr-feedback.conf").write_text("[Service]\nCPUQuota=600%\n")
    calls = tmp_path / "calls"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "systemctl"
    fake.write_text('#!/bin/sh\necho "$*" >> "$CALLS"\n[ "${FAIL_RELOAD:-0}" = 0 ]\n')
    fake.chmod(0o755)
    env = dict(
        os.environ,
        XDG_RUNTIME_DIR=str(runtime),
        CALLS=str(calls),
        PATH=f"{bindir}:{os.environ['PATH']}",
    )

    def invoke(action, **overrides):
        return subprocess.run(
            ["bash", "scripts/set_transcriber_cpu_runtime.sh", action],
            env=dict(env, **overrides),
            capture_output=True,
            text=True,
        )

    target = directory / "zzzzzz-gentle-cpu.conf"
    assert invoke("gentle").returncode == 0
    original = target.read_bytes()
    assert invoke("gentle").returncode == 0
    assert target.read_bytes() == original
    quota = None
    for path in sorted(directory.glob("*.conf")):
        for line in path.read_text().splitlines():
            if line.startswith("CPUQuota="):
                quota = line.split("=", 1)[1]
    assert quota == "300%"
    assert "CPUWeight=10" in target.read_text()
    assert set(calls.read_text().splitlines()) == {"--user daemon-reload"}
    assert invoke("release-default").returncode == 0
    assert not target.exists()
    assert invoke("release-default").returncode == 0
    assert invoke("gentle", FAIL_RELOAD="1").returncode != 0
    assert not target.exists()
    assert not list(directory.glob(".gentle-pending.*"))
    target.write_text("operator-owned different configuration")
    assert invoke("gentle").returncode == 2
    assert invoke("release-default").returncode == 2
    assert target.read_text() == "operator-owned different configuration"
    target.unlink()
    target.symlink_to(directory / "zzzz-asr-feedback.conf")
    assert invoke("gentle").returncode == 2
    assert (directory / "zzzz-asr-feedback.conf").read_text().endswith("600%\n")


def test_cpu_runtime_rejects_unknown_action_and_missing_runtime(tmp_path):
    script = Path("scripts/set_transcriber_cpu_runtime.sh")
    for action in ("invalid", "gentle"):
        result = subprocess.run(
            ["bash", str(script), action],
            env=dict(os.environ, XDG_RUNTIME_DIR=str(tmp_path / "missing")),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
