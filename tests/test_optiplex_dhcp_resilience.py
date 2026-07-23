from pathlib import Path


def test_optiplex_services_resolve_the_active_lan_address_instead_of_a_fixed_dhcp_lease() -> None:
    api_service = Path("deploy/systemd/talkingboats-api.service.example").read_text(
        encoding="utf-8"
    )
    transcriber_service = Path(
        "deploy/systemd/talkingboats-uploaded-clip-transcriber.service.example"
    ).read_text(encoding="utf-8")
    lexical_service = Path(
        "deploy/systemd/talkingboats-lexical-refresh.service.example"
    ).read_text(encoding="utf-8")
    healthcheck = Path("scripts/talkingboats_optiplex_healthcheck.sh").read_text(
        encoding="utf-8"
    )

    for content in [api_service, transcriber_service, lexical_service, healthcheck]:
        assert "talkingboats_lan_address.sh" in content
        assert "192.168.1.247" not in content


def test_healthcheck_does_not_restart_an_api_that_is_already_starting() -> None:
    healthcheck = Path("scripts/talkingboats_optiplex_healthcheck.sh").read_text(
        encoding="utf-8"
    )
    service = Path(
        "deploy/systemd/talkingboats-optiplex-healthcheck.service.example"
    ).read_text(encoding="utf-8")

    assert "activating" in healthcheck
    assert "restart_deferred" in healthcheck
    assert "Restart=on-failure" not in service


def test_dhcp_resilience_overrides_replace_legacy_unit_dropins() -> None:
    overrides = list(Path("deploy/systemd/overrides").glob("**/z99-dhcp-resilience.conf"))

    assert len(overrides) == 5
    for override in overrides:
        content = override.read_text(encoding="utf-8")
        assert "talkingboats_lan_address.sh" in content
        assert "192.168.1.247" not in content
