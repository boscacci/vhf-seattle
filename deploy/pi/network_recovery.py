#!/usr/bin/env python3
"""Bounded recovery of the saved Pi Wi-Fi profile; no cloud dependencies."""

import argparse
import fcntl
import ipaddress
import json
import os
import socket
import subprocess
import time
import uuid
from pathlib import Path


def decide(state, now, gateway_ok, api_ok):
    if not isinstance(state, dict):
        raise ValueError("invalid state")
    failures = state.get("failures", 0)
    attempts = state.get("attempts", [])
    if (
        type(failures) is not int
        or failures < 0
        or not isinstance(attempts, list)
        or any(type(t) not in (int, float) or t < 0 for t in attempts)
    ):
        raise ValueError("invalid state")
    attempts = [t for t in attempts if now - t < 3600]
    result = {"failures": 0 if gateway_ok or api_ok else failures + 1, "attempts": attempts}
    if gateway_ok or api_ok:
        return result, "healthy" if gateway_ok and api_ok else "partial"
    if any(t > now for t in attempts):
        return result, "clock_wait"
    if result["failures"] < 3:
        return result, "waiting"
    if len(attempts) >= 3:
        return result, "budget_exhausted"
    if attempts and now - max(attempts) < 300 * 2 ** (len(attempts) - 1):
        return result, "backoff"
    result["attempts"].append(now)
    return result, "reconnect"


def command(args, timeout):
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return None


def emit(event, **fields):
    print(json.dumps({"event": "pi_network_recovery", "status": event, **fields}), flush=True)


def run(args):
    # Numeric LAN targets avoid making DNS or Internet failure a reconnect trigger.
    ipaddress.IPv4Address(args.gateway)
    ipaddress.IPv4Address(args.api)
    uuid.UUID(args.connection)
    state_dir = Path(args.state_dir)
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state_dir / "lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ping = command(["ping", "-n", "-c", "1", "-W", "2", "-I", "wlan0", args.gateway], 4)
        gateway_ok = ping is not None and ping.returncode == 0
        try:
            with socket.create_connection((args.api, 8034), timeout=3):
                api_ok = True
        except OSError:
            api_ok = False
        path = state_dir / "state.json"
        state = json.loads(path.read_text()) if path.exists() else {}
        state, action = decide(state, time.time(), gateway_ok, api_ok)
        if args.probe_only:
            emit("probe_only", gateway_ok=gateway_ok, api_ok=api_ok, would_do=action)
            return
        # Persist the attempt BEFORE running nmcli, including failed/timed-out attempts.
        pending = state_dir / "state.pending"
        with pending.open("w") as output:
            json.dump(state, output)
            output.flush()
            os.fsync(output.fileno())
        pending.replace(path)
        emit(
            action,
            gateway_ok=gateway_ok,
            api_ok=api_ok,
            consecutive_failures=state["failures"],
            attempts_last_hour=len(state["attempts"]),
        )
        if action == "reconnect":
            result = command(
                [
                    "nmcli",
                    "--wait",
                    "20",
                    "connection",
                    "up",
                    "uuid",
                    args.connection,
                    "ifname",
                    "wlan0",
                ],
                25,
            )
            emit(
                "reconnect_completed"
                if result is not None and result.returncode == 0
                else "reconnect_failed"
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection", required=True)
    parser.add_argument("--gateway", default="192.168.1.1")
    parser.add_argument("--api", default="192.168.1.207")
    parser.add_argument("--state-dir", default="/var/lib/talkingboats-network-recovery")
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args()
    try:
        run(args)
    except (OSError, ValueError) as error:
        # Do not log profile identifiers, command output, or arbitrary file contents.
        emit("error", error_type=type(error).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
