#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root" >&2
  exit 2
fi

release_root="${1:?release root is required}"
release_commit="${TALKINGBOATS_RELEASE_COMMIT:?release commit is required}"
artifact_sha256="${TALKINGBOATS_RELEASE_SHA256:?release artifact sha256 is required}"
source_timeout_seconds="${TALKINGBOATS_ICECAST_SOURCE_TIMEOUT_SECONDS:-90000}"
healthcheck_source="${release_root}/deploy/pi/live-radio/talkingboats-pi-healthcheck"
healthcheck_target="${TALKINGBOATS_PI_HEALTHCHECK_PATH:-/opt/talkingboats/bin/talkingboats-pi-healthcheck}"
reset_source="${release_root}/deploy/pi/live-radio/talkingboats-reset-voice-sdr"
reset_target="${TALKINGBOATS_PI_RESET_VOICE_SDR_PATH:-/opt/talkingboats/bin/talkingboats-reset-voice-sdr}"
capture_unit_source="${release_root}/deploy/systemd/talkingboats-profile-capture.service.example"
capture_unit_target="${TALKINGBOATS_PI_CAPTURE_UNIT_PATH:-/etc/systemd/system/talkingboats-profile-capture.service}"
icecast_config="${TALKINGBOATS_ICECAST_CONFIG_PATH:-/etc/icecast2/icecast.xml}"
release_base="${TALKINGBOATS_PI_RELEASE_ROOT:-/opt/talkingboats/releases/pi-capture-health}"
release_dir="${release_base}/${release_commit}"
icecast_backup="${icecast_config}.break-glass-${release_commit}"
previous_healthcheck="${release_dir}/previous-talkingboats-pi-healthcheck"
previous_reset="${release_dir}/previous-talkingboats-reset-voice-sdr"
previous_capture_unit="${release_dir}/previous-talkingboats-profile-capture.service"

[[ "${release_commit}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "release commit must be a full lowercase Git SHA" >&2
  exit 2
}
[[ "${artifact_sha256}" =~ ^[0-9a-f]{64}$ ]] || {
  echo "release artifact sha256 must be a full lowercase digest" >&2
  exit 2
}
[[ "${source_timeout_seconds}" =~ ^[1-9][0-9]*$ ]] &&
  ((source_timeout_seconds > 86400)) || {
  echo "Icecast source timeout must exceed the daily capture runtime" >&2
  exit 2
}
[[ -f "${healthcheck_source}" && -f "${reset_source}" &&
  -f "${capture_unit_source}" && -f "${icecast_config}" ]] || {
  echo "release runtime file or Icecast config is missing" >&2
  exit 2
}
[[ "$(grep -Ec '<source-timeout>[0-9]+</source-timeout>' "${icecast_config}")" == "1" ]] || {
  echo "expected exactly one numeric Icecast source timeout" >&2
  exit 2
}

install -d -m 0755 "${release_dir}"
cp -a "${icecast_config}" "${icecast_backup}"
if [[ -f "${healthcheck_target}" ]]; then
  cp -a "${healthcheck_target}" "${previous_healthcheck}"
fi
if [[ -f "${reset_target}" ]]; then
  cp -a "${reset_target}" "${previous_reset}"
fi
if [[ -f "${capture_unit_target}" ]]; then
  cp -a "${capture_unit_target}" "${previous_capture_unit}"
fi

rollback_required=true
rollback() {
  if [[ "${rollback_required}" != "true" ]]; then
    return
  fi
  cp -a "${icecast_backup}" "${icecast_config}"
  if [[ -f "${previous_healthcheck}" ]]; then
    install -m 0755 "${previous_healthcheck}" "${healthcheck_target}"
  fi
  if [[ -f "${previous_reset}" ]]; then
    install -m 0755 "${previous_reset}" "${reset_target}"
  fi
  if [[ -f "${previous_capture_unit}" ]]; then
    install -m 0644 "${previous_capture_unit}" "${capture_unit_target}"
  fi
  systemctl daemon-reload || true
  systemctl reload icecast2.service || true
  systemctl restart talkingboats-profile-capture.service || true
  systemctl reset-failed talkingboats-pi-healthcheck.service || true
  systemctl start talkingboats-pi-healthcheck.service || true
  systemctl start talkingboats-pi-healthcheck.timer || true
}
trap rollback ERR

systemctl stop talkingboats-pi-healthcheck.timer
systemctl stop talkingboats-pi-healthcheck.service || true

sed -Ei \
  "s|<source-timeout>[0-9]+</source-timeout>|<source-timeout>${source_timeout_seconds}</source-timeout>|" \
  "${icecast_config}"
python3 -c 'import sys; from xml.etree import ElementTree; ElementTree.parse(sys.argv[1])' \
  "${icecast_config}"
install -m 0755 "${healthcheck_source}" "${healthcheck_target}"
install -m 0755 "${reset_source}" "${reset_target}"
install -m 0644 "${capture_unit_source}" "${capture_unit_target}"

systemctl daemon-reload
systemctl reload icecast2.service
systemctl restart talkingboats-profile-capture.service
systemctl reset-failed talkingboats-pi-healthcheck.service
systemctl start talkingboats-pi-healthcheck.service
systemctl start talkingboats-pi-healthcheck.timer
systemctl is-active --quiet icecast2.service
systemctl is-active --quiet talkingboats-profile-capture.service
systemctl is-active --quiet talkingboats-pi-healthcheck.timer

install -m 0755 "$0" "${release_dir}/apply_pi_capture_health_release.sh"
install -m 0755 "${healthcheck_source}" \
  "${release_dir}/talkingboats-pi-healthcheck"
install -m 0755 "${reset_source}" \
  "${release_dir}/talkingboats-reset-voice-sdr"
install -m 0644 "${capture_unit_source}" \
  "${release_dir}/talkingboats-profile-capture.service"
printf '%s\n' "${release_commit}" > "${release_dir}/release-commit"
printf '%s\n' "${artifact_sha256}" > "${release_dir}/release-artifact-sha256"
date -u +%Y-%m-%dT%H:%M:%SZ > "${release_dir}/deployed-at-utc"
sha256sum "${healthcheck_target}" "${reset_target}" "${capture_unit_target}" \
  > "${release_dir}/installed-files.sha256"

rollback_required=false
trap - ERR
printf 'event=talkingboats_pi_capture_health_deployed commit=%s artifact_sha256=%s\n' \
  "${release_commit}" "${artifact_sha256}"
