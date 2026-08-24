from pathlib import Path

from talkingboats.config import DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT


def test_public_clip_refresh_exports_validates_dev_then_promotes_prod() -> None:
    script = Path("scripts/refresh_public_clips.sh").read_text(encoding="utf-8")

    assert 'output_dir="${TALKINGBOATS_PUBLIC_REFRESH_OUTPUT_DIR:-outputs/public-site}"' in script
    assert 'clip_store_backend="${TALKINGBOATS_CLIP_STORE_BACKEND:-dynamodb}"' in script
    assert (
        f"TALKINGBOATS_PUBLIC_REFRESH_EXPORT_LIMIT:-{DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT}" in script
    )
    assert 'public_export_lock_file="${TALKINGBOATS_PUBLIC_EXPORT_LOCK_FILE:-' in script
    assert "flock -n 9" in script
    assert "talkingboats-export-public" in script
    assert '--clip-store-backend "${clip_store_backend}"' in script
    assert '--output-dir "${output_dir}"' in script
    assert "verify_dev_generated_assets" in script
    assert "TALKINGBOATS_DEV_GENERATED_ASSET_URL" in script
    assert 'scripts/deploy_generated_public_assets.sh "prod" "${output_dir}"' in script
    assert script.index("verify_dev_generated_assets") < script.index(
        'scripts/deploy_generated_public_assets.sh "prod"'
    )


def test_public_clip_refresh_runs_every_fifteen_minutes_with_bounded_resources() -> None:
    service = Path("deploy/systemd/talkingboats-public-clip-refresh.service.example").read_text(
        encoding="utf-8"
    )
    timer = Path("deploy/systemd/talkingboats-public-clip-refresh.timer.example").read_text(
        encoding="utf-8"
    )

    assert "Type=oneshot" in service
    assert (
        "WorkingDirectory=%h/repos/elliott-bay-vhf/.runtime/live-ais-deploy"
        in service
    )
    assert "scripts/refresh_public_clips.sh" in service
    assert "Restart=on-failure" in service
    assert "TimeoutStartSec=20min" in service
    assert "Nice=15" in service
    assert "CPUQuota=75%" in service
    assert "CPUWeight=10" in service
    assert "OnBootSec=5min" in timer
    assert "OnUnitActiveSec=15min" in timer
    assert "RandomizedDelaySec=30s" in timer
    assert "Persistent=true" in timer
    assert "Unit=talkingboats-public-clip-refresh.service" in timer


def test_lexical_refresh_releases_the_public_export_lock_during_analysis() -> None:
    lexical_script = Path("scripts/refresh_lexical_analysis.sh").read_text(encoding="utf-8")
    boot_recovery = Path("scripts/talkingboats_optiplex_boot_recovery.sh").read_text(
        encoding="utf-8"
    )

    assert "TALKINGBOATS_PUBLIC_EXPORT_LOCK_FILE" in lexical_script
    first_lock = lexical_script.index("flock 8")
    unlock = lexical_script.index("flock -u 8")
    analysis = lexical_script.index("talkingboats-analyze-transcripts")
    final_lock = lexical_script.index("flock 8", first_lock + 1)
    analysis_swap = lexical_script.index(
        'mv "${analysis_work_dir}/analysis" "${output_dir}/analysis"'
    )
    assert first_lock < unlock < analysis < final_lock < analysis_swap
    assert (
        '--public-audio-manifest-path "${analysis_manifest_path}"' in lexical_script
    )
    assert "talkingboats-public-clip-refresh.timer" in boot_recovery
