#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="${TALKINGBOATS_PI_DEPLOY_TARGET:-rob@192.168.1.114}"
release_commit="${TALKINGBOATS_RELEASE_COMMIT:-$(git -C "${repo_root}" rev-parse HEAD)}"

[[ "${target}" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$ ]] || {
  echo "invalid Pi deployment target" >&2
  exit 2
}
[[ "${release_commit}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "TALKINGBOATS_RELEASE_COMMIT must be a full lowercase Git SHA" >&2
  exit 2
}
[[ "$(git -C "${repo_root}" rev-parse HEAD)" == "${release_commit}" ]] || {
  echo "checked-out commit does not match TALKINGBOATS_RELEASE_COMMIT" >&2
  exit 2
}
[[ -z "$(git -C "${repo_root}" status --porcelain --untracked-files=no)" ]] || {
  echo "tracked worktree changes are not deployable" >&2
  exit 2
}

artifact_dir="$(mktemp -d)"
remote_stage=""
cleanup() {
  find "${artifact_dir}" -depth -delete
  if [[ -n "${remote_stage}" && "${remote_stage}" == /tmp/talkingboats-pi-capture-health.* ]]; then
    ssh -o BatchMode=yes "${target}" \
      "find '${remote_stage}' -depth -delete" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

artifact="${artifact_dir}/pi-capture-health-${release_commit}.tar.gz"
tar -C "${repo_root}" -czf "${artifact}" \
  deploy/pi/live-radio/talkingboats-pi-healthcheck \
  deploy/pi/live-radio/talkingboats-reset-voice-sdr \
  deploy/systemd/talkingboats-profile-capture.service.example \
  deploy/pi/install_live_radio.sh \
  scripts/apply_pi_capture_health_release.sh
artifact_sha256="$(sha256sum "${artifact}" | awk '{print $1}')"

remote_stage="$(ssh -o BatchMode=yes -o ConnectTimeout=8 "${target}" \
  'mktemp -d /tmp/talkingboats-pi-capture-health.XXXXXX')"
[[ "${remote_stage}" == /tmp/talkingboats-pi-capture-health.* ]] || {
  echo "unexpected remote staging path" >&2
  exit 2
}

scp -q -o BatchMode=yes "${artifact}" "${target}:${remote_stage}/release.tar.gz"
ssh -o BatchMode=yes "${target}" \
  "printf '%s  %s\n' '${artifact_sha256}' '${remote_stage}/release.tar.gz' | sha256sum --check"
ssh -o BatchMode=yes "${target}" \
  "tar -xzf '${remote_stage}/release.tar.gz' -C '${remote_stage}'"
ssh -o BatchMode=yes "${target}" \
  "sudo -n env TALKINGBOATS_RELEASE_COMMIT='${release_commit}' TALKINGBOATS_RELEASE_SHA256='${artifact_sha256}' bash '${remote_stage}/scripts/apply_pi_capture_health_release.sh' '${remote_stage}'"

deployed_commit="$(ssh -o BatchMode=yes "${target}" \
  "sudo -n cat '/opt/talkingboats/releases/pi-capture-health/${release_commit}/release-commit'")"
[[ "${deployed_commit}" == "${release_commit}" ]] || {
  echo "deployed release identity did not match" >&2
  exit 1
}
printf 'event=talkingboats_pi_capture_health_release_complete commit=%s artifact_sha256=%s\n' \
  "${release_commit}" "${artifact_sha256}"
