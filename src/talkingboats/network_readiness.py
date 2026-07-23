"""Bounded readiness checks for OptiPlex services that need the LAN and DNS."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

DEFAULT_LAN_INTERFACE = "eth0"
DEFAULT_LAN_NETWORK = "192.168.1.0/24"


def lan_address_for_network(
    interface: str,
    network: str,
    *,
    run_command: Callable[..., Any] = subprocess.run,
) -> str | None:
    """Return the active IPv4 address on ``interface`` inside ``network``.

    The OptiPlex receives its LAN address through DHCP.  Readiness must therefore
    verify the intended LAN rather than pinning a particular lease address.
    """
    try:
        requested_network = ipaddress.ip_network(network, strict=False)
    except ValueError:
        return None
    if not isinstance(requested_network, ipaddress.IPv4Network):
        return None

    try:
        completed = run_command(
            ["ip", "-4", "-o", "addr", "show", "dev", interface],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    for candidate in re.findall(r"\binet\s+(\d+\.\d+\.\d+\.\d+/\d+)", completed.stdout):
        try:
            address = ipaddress.ip_interface(candidate).ip
        except ValueError:
            continue
        if isinstance(address, ipaddress.IPv4Address) and address in requested_network:
            return str(address)
    return None


def lan_address_ready(
    interface: str,
    address: str,
    *,
    run_command: Callable[..., Any] = subprocess.run,
) -> bool:
    """Return whether the requested IPv4 CIDR is present on an interface."""
    try:
        completed = run_command(
            ["ip", "-4", "-o", "addr", "show", "dev", interface],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return f"inet {address}" in completed.stdout


def dns_ready(
    host: str,
    *,
    run_command: Callable[..., Any] = subprocess.run,
) -> bool:
    """Return whether the configured resolver can resolve a required host."""
    try:
        completed = run_command(
            ["getent", "ahostsv4", host],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and bool(completed.stdout.strip())


def wait_for_readiness(
    *,
    lan_ready: Callable[[], bool],
    dns_ready: Callable[[], bool] | None,
    attempts: int,
    interval_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Wait for LAN readiness and, optionally, a DNS resolution check."""
    for attempt in range(1, attempts + 1):
        if lan_ready() and (dns_ready is None or dns_ready()):
            return True
        if attempt < attempts:
            sleep(interval_seconds)
    return False


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wait for the OptiPlex LAN address and optional DNS readiness."
    )
    parser.add_argument("--lan-interface", default=DEFAULT_LAN_INTERFACE)
    parser.add_argument(
        "--lan-address",
        help="Require this exact LAN address instead of resolving an address from --lan-network.",
    )
    parser.add_argument("--lan-network", default=DEFAULT_LAN_NETWORK)
    parser.add_argument("--dns-host")
    parser.add_argument(
        "--print-address",
        action="store_true",
        help="Print the resolved IPv4 address only after readiness succeeds.",
    )
    parser.add_argument("--attempts", type=positive_integer, default=90)
    parser.add_argument("--interval-seconds", type=nonnegative_float, default=2.0)
    args = parser.parse_args()

    resolved_address: str | None = None

    def lan_ready() -> bool:
        nonlocal resolved_address
        if args.lan_address:
            if lan_address_ready(args.lan_interface, args.lan_address):
                resolved_address = args.lan_address.split("/", maxsplit=1)[0]
                return True
            resolved_address = None
            return False
        resolved_address = lan_address_for_network(args.lan_interface, args.lan_network)
        return resolved_address is not None

    ready = wait_for_readiness(
        lan_ready=lan_ready,
        dns_ready=(lambda: dns_ready(args.dns_host)) if args.dns_host else None,
        attempts=args.attempts,
        interval_seconds=args.interval_seconds,
    )
    if ready and args.print_address:
        assert resolved_address is not None
        print(resolved_address)
        return 0

    event = {
        "event": "talkingboats_network_ready" if ready else "talkingboats_network_wait_timeout",
        "interface": args.lan_interface,
        "address": resolved_address,
        "network": args.lan_network,
        "dns_host": args.dns_host,
        "attempts": args.attempts,
    }
    print(json.dumps(event, sort_keys=True), file=sys.stdout if ready else sys.stderr)
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
