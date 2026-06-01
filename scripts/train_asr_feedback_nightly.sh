#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

export PATH="/home/rob/.local/bin:/snap/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

db_path="${TALKINGBOATS_ASR_FEEDBACK_DB_PATH:-/home/rob/.local/share/talkingboats/live-transcripts.sqlite3}"
output_dir="${TALKINGBOATS_ASR_FEEDBACK_OUTPUT_DIR:-outputs/asr-feedback}"
conda_env="${TALKINGBOATS_ASR_FEEDBACK_CONDA_ENV:-dell}"
conda_bin="${TALKINGBOATS_CONDA_BIN:-/home/rob/miniforge3/condabin/conda}"
lock_dir="${TALKINGBOATS_ASR_FEEDBACK_LOCK_DIR:-outputs/.asr-feedback-training.lock}"
raw_bucket="${TALKINGBOATS_RAW_BUCKET:-}"
aws_region="${AWS_REGION:-${TALKINGBOATS_AWS_REGION:-us-west-2}}"
base_model="${TALKINGBOATS_ASR_FEEDBACK_BASE_MODEL:-openai/whisper-small.en}"
min_corrections="${TALKINGBOATS_ASR_FEEDBACK_MIN_CORRECTIONS:-20}"
max_corrections="${TALKINGBOATS_ASR_FEEDBACK_MAX_CORRECTIONS:-}"
epochs="${TALKINGBOATS_ASR_FEEDBACK_EPOCHS:-3}"
train_batch_size="${TALKINGBOATS_ASR_FEEDBACK_TRAIN_BATCH_SIZE:-4}"
gradient_accumulation_steps="${TALKINGBOATS_ASR_FEEDBACK_GRADIENT_ACCUMULATION_STEPS:-2}"
learning_rate="${TALKINGBOATS_ASR_FEEDBACK_LEARNING_RATE:-0.00001}"
warmup_steps="${TALKINGBOATS_ASR_FEEDBACK_WARMUP_STEPS:-20}"
quantization="${TALKINGBOATS_ASR_FEEDBACK_QUANTIZATION:-int8}"
restart_service="${TALKINGBOATS_ASR_RESTART_SERVICE:-talkingboats-uploaded-clip-transcriber.service}"

usage() {
  cat <<'EOF'
Usage: scripts/train_asr_feedback_nightly.sh

Runs the reviewed-transcript ASR feedback trainer. It materializes corrected
audio/transcript pairs from S3, fine-tunes Whisper, converts the result to a
faster-whisper/CTranslate2 model directory, promotes outputs/asr-feedback/latest-ct2,
and restarts the uploaded-clip transcriber service by default.

Environment overrides:
  TALKINGBOATS_ASR_FEEDBACK_DB_PATH        SQLite transcript DB path
  TALKINGBOATS_ASR_FEEDBACK_OUTPUT_DIR     Training artifact directory
  TALKINGBOATS_ASR_FEEDBACK_CONDA_ENV      Conda env; defaults to dell
  TALKINGBOATS_CONDA_BIN                   Conda binary path
  TALKINGBOATS_RAW_BUCKET                  Private raw audio bucket
  TALKINGBOATS_ASR_FEEDBACK_BASE_MODEL     Hugging Face Whisper checkpoint
  TALKINGBOATS_ASR_FEEDBACK_MIN_CORRECTIONS Minimum reviewed corrections to train
  TALKINGBOATS_ASR_RESTART_SERVICE         systemd user service to restart
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

if [[ ! -f "${db_path}" ]]; then
  echo "Transcript database does not exist: ${db_path}" >&2
  exit 1
fi

if [[ -z "${raw_bucket}" ]]; then
  echo "TALKINGBOATS_RAW_BUCKET is required for ASR feedback training." >&2
  exit 2
fi

mkdir -p "$(dirname "${lock_dir}")"
if ! mkdir "${lock_dir}" 2>/dev/null; then
  echo "ASR feedback training is already running; skipping this tick."
  exit 0
fi
trap cleanup EXIT

args=(
  talkingboats-train-asr-feedback nightly
  --db-path "${db_path}"
  --output-dir "${output_dir}"
  --bucket "${raw_bucket}"
  --aws-region "${aws_region}"
  --base-model "${base_model}"
  --min-corrections "${min_corrections}"
  --epochs "${epochs}"
  --train-batch-size "${train_batch_size}"
  --gradient-accumulation-steps "${gradient_accumulation_steps}"
  --learning-rate "${learning_rate}"
  --warmup-steps "${warmup_steps}"
  --quantization "${quantization}"
  --restart-service "${restart_service}"
)

if [[ -n "${max_corrections}" ]]; then
  args+=(--max-corrections "${max_corrections}")
fi

if [[ "${TALKINGBOATS_ASR_FEEDBACK_SKIP_RESTART:-}" == "1" ]]; then
  args+=(--skip-restart)
fi

echo "Running ASR feedback training from ${db_path} into ${output_dir}"
"${conda_bin}" run --no-capture-output -n "${conda_env}" "${args[@]}"
echo "ASR feedback training tick complete"
