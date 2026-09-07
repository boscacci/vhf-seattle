#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: scripts/apply_optiplex_performance_release.sh dev|prod RELEASE_ROOT" >&2
}

environment="${1:-}"
release_root="${2:-}"
release_commit="${TALKINGBOATS_RELEASE_COMMIT:-}"
artifact_sha256="${TALKINGBOATS_RELEASE_SHA256:-}"
module_relative="src/talkingboats/live_radio_proxy.py"
dev_drop_in_relative="deploy/systemd/overrides/talkingboats-live-radio-proxy.service.d/zzz-ci-performance-release.conf"

if [[ $# -ne 2 ]]; then
  usage
  exit 2
fi
[[ "${environment}" == "dev" || "${environment}" == "prod" ]] || {
  usage
  exit 2
}
[[ "${release_commit}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "release commit must be a full lowercase Git SHA" >&2
  exit 2
}
[[ "${artifact_sha256}" =~ ^[0-9a-f]{64}$ ]] || {
  echo "release artifact sha256 must be a full lowercase digest" >&2
  exit 2
}
[[ -f "${release_root}/${module_relative}" &&
  -f "${release_root}/public-site/index.html" &&
  -f "${release_root}/public-site/assets/app.js" &&
  -f "${release_root}/public-site/assets/styles.css" &&
  -f "${release_root}/${dev_drop_in_relative}" ]] || {
  echo "performance release artifact is incomplete" >&2
  exit 2
}

release_base="${TALKINGBOATS_PERFORMANCE_RELEASE_ROOT:-${HOME}/.local/share/talkingboats/releases/performance}"
record_dir="${release_base}/${environment}/${release_commit}"
install -d -m 0755 "${record_dir}"

if [[ "${environment}" == "dev" ]]; then
  current_link="${release_base}/dev/current"
  next_link="${release_base}/dev/current.next"
  drop_in_target="${TALKINGBOATS_PERFORMANCE_DEV_DROP_IN_PATH:-${HOME}/.config/systemd/user/talkingboats-live-radio-proxy.service.d/zzz-ci-performance-release.conf}"
  prior_target="$(readlink "${current_link}" 2>/dev/null || true)"
  prior_drop_in="${record_dir}/previous-zzz-ci-performance-release.conf"
  had_prior_drop_in=false

  if [[ ! -f "${record_dir}/release-artifact-sha256" ]]; then
    cp -a "${release_root}/src" "${record_dir}/src"
    cp -a "${release_root}/public-site" "${record_dir}/public-site"
    install -D -m 0644 "${release_root}/${dev_drop_in_relative}" \
      "${record_dir}/${dev_drop_in_relative}"
  fi
  if [[ -f "${record_dir}/release-artifact-sha256" ]]; then
    test "$(tr -d '\n' < "${record_dir}/release-artifact-sha256")" = "${artifact_sha256}"
  fi
  install -d -m 0755 "$(dirname "${drop_in_target}")" "${HOME}/.local/state/talkingboats"
  if [[ -f "${drop_in_target}" ]]; then
    cp -a "${drop_in_target}" "${prior_drop_in}"
    had_prior_drop_in=true
  fi
  install -m 0644 "${release_root}/${dev_drop_in_relative}" "${drop_in_target}"
  ln -sfn "${record_dir}" "${next_link}"
  mv -Tf "${next_link}" "${current_link}"

  rollback_dev() {
    if [[ -n "${prior_target}" ]]; then
      ln -sfn "${prior_target}" "${next_link}"
      mv -Tf "${next_link}" "${current_link}"
    else
      rm -f "${current_link}"
    fi
    if [[ "${had_prior_drop_in}" == "true" ]]; then
      install -m 0644 "${prior_drop_in}" "${drop_in_target}"
    else
      rm -f "${drop_in_target}"
    fi
    systemctl --user daemon-reload || true
    systemctl --user restart talkingboats-live-radio-proxy.service || true
  }
  trap rollback_dev ERR
  systemctl --user daemon-reload
  systemctl --user restart talkingboats-live-radio-proxy.service
  systemctl --user is-active --quiet talkingboats-live-radio-proxy.service
  curl --fail --silent --show-error --retry 20 --retry-delay 1 --retry-connrefused \
    http://172.20.0.1:8095/api/live/performance |
    jq -e '.hosts[0].thermal.sensorCount >= 2 and (.hosts[0].thermal.sensors | length) >= 2' >/dev/null
  trap - ERR
else
  runtime_root="${TALKINGBOATS_PERFORMANCE_PROD_RUNTIME_ROOT:-${HOME}/repos/elliott-bay-vhf/.runtime/live-ais-deploy}"
  module_target="${runtime_root}/${module_relative}"
  module_backup="${record_dir}/previous-live_radio_proxy.py"
  module_pending="${module_target}.pending-${release_commit}"
  [[ -f "${module_target}" ]] || {
    echo "production live proxy module is missing: ${module_target}" >&2
    exit 2
  }
  if [[ ! -f "${module_backup}" ]]; then
    cp -a "${module_target}" "${module_backup}"
  fi

  rollback_prod() {
    install -m 0644 "${module_backup}" "${module_target}"
    systemctl --user restart talkingboats-public-live-radio-proxy.service || true
  }
  trap rollback_prod ERR
  install -m 0644 "${release_root}/${module_relative}" "${module_pending}"
  mv -f "${module_pending}" "${module_target}"
  systemctl --user restart talkingboats-public-live-radio-proxy.service
  systemctl --user is-active --quiet talkingboats-public-live-radio-proxy.service
  curl --fail --silent --show-error --retry 20 --retry-delay 1 --retry-connrefused \
    http://127.0.0.1:8096/api/live/performance |
    jq -e '.hosts[0].thermal.sensorCount >= 2 and (.hosts[0].thermal.sensors | length) >= 2' >/dev/null
  trap - ERR
fi

printf '%s\n' "${release_commit}" > "${record_dir}/release-commit"
printf '%s\n' "${artifact_sha256}" > "${record_dir}/release-artifact-sha256"
date -u +%Y-%m-%dT%H:%M:%SZ > "${record_dir}/deployed-at-utc"
sha256sum "${release_root}/${module_relative}" \
  "${release_root}/public-site/index.html" \
  "${release_root}/public-site/assets/app.js" \
  "${release_root}/public-site/assets/styles.css" > "${record_dir}/release-files.sha256"
printf 'event=talkingboats_performance_release_deployed environment=%s commit=%s artifact_sha256=%s\n' \
  "${environment}" "${release_commit}" "${artifact_sha256}"
