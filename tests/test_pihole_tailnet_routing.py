from pathlib import Path

PROXY_DIR = Path("deploy/optiplex/vhf-dev-proxy")


def test_tailnet_front_door_defaults_to_pihole_instead_of_vhf() -> None:
    compose = (PROXY_DIR / "compose.yaml").read_text(encoding="utf-8")
    nginx_conf = (PROXY_DIR / "nginx.conf").read_text(encoding="utf-8")

    assert "pi.hole 127.0.0.1:9444;" in nginx_conf
    assert "default 127.0.0.1:9444;" in nginx_conf
    assert "default 127.0.0.1:9443;" not in nginx_conf
    assert "listen 127.0.0.1:9444 ssl default_server;" in nginx_conf
    assert "server_name pi.hole;" in nginx_conf
    assert "ssl_certificate /etc/nginx/pihole/tls.pem;" in nginx_conf
    assert "ssl_certificate_key /etc/nginx/pihole/tls.pem;" in nginx_conf
    assert "proxy_pass http://127.0.0.1:8082;" in nginx_conf
    assert (
        "/home/rob/pihole-docker/etc-pihole:"
        "/etc/nginx/pihole:ro"
    ) in compose
