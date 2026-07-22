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
        "/home/rob/miniforge3/condabin/conda run --no-capture-output -n dell "
        "python -m talkingboats.network_readiness --lan-address 192.168.1.247/24"
    )
    assert f"ExecStartPre={readiness_command}" in api_service
    assert f"ExecStartPre={readiness_command}" in transcriber_service
    assert "--dns-host dynamodb.us-west-2.amazonaws.com" in transcriber_service
