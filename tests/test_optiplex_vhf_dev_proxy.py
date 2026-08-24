from pathlib import Path

PROXY_DIR = Path("deploy/optiplex/vhf-dev-proxy")
SYSTEMD_DIR = Path("deploy/systemd")


def test_vhf_dev_proxy_has_user_systemd_boot_service() -> None:
    service = (PROXY_DIR / "vhf-dev-proxy.service").read_text(encoding="utf-8")

    assert "Description=Start VHF dev Tailnet proxy" in service
    assert "After=docker.service network-online.target" in service
    assert "Wants=network-online.target" in service
    assert "StartLimitIntervalSec=0" in service
    assert (
        "WorkingDirectory=%h/repos/elliott-bay-vhf/deploy/optiplex/vhf-dev-proxy"
        in service
    )
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
    assert "pi.hole 127.0.0.1:9444;" in nginx_conf
    assert "dev.seattleboatradio.com 127.0.0.1:9443;" in nginx_conf
    assert "gotify.robertboscacci.com 127.0.0.1:8444;" in nginx_conf
    assert "laundry.robertboscacci.com 127.0.0.1:8444;" in nginx_conf
    assert "default 127.0.0.1:9444;" in nginx_conf
    assert "listen 100.124.5.39:443;" in nginx_conf
    assert "listen [fd7a:115c:a1e0::2601:597]:443;" in nginx_conf
    assert "listen 127.0.0.1:9443 ssl;" in nginx_conf
    assert "listen 127.0.0.1:9444 ssl default_server;" in nginx_conf
    assert "server_name pi.hole;" in nginx_conf
    assert "ssl_certificate /etc/nginx/pihole/tls.pem;" in nginx_conf
    assert "proxy_pass http://127.0.0.1:8082;" in nginx_conf
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
        assert "StartLimitIntervalSec=0" in service, service_name
        assert "Restart=always" in service, service_name
        assert "RestartSec=" in service, service_name
        assert "[Install]" in service, service_name
        assert "WantedBy=default.target" in service, service_name
        assert "WantedBy=multi-user.target" not in service, service_name


def test_optiplex_api_uses_one_systemd_managed_worker_and_warms_search() -> None:
    service = (SYSTEMD_DIR / "talkingboats-api.service.example").read_text(encoding="utf-8")
    override = Path(
        "deploy/systemd/overrides/talkingboats-api.service.d/z99-dhcp-resilience.conf"
    ).read_text(encoding="utf-8")
    warm_script = Path("scripts/talkingboats_warm_search.sh").read_text(encoding="utf-8")

    assert "uvicorn talkingboats.api:app" in service
    assert "--workers" not in service
    assert "--workers" not in override
    assert (
        "ExecStartPost=%h/repos/elliott-bay-vhf/.runtime/live-ais-deploy/"
        "scripts/talkingboats_warm_search.sh"
        in service
    )
    assert "TALKINGBOATS_SEARCH_WARM_URL" in warm_script
    assert "TALKINGBOATS_SEARCH_WARM_TIMEOUT_SECONDS" in warm_script
    assert "curl --fail --silent --show-error" in warm_script
    assert "talkingboats_search_warm" in warm_script


def test_optiplex_proxy_units_allow_a_bounded_private_api_recovery_window() -> None:
    for service_name in [
        "talkingboats-live-radio-proxy.service.example",
        "talkingboats-public-live-radio-proxy.service.example",
    ]:
        service = (SYSTEMD_DIR / service_name).read_text(encoding="utf-8")
        assert "TALKINGBOATS_PROXY_PRIVATE_API_READ_TIMEOUT_SECONDS=30" in service


def test_optiplex_vhf_reboot_timers_are_persistent() -> None:
    for timer_name in [
        "talkingboats-lexical-refresh.timer.example",
    ]:
        timer = (SYSTEMD_DIR / timer_name).read_text(encoding="utf-8")
        assert "OnStartupSec=15min" in timer, timer_name
        assert "Persistent=true" in timer, timer_name
        assert "WantedBy=timers.target" in timer, timer_name


def test_optiplex_vhf_boot_recovery_user_service_resets_and_starts_units() -> None:
    service = (SYSTEMD_DIR / "talkingboats-optiplex-boot-recovery.service.example").read_text(
        encoding="utf-8"
    )
    script = Path("scripts/talkingboats_optiplex_boot_recovery.sh").read_text(
        encoding="utf-8"
    )

    assert "After=network-online.target" in service
    assert "StartLimitIntervalSec=0" in service
    assert (
        "ExecStart=%h/repos/elliott-bay-vhf/.runtime/live-ais-deploy/"
        "scripts/talkingboats_optiplex_boot_recovery.sh"
        in service
    )
    assert "WantedBy=default.target" in service
    assert "systemctl --user reset-failed" in script
    assert "systemctl --user start" in script
    assert "talkingboats-api.service" in script
    assert "talkingboats-uploaded-clip-transcriber.service" in script
    assert "talkingboats-lexical-refresh.timer" in script
    assert "vhf-dev-proxy.service" in script
    assert "TALKINGBOATS_SEARCH_WARM_URL" in script
    assert "talkingboats_boot_recovery_search_warm" in script


def test_optiplex_recurring_healthcheck_covers_api_proxies_and_transcriber() -> None:
    service = Path(
        "deploy/systemd/talkingboats-optiplex-healthcheck.service.example"
    ).read_text(encoding="utf-8")
    timer = Path(
        "deploy/systemd/talkingboats-optiplex-healthcheck.timer.example"
    ).read_text(encoding="utf-8")
    script = Path("scripts/talkingboats_optiplex_healthcheck.sh").read_text(encoding="utf-8")

    assert (
        "ExecStart=%h/repos/elliott-bay-vhf/.runtime/live-ais-deploy/" in service
    )
    assert "talkingboats_optiplex_healthcheck.sh" in service
    assert "TimeoutStartSec=2min" in service
    assert "OnBootSec=3min" in timer
    assert "OnUnitActiveSec=2min" in timer
    assert "Persistent=true" in timer
    assert "Unit=talkingboats-optiplex-healthcheck.service" in timer
    assert "talkingboats-api.service" in script
    assert "talkingboats-live-radio-proxy.service" in script
    assert "talkingboats-public-live-radio-proxy.service" in script
    assert "talkingboats-uploaded-clip-transcriber.service" in script
    assert "talkingboats_lan_address.sh" in script
    assert "192.168.1.247:8034/healthz" not in script
    assert "172.20.0.1:8095/healthz" in script
    assert "127.0.0.1:8096/healthz" in script
    assert "uploaded_clip_transcriber_poll" in script
    assert "uploaded_clip_transcriber_start" in script
    assert "transcriber_startup_grace" in script
