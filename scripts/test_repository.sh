#!/usr/bin/env bash
# Keep disposable fixtures off the capture host's disk journals; retain every test.
set -Eeuo pipefail
scratch="$(mktemp -d /dev/shm/talkingboats-pytest.XXXXXX)"
[[ "${scratch}" =~ ^/dev/shm/talkingboats-pytest\.[A-Za-z0-9]+$ ]] || exit 2
cleanup() { rm -rf -- "${scratch}"; }
trap cleanup EXIT
export TMPDIR="${scratch}"
export PYTHONDONTWRITEBYTECODE=1
"${HOME}/miniforge3/condabin/conda" run --no-capture-output -n dell \
  pytest -q --basetemp="${scratch}/cases" -o "cache_dir=${scratch}/cache" \
  -o faulthandler_timeout=60 "$@"
