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
    assert 'analysis_work_dir="${run_state_dir}/work"' in script
    assert 'previous_analysis_dir="${output_dir}.analysis-previous"' in script
    assert 'analysis_work_dir="${output_dir}/.analysis-refresh"' not in script
    assert "rm -rf \"${output_dir}/analysis\"" not in script
    assert '--output-dir "${analysis_work_dir}"' in script
    assert 'cp -a "${analysis_work_dir}/analysis" "${output_dir}/analysis"' in script
    assert "talkingboats-analyze-transcripts" in script
    assert "--clip-store-backend \"${clip_store_backend}\"" in script
    assert 'analysis_manifest_path="${analysis_work_dir}/public_manifest.snapshot.json"' in script
    assert '--public-audio-manifest-path "${analysis_manifest_path}"' in script
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
    assert "--retry 3 --retry-all-errors --retry-delay 5" in script
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


def test_lexical_refresh_systemd_timer_runs_weekly() -> None:
    service = Path(
        "deploy/systemd/talkingboats-lexical-refresh.service.example"
    ).read_text(encoding="utf-8")
    timer = Path("deploy/systemd/talkingboats-lexical-refresh.timer.example").read_text(
        encoding="utf-8"
    )

    assert "Type=oneshot" in service
    assert (
        "WorkingDirectory=%h/repos/elliott-bay-vhf/.runtime/live-ais-deploy"
        in service
    )
    assert (
        "EnvironmentFile=-%h/repos/elliott-bay-vhf/.runtime/live-ais-deploy/.env"
        in service
    )
    assert (
        "ExecStart=%h/repos/elliott-bay-vhf/.runtime/live-ais-deploy/scripts/refresh_lexical_analysis.sh"
        in service
    )
    assert "StartLimitIntervalSec=6h" in service
    assert "StartLimitBurst=2" in service
    assert "talkingboats_lan_address.sh --dns-host dynamodb.us-west-2.amazonaws.com" in service
    assert "Restart=on-failure" in service
    assert "RestartSec=15min" in service
    assert "TimeoutStartSec=2h" in service
    assert "CPUQuota=150%" in service
    assert "CPUWeight=20" in service
    assert "weekly" in timer
    assert "OnCalendar=Sun *-*-* 10:15:00 UTC" in timer
    assert "OnUnitActiveSec" not in timer
    assert "RandomizedDelaySec=5min" in timer
    assert "OnUnitActiveSec=6h" not in timer
    assert "Persistent=true" in timer
    assert "Unit=talkingboats-lexical-refresh.service" in timer


def test_lexical_refresh_checkpoints_expensive_stages_and_caps_reads() -> None:
    script = Path("scripts/refresh_lexical_analysis.sh").read_text(encoding="utf-8")

    assert "TALKINGBOATS_LEXICAL_MAX_READ_CAPACITY_UNITS:-6000000" in script
    assert 'TALKINGBOATS_DYNAMO_READ_CAPACITY_LIMIT="${max_read_capacity_units}"' in script
    assert (
        'TALKINGBOATS_CLIP_COUNT_AGGREGATES_ENABLED="${TALKINGBOATS_CLIP_COUNT_AGGREGATES_ENABLED:-true}"'
        in script
    )
    assert 'run_id="${TALKINGBOATS_LEXICAL_RUN_ID:-$(date -u +%G-W%V)}"' in script
    assert 'analysis_complete_marker="${run_state_dir}/analysis.complete"' in script
    assert 'refresh_complete_marker="${run_state_dir}/refresh.complete"' in script
    assert 'if [[ -f "${refresh_complete_marker}" ]]' in script
    assert 'touch "${analysis_complete_marker}"' in script
    assert 'touch "${refresh_complete_marker}"' in script
