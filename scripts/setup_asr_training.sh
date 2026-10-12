#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
training_env="${HOME}/.local/share/talkingboats/asr-training-env"
conda_python="${HOME}/miniforge3/envs/dell/bin/python"
# Reuse Conda serving packages read-only; isolate the small training additions.
if [[ ! -x "${training_env}/bin/python" ]]; then
  "${conda_python}" -m venv --system-site-packages "${training_env}"
fi
"${training_env}/bin/python" -m pip install -r "${repo_root}/config/asr-training-requirements.txt"
"${training_env}/bin/python" -c 'import torch, peft, transformers, ctranslate2; print("ASR training dependencies ready")'
