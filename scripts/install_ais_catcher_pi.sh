#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo on the Raspberry Pi." >&2
  exit 1
fi

build_dir="${AISCATCHER_BUILD_DIR:-/opt/talkingboats/build/AIS-catcher}"
repo_url="${AISCATCHER_REPO_URL:-https://github.com/jvde-github/AIS-catcher.git}"

apt-get update
apt-get install -y \
  build-essential \
  cmake \
  git \
  librtlsdr-dev \
  pkg-config

install -d -m 0755 "$(dirname "${build_dir}")"
if [[ -d "${build_dir}/.git" ]]; then
  git -C "${build_dir}" pull --ff-only
else
  rm -rf "${build_dir}"
  git clone --depth 1 "${repo_url}" "${build_dir}"
fi

cmake -S "${build_dir}" -B "${build_dir}/build"
cmake --build "${build_dir}/build" --parallel "$(nproc)"
install -m 0755 "${build_dir}/build/AIS-catcher" /usr/local/bin/AIS-catcher

/usr/local/bin/AIS-catcher -L >/dev/null || true
echo "AIS-catcher installed at /usr/local/bin/AIS-catcher"
