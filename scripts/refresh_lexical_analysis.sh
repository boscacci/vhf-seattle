#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

export PATH="/home/rob/.local/bin:/snap/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

db_path="${TALKINGBOATS_LEXICAL_DB_PATH:-/home/rob/.local/share/talkingboats/live-transcripts.sqlite3}"
output_dir="${TALKINGBOATS_LEXICAL_OUTPUT_DIR:-outputs/public-site}"
deploy_env="${TALKINGBOATS_LEXICAL_DEPLOY_ENV:-dev}"
conda_env="${TALKINGBOATS_LEXICAL_CONDA_ENV:-dell}"
conda_bin="${TALKINGBOATS_CONDA_BIN:-/home/rob/miniforge3/condabin/conda}"
lock_dir="${TALKINGBOATS_LEXICAL_LOCK_DIR:-outputs/.lexical-refresh.lock}"
page_size="${TALKINGBOATS_LEXICAL_PAGE_SIZE:-500}"
export_limit="${TALKINGBOATS_LEXICAL_EXPORT_LIMIT:-3000}"
raw_bucket_output="${TALKINGBOATS_LEXICAL_RAW_BUCKET_OUTPUT:-raw_audio_bucket}"

usage() {
  cat <<'EOF'
Usage: scripts/refresh_lexical_analysis.sh

Regenerates Elliott Bay VHF lexical-analysis artifacts from the clip database,
rebuilds the public static export, and deploys it to dev by default.

Environment overrides:
  TALKINGBOATS_LEXICAL_DB_PATH          SQLite transcript DB path
  TALKINGBOATS_LEXICAL_OUTPUT_DIR       Static export directory
  TALKINGBOATS_LEXICAL_DEPLOY_ENV       dev or prod; defaults to dev
  TALKINGBOATS_LEXICAL_CONDA_ENV        Conda env; defaults to dell
  TALKINGBOATS_CONDA_BIN                Conda binary path
  TALKINGBOATS_LEXICAL_PAGE_SIZE        Analysis DB page size
  TALKINGBOATS_LEXICAL_EXPORT_LIMIT     Public clip export limit
  TALKINGBOATS_LEXICAL_RAW_BUCKET_OUTPUT OpenTofu output name for raw bucket
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

if [[ "${deploy_env}" != "dev" && "${deploy_env}" != "prod" ]]; then
  echo "TALKINGBOATS_LEXICAL_DEPLOY_ENV must be dev or prod, got: ${deploy_env}" >&2
  exit 2
fi

if [[ ! -f "${db_path}" ]]; then
  echo "Transcript database does not exist: ${db_path}" >&2
  exit 1
fi

mkdir -p "$(dirname "${lock_dir}")"
if ! mkdir "${lock_dir}" 2>/dev/null; then
  echo "Lexical refresh is already running; skipping this tick."
  exit 0
fi
trap cleanup EXIT

mkdir -p "${output_dir}"
raw_bucket="$(cd infra/opentofu && tofu output -raw "${raw_bucket_output}")"

echo "Refreshing lexical analysis from ${db_path} into ${output_dir}"
rm -rf "${output_dir}/analysis"
"${conda_bin}" run --no-capture-output -n "${conda_env}" \
  talkingboats-analyze-transcripts \
  --db-path "${db_path}" \
  --output-dir "${output_dir}" \
  --page-size "${page_size}"

echo "Rebuilding public export from ${db_path}"
"${conda_bin}" run --no-capture-output -n "${conda_env}" \
  talkingboats-export-public \
  --clip-db-path "${db_path}" \
  --raw-bucket "${raw_bucket}" \
  --site-source public-site \
  --output-dir "${output_dir}" \
  --limit "${export_limit}"

echo "Deploying refreshed analysis to ${deploy_env}"
scripts/deploy_public_site.sh "${deploy_env}" "${output_dir}"
echo "Refresh complete"
