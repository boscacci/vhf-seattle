from pathlib import Path


def test_static_shell_deploy_preserves_generated_public_assets() -> None:
    script = Path("scripts/deploy_static_shell.sh").read_text(encoding="utf-8")

    assert "aws s3 sync" in script
    assert "--delete" not in script
    assert '--exclude "public_manifest.json"' in script
    assert '--exclude "clips/*"' in script
    assert '--exclude "analysis/*"' in script
    assert '"/" "/index.html" "/assets/*" "/favicon.svg"' in script
    assert "dev_public_site_bucket" in script
    assert "cloudfront create-invalidation" in script
    assert "enforce_branch_hygiene" in script
    assert "TALKINGBOATS_TOFU_DIR" in script


def test_full_public_deploy_supports_external_tofu_state_dir() -> None:
    script = Path("scripts/deploy_public_site.sh").read_text(encoding="utf-8")

    assert 'tofu_dir="${TALKINGBOATS_TOFU_DIR:-infra/opentofu}"' in script
    assert 'cd "${tofu_dir}"' in script


def test_deploy_scripts_fail_fast_when_tofu_outputs_are_missing() -> None:
    for path in ("scripts/deploy_static_shell.sh", "scripts/deploy_public_site.sh"):
        script = Path(path).read_text(encoding="utf-8")

        assert "tofu_output_raw()" in script
        assert "No outputs found" in script
        assert "OpenTofu output" in script
        assert 'bucket="$(tofu_output_raw "${bucket_output}")"' in script


def test_mobile_auth_env_writer_uses_tofu_outputs_and_gitignored_local_file() -> None:
    script = Path("scripts/write_mobile_auth_env.sh").read_text(encoding="utf-8")
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "dev_cognito_domain" in script
    assert "dev_cognito_mobile_client_id" in script
    assert "dev_cognito_allowed_email" in script
    assert "tofu_output_raw_or_default" in script
    assert "cognito_domain=\"$(tofu_output_raw dev_cognito_domain)\"" in script
    assert "EXPO_PUBLIC_COGNITO_REDIRECT_URI" in script
    assert "mobile/.env*" in gitignore
    assert "*.env.local" in gitignore


def test_docker_orchestration_files_cover_optiplex_services_without_secrets() -> None:
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
    assert "TALKINGBOATS_TRANSCRIBE_TRUST_EDGE_PREPROCESSED_AUDIO=true" in env_example
    assert "changeme" not in env_example.lower()
    assert "config/optiplex.env" in gitignore
    assert "config/optiplex.env" in dockerignore
    assert "Docker Compose" in docs
