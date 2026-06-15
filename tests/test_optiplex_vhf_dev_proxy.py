from pathlib import Path

PROXY_DIR = Path("deploy/optiplex/vhf-dev-proxy")
SYSTEMD_DIR = Path("deploy/systemd")


def test_vhf_dev_proxy_has_user_systemd_boot_service() -> None:
    service = (PROXY_DIR / "vhf-dev-proxy.service").read_text(encoding="utf-8")

    assert "Description=Start VHF dev Tailnet proxy" in service
    assert "After=docker.service network-online.target" in service
    assert "Wants=network-online.target" in service
    assert "WorkingDirectory=/home/rob/vhf-dev-proxy" in service
    assert "/usr/bin/docker info" in service
    assert "ExecStart=/usr/bin/docker compose up -d" in service
    assert "ExecStop=/usr/bin/docker compose stop" in service
    assert "RemainAfterExit=yes" in service
    assert "Restart=on-failure" in service
    assert "RestartSec=10" in service
    assert "TimeoutStartSec=90" in service
    assert "WantedBy=default.target" in service


def test_vhf_dev_proxy_nginx_tracks_shared_tailnet_sni_front_door() -> None:
    nginx_conf = (PROXY_DIR / "nginx.conf").read_text(encoding="utf-8")

    assert "stream {" in nginx_conf
    assert "ssl_preread_server_name" in nginx_conf
    assert "gotify.robertboscacci.com 127.0.0.1:8444;" in nginx_conf
    assert "laundry.robertboscacci.com 127.0.0.1:8444;" in nginx_conf
    assert "default 127.0.0.1:9443;" in nginx_conf
    assert "listen 100.124.5.39:443;" in nginx_conf
    assert "listen [fd7a:115c:a1e0::2601:597]:443;" in nginx_conf
    assert "listen 127.0.0.1:9443 ssl;" in nginx_conf
    assert "proxy_pass http://172.20.0.1:8095;" in nginx_conf
    assert "proxy_set_header X-TalkingBoats-Tailnet-Dev 1;" in nginx_conf


def test_optiplex_vhf_user_services_restart_and_install_under_default_target() -> None:
    service_names = [
        "talkingboats-api.service.example",
        "talkingboats-live-radio-proxy.service.example",
        "talkingboats-public-live-radio-proxy.service.example",
        "talkingboats-uploaded-clip-transcriber.service.example",
    ]

    for service_name in service_names:
        service = (SYSTEMD_DIR / service_name).read_text(encoding="utf-8")
        assert "Restart=always" in service, service_name
        assert "RestartSec=" in service, service_name
        assert "[Install]" in service, service_name
        assert "WantedBy=default.target" in service, service_name
        assert "WantedBy=multi-user.target" not in service, service_name


def test_optiplex_vhf_reboot_timers_are_persistent() -> None:
    for timer_name in [
        "talkingboats-lexical-refresh.timer.example",
    ]:
        timer = (SYSTEMD_DIR / timer_name).read_text(encoding="utf-8")
        assert "Persistent=true" in timer, timer_name
        assert "WantedBy=timers.target" in timer, timer_name
