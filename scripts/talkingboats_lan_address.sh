#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
conda_bin="${TALKINGBOATS_CONDA_BIN:-/home/rob/miniforge3/condabin/conda}"
conda_env="${TALKINGBOATS_LAN_CONDA_ENV:-dell}"
lan_interface="${TALKINGBOATS_LAN_INTERFACE:-eth0}"
lan_network="${TALKINGBOATS_LAN_NETWORK:-192.168.1.0/24}"
attempts="${TALKINGBOATS_LAN_READINESS_ATTEMPTS:-10}"
interval_seconds="${TALKINGBOATS_LAN_READINESS_INTERVAL_SECONDS:-2}"

cd "${repo_root}"
exec "${conda_bin}" run --no-capture-output -n "${conda_env}" \
  python -m talkingboats.network_readiness \
  --lan-interface "${lan_interface}" \
  --lan-network "${lan_network}" \
  --attempts "${attempts}" \
  --interval-seconds "${interval_seconds}" \
  --print-address \
  "$@"
