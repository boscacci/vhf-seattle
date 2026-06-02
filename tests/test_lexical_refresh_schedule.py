from pathlib import Path

from talkingboats.config import DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT


def test_lexical_refresh_script_regenerates_exports_and_deploys_dev() -> None:
    script = Path("scripts/refresh_lexical_analysis.sh").read_text(encoding="utf-8")

    assert "TALKINGBOATS_LEXICAL_OUTPUT_DIR" in script
    assert "TALKINGBOATS_LEXICAL_DEPLOY_ENV" in script
    assert 'clip_store_backend="${TALKINGBOATS_CLIP_STORE_BACKEND:-dynamodb}"' in script
    assert 'raw_bucket="${TALKINGBOATS_RAW_BUCKET:-}"' in script
    assert 'tofu_dir="${TALKINGBOATS_TOFU_DIR:-infra/opentofu}"' in script
    assert (
        f"TALKINGBOATS_LEXICAL_EXPORT_LIMIT:-{DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT}"
        in script
    )
    assert "/home/rob/.local/bin:/snap/bin" in script
    assert "mkdir \"${lock_dir}\"" in script
    assert "trap cleanup EXIT" in script
    assert "rm -rf \"${output_dir}/analysis\"" in script
    assert "talkingboats-analyze-transcripts" in script
    assert "--clip-store-backend \"${clip_store_backend}\"" in script
    assert "--output-dir \"${output_dir}\"" in script
    assert "talkingboats-export-public" in script
    assert "--clip-db-path" not in script
    assert "live-transcripts.sqlite3" not in script
    assert 'if [[ -z "${raw_bucket}" ]]; then' in script
    assert 'cd "${tofu_dir}"' in script
    assert "scripts/deploy_public_site.sh \"${deploy_env}\" \"${output_dir}\"" in script
    assert "Refresh complete" in script


def test_lexical_refresh_systemd_timer_runs_every_six_hours() -> None:
    service = Path(
        "deploy/systemd/talkingboats-lexical-refresh.service.example"
    ).read_text(encoding="utf-8")
    timer = Path("deploy/systemd/talkingboats-lexical-refresh.timer.example").read_text(
        encoding="utf-8"
    )

    assert "Type=oneshot" in service
    assert "WorkingDirectory=/home/rob/repos/elliott-bay-vhf-live-ais-deploy" in service
    assert (
        "EnvironmentFile=-/home/rob/repos/elliott-bay-vhf-live-ais-deploy/.env" in service
    )
    assert (
        "ExecStart=/home/rob/repos/elliott-bay-vhf-live-ais-deploy/scripts/refresh_lexical_analysis.sh"
        in service
    )
    assert "CPUQuota=150%" in service
    assert "CPUWeight=20" in service
    assert "OnBootSec=15min" in timer
    assert "OnUnitActiveSec=6h" in timer
    assert "Persistent=true" in timer
    assert "Unit=talkingboats-lexical-refresh.service" in timer
