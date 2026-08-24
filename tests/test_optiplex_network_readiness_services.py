from pathlib import Path

SYSTEMD_DIR = Path("deploy/systemd")


def test_optiplex_audio_services_wait_for_lan_and_dns_before_starting() -> None:
    api_service = (SYSTEMD_DIR / "talkingboats-api.service.example").read_text(
        encoding="utf-8"
    )
    transcriber_service = (
        SYSTEMD_DIR / "talkingboats-uploaded-clip-transcriber.service.example"
    ).read_text(encoding="utf-8")

    readiness_command = (
        "%h/repos/elliott-bay-vhf/.runtime/live-ais-deploy/scripts/"
        "talkingboats_lan_address.sh"
    )
    assert f"ExecStartPre=/bin/bash {readiness_command}" in api_service
    assert f"ExecStartPre=/bin/bash {readiness_command}" in transcriber_service
    assert "--dns-host dynamodb.us-west-2.amazonaws.com" in transcriber_service
    assert "192.168.1.247" not in api_service
    assert "192.168.1.247" not in transcriber_service
