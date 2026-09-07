from pathlib import Path

PROXY_DIR = Path("deploy/optiplex/vhf-dev-proxy")


def test_pihole_tls_backend_leaves_shared_sni_port_free() -> None:
    compose = (PROXY_DIR / "compose.yaml").read_text(encoding="utf-8")
    nginx_conf = (PROXY_DIR / "nginx.conf").read_text(encoding="utf-8")

    assert "127.0.0.1:9444" not in nginx_conf
    assert "default 127.0.0.1:9443;" not in nginx_conf
    assert "listen 127.0.0.1:9447 ssl default_server;" in nginx_conf
    assert "server_name pi.hole;" in nginx_conf
    assert "ssl_certificate /etc/nginx/pihole/tls.pem;" in nginx_conf
    assert "ssl_certificate_key /etc/nginx/pihole/tls.pem;" in nginx_conf
    assert "proxy_pass http://127.0.0.1:8082;" in nginx_conf
    assert (
        "/home/rob/pihole-docker/etc-pihole:"
        "/etc/nginx/pihole:ro"
    ) in compose
