#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo on the Raspberry Pi." >&2
  exit 1
fi

build_dir="${RTLSDR_AIRBAND_BUILD_DIR:-/opt/talkingboats/build/RTLSDR-Airband}"
repo_url="${RTLSDR_AIRBAND_REPO_URL:-https://github.com/rtl-airband/RTLSDR-Airband.git}"
version="${RTLSDR_AIRBAND_VERSION:-v5.2.0}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
buffered_clip_patch="${repo_root}/deploy/pi/patches/rtl-airband-buffered-clips-v5.2.0.patch"

apt-get update
apt-get install -y \
  build-essential \
  cmake \
  git \
  libconfig++-dev \
  libfftw3-dev \
  libmp3lame-dev \
  librtlsdr-dev \
  libshout3-dev \
  pkg-config

install -d -m 0755 "$(dirname "${build_dir}")"
if [[ -d "${build_dir}/.git" ]]; then
  git -C "${build_dir}" fetch --depth 1 origin "refs/tags/${version}:refs/tags/${version}"
else
  rm -rf "${build_dir}"
  git clone --depth 1 --branch "${version}" "${repo_url}" "${build_dir}"
fi
git -C "${build_dir}" checkout --detach --force "${version}"
git -C "${build_dir}" reset --hard "${version}"
if [[ ! -f "${buffered_clip_patch}" ]]; then
  echo "Missing buffered clip patch: ${buffered_clip_patch}" >&2
  exit 2
fi
git -C "${build_dir}" apply --check "${buffered_clip_patch}"
git -C "${build_dir}" apply "${buffered_clip_patch}"

# Upstream's version helper is executed by CMake from the build directory, so make
# its git lookup explicit before configuring.
sed -i 's/git describe --tags --abbrev --dirty --always/git -C "${PROJECT_ROOT_PATH}" describe --tags --abbrev --dirty --always/' \
  "${build_dir}/scripts/find_version"

cmake -S "${build_dir}" -B "${build_dir}/build" -DNFM=ON
cmake --build "${build_dir}/build" --parallel "$(nproc)"
install -m 0755 "${build_dir}/build/src/rtl_airband" /usr/local/bin/rtl_airband

/usr/local/bin/rtl_airband -h >/dev/null || true
echo "RTLSDR-Airband installed at /usr/local/bin/rtl_airband"
