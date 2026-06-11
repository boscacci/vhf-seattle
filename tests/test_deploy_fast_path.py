from pathlib import Path


def test_static_shell_deploy_preserves_generated_public_assets() -> None:
    script = Path("scripts/deploy_static_shell.sh").read_text(encoding="utf-8")

    assert "aws s3 sync" in script
    assert "--delete" not in script
    assert '--exclude "public_manifest.json"' in script
    assert '--exclude "clips/*"' in script
    assert '--exclude "analysis/*"' in script
    for path in (
        '"/"',
        '"/index.html"',
        '"/assets/*"',
        '"/favicon.svg"',
        '"/clips/*"',
        '"/hall-of-fame/*"',
        '"/live/*"',
        '"/ais/*"',
        '"/analysis/index.html"',
        '"/about/*"',
        '"/performance/*"',
        '"/operator/*"',
    ):
        assert path in script
    assert "dev_only_route_index_paths" in script
    assert '"hall-of-fame/index.html"' in script
    assert '"hall-of-fame/"' in script
    assert '"about/index.html"' in script
    assert '"about/"' in script
    assert '"performance/index.html"' in script
    assert '"operator/index.html"' in script
    assert 'if [[ "${environment}" == "dev" ]]; then' in script
    assert "prod_retired_route_paths" in script
    assert "retired_route_paths" in script
    assert '"fine-tuning/index.html"' in script
    assert '"/fine-tuning/*"' in script
    assert "aws s3 rm" in script
    assert "dev_public_site_bucket" in script
    assert "cloudfront create-invalidation" in script
    assert "enforce_branch_hygiene" in script
    assert "TALKINGBOATS_TOFU_DIR" in script
    assert "sync_tailnet_dev_static_shell" in script
    assert "TALKINGBOATS_DEV_TAILNET_SSH_TARGET:-optiplex" in script
    assert "TALKINGBOATS_DEV_TAILNET_PUBLIC_SITE_DIR" in script
    assert "TALKINGBOATS_SKIP_TAILNET_DEV_SYNC" in script
    assert "rsync -az" in script
    assert "upload_shell_entrypoint" in script
    assert '--key "index.html"' in script
    assert '--key "assets/app.js"' in script
    assert '--cache-control "no-store"' in script


def test_full_public_deploy_supports_external_tofu_state_dir() -> None:
    script = Path("scripts/deploy_public_site.sh").read_text(encoding="utf-8")

    assert 'tofu_dir="${TALKINGBOATS_TOFU_DIR:-infra/opentofu}"' in script
    assert 'cd "${tofu_dir}"' in script


def test_lexical_refresh_analyzes_transcript_store_after_public_export() -> None:
    script = Path("scripts/refresh_lexical_analysis.sh").read_text(encoding="utf-8")

    export_index = script.index("talkingboats-export-public")
    analysis_index = script.index("talkingboats-analyze-transcripts")

    assert export_index < analysis_index
    assert "--clip-store-backend \"${clip_store_backend}\"" in script
    assert "--public-audio-manifest-path" in script
    assert '"${output_dir}/public_manifest.json"' in script
    assert "--public-manifest-path" not in script
    assert "Refreshing lexical analysis from transcript store" in script


def test_ais_cloud_deploy_stores_raw_token_in_secrets_manager_not_tofu_state() -> None:
    script = Path("scripts/deploy_ais_cloud.sh").read_text(encoding="utf-8")

    assert "openssl rand -base64 48" in script
    assert "shasum -a 256" in script
    assert "TF_VAR_ais_ingest_token_sha256" in script
    assert "TF_VAR_ais_ingest_token=" not in script
    assert "aws secretsmanager get-secret-value" in script
    assert "aws secretsmanager put-secret-value" in script
    assert "ais_ingest_secret_name" in script
    assert "ais_ingest_secret_kms_key_arn" in script
    assert "--secret-string" in script
    assert "set -x" not in script
    assert "token=" in script
    assert "echo \"${token}" not in script


def test_deploy_scripts_discover_existing_aws_targets_when_tofu_outputs_are_missing() -> None:
    for path in ("scripts/deploy_static_shell.sh", "scripts/deploy_public_site.sh"):
        script = Path(path).read_text(encoding="utf-8")

        assert "deploy_output_raw()" in script
        assert "fallback_output_raw()" in script
        assert "No outputs found" in script
        assert "OpenTofu output" in script
        assert "aws sts get-caller-identity" in script
        assert "aws cloudfront list-distributions" in script
        assert 'bucket="$(deploy_output_raw "${bucket_output}")"' in script


def test_deploy_scripts_allow_archive_sources_for_dev_only() -> None:
    for path in ("scripts/deploy_static_shell.sh", "scripts/deploy_public_site.sh"):
        script = Path(path).read_text(encoding="utf-8")

        assert 'if [[ "${branch}" == "unknown" ]]; then' in script
        assert "Allowing dev" in script
        assert (
            "Refusing prod deploy from branch" in script
            or "Refusing prod shell deploy from branch" in script
        )


def test_deploy_scripts_force_shell_revalidation() -> None:
    for path in ("scripts/deploy_static_shell.sh", "scripts/deploy_public_site.sh"):
        script = Path(path).read_text(encoding="utf-8")

        assert "upload_shell_entrypoint" in script
        assert '--key "index.html"' in script
        assert '--key "assets/app.js"' in script
        assert '--content-type "text/html"' in script
        assert '--content-type "text/javascript"' in script
        assert '--cache-control "no-store"' in script


def test_native_mobile_auth_env_writer_is_removed_while_paused() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert not Path("scripts/write_mobile_auth_env.sh").exists()
    assert not Path("mobile").exists()
    assert "mobile/.env*" not in gitignore
    assert "*.env.local" in gitignore


def test_paused_native_mobile_auth_scripts_are_removed() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")

    assert not Path("scripts/configure_dev_google_cognito_idp.sh").exists()
    assert "aws_cognito_identity_provider" not in main_tf
    assert "aws_cognito_user_pool_client" not in main_tf
    assert "client_secret" not in main_tf


def test_docker_orchestration_files_cover_home_processor_services_without_secrets() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    compose = Path("compose.yaml").read_text(encoding="utf-8")
    env_example = Path("config/optiplex.env.example").read_text(encoding="utf-8")
    docs = Path("docs/docker-orchestration.md").read_text(encoding="utf-8")
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

    assert "python:3.12-slim" in dockerfile
    assert "ffmpeg" in dockerfile
    assert "INSTALL_EXTRAS" in dockerfile
    assert "live-proxy" in compose
    assert "private-api" in compose
    assert "uploaded-clip-transcriber" in compose
    assert "TALKINGBOATS_TRANSCRIBE_TRUST_EDGE_PREPROCESSED_AUDIO" in compose
    assert "live-transcriber" in compose
    assert "lexical-refresh" in compose
    assert "profiles" in compose
    assert "TALKINGBOATS_INGEST_TOKEN=" in env_example
    assert "TALKINGBOATS_CLIP_STORE_BACKEND=dynamodb" in env_example
    assert "TALKINGBOATS_DURABLE_EVENTS_TABLE=" in env_example
    assert "TALKINGBOATS_DURABLE_EVENTS_REQUIRED=true" in env_example
    assert "TALKINGBOATS_TRANSCRIBE_TRUST_EDGE_PREPROCESSED_AUDIO=true" in env_example
    assert "changeme" not in env_example.lower()
    assert "config/optiplex.env" in gitignore
    assert "config/optiplex.env" in dockerignore
    assert "Docker Compose" in docs


def test_vhf_dev_tailnet_proxy_config_documents_custom_tls_front_door() -> None:
    compose = Path("deploy/optiplex/vhf-dev-proxy/compose.yaml").read_text(
        encoding="utf-8"
    )
    nginx = Path("deploy/optiplex/vhf-dev-proxy/nginx.conf").read_text(
        encoding="utf-8"
    )
    service = Path(
        "deploy/optiplex/vhf-dev-proxy/vhf-dev-cert-renew.service"
    ).read_text(encoding="utf-8")
    docs = Path("docs/deployment-hygiene.md").read_text(encoding="utf-8")

    assert "vhf-dev-tailnet-proxy" in compose
    assert "network_mode: host" in compose
    assert "/home/rob/vhf-dev-letsencrypt:/etc/letsencrypt:ro" in compose
    assert "listen 100.124.5.39:443 ssl;" in nginx
    assert "listen [fd7a:115c:a1e0::2601:597]:443 ssl;" in nginx
    assert "server_name vhf-dev.robertboscacci.com;" in nginx
    assert (
        "ssl_certificate /etc/letsencrypt/live/vhf-dev.robertboscacci.com/fullchain.pem;"
        in nginx
    )
    assert "proxy_set_header X-TalkingBoats-Tailnet-Dev 1;" in nginx
    assert "proxy_pass http://172.20.0.1:8095;" in nginx
    assert "certbot/dns-route53 renew" in service
    assert "docker kill -s HUP vhf-dev-tailnet-proxy" in service
    assert "Pi-hole" in docs
    assert "admin UI on alternate ports" in docs
    assert "must not bind the Ubuntu micro-computer tailnet `80/443`" in docs
