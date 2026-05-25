from __future__ import annotations

from pathlib import Path

from talkingboats.icecast_source import build_source_headers, read_netrc_password


def test_source_headers_use_http10_without_chunked_framing() -> None:
    headers = build_source_headers(
        host="127.0.0.1",
        port=8000,
        mount="/talkingboats-live.mp3",
        username="source",
        password="secret",
        ice_name="Talking Boats VHF 14",
        ice_public="0",
    ).decode("ascii")

    assert headers.startswith("PUT /talkingboats-live.mp3 HTTP/1.0\r\n")
    assert "Authorization: Basic " in headers
    assert "Content-Type: audio/mpeg\r\n" in headers
    assert "Transfer-Encoding" not in headers
    assert headers.endswith("\r\n\r\n")


def test_netrc_password_reader_uses_machine_and_login(tmp_path: Path) -> None:
    netrc_path = tmp_path / "icecast.netrc"
    netrc_path.write_text("machine 127.0.0.1 login source password secret\n", encoding="utf-8")

    assert read_netrc_password(netrc_path, host="127.0.0.1", username="source") == "secret"
