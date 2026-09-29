import os
import subprocess


def test_cpu_release_leaves_two_cores_and_preserves_running_batch(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    cpu_count = bindir / "getconf"
    cpu_count.write_text("#!/bin/sh\necho 8\n")
    cpu_count.chmod(0o755)
    calls = tmp_path / "calls"
    fake = bindir / "systemctl"
    fake.write_text('#!/bin/sh\necho "$*" >> "$CALLS"\n')
    fake.chmod(0o755)
    env = dict(
        os.environ,
        PATH=f"{bindir}:{os.environ['PATH']}",
        CALLS=str(calls),
        TALKINGBOATS_CPU_RELEASE_HOME=str(tmp_path),
        TALKINGBOATS_RELEASE_COMMIT="a" * 40,
        TALKINGBOATS_RELEASE_SHA256="b" * 64,
    )
    result = subprocess.run(
        ["bash", "scripts/apply_transcriber_cpu_release.sh", "."],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    conf = (
        tmp_path / ".config/systemd/user/talkingboats-uploaded-clip-transcriber.service.d/"
        "zzz-cpu-budget.conf"
    ).read_text()
    assert "--cpu-threads 6" in conf
    assert "CPUQuota=600%" in conf
    assert "--once --limit 1000" in conf
    assert "Nice=10" in conf
    assert "CPUWeight=25" in conf
    assert "restart" not in calls.read_text()
    assert "stop" not in calls.read_text()
    # Safe retry preserves the original rollback snapshot.
    result = subprocess.run(
        ["bash", "scripts/apply_transcriber_cpu_release.sh", "."],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    record = tmp_path / ".local/share/talkingboats/releases/transcriber-cpu" / ("a" * 40)
    assert (record / "previous-absent").exists()

    # A different artifact must not reuse an existing immutable release identity.
    env["TALKINGBOATS_RELEASE_SHA256"] = "c" * 64
    result = subprocess.run(
        ["bash", "scripts/apply_transcriber_cpu_release.sh", "."],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    # Reject a different host shape before altering its policy.
    cpu_count.write_text("#!/bin/sh\necho 4\n")
    result = subprocess.run(
        ["bash", "scripts/apply_transcriber_cpu_release.sh", "."],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "eight-core" in result.stderr
