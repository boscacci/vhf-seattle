#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

export PATH="/home/rob/.local/bin:/snap/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

output_dir="${TALKINGBOATS_PUBLIC_REFRESH_OUTPUT_DIR:-outputs/public-site}"
clip_store_backend="${TALKINGBOATS_CLIP_STORE_BACKEND:-dynamodb}"
conda_env="${TALKINGBOATS_PUBLIC_REFRESH_CONDA_ENV:-dell}"
conda_bin="${TALKINGBOATS_CONDA_BIN:-/home/rob/miniforge3/condabin/conda}"
public_export_lock_file="${TALKINGBOATS_PUBLIC_EXPORT_LOCK_FILE:-outputs/.public-export.lock}"
export_limit="${TALKINGBOATS_PUBLIC_REFRESH_EXPORT_LIMIT:-3000}"
raw_bucket_output="${TALKINGBOATS_PUBLIC_REFRESH_RAW_BUCKET_OUTPUT:-raw_audio_bucket}"
raw_bucket="${TALKINGBOATS_RAW_BUCKET:-}"
tofu_dir="${TALKINGBOATS_TOFU_DIR:-infra/opentofu}"
dev_generated_asset_url="${TALKINGBOATS_DEV_GENERATED_ASSET_URL:-https://dev.seattleboatradio.com/public_manifest.json}"

usage() {
  cat <<'EOF'
Usage: scripts/refresh_public_clips.sh

Rebuilds the public clip export, verifies that exact manifest on the tailnet
dev site, and promotes only generated artifacts to production.

Environment overrides:
  TALKINGBOATS_PUBLIC_REFRESH_OUTPUT_DIR       Static export directory
  TALKINGBOATS_CLIP_STORE_BACKEND              Clip store backend
  TALKINGBOATS_PUBLIC_REFRESH_CONDA_ENV        Conda environment
  TALKINGBOATS_CONDA_BIN                       Conda binary path
  TALKINGBOATS_PUBLIC_EXPORT_LOCK_FILE         Lock shared with lexical refresh
  TALKINGBOATS_PUBLIC_REFRESH_EXPORT_LIMIT     Public clip export limit
  TALKINGBOATS_PUBLIC_REFRESH_RAW_BUCKET_OUTPUT OpenTofu raw bucket output
  TALKINGBOATS_RAW_BUCKET                      Raw bucket override
  TALKINGBOATS_TOFU_DIR                        OpenTofu directory
  TALKINGBOATS_DEV_GENERATED_ASSET_URL         Dev manifest validation URL
EOF
}

manifest_generated_at() {
  python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["generated_at"])' "$1"
}

verify_dev_generated_assets() {
  local local_generated_at
  local remote_generated_at
  local cache_bust
  local_generated_at="$(manifest_generated_at "${output_dir}/public_manifest.json")"
  cache_bust="$(date +%s)"
  remote_generated_at="$(
    curl --fail --silent --show-error --max-time 30 \
      "${dev_generated_asset_url}?cache-bust=${cache_bust}" |
      python3 -c 'import json, sys; print(json.load(sys.stdin)["generated_at"])'
  )"
  if [[ "${remote_generated_at}" != "${local_generated_at}" ]]; then
    printf \
      'event=talkingboats_public_clip_refresh_failed stage=dev_validation expected=%s actual=%s\n' \
      "${local_generated_at}" \
      "${remote_generated_at}" >&2
    return 1
  fi
  printf \
    'event=talkingboats_public_clip_refresh_dev_verified generated_at=%s\n' \
    "${local_generated_at}"
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
if [[ $# -ne 0 ]]; then
  usage >&2
  exit 2
fi

mkdir -p "$(dirname "${public_export_lock_file}")"
exec 9>"${public_export_lock_file}"
if ! flock -n 9; then
  echo "event=talkingboats_public_clip_refresh_skipped reason=export_locked"
  exit 0
fi

mkdir -p "${output_dir}"
if [[ -z "${raw_bucket}" ]]; then
  raw_bucket="$(cd "${tofu_dir}" && tofu output -raw "${raw_bucket_output}")"
fi

echo "event=talkingboats_public_clip_refresh_started environment=dev"
export TALKINGBOATS_CLIP_STORE_BACKEND="${clip_store_backend}"
"${conda_bin}" run --no-capture-output -n "${conda_env}" \
  talkingboats-export-public \
  --clip-store-backend "${clip_store_backend}" \
  --raw-bucket "${raw_bucket}" \
  --site-source public-site \
  --output-dir "${output_dir}" \
  --limit "${export_limit}"

verify_dev_generated_assets
echo "event=talkingboats_public_clip_refresh_promoting environment=prod"
TALKINGBOATS_TOFU_OUTPUT_QUIET=1 scripts/deploy_generated_public_assets.sh "prod" "${output_dir}"
echo "event=talkingboats_public_clip_refresh_complete environment=prod"
