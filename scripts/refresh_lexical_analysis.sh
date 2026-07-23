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
lock_file="${TALKINGBOATS_LEXICAL_LOCK_FILE:-outputs/.lexical-refresh.lock}"
analysis_work_dir="${output_dir}/.analysis-refresh"
previous_analysis_dir="${output_dir}/.analysis-previous"
page_size="${TALKINGBOATS_LEXICAL_PAGE_SIZE:-500}"
export_limit="${TALKINGBOATS_LEXICAL_EXPORT_LIMIT:-3000}"
raw_bucket_output="${TALKINGBOATS_LEXICAL_RAW_BUCKET_OUTPUT:-raw_audio_bucket}"
raw_bucket="${TALKINGBOATS_RAW_BUCKET:-}"
tofu_dir="${TALKINGBOATS_TOFU_DIR:-infra/opentofu}"
search_warm_url="${TALKINGBOATS_SEARCH_WARM_URL:-}"
search_warm_timeout_seconds="${TALKINGBOATS_SEARCH_WARM_TIMEOUT_SECONDS:-30}"
dev_generated_asset_url="${TALKINGBOATS_DEV_GENERATED_ASSET_URL:-https://dev.seattleboatradio.com/public_manifest.json}"

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
  TALKINGBOATS_LEXICAL_LOCK_FILE        Crash-safe refresh lock file
  TALKINGBOATS_LEXICAL_PAGE_SIZE        Analysis clip-store page size
  TALKINGBOATS_LEXICAL_EXPORT_LIMIT     Public clip export limit
  TALKINGBOATS_LEXICAL_RAW_BUCKET_OUTPUT OpenTofu output name for raw bucket
  TALKINGBOATS_RAW_BUCKET               Raw bucket override; skips OpenTofu output lookup
  TALKINGBOATS_SEARCH_WARM_URL          Private read-only search URL used to warm the refreshed index
  TALKINGBOATS_SEARCH_WARM_TIMEOUT_SECONDS Search warmup timeout; defaults to 30 seconds
  TALKINGBOATS_DEV_GENERATED_ASSET_URL  Tailnet dev manifest URL used to validate generated assets
EOF
}

resolve_search_warm_url() {
  local lan_address
  if [[ -n "${search_warm_url}" ]]; then
    printf '%s' "${search_warm_url}"
    return 0
  fi
  lan_address="$(/bin/bash "${repo_root}/scripts/talkingboats_lan_address.sh")"
  printf 'http://%s:8034/api/clips/search?q=seattle+traffic&limit=1&recency=24h' "${lan_address}"
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
  remote_generated_at="$(curl --fail --silent --show-error --max-time 30 "${dev_generated_asset_url}?cache-bust=${cache_bust}" | python3 -c 'import json, sys; print(json.load(sys.stdin)["generated_at"])')"
  if [[ "${remote_generated_at}" != "${local_generated_at}" ]]; then
    echo "Dev generated manifest is stale: expected ${local_generated_at}, got ${remote_generated_at}" >&2
    return 1
  fi
  echo "Verified dev generated manifest at ${local_generated_at}"
}

cleanup() {
  rm -rf "${analysis_work_dir:-}" 2>/dev/null || true
  if [[ -n "${previous_analysis_dir:-}" && -d "${previous_analysis_dir}" ]]; then
    if [[ ! -d "${output_dir}/analysis" ]]; then
      mv "${previous_analysis_dir}" "${output_dir}/analysis" 2>/dev/null || true
    else
      rm -rf "${previous_analysis_dir}" 2>/dev/null || true
    fi
  fi
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

valid_deploy_env_count=0
dev_target_requested=0
prod_target_requested=0
for deploy_env in ${deploy_envs}; do
  if [[ "${deploy_env}" != "dev" && "${deploy_env}" != "prod" ]]; then
    echo "Deploy targets must be dev or prod, got: ${deploy_env}" >&2
    exit 2
  fi
  if [[ "${deploy_env}" == "dev" ]]; then
    dev_target_requested=1
  else
    prod_target_requested=1
  fi
  valid_deploy_env_count=$((valid_deploy_env_count + 1))
done
if [[ "${valid_deploy_env_count}" -eq 0 ]]; then
  echo "At least one deploy target is required." >&2
  exit 2
fi
if [[ "${prod_target_requested}" -eq 1 && "${dev_target_requested}" -ne 1 && "${TALKINGBOATS_ALLOW_PROD_WITHOUT_DEV:-0}" != "1" ]]; then
  echo "Refusing prod promotion without dev validation. Set TALKINGBOATS_ALLOW_PROD_WITHOUT_DEV=1 only for an emergency." >&2
  exit 2
fi

mkdir -p "$(dirname "${lock_file}")"
exec 9>"${lock_file}"
if ! flock -n 9; then
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

echo "Refreshing lexical analysis from transcript store into ${analysis_work_dir}"
rm -rf "${analysis_work_dir}" "${previous_analysis_dir}"
mkdir -p "${analysis_work_dir}"
"${conda_bin}" run --no-capture-output -n "${conda_env}" \
  talkingboats-analyze-transcripts \
  --clip-store-backend "${clip_store_backend}" \
  --public-audio-manifest-path "${output_dir}/public_manifest.json" \
  --output-dir "${analysis_work_dir}" \
  --page-size "${page_size}"
if [[ ! -d "${analysis_work_dir}/analysis" ]]; then
  echo "Lexical analysis did not produce ${analysis_work_dir}/analysis" >&2
  exit 1
fi
if [[ -d "${output_dir}/analysis" ]]; then
  mv "${output_dir}/analysis" "${previous_analysis_dir}"
fi
mv "${analysis_work_dir}/analysis" "${output_dir}/analysis"
rm -rf "${analysis_work_dir}" "${previous_analysis_dir}"

echo "Warming refreshed public transcript search"
search_warm_url="$(resolve_search_warm_url)"
curl --fail --silent --show-error --max-time "${search_warm_timeout_seconds}" \
  "${search_warm_url}" >/dev/null

echo "Deploying refreshed export to ${deploy_envs}"
for deploy_env in ${deploy_envs}; do
  case "${deploy_env}" in
    dev)
      verify_dev_generated_assets
      ;;
    prod)
      scripts/deploy_generated_public_assets.sh "prod" "${output_dir}"
      ;;
  esac
done
echo "Refresh complete"
