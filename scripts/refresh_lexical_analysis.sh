#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

export PATH="/home/rob/.local/bin:/snap/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

output_dir="${TALKINGBOATS_LEXICAL_OUTPUT_DIR:-outputs/public-site}"
deploy_envs="${TALKINGBOATS_LEXICAL_DEPLOY_ENVS:-${TALKINGBOATS_LEXICAL_DEPLOY_ENV:-dev prod}}"
clip_store_backend="${TALKINGBOATS_CLIP_STORE_BACKEND:-dynamodb}"
conda_env="${TALKINGBOATS_LEXICAL_CONDA_ENV:-dell}"
conda_bin="${TALKINGBOATS_CONDA_BIN:-/home/rob/miniforge3/condabin/conda}"
lock_dir="${TALKINGBOATS_LEXICAL_LOCK_DIR:-outputs/.lexical-refresh.lock}"
page_size="${TALKINGBOATS_LEXICAL_PAGE_SIZE:-500}"
export_limit="${TALKINGBOATS_LEXICAL_EXPORT_LIMIT:-3000}"
raw_bucket_output="${TALKINGBOATS_LEXICAL_RAW_BUCKET_OUTPUT:-raw_audio_bucket}"
raw_bucket="${TALKINGBOATS_RAW_BUCKET:-}"
tofu_dir="${TALKINGBOATS_TOFU_DIR:-infra/opentofu}"

usage() {
  cat <<'EOF'
Usage: scripts/refresh_lexical_analysis.sh

Regenerates Elliott Bay VHF lexical-analysis artifacts from the clip store,
rebuilds the public static export, and deploys it to dev by default.

Environment overrides:
  TALKINGBOATS_LEXICAL_OUTPUT_DIR       Static export directory
  TALKINGBOATS_LEXICAL_DEPLOY_ENVS      Space-separated deploy targets; defaults to "dev prod"
  TALKINGBOATS_LEXICAL_DEPLOY_ENV       Legacy single deploy target override
  TALKINGBOATS_CLIP_STORE_BACKEND       Clip store backend; defaults to dynamodb
  TALKINGBOATS_LEXICAL_CONDA_ENV        Conda env; defaults to dell
  TALKINGBOATS_CONDA_BIN                Conda binary path
  TALKINGBOATS_LEXICAL_PAGE_SIZE        Analysis clip-store page size
  TALKINGBOATS_LEXICAL_EXPORT_LIMIT     Public clip export limit
  TALKINGBOATS_LEXICAL_RAW_BUCKET_OUTPUT OpenTofu output name for raw bucket
  TALKINGBOATS_RAW_BUCKET               Raw bucket override; skips OpenTofu output lookup
EOF
}

cleanup() {
  if [[ -n "${lock_dir:-}" && -d "${lock_dir}" ]]; then
    rmdir "${lock_dir}" 2>/dev/null || true
  fi
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

valid_deploy_env_count=0
for deploy_env in ${deploy_envs}; do
  if [[ "${deploy_env}" != "dev" && "${deploy_env}" != "prod" ]]; then
    echo "Deploy targets must be dev or prod, got: ${deploy_env}" >&2
    exit 2
  fi
  valid_deploy_env_count=$((valid_deploy_env_count + 1))
done
if [[ "${valid_deploy_env_count}" -eq 0 ]]; then
  echo "At least one deploy target is required." >&2
  exit 2
fi

mkdir -p "$(dirname "${lock_dir}")"
if ! mkdir "${lock_dir}" 2>/dev/null; then
  echo "Lexical refresh is already running; skipping this tick."
  exit 0
fi
trap cleanup EXIT

mkdir -p "${output_dir}"
if [[ -z "${raw_bucket}" ]]; then
  raw_bucket="$(cd "${tofu_dir}" && tofu output -raw "${raw_bucket_output}")"
fi

echo "Rebuilding public export from ${clip_store_backend}"
export TALKINGBOATS_CLIP_STORE_BACKEND="${clip_store_backend}"
"${conda_bin}" run --no-capture-output -n "${conda_env}" \
  talkingboats-export-public \
  --clip-store-backend "${clip_store_backend}" \
  --raw-bucket "${raw_bucket}" \
  --site-source public-site \
  --output-dir "${output_dir}" \
  --limit "${export_limit}"

echo "Refreshing lexical analysis from transcript store into ${output_dir}"
rm -rf "${output_dir}/analysis"
"${conda_bin}" run --no-capture-output -n "${conda_env}" \
  talkingboats-analyze-transcripts \
  --clip-store-backend "${clip_store_backend}" \
  --public-audio-manifest-path "${output_dir}/public_manifest.json" \
  --output-dir "${output_dir}" \
  --page-size "${page_size}"

echo "Deploying refreshed export to ${deploy_envs}"
for deploy_env in ${deploy_envs}; do
  case "${deploy_env}" in
    dev)
      scripts/deploy_public_site.sh "dev" "${output_dir}"
      ;;
    prod)
      scripts/deploy_generated_public_assets.sh "prod" "${output_dir}"
      ;;
  esac
done
echo "Refresh complete"
