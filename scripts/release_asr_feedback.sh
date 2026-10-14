#!/usr/bin/env bash
# Immutable dev delivery; production promotes the same artifact after one recorded approval.
set -Eeuo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
action="${1:-}"
[[ "${action}" == build || "${action}" == dev || "${action}" == prod ]] || {
  echo 'Usage: release_asr_feedback.sh build|dev|prod [annotated-tag approval.json]' >&2; exit 2;
}
commit="$(git -C "${repo_root}" rev-parse HEAD)"
[[ -z "$(git -C "${repo_root}" status --porcelain)" ]] || { echo 'Release requires a clean worktree.' >&2; exit 2; }
candidate_root="${HOME}/.local/share/talkingboats/release-candidates/asr"
if [[ "${action}" == prod ]]; then
  release_tag="${2:?production requires an annotated release tag}"
  approval_file="${3:?production requires the single recorded human approval}"
  [[ "${release_tag}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 2
  [[ "$(git -C "${repo_root}" cat-file -t "refs/tags/${release_tag}")" == tag ]] || exit 2
  commit="$(git -C "${repo_root}" rev-parse "${release_tag}^{commit}")"
fi
candidate="${candidate_root}/${commit}"
artifact="${candidate}/release.tar.gz"
if [[ "${action}" == build ]]; then
  [[ -f "${repo_root}/config/channel-selection.json" ]] || exit 2
  install -d -m 0755 "${candidate}"
  if [[ ! -f "${artifact}" ]]; then
    "${HOME}/miniforge3/envs/dell/bin/python" "${repo_root}/scripts/build_docktalk_artifact.py" "${repo_root}" "${commit}" "${artifact}.pending"
    mv "${artifact}.pending" "${artifact}"
    sha256sum "${artifact}" | awk '{print $1}' > "${candidate}/artifact.sha256"
    printf '%s\n' "${commit}" > "${candidate}/release-commit"
  fi
  printf 'event=asr_release_built commit=%s digest=%s\n' "${commit}" "$(cat "${candidate}/artifact.sha256")"
  exit 0
fi
[[ -f "${artifact}" && -f "${candidate}/artifact.sha256" ]] || { echo 'Build the candidate first.' >&2; exit 2; }
digest="$(cat "${candidate}/artifact.sha256")"
[[ "$(sha256sum "${artifact}" | awk '{print $1}')" == "${digest}" ]] || exit 2
release_root="${HOME}/.local/share/talkingboats/releases/asr/${action}/${commit}"
install -d -m 0700 "${release_root}"
if [[ ! -f "${release_root}/release-commit" ]]; then
  tar -xzf "${artifact}" -C "${release_root}"
  printf '%s\n' "${commit}" > "${release_root}/release-commit"
  printf '%s\n' "${digest}" > "${release_root}/artifact.sha256"
fi
[[ "$(cat "${release_root}/artifact.sha256")" == "${digest}" ]] || exit 2
if [[ "${action}" == prod ]]; then
  "${HOME}/miniforge3/envs/dell/bin/python" "${release_root}/scripts/verify_asr_approval.py" \
    "${approval_file}" "${release_tag}" "${commit}" "${digest}" "${candidate}/dev-smoke.json"
  [[ -f "${HOME}/.config/talkingboats/docktalk-claim" && $(stat -c '%a' "${HOME}/.config/talkingboats/docktalk-claim") == 600 ]] || { echo 'Private DockTalk enrollment file is required.' >&2; exit 2; }
  [[ $(getconf _NPROCESSORS_ONLN) == 8 ]] || { echo 'Continuous six-thread policy requires the eight-core OptiPlex.' >&2; exit 2; }
  git -C "${repo_root}" merge-base --is-ancestor "${commit}" origin/main || {
    echo 'Production tag must select an accepted, dev-tested default-branch commit.' >&2; exit 2;
  }
fi
state_root="${HOME}/.config/talkingboats"
install -d -m 0700 "${state_root}"
runtime_env_backup="${release_root}/previous-asr-env-${action}-$(date -u +%s%N)"
[[ ! -f "${state_root}/asr.env" ]] || cp -a "${state_root}/asr.env" "${runtime_env_backup}"
# Store only in the established private runtime configuration, never the artifact or logs.
TALKINGBOATS_ASR_RELEASE_COMMIT="${commit}" \
TALKINGBOATS_ASR_STORAGE_ROOT="${TALKINGBOATS_ASR_STORAGE_ROOT:-}" \
"${HOME}/miniforge3/envs/dell/bin/python" "${release_root}/scripts/configure_asr_runtime.py"
unit_root="${HOME}/.config/systemd/user"
if [[ "${action}" == dev ]]; then
  analysis_site="$("${HOME}/miniforge3/envs/dell/bin/python" - <<'PY'
from pathlib import Path
values = dict(line.partition('=')[::2] for line in (Path.home()/'.config/talkingboats/asr.env').read_text().splitlines())
print(Path(values['TALKINGBOATS_ASR_OUTPUT_DIR']).parent/'dev-analysis')
PY
)"
  source_site="$("${HOME}/miniforge3/envs/dell/bin/python" - <<'PY'
from pathlib import Path
values = dict(line.partition('=')[::2] for line in (Path.home()/'.config/talkingboats/asr.env').read_text().splitlines())
print(values['TALKINGBOATS_PUBLIC_SITE_DIR'])
PY
)"
  PYTHONPATH="${release_root}/src" CUDA_VISIBLE_DEVICES='' \
    "${HOME}/miniforge3/envs/dell/bin/python" "${release_root}/scripts/prepare_dev_analysis.py" "${source_site}" "${analysis_site}"
  current="${HOME}/.local/share/talkingboats/releases/asr/dev/current"
  prior="$(readlink "${current}" 2>/dev/null || true)"
  api_dropin="${unit_root}/talkingboats-api-dev.service.d/zzzz-asr-release.conf"
  proxy_dropin="${unit_root}/talkingboats-live-radio-proxy.service.d/zzzz-asr-release.conf"
  install -d -m 0755 "$(dirname "${api_dropin}")" "$(dirname "${proxy_dropin}")"
  for path in "${api_dropin}" "${proxy_dropin}"; do
    [[ ! -f "${path}" ]] || cp -a "${path}" "${release_root}/previous-$(basename "$(dirname "${path}")")"
  done
  rollback_dev() {
    if [[ -f "${runtime_env_backup}" ]]; then cp -a "${runtime_env_backup}" "${state_root}/asr.env"; else rm -f "${state_root}/asr.env"; fi
    for path in "${api_dropin}" "${proxy_dropin}"; do
      backup="${release_root}/previous-$(basename "$(dirname "${path}")")"
      if [[ -f "${backup}" ]]; then cp -a "${backup}" "${path}"; else rm -f "${path}"; fi
    done
    if [[ -n "${prior}" ]]; then ln -sfn "${prior}" "${current}"; else rm -f "${current}"; fi
    systemctl --user daemon-reload
    systemctl --user restart talkingboats-api-dev.service talkingboats-live-radio-proxy.service
  }
  trap rollback_dev ERR
  ln -sfn "${release_root}" "${current}.next"
  mv -Tf "${current}.next" "${current}"
  cat > "${api_dropin}" <<EOF
[Service]
WorkingDirectory=${current}
Environment=PYTHONPATH=${current}/src
EnvironmentFile=${state_root}/asr.env
Environment=TALKINGBOATS_ANALYSIS_SITE_DIR=${analysis_site}
EOF
  cat > "${proxy_dropin}" <<EOF
[Service]
WorkingDirectory=${current}
Environment=PYTHONPATH=${current}/src
Environment=TALKINGBOATS_PROXY_STATIC_SHELL_DIR=${current}/public-site
EnvironmentFile=${state_root}/asr.env
Environment=TALKINGBOATS_ANALYSIS_SITE_DIR=${analysis_site}
EOF
  install -m 0644 "${release_root}/deploy/systemd/talkingboats-asr-experiment@.service.example" \
    "${unit_root}/talkingboats-asr-experiment@.service"
  systemctl --user daemon-reload
  systemctl --user restart talkingboats-api-dev.service talkingboats-live-radio-proxy.service
  curl --fail --silent --show-error --retry 20 --retry-delay 1 --retry-connrefused http://127.0.0.1:8035/healthz >/dev/null
  TALKINGBOATS_ASR_SMOKE_FFMPEG="${HOME}/miniforge3/envs/dell/bin/ffmpeg" TALKINGBOATS_BROWSER_DEPENDENCY_ROOT="${repo_root}" node "${release_root}/scripts/asr_browser_smoke.mjs"
  printf '{"commit":"%s","artifact_sha256":"%s","dev_playwright_passed":true,"tested_at":"%s"}\n' \
    "${commit}" "${digest}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${candidate}/dev-smoke.json"
  trap - ERR
else
  runtime="${HOME}/repos/elliott-bay-vhf/.runtime/live-ais-deploy"
  backup="${release_root}/previous-runtime"
  install -d -m 0700 "${backup}"
  for service in talkingboats-api talkingboats-public-live-radio-proxy talkingboats-uploaded-clip-transcriber talkingboats-public-clip-refresh talkingboats-lexical-refresh; do
    path="${unit_root}/${service}.service.d/zzzz-asr-feedback.conf"
    [[ ! -f "${path}" ]] || cp -a "${path}" "${backup}/${service}.conf"
  done
  timer_was_active="$(systemctl --user is-active talkingboats-uploaded-clip-transcriber.timer || true)"
  timer_was_enabled="$(systemctl --user is-enabled talkingboats-uploaded-clip-transcriber.timer || true)"
  worker_was_active="$(systemctl --user is-active talkingboats-uploaded-clip-transcriber.service || true)"
  worker_was_enabled="$(systemctl --user is-enabled talkingboats-uploaded-clip-transcriber.service || true)"
  printf '{"timer_active":"%s","timer_enabled":"%s","worker_active":"%s","worker_enabled":"%s"}\n' \
    "${timer_was_active}" "${timer_was_enabled}" "${worker_was_active}" "${worker_was_enabled}" > "${backup}/worker-state.json"

  for part in src scripts config public-site; do
    [[ ! -d "${runtime}/${part}" ]] || cp -a "${runtime}/${part}" "${backup}/${part}"
  done
  rollback_prod() {
    if [[ -f "${runtime_env_backup}" ]]; then cp -a "${runtime_env_backup}" "${state_root}/asr.env"; else rm -f "${state_root}/asr.env"; fi
    for part in src scripts config public-site; do
      [[ ! -d "${backup}/${part}" ]] || cp -a "${backup}/${part}/." "${runtime}/${part}/"
    done
    for service in talkingboats-api talkingboats-public-live-radio-proxy talkingboats-uploaded-clip-transcriber talkingboats-public-clip-refresh talkingboats-lexical-refresh; do
      path="${unit_root}/${service}.service.d/zzzz-asr-feedback.conf"
      if [[ -f "${backup}/${service}.conf" ]]; then cp -a "${backup}/${service}.conf" "${path}"; else rm -f "${path}"; fi
    done
    systemctl --user stop talkingboats-uploaded-clip-transcriber.service || true
    systemctl --user daemon-reload
    if [[ "${timer_was_enabled}" == enabled ]]; then
      systemctl --user enable talkingboats-uploaded-clip-transcriber.timer
    else
      systemctl --user disable talkingboats-uploaded-clip-transcriber.timer
    fi
    if [[ "${worker_was_enabled}" == enabled ]]; then
      systemctl --user enable talkingboats-uploaded-clip-transcriber.service
    else
      systemctl --user disable talkingboats-uploaded-clip-transcriber.service
    fi
    if [[ "${worker_was_active}" == active || "${worker_was_active}" == activating ]]; then
      systemctl --user start --no-block talkingboats-uploaded-clip-transcriber.service
    fi
    [[ "${timer_was_active}" != active ]] || systemctl --user start talkingboats-uploaded-clip-transcriber.timer
    "${release_root}/scripts/deploy_asr_receiver.sh" "${release_root}" "${commit}" "${digest}" rollback || true
    systemctl --user restart talkingboats-api.service talkingboats-public-live-radio-proxy.service || true
    "${release_root}/scripts/deploy_static_shell.sh" prod "${backup}/public-site" || true
    printf 'event=asr_release_rollback environment=prod commit=%s require_static_cache_check=true\n' "${commit}" >&2
  }
  trap rollback_prod ERR
  systemctl --user stop talkingboats-uploaded-clip-transcriber.timer talkingboats-uploaded-clip-transcriber.service
  TALKINGBOATS_ASR_RELEASE_ROOT="${release_root}" PYTHONPATH="${release_root}/src" "${HOME}/miniforge3/envs/dell/bin/python" - <<'PYCODE'
import os,runpy
from pathlib import Path
values=dict(line.partition('=')[::2] for line in (Path.home()/'.config/talkingboats/asr.env').read_text().splitlines())
os.environ.update(values)
runpy.run_path(str(Path(os.environ['TALKINGBOATS_ASR_RELEASE_ROOT'])/'scripts/activate_recording_policy.py'),run_name='__main__')
PYCODE
  for part in src scripts config public-site; do
    install -d -m 0755 "${runtime}/${part}"
    cp -a "${release_root}/${part}/." "${runtime}/${part}/"
  done
  for service in talkingboats-api talkingboats-public-live-radio-proxy talkingboats-uploaded-clip-transcriber talkingboats-public-clip-refresh talkingboats-lexical-refresh; do
    install -d -m 0755 "${unit_root}/${service}.service.d"
    printf '[Service]\nEnvironmentFile=%s/asr.env\n' "${state_root}" > "${unit_root}/${service}.service.d/zzzz-asr-feedback.conf"
    if [[ "${service}" == talkingboats-uploaded-clip-transcriber ]]; then
      cat "${release_root}/deploy/systemd/overrides/talkingboats-uploaded-clip-transcriber.service.d/zzzz-asr-continuous.conf" >> "${unit_root}/${service}.service.d/zzzz-asr-feedback.conf"
    fi
  done
  systemctl --user daemon-reload
  systemctl --user restart talkingboats-api.service talkingboats-public-live-radio-proxy.service
  PYTHONPATH="${release_root}/src" "${HOME}/miniforge3/envs/dell/bin/python" - <<'PYCODE'
import os
from pathlib import Path
values = dict(line.partition("=")[::2] for line in (Path.home()/".config/talkingboats/asr.env").read_text().splitlines())
os.environ.update(values)
import boto3
from talkingboats.queue_channel_indexes import seed_indexes
from talkingboats.recording_policy import queue_checkpoint
result = seed_indexes(boto3.resource("dynamodb", region_name="us-west-2").Table(values["TALKINGBOATS_ASR_FEEDBACK_TABLE"]), queue_checkpoint(Path(values["TALKINGBOATS_ASR_OUTPUT_DIR"])))
print("event=asr_queue_index_cutover complete=" + str(result["complete"]).lower())
if not result["complete"]:
    raise SystemExit("bounded cutover paused; retry the same approved artifact to resume")
PYCODE
  "${release_root}/scripts/deploy_asr_receiver.sh" "${release_root}" "${commit}" "${digest}"
  # Purge derived caches before publishing; raw corpus objects and clip-state history are untouched.
  PYTHONPATH="${release_root}/src" "${HOME}/miniforge3/envs/dell/bin/python" - "${release_root}" "${commit}" <<'PYCODE'
import os, sys
from pathlib import Path
values = dict(line.partition("=")[::2] for line in (Path.home()/".config/talkingboats/asr.env").read_text().splitlines())
os.environ.update(values)
from talkingboats.channel_exclusion_cache import sanitize_caches
sanitize_caches(Path(values["TALKINGBOATS_PUBLIC_SITE_DIR"]), Path(values["TALKINGBOATS_ASR_OUTPUT_DIR"]).parent/"release-cache-backups"/sys.argv[2])
import subprocess
site = values["TALKINGBOATS_PUBLIC_SITE_DIR"]
snapshot = str(Path(values["TALKINGBOATS_ASR_OUTPUT_DIR"]).parent/"dev-analysis")
subprocess.run([sys.executable, str(Path(sys.argv[1])/"scripts/prepare_dev_analysis.py"), site, snapshot, "--promote-to", site], check=True)
PYCODE
  "${release_root}/scripts/deploy_static_shell.sh" prod "${release_root}/public-site"
  systemctl --user disable talkingboats-uploaded-clip-transcriber.timer
  systemctl --user enable talkingboats-uploaded-clip-transcriber.service
  systemctl --user start --no-block talkingboats-uploaded-clip-transcriber.service
  systemctl --user start talkingboats-public-clip-refresh.service
  cp "${approval_file}" "${release_root}/human-approval.json"
  TALKINGBOATS_ASR_RELEASE_COMMIT="${commit}" "${HOME}/miniforge3/envs/dell/bin/python" - <<'PYCODE'
import json
from pathlib import Path
values = dict(line.partition("=")[::2] for line in (Path.home()/".config/talkingboats/asr.env").read_text().splitlines())
path = Path(values["TALKINGBOATS_ASR_OUTPUT_DIR"])/"production-overlay.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({"commit": values["TALKINGBOATS_ASR_RELEASE_COMMIT"], "serving_model": values["TALKINGBOATS_ACTIVE_ASR_MODEL"]}))
path.chmod(0o600)
PYCODE
  TALKINGBOATS_BROWSER_DEPENDENCY_ROOT="${repo_root}" node "${release_root}/scripts/docktalk_browser_smoke.mjs"
  "${HOME}/miniforge3/envs/dell/bin/python" "${release_root}/scripts/verify_docktalk_release.py" --output "${release_root}/docktalk-soak.json"
  trap - ERR
fi
printf 'event=asr_release_deployed environment=%s commit=%s digest=%s\n' "${action}" "${commit}" "${digest}"
