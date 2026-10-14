"""Bounded, outbound-only DockTalk alongside client; remote text is never executable."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shlex
import socket
import subprocess
import tempfile
import threading
import time
import urllib.parse
import zlib
from pathlib import Path

BASE_HOST = "docktalk-edge.fly.dev"
VERSION = "2"
MAX_RESPONSE = 65536


def emit(event: str, **fields):
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def parse_claim(text: str) -> dict[str, str]:
    if len(text) > MAX_RESPONSE or any(x in text for x in ("$", "`")):
        raise ValueError("unsafe claim response")
    fields = {}
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    for assignment in lexer:
        key, separator, value = assignment.partition("=")
        if (
            not separator
            or key not in {"NODE_ID", "PORT_ID", "PORT_NAME", "PUSH_TOKEN", "MODE"}
            or key in fields
        ):
            raise ValueError("invalid claim fields")
        fields[key] = value
    if (
        not {"NODE_ID", "PORT_NAME", "PUSH_TOKEN", "MODE"} <= set(fields)
        or fields["MODE"] != "alongside"
    ):
        raise ValueError("claim is not an alongside identity")
    if "PORT_ID" in fields and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", fields["PORT_ID"]):
        raise ValueError("invalid port identity")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", fields["NODE_ID"]):
        raise ValueError("invalid node identity")
    if not re.fullmatch(r"[A-Za-z0-9._~+/=-]{16,4096}", fields["PUSH_TOKEN"]):
        raise ValueError("invalid node credential")
    if (
        not fields["PORT_NAME"]
        or len(fields["PORT_NAME"]) > 160
        or any(ord(c) < 32 for c in fields["PORT_NAME"])
    ):
        raise ValueError("invalid port label")
    return fields


def parse_plan(text: str) -> dict[int, str]:
    if len(text) > MAX_RESPONSE:
        raise ValueError("channel plan exceeds bound")
    plan = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([0-9]{9}) ([A-Za-z0-9_-][A-Za-z0-9._-]{0,90}\.mp3)", line.strip())
        if not match or ".." in match[2]:
            raise ValueError("invalid channel plan")
        hz, mount = int(match[1]), match[2]
        if not 150_000_000 <= hz <= 170_000_000 or hz in plan or mount in plan.values():
            raise ValueError("duplicate or invalid channel plan")
        plan[hz] = mount
    if not plan:
        raise ValueError("empty channel plan")
    return plan


def api(method: str, path: str, *, token=None, body=None):
    # Paths and credentials stay out of logs and process arguments.
    connection = http.client.HTTPSConnection(BASE_HOST, timeout=15)
    headers = {"User-Agent": "DockTalk-node/2 (alongside)"}
    if token:
        headers["Authorization"] = "Bearer " + token
    payload = None
    if body is not None:
        payload = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, payload, headers)
        response = connection.getresponse()
        data = response.read(MAX_RESPONSE + 1)
        if not 200 <= response.status < 300 or len(data) > MAX_RESPONSE:
            raise RuntimeError("DockTalk request failed")
        return data.decode("utf-8")
    finally:
        connection.close()


def private_write(path: Path, data: str, *, mode=0o600):
    if path.is_symlink():
        raise ValueError("private state cannot be a symlink")
    fd, filename = tempfile.mkstemp(prefix=".docktalk-", dir=path.parent)
    pending = Path(filename)
    os.fchmod(fd, mode)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def load_identity(directory: Path):
    path = directory / "node.json"
    if path.stat().st_mode & 0o027:
        raise ValueError("node identity is publicly readable")
    values = json.loads(path.read_text())
    if set(values) - {"NODE_ID", "PORT_ID", "PORT_NAME", "PUSH_TOKEN", "MODE", "CLAIM"}:
        raise ValueError("unexpected stored identity fields")
    # Reuse the same validation on persisted identity without evaluating its values.
    parse_claim(
        " ".join(
            f"{k}={shlex.quote(values[k])}"
            for k in ("NODE_ID", "PORT_ID", "PORT_NAME", "PUSH_TOKEN", "MODE")
            if k in values
        )
    )
    if not re.fullmatch(r"DT-[A-Z0-9]{4}-[A-Z0-9]{4}", values["CLAIM"]):
        raise ValueError("invalid stored claim")
    return values


def preflight(claim_path: Path):
    """Check external coverage before pausing any shared services; never claim here."""
    from talkingboats.channel_metadata import CHANNEL_METADATA, LIVE_STREAM_CHANNELS

    if claim_path.stat().st_mode & 0o077:
        raise ValueError("claim file must be private")
    code = claim_path.read_text().strip()
    if not re.fullmatch(r"DT-[A-Z0-9]{4}-[A-Z0-9]{4}", code):
        raise ValueError("invalid claim code")
    plan = parse_plan(
        api(
            "GET", "/v1/nodes/conf?" + urllib.parse.urlencode({"code": code, "format": "alongside"})
        )
    )
    missing = [
        channel
        for channel in LIVE_STREAM_CHANNELS
        if sum(abs(hz - CHANNEL_METADATA[channel].frequency_hz) <= 2000 for hz in plan) != 1
    ]
    if missing:
        emit("docktalk_preflight_blocked", missing_channels=missing)
        raise ValueError("DockTalk server must configure all approved channels")
    emit("docktalk_preflight_passed", channels=len(LIVE_STREAM_CHANNELS), mode="alongside")


def provision(directory: Path, claim_path: Path):
    directory.mkdir(mode=0o750, parents=True, exist_ok=True)
    identity = directory / "node.json"
    if identity.exists():
        values = load_identity(directory)
    else:
        if claim_path.stat().st_mode & 0o077:
            raise ValueError("claim file must be private")
        code = claim_path.read_text().strip()
        if not re.fullmatch(r"DT-[A-Z0-9]{4}-[A-Z0-9]{4}", code):
            raise ValueError("invalid claim code")
        response_path = directory / "claim-response.txt"
        if not response_path.exists():
            response = api(
                "POST", "/v1/nodes/claim", body={"code": code, "hostname": socket.gethostname()}
            )
            private_write(response_path, response)
        values = {**parse_claim(response_path.read_text()), "CLAIM": code}
        private_write(identity, json.dumps(values))
    plan = api(
        "GET",
        "/v1/nodes/conf?"
        + urllib.parse.urlencode({"code": values["CLAIM"], "format": "alongside"}),
    )
    parsed = parse_plan(plan)
    mappings = match_streams(json.loads((directory / "streams.json").read_text()), parsed)
    private_write(directory / "plan.txt", plan)
    emit("docktalk_provisioned", mode="alongside", channels=len(mappings))


def receiver_streams(text: str):
    from talkingboats.channel_metadata import CHANNEL_METADATA, LIVE_STREAM_CHANNELS
    from talkingboats.receiver_config import channel_blocks, object_blocks

    streams = []
    for _, _, channel, body in channel_blocks(text):
        if channel not in LIVE_STREAM_CHANNELS:
            raise ValueError("receiver has an unapproved relay channel")
        outputs = [
            b for _, _, b in object_blocks(body) if re.match(r'\{\s*type\s*=\s*"icecast"', b)
        ]
        if len(outputs) != 1:
            raise ValueError("channel has no unique Icecast mount")
        mount = re.search(r'mountpoint\s*=\s*"([^"\n]+)"', outputs[0])
        if (
            not mount
            or not re.fullmatch(r"/?[A-Za-z0-9_-][A-Za-z0-9._-]*\.mp3", mount[1])
            or ".." in mount[1]
        ):
            raise ValueError("invalid local mount")
        streams.append(
            {
                "channel": channel,
                "hz": CHANNEL_METADATA[channel].frequency_hz,
                "url": "http://127.0.0.1:8000/" + mount[1].lstrip("/"),
            }
        )
    if {s["channel"] for s in streams} != set(LIVE_STREAM_CHANNELS):
        raise ValueError("receiver is missing relay channels")
    return streams


def match_streams(streams, plan):
    from talkingboats.channel_metadata import CHANNEL_METADATA, LIVE_STREAM_CHANNELS

    if {s["channel"] for s in streams} != set(LIVE_STREAM_CHANNELS) or len(streams) != 18:
        raise ValueError("relay requires the approved eighteen channels")
    mapped = []
    for stream in streams:
        channel = stream["channel"]
        expected = CHANNEL_METADATA[channel].frequency_hz
        if stream["hz"] != expected:
            raise ValueError("relay frequency mismatch")
        url = urllib.parse.urlsplit(stream["url"])
        if (
            url.scheme != "http"
            or url.hostname != "127.0.0.1"
            or url.port != 8000
            or url.query
            or url.fragment
            or url.username
            or ".." in url.path
            or not re.fullmatch(r"/[A-Za-z0-9._-]+\.mp3", url.path)
        ):
            raise ValueError("relay source is not an approved loopback mount")
        matches = [mount for hz, mount in plan.items() if abs(hz - expected) <= 2000]
        if len(matches) != 1:
            raise ValueError("DockTalk plan does not cover all approved channels")
        mapped.append({**stream, "mount": matches[0]})
    return mapped


def relay(mapping, identity, stop, health, lock):
    channel = mapping["channel"]
    while not stop.is_set():
        local = remote = None
        try:
            url = urllib.parse.urlsplit(mapping["url"])
            local = http.client.HTTPConnection("127.0.0.1", 8000, timeout=15)
            local.request("GET", url.path)
            audio = local.getresponse()
            if audio.status != 200:
                raise RuntimeError("local stream unavailable")
            remote = http.client.HTTPSConnection(BASE_HOST, timeout=15)
            remote.putrequest("PUT", "/v1/push/" + mapping["mount"])
            for key, value in {
                "Authorization": "Bearer " + identity["PUSH_TOKEN"],
                "X-DockTalk-Version": VERSION,
                "Content-Encoding": "gzip",
                "Transfer-Encoding": "chunked",
                "User-Agent": f"DockTalk-node/2 (alongside; {identity['NODE_ID']})",
            }.items():
                remote.putheader(key, value)
            remote.endheaders()
            encoder = zlib.compressobj(1, zlib.DEFLATED, 31)
            emit("docktalk_relay_connected", channel=channel)
            while not stop.is_set():
                chunk = audio.read(1024)
                if not chunk:
                    raise EOFError
                compressed = encoder.compress(chunk) + encoder.flush(zlib.Z_SYNC_FLUSH)
                remote.send(f"{len(compressed):x}\r\n".encode() + compressed + b"\r\n")
                with lock:
                    health[channel] = {
                        "last_sent_epoch": time.time(),
                        "audio_bytes": health.get(channel, {}).get("audio_bytes", 0) + len(chunk),
                    }
        except Exception as exc:
            emit("docktalk_relay_retry", channel=channel, error_type=type(exc).__name__)
        finally:
            if local:
                local.close()
            if remote:
                remote.close()
        stop.wait(5)


def run(directory: Path):
    identity = load_identity(directory)
    plan_path = Path("/run/docktalk/plan.txt")
    if not plan_path.exists():
        plan_path = directory / "plan.txt"
    plan = parse_plan(plan_path.read_text())
    mappings = match_streams(json.loads((directory / "streams.json").read_text()), plan)
    stop, lock, health = threading.Event(), threading.Lock(), {}
    threads = [
        threading.Thread(target=relay, args=(m, identity, stop, health, lock), daemon=True)
        for m in mappings
    ]
    for thread in threads:
        thread.start()
    emit("docktalk_started", channels=len(mappings), mode="alongside")
    last_plan_check = time.monotonic()
    while not stop.wait(30):
        with lock:
            snapshot = dict(health)
        private_write(Path("/run/docktalk/health.json"), json.dumps(snapshot))
        fresh = sum(time.time() - h["last_sent_epoch"] < 30 for h in snapshot.values())
        emit("docktalk_health", configured_channels=len(mappings), fresh_channels=fresh)
        if fresh < len(mappings):
            emit(
                "docktalk_degraded",
                missing_channels=sorted(
                    {m["channel"] for m in mappings}
                    - {c for c, h in snapshot.items() if time.time() - h["last_sent_epoch"] < 30}
                ),
            )
        if time.monotonic() - last_plan_check >= 600:
            try:
                text = api(
                    "GET",
                    "/v1/nodes/conf?"
                    + urllib.parse.urlencode({"code": identity["CLAIM"], "format": "alongside"}),
                )
                new_mappings = match_streams(
                    json.loads((directory / "streams.json").read_text()), parse_plan(text)
                )
                private_write(Path("/run/docktalk/plan.txt"), text)
                if new_mappings != mappings:
                    emit("docktalk_plan_changed")
                    stop.set()
                    return  # systemd restarts and loads the last validated runtime plan.
            except Exception as exc:
                emit("docktalk_plan_refresh_failed", error_type=type(exc).__name__)
            last_plan_check = time.monotonic()


def watchdog(directory: Path):
    identity = load_identity(directory)
    report = json.loads(
        api("GET", f"/v1/nodes/{identity['NODE_ID']}/pushage", token=identity["PUSH_TOKEN"])
    )
    age = report.get("age_s")
    restarted = subprocess.check_output(
        [
            "systemctl",
            "show",
            "docktalk-push.service",
            "--value",
            "-p",
            "ActiveEnterTimestampMonotonic",
        ],
        text=True,
    ).strip()
    uptime = time.monotonic() - int(restarted or 0) / 1_000_000
    stale = (
        age is not None
        and float(age) > 180
        or age is None
        and float(report.get("server_up_s", 0)) > 300
    )
    if stale and uptime > 180:
        emit("docktalk_watchdog_recovery", reason="server_reception_stale")
        subprocess.run(["systemctl", "restart", "docktalk-push.service"], check=True)


def vitals(directory: Path):
    identity = load_identity(directory)
    data = {
        "node": identity["NODE_ID"],
        "temp_c": int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000,
        "uptime_s": int(float(Path("/proc/uptime").read_text().split()[0])),
        "shed": False,
    }
    for name, command in [
        ("throttled", ["vcgencmd", "get_throttled"]),
        ("freq_mhz", ["vcgencmd", "measure_clock", "arm"]),
    ]:
        result = subprocess.check_output(command, text=True, timeout=5).strip().split("=")[-1]
        data[name] = int(result) // 1_000_000 if name == "freq_mhz" else result
    route = subprocess.check_output(["ip", "-4", "route", "show", "default"], text=True, timeout=5)
    match = re.search(r"\bdev\s+(\S+)", route)
    if match and match[1].startswith(("eth", "en")):
        data["uplink"] = "wired"
    else:
        for line in Path("/proc/net/wireless").read_text().splitlines()[2:]:
            parts = line.split()
            if len(parts) >= 4:
                data["wifi_dbm"] = float(parts[3].rstrip("."))
                break
    api("POST", "/v1/nodes/vitals", token=identity["PUSH_TOKEN"], body=data)
    emit("docktalk_vitals_sent")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["preflight", "provision", "run", "watchdog", "vitals", "map"]
    )
    parser.add_argument("--directory", type=Path, default=Path("/etc/docktalk"))
    parser.add_argument("--claim-file", type=Path)
    parser.add_argument("--receiver-config", type=Path)
    args = parser.parse_args()
    try:
        if args.action in {"provision", "preflight"}:
            if args.claim_file is None:
                parser.error("private claim file required")
            if args.action == "preflight":
                preflight(args.claim_file)
            else:
                provision(args.directory, args.claim_file)
        elif args.action == "map":
            private_write(
                args.directory / "streams.json",
                json.dumps(receiver_streams(args.receiver_config.read_text())),
            )
        else:
            if args.action == "run" and Path("/run/docktalk/plan.txt").exists():
                # Runtime refresh is already validated. Never replace root-owned configuration.
                load_identity(args.directory)
                match_streams(
                    json.loads((args.directory / "streams.json").read_text()),
                    parse_plan(Path("/run/docktalk/plan.txt").read_text()),
                )
            globals()[args.action](args.directory)
    except Exception as exc:
        emit("docktalk_failed", action=args.action, error_type=type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
