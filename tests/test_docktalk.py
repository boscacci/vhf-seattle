import pytest

from talkingboats.docktalk import parse_claim, parse_plan


def test_claim_parser_accepts_literal_alongside_identity_only():
    result = parse_claim(
        "NODE_ID=node-seattle PORT_NAME='Puget Sound' PUSH_TOKEN=0123456789abcdef MODE=alongside"
    )
    assert result["MODE"] == "alongside"


@pytest.mark.parametrize(
    "response",
    [
        "NODE_ID=$(id) PORT_NAME=Seattle PUSH_TOKEN=0123456789abcdef MODE=alongside",
        "NODE_ID=n PORT_NAME=Seattle PUSH_TOKEN=0123456789abcdef MODE=dedicated",
        "NODE_ID=n PORT_NAME=Seattle PUSH_TOKEN=0123456789abcdef MODE=alongside;reboot",
        "NODE_ID=n PORT_NAME=Seattle PUSH_TOKEN=0123456789abcdef MODE=alongside EXTRA=bad",
        "NODE_ID=n NODE_ID=other PORT_NAME=Seattle PUSH_TOKEN=0123456789abcdef MODE=alongside",
    ],
)
def test_claim_parser_rejects_execution_duplicate_fields_and_other_modes(response):
    with pytest.raises(ValueError):
        parse_claim(response)


def test_plan_matches_frequency_and_rejects_traversal():
    assert parse_plan("157100000 seattle-22a.mp3\n")[157100000] == "seattle-22a.mp3"
    with pytest.raises(ValueError):
        parse_plan("157100000 ../secret.mp3\n")


def test_retry_reuses_saved_identity_and_secret_files_are_private(tmp_path, monkeypatch):
    import json

    import talkingboats.docktalk as module
    from talkingboats.channel_metadata import CHANNEL_METADATA, LIVE_STREAM_CHANNELS

    directory = tmp_path / "node"
    directory.mkdir()
    claim = tmp_path / "claim"
    claim.write_text("DT-XXXX-XXXX")
    claim.chmod(0o600)
    streams = [
        {
            "channel": c,
            "hz": CHANNEL_METADATA[c].frequency_hz,
            "url": f"http://127.0.0.1:8000/talkingboats-{c.lower()}.mp3",
        }
        for c in LIVE_STREAM_CHANNELS
    ]
    (directory / "streams.json").write_text(json.dumps(streams))
    plan = "\n".join(f"{s['hz']} harbor-{s['channel'].lower()}.mp3" for s in streams)
    requests = []

    def api(method, path, **kwargs):
        requests.append(method)
        return (
            "NODE_ID=node PORT_NAME=Seattle PUSH_TOKEN=0123456789abcdef MODE=alongside"
            if method == "POST"
            else plan
        )

    monkeypatch.setattr(module, "api", api)
    module.provision(directory, claim)
    module.provision(directory, claim)
    assert requests.count("POST") == 1
    assert (directory / "node.json").stat().st_mode & 0o777 == 0o600
    assert (directory / "claim-response.txt").stat().st_mode & 0o777 == 0o600


def test_malformed_claim_is_retained_privately_without_reclaiming(tmp_path, monkeypatch):
    import talkingboats.docktalk as module

    directory = tmp_path / "node"
    directory.mkdir()
    claim = tmp_path / "claim"
    claim.write_text("DT-XXXX-XXXX")
    claim.chmod(0o600)
    calls = []
    monkeypatch.setattr(module, "api", lambda *a, **kw: calls.append(a) or "NODE_ID=$(reboot)")
    for _ in range(2):
        with pytest.raises(ValueError):
            module.provision(directory, claim)
    assert len(calls) == 1
    assert not (directory / "node.json").exists()


def test_relay_failure_is_independent_and_never_logs_credentials(monkeypatch, capsys):
    import threading

    import talkingboats.docktalk as module

    class Stop:
        stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, seconds):
            self.stopped = True
            return True

    class Failed:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            raise OSError("secret-token-must-not-be-logged")

        def close(self):
            pass

    monkeypatch.setattr(module.http.client, "HTTPConnection", Failed)
    module.relay(
        {"channel": "22A", "url": "http://127.0.0.1:8000/talkingboats-22a.mp3"},
        {},
        Stop(),
        {},
        threading.Lock(),
    )
    output = capsys.readouterr().out
    assert "docktalk_relay_retry" in output and "OSError" in output
    assert "secret-token-must-not-be-logged" not in output


def test_upstream_audio_round_trips_through_chunked_gzip(monkeypatch):
    import threading
    import zlib

    import talkingboats.docktalk as module

    chunks = iter([b"fixture-audio" * 100, b""])

    class Local:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return self

        status = 200

        def read(self, size):
            return next(chunks)

        def close(self):
            pass

    sent, headers = [], {}

    class Remote(Local):
        def putrequest(self, *args):
            assert args == ("PUT", "/v1/push/harbor-22a.mp3")

        def putheader(self, key, value):
            headers[key] = value

        def endheaders(self):
            pass

        def send(self, data):
            sent.append(data)

    class Stop:
        stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, seconds):
            self.stopped = True
            return True

    monkeypatch.setattr(module.http.client, "HTTPConnection", Local)
    monkeypatch.setattr(module.http.client, "HTTPSConnection", Remote)
    health = {}
    module.relay(
        {
            "channel": "22A",
            "url": "http://127.0.0.1:8000/talkingboats-22a.mp3",
            "mount": "harbor-22a.mp3",
        },
        {"PUSH_TOKEN": "private", "NODE_ID": "n"},
        Stop(),
        health,
        threading.Lock(),
    )
    length, payload = sent[0].split(b"\r\n", 1)
    assert zlib.decompressobj(31).decompress(payload[: int(length, 16)]) == b"fixture-audio" * 100
    assert health["22A"]["audio_bytes"] == len(b"fixture-audio" * 100)
    assert headers["Transfer-Encoding"] == "chunked"


def test_node_service_has_no_usb_or_receiver_access():
    from pathlib import Path

    unit = Path("deploy/pi/docktalk-push.service").read_text()
    assert "User=docktalk" in unit and "PrivateDevices=true" in unit
    assert "ProtectSystem=strict" in unit and "MemoryMax=512M" in unit
    assert "CPUQuota=25%" in unit and "NoNewPrivileges=true" in unit
    assert "CapabilityBoundingSet=" in unit


def test_claim_parser_accepts_optional_literal_port_id():
    result = parse_claim(
        "NODE_ID=node PORT_ID=sea PORT_NAME=Seattle PUSH_TOKEN=0123456789abcdef MODE=alongside"
    )
    assert result["PORT_ID"] == "sea"


@pytest.mark.parametrize("port_id", ["../secret", "$(id)", "sea;reboot"])
def test_claim_parser_rejects_unsafe_port_id(port_id):
    with pytest.raises(ValueError):
        parse_claim(
            f"NODE_ID=node PORT_ID={port_id} PORT_NAME=Seattle "
            "PUSH_TOKEN=0123456789abcdef MODE=alongside"
        )


def test_docktalk_preflight_accepts_available_channels_without_claiming(tmp_path, monkeypatch):
    import talkingboats.docktalk as module
    from talkingboats.channel_metadata import CHANNEL_METADATA, LIVE_STREAM_CHANNELS

    claim = tmp_path / "claim"
    claim.write_text("DT-XXXX-XXXX")
    claim.chmod(0o600)
    requests = []
    plan = "\n".join(
        f"{CHANNEL_METADATA[c].frequency_hz} harbor-{c.lower()}.mp3" for c in LIVE_STREAM_CHANNELS
    )

    def api(method, path, **kwargs):
        requests.append(method)
        return plan

    monkeypatch.setattr(module, "api", api)
    module.preflight(claim)
    assert requests == ["GET"]
    plan = "\n".join(plan.splitlines()[:6])
    module.preflight(claim)
    assert requests == ["GET", "GET"]
    claim.chmod(0o644)
    with pytest.raises(ValueError):
        module.preflight(claim)
    assert requests == ["GET", "GET"]


def test_relay_matches_available_plan_but_never_uses_unapproved_channels():
    import talkingboats.docktalk as module
    from talkingboats.channel_metadata import CHANNEL_METADATA, LIVE_STREAM_CHANNELS

    streams = [
        {
            "channel": c,
            "hz": CHANNEL_METADATA[c].frequency_hz,
            "url": f"http://127.0.0.1:8000/talkingboats-{c.lower()}.mp3",
        }
        for c in LIVE_STREAM_CHANNELS
    ]
    plan = {
        CHANNEL_METADATA[c].frequency_hz: f"harbor-{c.lower()}.mp3"
        for c in ["13", "14", "16", "66A", "71", "78A"]
    }
    plan[CHANNEL_METADATA["74"].frequency_hz] = "harbor-74.mp3"
    mapped = module.match_streams(streams, plan)
    assert {m["channel"] for m in mapped} == {"13", "14", "16", "66A", "71", "78A"}
    with pytest.raises(ValueError):
        module.match_streams(streams, {CHANNEL_METADATA["74"].frequency_hz: "harbor-74.mp3"})
    plan[CHANNEL_METADATA["13"].frequency_hz + 1000] = "ambiguous.mp3"
    with pytest.raises(ValueError):
        module.match_streams(streams, plan)


def test_partial_relay_acceptance_still_requires_local_coverage_and_fresh_audio():
    import runpy

    validate = runpy.run_path("scripts/verify_docktalk_release.py")["validate_observation"]
    state = {
        "live_mounts": 18,
        "configured_relay_channels": 6,
        "missing_relay_channels": [],
        "fresh_relay_channels": 6,
        "receiver_recorded_channels": ["13", "14", "16", "22A", "65A", "66A", "71", "77", "78A"],
        "unexpected_live_only_files": 0,
        "docktalk_age_seconds": 1,
        "temp_c": 42,
    }
    validate(state)
    for change in (
        {"missing_relay_channels": ["13"]},
        {"live_mounts": 17},
        {"configured_relay_channels": 0},
        {"unexpected_live_only_files": 1},
        {"docktalk_age_seconds": 61},
    ):
        with pytest.raises(RuntimeError):
            validate({**state, **change})
