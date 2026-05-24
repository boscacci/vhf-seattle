from __future__ import annotations

import argparse
import base64
import netrc
import os
import socket
import sys
from pathlib import Path


def build_source_headers(
    *,
    host: str,
    port: int,
    mount: str,
    username: str,
    password: str,
    ice_name: str,
    ice_public: str,
) -> bytes:
    if not mount.startswith("/"):
        mount = f"/{mount}"
    auth = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    headers = [
        f"PUT {mount} HTTP/1.0",
        f"Host: {host}:{port}",
        f"Authorization: Basic {auth}",
        "Content-Type: audio/mpeg",
        f"Ice-Name: {ice_name}",
        f"Ice-Public: {ice_public}",
        "Connection: close",
        "",
        "",
    ]
    return "\r\n".join(headers).encode("ascii")


def read_netrc_password(netrc_file: Path, *, host: str, username: str) -> str:
    credentials = netrc.netrc(str(netrc_file)).authenticators(host)
    if credentials is None:
        raise RuntimeError(f"no netrc credentials for {host}")
    login, _, password = credentials
    if login != username:
        raise RuntimeError(f"netrc login for {host} is {login!r}, expected {username!r}")
    if not password:
        raise RuntimeError(f"netrc password for {host} is empty")
    return password


def stream_to_icecast(
    *,
    host: str,
    port: int,
    mount: str,
    netrc_file: Path,
    username: str,
    ice_name: str,
    ice_public: str,
    chunk_size: int = 4096,
) -> None:
    password = read_netrc_password(netrc_file, host=host, username=username)
    headers = build_source_headers(
        host=host,
        port=port,
        mount=mount,
        username=username,
        password=password,
        ice_name=ice_name,
        ice_public=ice_public,
    )
    with socket.create_connection((host, port), timeout=10) as sock:
        sock.sendall(headers)
        while True:
            chunk = os.read(sys.stdin.fileno(), chunk_size)
            if not chunk:
                return
            sock.sendall(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream stdin to Icecast without chunked framing.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--mount", required=True)
    parser.add_argument("--netrc-file", type=Path, required=True)
    parser.add_argument("--username", default="source")
    parser.add_argument("--ice-name", required=True)
    parser.add_argument("--ice-public", default="0")
    args = parser.parse_args()
    stream_to_icecast(
        host=args.host,
        port=args.port,
        mount=args.mount,
        netrc_file=args.netrc_file,
        username=args.username,
        ice_name=args.ice_name,
        ice_public=args.ice_public,
    )


if __name__ == "__main__":
    main()
