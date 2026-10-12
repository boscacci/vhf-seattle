#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
conda_python="${HOME}/miniforge3/envs/dell/bin/python"
storage="${TALKINGBOATS_ASR_STORAGE_ROOT:-}"
if [[ -z "${storage}" ]]; then
  storage="$("${conda_python}" - <<'PY'
from pathlib import Path
path = Path.home()/'.config/talkingboats/asr.env'
values = dict(line.partition('=')[::2] for line in path.read_text().splitlines()) if path.exists() else {}
print(Path(values['TALKINGBOATS_ASR_OUTPUT_DIR']).parent if values.get('TALKINGBOATS_ASR_OUTPUT_DIR') else Path.home()/'.local/share/talkingboats/asr-storage')
PY
)"
fi
if [[ "${storage}" == /mnt/* ]]; then
  volume="/mnt/${storage#/mnt/}"; volume="/mnt/$(printf '%s' "${volume#/mnt/}" | cut -d/ -f1)"
  mountpoint -q "${volume}" || { echo 'ASR data volume is not mounted.' >&2; exit 2; }
fi
identity="$(sha256sum "${repo_root}/config/asr-training-requirements.txt" | cut -c1-16)"
training_env="${storage}/training-env/${identity}"
install -d -m 0700 "${storage}/tmp" "${storage}/pip-cache"
export TMPDIR="${storage}/tmp" PIP_CACHE_DIR="${storage}/pip-cache"
if [[ ! -x "${training_env}/bin/python" ]]; then
  "${conda_python}" -m venv "${training_env}"
fi
# Install the pinned CPU wheel from PyTorch's official index; no CUDA dependencies.
"${training_env}/bin/python" -m pip install 'torch==2.10.0+cpu' --index-url https://download.pytorch.org/whl/cpu
"${training_env}/bin/python" -m pip install -r "${repo_root}/config/asr-training-requirements.txt"
"${training_env}/bin/python" -m pip check
"${training_env}/bin/python" -c 'import torch, peft, transformers, ctranslate2; assert torch.__version__ == "2.10.0+cpu"; print("ASR isolated CPU dependencies ready")'
link="${HOME}/.local/share/talkingboats/asr-training-env"
if [[ -d "${link}" && ! -L "${link}" ]]; then
  mv "${link}" "${link}.previous-$(date -u +%Y%m%dT%H%M%SZ)"
fi
ln -sfn "${training_env}" "${link}"
