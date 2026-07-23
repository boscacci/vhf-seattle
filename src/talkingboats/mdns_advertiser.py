"""Advertise the OptiPlex private API on the LAN with mDNS."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import signal
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from talkingboats.network_readiness import DEFAULT_LAN_NETWORK, lan_address_for_network

DEFAULT_HOSTNAME = "optiplex.local"
DEFAULT_INTERFACE = "eth0"
DEFAULT_PORT = 8034
DEFAULT_POLL_SECONDS = 15.0
SERVICE_TYPE = "_http._tcp.local."
SERVICE_NAME = f"Talking Boats Private API.{SERVICE_TYPE}"


class ZeroconfPublisher(Protocol):
    def register_service(self, info: object) -> None: ...

    def unregister_service(self, info: object) -> None: ...

    def close(self) -> None: ...


class StopEvent(Protocol):
    def is_set(self) -> bool: ...

    def wait(self, timeout: float) -> bool: ...


@dataclass(frozen=True)
class MdnsConfig:
    hostname: str = DEFAULT_HOSTNAME
    interface: str = DEFAULT_INTERFACE
    network: str = DEFAULT_LAN_NETWORK
    port: int = DEFAULT_PORT
    poll_seconds: float = DEFAULT_POLL_SECONDS


@dataclass(frozen=True)
class MdnsServiceRecord:
    service_type: str
    service_name: str
    address: str
    port: int
    properties: dict[str, str]
    server: str


def normalized_hostname(hostname: str) -> str:
    candidate = hostname.strip().rstrip(".").lower()
    if not candidate:
        raise ValueError("hostname is required")
    if not candidate.endswith(".local"):
        candidate = f"{candidate}.local"
    return f"{candidate}."


def build_service_record(*, hostname: str, address: str, port: int) -> MdnsServiceRecord:
    ipaddress.IPv4Address(address)
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return MdnsServiceRecord(
        service_type=SERVICE_TYPE,
        service_name=SERVICE_NAME,
        address=address,
        port=port,
        properties={"path": "/healthz"},
        server=normalized_hostname(hostname),
    )


def _default_address_resolver(interface: str, network: str) -> str | None:
    return lan_address_for_network(interface, network)


def _log_event(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def advertise(
    config: MdnsConfig,
    *,
    address_resolver: Callable[[str, str], str | None] = _default_address_resolver,
    publisher_factory: Callable[[str], ZeroconfPublisher],
    service_info_factory: Callable[[MdnsServiceRecord], object],
    stop_event: StopEvent,
    log: Callable[[str], None],
) -> None:
    publisher: ZeroconfPublisher | None = None
    service_info: object | None = None
    advertised_address: str | None = None

    def close_advertisement() -> None:
        nonlocal publisher, service_info, advertised_address
        if publisher is not None and service_info is not None:
            publisher.unregister_service(service_info)
        if publisher is not None:
            publisher.close()
        publisher = None
        service_info = None
        advertised_address = None

    try:
        while not stop_event.is_set():
            address = address_resolver(config.interface, config.network)
            if address != advertised_address:
                close_advertisement()
                if address is not None:
                    record = build_service_record(
                        hostname=config.hostname,
                        address=address,
                        port=config.port,
                    )
                    publisher = publisher_factory(address)
                    service_info = service_info_factory(record)
                    publisher.register_service(service_info)
                    advertised_address = address
                    log(
                        json.dumps(
                            {
                                "address": address,
                                "event": "talkingboats_mdns_advertised",
                                "hostname": record.server,
                                "interface": config.interface,
                            },
                            sort_keys=True,
                        )
                    )
                else:
                    log(
                        json.dumps(
                            {
                                "event": "talkingboats_mdns_address_unavailable",
                                "interface": config.interface,
                                "network": config.network,
                            },
                            sort_keys=True,
                        )
                    )
            stop_event.wait(config.poll_seconds)
    finally:
        close_advertisement()


def _runtime_factories() -> tuple[
    Callable[[str], ZeroconfPublisher], Callable[[MdnsServiceRecord], object]
]:
    try:
        from zeroconf import IPVersion, ServiceInfo, Zeroconf
    except ImportError as exc:  # pragma: no cover - exercised on the deployment host
        raise RuntimeError(
            "The mDNS advertiser requires zeroconf. Install the project with its mdns extra."
        ) from exc

    def publisher_factory(address: str) -> ZeroconfPublisher:
        return Zeroconf(interfaces=[address], ip_version=IPVersion.V4Only)

    def service_info_factory(record: MdnsServiceRecord) -> object:
        return ServiceInfo(
            type_=record.service_type,
            name=record.service_name,
            addresses=[ipaddress.IPv4Address(record.address).packed],
            port=record.port,
            properties=record.properties,
            server=record.server,
        )

    return publisher_factory, service_info_factory


def parse_args(argv: Sequence[str] | None = None) -> MdnsConfig:
    parser = argparse.ArgumentParser(
        description="Advertise the Talking Boats private API over mDNS."
    )
    parser.add_argument(
        "--hostname", default=os.getenv("TALKINGBOATS_MDNS_HOSTNAME", DEFAULT_HOSTNAME)
    )
    parser.add_argument(
        "--interface", default=os.getenv("TALKINGBOATS_MDNS_INTERFACE", DEFAULT_INTERFACE)
    )
    parser.add_argument(
        "--network", default=os.getenv("TALKINGBOATS_LAN_NETWORK", DEFAULT_LAN_NETWORK)
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    args = parser.parse_args(argv)
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    build_service_record(hostname=args.hostname, address="192.0.2.1", port=args.port)
    return MdnsConfig(
        hostname=args.hostname,
        interface=args.interface,
        network=args.network,
        port=args.port,
        poll_seconds=args.poll_seconds,
    )


def main(argv: Sequence[str] | None = None) -> None:
    config = parse_args(argv)
    stop_event = threading.Event()

    def request_stop(_: int, __: Any) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    publisher_factory, service_info_factory = _runtime_factories()
    advertise(
        config,
        publisher_factory=publisher_factory,
        service_info_factory=service_info_factory,
        stop_event=stop_event,
        log=print,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
