import re
from pathlib import Path


def test_talkingboats_tables_use_free_aws_owned_encryption() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")

    for resource_name in ("radio_events", "ais_connections", "dev_radio_events"):
        match = re.search(
            rf'resource "aws_dynamodb_table" "{resource_name}" \{{(?P<body>.*?)\n\}}',
            main_tf,
            re.DOTALL,
        )
        assert match is not None
        assert "server_side_encryption" in match["body"]
        assert "enabled = false" in match["body"]


def test_ais_installation_defaults_to_one_snapshot_per_minute() -> None:
    installer = Path("deploy/pi/install_live_radio.sh").read_text(encoding="utf-8")
    env_example = Path("deploy/pi/talkingboats-capture.env.example").read_text(
        encoding="utf-8"
    )

    assert installer.count('TALKINGBOATS_AIS_HTTP_INTERVAL_SECONDS "60"') == 1
    assert "TALKINGBOATS_AIS_HTTP_INTERVAL_SECONDS=%q\\n' \"60\"" in installer
    assert "TALKINGBOATS_AIS_HTTP_INTERVAL_SECONDS=60" in env_example
