from dataclasses import dataclass

from talkingboats.network_readiness import (
    dns_ready,
    lan_address_for_network,
    lan_address_ready,
    wait_for_readiness,
)


@dataclass
class Completed:
    stdout: str
    returncode: int = 0


def test_wait_for_readiness_retries_until_lan_address_is_present() -> None:
    checks = iter([False, True])
    sleeps: list[float] = []

    ready = wait_for_readiness(
        lan_ready=lambda: next(checks),
        dns_ready=None,
        attempts=3,
        interval_seconds=2.0,
        sleep=sleeps.append,
    )

    assert ready is True
    assert sleeps == [2.0]


def test_wait_for_readiness_requires_dns_when_requested() -> None:
    sleeps: list[float] = []

    ready = wait_for_readiness(
        lan_ready=lambda: True,
        dns_ready=lambda: False,
        attempts=3,
        interval_seconds=0.5,
        sleep=sleeps.append,
    )

    assert ready is False
    assert sleeps == [0.5, 0.5]


def test_lan_address_ready_uses_the_requested_interface_and_address() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run_command(command: list[str], **kwargs: object) -> Completed:
        calls.append((command, kwargs))
        return Completed("2: eth0    inet 192.168.1.247/24 scope global eth0\n")

    assert lan_address_ready("eth0", "192.168.1.247/24", run_command=run_command)
    assert calls[0][0] == ["ip", "-4", "-o", "addr", "show", "dev", "eth0"]


def test_lan_address_for_network_uses_the_current_dhcp_address_on_the_lan() -> None:
    def run_command(_: list[str], **__: object) -> Completed:
        return Completed(
            "2: eth0    inet 192.168.1.207/24 brd 192.168.1.255 scope global eth0\n"
        )

    assert (
        lan_address_for_network("eth0", "192.168.1.0/24", run_command=run_command)
        == "192.168.1.207"
    )


def test_lan_address_for_network_rejects_an_address_outside_the_configured_lan() -> None:
    def run_command(_: list[str], **__: object) -> Completed:
        return Completed("2: eth0    inet 10.0.0.17/24 scope global eth0\n")

    assert (
        lan_address_for_network("eth0", "192.168.1.0/24", run_command=run_command)
        is None
    )


def test_dns_ready_requires_a_successful_resolver_answer() -> None:
    calls: list[list[str]] = []

    def run_command(command: list[str], **_: object) -> Completed:
        calls.append(command)
        return Completed("18.208.88.157 STREAM dynamodb.us-west-2.amazonaws.com\n")

    assert dns_ready("dynamodb.us-west-2.amazonaws.com", run_command=run_command)
    assert calls == [["getent", "ahostsv4", "dynamodb.us-west-2.amazonaws.com"]]
