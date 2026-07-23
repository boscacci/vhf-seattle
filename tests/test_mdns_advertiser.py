from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from talkingboats.mdns_advertiser import MdnsConfig, advertise, normalized_hostname


def test_normalized_hostname_is_a_local_fqdn() -> None:
    assert normalized_hostname("optiplex") == "optiplex.local."
    assert normalized_hostname("optiplex.local") == "optiplex.local."
    assert normalized_hostname("OPTiPLeX.LOCAL.") == "optiplex.local."


@dataclass
class FakeZeroconf:
    registered: list[object] = field(default_factory=list)
    unregistered: list[object] = field(default_factory=list)
    closed: bool = False

    def register_service(self, info: object) -> None:
        self.registered.append(info)

    def unregister_service(self, info: object) -> None:
        self.unregistered.append(info)

    def close(self) -> None:
        self.closed = True


class StopAfterWaits:
    def __init__(self, waits: int) -> None:
        self._waits = waits
        self._calls = 0

    def is_set(self) -> bool:
        return self._calls >= self._waits

    def wait(self, _: float) -> bool:
        self._calls += 1
        return self.is_set()


def test_advertiser_replaces_the_record_when_dhcp_address_changes() -> None:
    addresses = iter(["192.168.1.207", "192.168.1.207", "192.168.1.208"])
    publishers: list[FakeZeroconf] = []
    service_infos: list[object] = []

    def resolver(_: str, __: str) -> str | None:
        return next(addresses)

    def publisher_factory(_: str) -> FakeZeroconf:
        publisher = FakeZeroconf()
        publishers.append(publisher)
        return publisher

    def info_factory(record: object) -> object:
        service_infos.append(record)
        return record

    advertise(
        MdnsConfig(interface="eth0", network="192.168.1.0/24", poll_seconds=1),
        address_resolver=resolver,
        publisher_factory=publisher_factory,
        service_info_factory=info_factory,
        stop_event=StopAfterWaits(3),
        log=lambda _: None,
    )

    assert [info.address for info in service_infos] == ["192.168.1.207", "192.168.1.208"]
    assert [info.server for info in service_infos] == ["optiplex.local.", "optiplex.local."]
    assert len(publishers) == 2
    assert publishers[0].unregistered == publishers[0].registered
    assert publishers[0].closed
    assert publishers[1].unregistered == publishers[1].registered
    assert publishers[1].closed


def test_mdsn_user_service_stays_lan_scoped_and_restores_after_reboot() -> None:
    service = Path("deploy/systemd/talkingboats-mdns-advertiser.service.example").read_text(
        encoding="utf-8"
    )

    assert "talkingboats-mdns-advertiser" in service
    assert "--hostname optiplex.local" in service
    assert "--interface eth0" in service
    assert "Restart=always" in service
    assert "WantedBy=default.target" in service
