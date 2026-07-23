from pathlib import Path

from talkingboats.config import DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT


def test_lexical_refresh_script_regenerates_exports_and_promotes_generated_prod_assets() -> None:
    script = Path("scripts/refresh_lexical_analysis.sh").read_text(encoding="utf-8")

    assert "TALKINGBOATS_LEXICAL_OUTPUT_DIR" in script
    assert "TALKINGBOATS_LEXICAL_DEPLOY_ENV" in script
    assert "TALKINGBOATS_LEXICAL_DEPLOY_ENVS" in script
    assert (
        'deploy_envs="${TALKINGBOATS_LEXICAL_DEPLOY_ENVS:-'
        '${TALKINGBOATS_LEXICAL_DEPLOY_ENV:-dev prod}}"' in script
    )
    assert 'clip_store_backend="${TALKINGBOATS_CLIP_STORE_BACKEND:-dynamodb}"' in script
    assert 'raw_bucket="${TALKINGBOATS_RAW_BUCKET:-}"' in script
    assert 'tofu_dir="${TALKINGBOATS_TOFU_DIR:-infra/opentofu}"' in script
    assert (
        f"TALKINGBOATS_LEXICAL_EXPORT_LIMIT:-{DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT}"
        in script
    )
    assert "/home/rob/.local/bin:/snap/bin" in script
    assert 'exec 9>"${lock_file}"' in script
    assert "flock -n 9" in script
    assert 'analysis_work_dir="${output_dir}/.analysis-refresh"' in script
    assert 'previous_analysis_dir="${output_dir}/.analysis-previous"' in script
    assert "rm -rf \"${output_dir}/analysis\"" not in script
    assert '--output-dir "${analysis_work_dir}"' in script
    assert 'mv "${analysis_work_dir}/analysis" "${output_dir}/analysis"' in script
    assert "talkingboats-analyze-transcripts" in script
    assert "--clip-store-backend \"${clip_store_backend}\"" in script
    assert "--public-audio-manifest-path \"${output_dir}/public_manifest.json\"" in script
    assert "--public-manifest-path" not in script
    assert "--output-dir \"${output_dir}\"" in script
    assert "talkingboats-export-public" in script
    assert "--clip-db-path" not in script
    assert "live-transcripts.sqlite3" not in script
    assert 'if [[ -z "${raw_bucket}" ]]; then' in script
    assert 'cd "${tofu_dir}"' in script
    assert "for deploy_env in ${deploy_envs}; do" in script
    assert "verify_dev_generated_assets" in script
    assert "TALKINGBOATS_DEV_GENERATED_ASSET_URL" in script
    assert "Refusing prod promotion without dev validation" in script
    assert "scripts/deploy_generated_public_assets.sh \"prod\" \"${output_dir}\"" in script
    assert "TALKINGBOATS_SEARCH_WARM_URL" in script
    assert 'curl --fail --silent --show-error --max-time "${search_warm_timeout_seconds}"' in script
    assert 'echo "Warming refreshed public transcript search"' in script
    assert "Refresh complete" in script


def test_lexical_refresh_lock_is_released_after_process_termination() -> None:
    script = Path("scripts/refresh_lexical_analysis.sh").read_text(encoding="utf-8")

    assert 'lock_file="${TALKINGBOATS_LEXICAL_LOCK_FILE:-outputs/.lexical-refresh.lock}"' in script
    assert 'exec 9>"${lock_file}"' in script
    assert "flock -n 9" in script
    assert 'mkdir "${lock_dir}"' not in script


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
    assert "StartLimitIntervalSec=0" in service
    assert "talkingboats_lan_address.sh --dns-host dynamodb.us-west-2.amazonaws.com" in service
    assert "Restart=on-failure" in service
    assert "RestartSec=5min" in service
    assert "CPUQuota=150%" in service
    assert "CPUWeight=20" in service
    assert "OnBootSec=15min" in timer
    assert "OnUnitActiveSec=6h" in timer
    assert "Persistent=true" in timer
    assert "Unit=talkingboats-lexical-refresh.service" in timer
