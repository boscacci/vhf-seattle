"""Network outages must not turn into disruptive reconnect loops."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("recovery", Path("deploy/pi/network_recovery.py"))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def test_requires_three_consecutive_failures():
    state = {}
    for now in (1000, 1060):
        state, action = recovery.decide(state, now, False, False)
        assert action == "waiting"
    state, action = recovery.decide(state, 1120, False, False)
    assert action == "reconnect"
    assert state["attempts"] == [1120]


@pytest.mark.parametrize("gateway,api", [(True, True), (True, False), (False, True)])
def test_reachable_lan_never_triggers_reconnect(gateway, api):
    state, action = recovery.decide({"failures": 5}, 1000, gateway, api)
    assert action != "reconnect"
    assert state["failures"] == 0


def test_recovery_backoff_and_hourly_budget_survive_brief_success():
    state = {"failures": 3}
    state, action = recovery.decide(state, 1000, False, False)
    assert action == "reconnect"
    state, action = recovery.decide(state, 1299, False, False)
    assert action == "backoff"
    state, action = recovery.decide(state, 1300, False, False)
    assert action == "reconnect"
    state, action = recovery.decide(state, 1899, False, False)
    assert action == "backoff"
    state, action = recovery.decide(state, 1900, False, False)
    assert action == "reconnect"
    state, _ = recovery.decide(state, 1960, True, True)
    for now in (2020, 2080, 2140, 4000):
        state, action = recovery.decide(state, now, False, False)
        assert action != "reconnect"
    state, action = recovery.decide(state, 4601, False, False)
    assert action == "reconnect"


def test_clock_rollback_fails_closed():
    state, action = recovery.decide({"failures": 3, "attempts": [2000]}, 1000, False, False)
    assert action == "clock_wait"


@pytest.mark.parametrize(
    "state", [{"attempts": "bad"}, {"failures": -1}, {"attempts": ["bad"]}, []]
)
def test_invalid_state_rejected_without_reconnect(state):
    with pytest.raises(ValueError):
        recovery.decide(state, 1000, False, False)


def arguments(tmp_path, probe_only=False):
    from argparse import Namespace

    return Namespace(
        gateway="192.168.1.1",
        api="192.168.1.207",
        connection="00000000-0000-4000-8000-000000000000",
        state_dir=str(tmp_path),
        probe_only=probe_only,
    )


def test_failed_reconnect_is_persisted_before_command_and_not_retried(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    path = tmp_path / "state.json"
    path.write_text('{"failures": 2}')
    commands = []

    def command(args, timeout):
        commands.append(args[0])
        if args[0] == "nmcli":
            assert json.loads(path.read_text())["attempts"] == [1000]
        return SimpleNamespace(returncode=1)

    def offline(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(recovery, "command", command)
    monkeypatch.setattr(recovery.socket, "create_connection", offline)
    monkeypatch.setattr(recovery.time, "time", lambda: 1000)
    recovery.run(arguments(tmp_path))
    recovery.run(arguments(tmp_path))
    assert commands.count("nmcli") == 1


def test_probe_only_does_not_reconnect_or_write_state(tmp_path, monkeypatch):
    from types import SimpleNamespace

    path = tmp_path / "state.json"
    path.write_text('{"failures": 2}')
    commands = []

    def command(args, timeout):
        commands.append(args[0])
        return SimpleNamespace(returncode=1)

    def offline(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(recovery, "command", command)
    monkeypatch.setattr(recovery.socket, "create_connection", offline)
    recovery.run(arguments(tmp_path, probe_only=True))
    assert commands == ["ping"]
    assert path.read_text() == '{"failures": 2}'


def test_command_timeout_is_bounded(monkeypatch):
    import subprocess

    def timeout(args, **kwargs):
        assert kwargs["timeout"] == 25
        raise subprocess.TimeoutExpired(args, 25)

    monkeypatch.setattr(recovery.subprocess, "run", timeout)
    assert recovery.command(["nmcli"], 25) is None


def test_release_requires_dev_smoke_and_production_approval():
    workflow = Path(".github/workflows/deploy-pi-network.yml").read_text()
    assert "environment: production\n" in workflow
    assert "production-break-glass" not in workflow
    assert "dev-smoke-passed" in workflow
    assert "git archive" not in workflow
    assert "artifact_sha256" in workflow
