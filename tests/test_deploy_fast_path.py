from pathlib import Path


def test_static_shell_deploy_preserves_generated_public_assets() -> None:
    script = Path("scripts/deploy_static_shell.sh").read_text(encoding="utf-8")

    assert "aws s3 sync" in script
    assert "--delete" not in script
    assert "public_manifest.json" not in script
    assert '"/" "/index.html" "/assets/*" "/favicon.svg"' in script
    assert "dev_public_site_bucket" in script
    assert "cloudfront create-invalidation" in script
    assert "enforce_branch_hygiene" in script


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
    assert "live-transcriber" in compose
    assert "lexical-refresh" in compose
    assert "profiles" in compose
    assert "TALKINGBOATS_INGEST_TOKEN=" in env_example
    assert "changeme" not in env_example.lower()
    assert "config/optiplex.env" in gitignore
    assert "config/optiplex.env" in dockerignore
    assert "Docker Compose" in docs
