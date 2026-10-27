#!/usr/bin/env bash
# Promote only the project-budget exporter and its dev-tested public snapshot.
set -Eeuo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
action="${1:-}"
if [[ "${action}" != dev && "${action}" != prod ]]; then
  echo 'Usage: release_operations_snapshot.sh dev|prod [annotated-tag approval.json]' >&2
  exit 2
fi
[[ -z "$(git -C "${root}" status --porcelain)" ]] || { echo 'Clean checkout required.' >&2; exit 2; }
commit="$(git -C "${root}" rev-parse HEAD)"
if [[ "${action}" == prod ]]; then
  tag="${2:?production requires a release tag}"
  approval="${3:?production requires the single recorded human approval}"
  [[ "${tag}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 2
  [[ "$(git -C "${root}" cat-file -t "refs/tags/${tag}")" == tag ]] || exit 2
  commit="$(git -C "${root}" rev-parse "${tag}^{commit}")"
fi
git -C "${root}" merge-base --is-ancestor "${commit}" origin/main
[[ "$(aws sts get-caller-identity --query Account --output text)" == 062008221187 ]] || exit 2
python_bin="${HOME}/miniforge3/envs/dell/bin/python"
candidate="${HOME}/.local/share/talkingboats/release-candidates/operations/${commit}"
install -d -m 0700 "${candidate}"
artifact="${candidate}/release.tar.gz"
if [[ "${action}" == dev && ! -f "${artifact}" ]]; then
  pending="$(mktemp "${candidate}/release.pending.XXXXXX")"
  trap 'rm -f "${pending}"' EXIT
  git -C "${root}" archive --format=tar "${commit}" | gzip -n > "${pending}"
  mv "${pending}" "${artifact}"
  sha256sum "${artifact}" | awk '{print $1}' > "${candidate}/artifact.sha256"
fi
digest="$(cat "${candidate}/artifact.sha256")"
[[ "$(sha256sum "${artifact}" | awk '{print $1}')" == "${digest}" ]] || exit 2
release="${HOME}/.local/share/talkingboats/releases/operations/${action}/${commit}"
install -d -m 0700 "${release}"
if [[ ! -f "${release}/release-commit" ]]; then
  tar -xzf "${artifact}" -C "${release}"
  printf '%s\n' "${commit}" > "${release}/release-commit"
  printf '%s\n' "${digest}" > "${release}/artifact.sha256"
fi
[[ "$(cat "${release}/artifact.sha256")" == "${digest}" ]] || exit 2
runtime="${HOME}/repos/elliott-bay-vhf/.runtime/live-ais-deploy"
site="${runtime}/outputs/public-site"
dropin="${HOME}/.config/systemd/user/talkingboats-live-radio-proxy.service.d/zzzzz-project-budget.conf"

if [[ "${action}" == dev ]]; then
  exec 9>"${runtime}/outputs/.public-export.lock"
  flock -w 30 9
  # Hard links keep the existing public clips available without copying media.
  # The atomic snapshot writer replaces only the candidate operations.json link.
  install -d -m 0755 "${release}/generated-site"
  if [[ ! -f "${release}/generated-site/public_manifest.json" ]]; then
    cp -al "${site}/." "${release}/generated-site/"
  fi
  "${python_bin}" "${release}/src/talkingboats/aws_operations_snapshot.py" \
    --manifest "${site}/public_manifest.json" --cache "${release}/operations-cache.json" \
    --output "${release}/generated-site/operations.json"
  flock -u 9
  [[ ! -f "${dropin}" ]] || cp -a "${dropin}" "${release}/previous-dropin.conf"
  rollback_dev() {
    if [[ -f "${release}/previous-dropin.conf" ]]; then
      install -m 0644 "${release}/previous-dropin.conf" "${dropin}"
    else
      rm -f "${dropin}"
    fi
    systemctl --user daemon-reload
    systemctl --user restart talkingboats-live-radio-proxy.service || true
  }
  trap rollback_dev ERR
  install -d -m 0755 "$(dirname "${dropin}")"
  printf '[Service]\nEnvironment=TALKINGBOATS_PROXY_PUBLIC_SITE_DIR=%s/generated-site\n' \
    "${release}" > "${dropin}.pending"
  mv "${dropin}.pending" "${dropin}"
  systemctl --user daemon-reload
  systemctl --user restart talkingboats-live-radio-proxy.service
  curl --fail --silent --show-error --retry 10 --retry-delay 1 --retry-connrefused \
    --retry-max-time 30 --max-time 10 http://172.20.0.1:8095/operations.json >/dev/null
  TALKINGBOATS_BROWSER_DEPENDENCY_ROOT="${root}" TALKINGBOATS_BUDGET_SMOKE_OUTPUT_DIR="${release}/smoke-failures" \
    node "${release}/scripts/budget_browser_smoke.mjs" \
    > "${release}/browser-smoke.json"
  snapshot_sha="$(sha256sum "${release}/generated-site/operations.json" | awk '{print $1}')"
  printf '{"commit":"%s","artifact_sha256":"%s","snapshot_sha256":"%s","dev_playwright_passed":true,"tested_at":"%s"}\n' \
    "${commit}" "${digest}" "${snapshot_sha}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${candidate}/dev-smoke.json"
  trap - ERR
else
  "${python_bin}" "${release}/scripts/verify_asr_approval.py" \
    "${approval}" "${tag}" "${commit}" "${digest}" "${candidate}/dev-smoke.json"
  dev_release="${HOME}/.local/share/talkingboats/releases/operations/dev/${commit}"
  snapshot="${dev_release}/generated-site/operations.json"
  snapshot_sha="$(sha256sum "${snapshot}" | awk '{print $1}')"
  [[ "${snapshot_sha}" == "$("${python_bin}" -c 'import json,sys; print(json.load(open(sys.argv[1]))["snapshot_sha256"])' "${candidate}/dev-smoke.json")" ]] || exit 2
  "${python_bin}" - "${snapshot}" <<'PY'
import json, sys
from datetime import UTC, datetime
payload = json.load(open(sys.argv[1]))
assert payload['budget']['scope'] == 'project'
assert payload['budget']['month'] == datetime.now(UTC).date().replace(day=1).isoformat()
PY
  exec 9>"${runtime}/outputs/.public-export.lock"
  flock -w 30 9
  install -d -m 0700 "${release}/previous"
  module="src/talkingboats/aws_operations_snapshot.py"
  cache="${runtime}/outputs/public-operations-cache.json"
  bucket="$(tofu -chdir="${root}/infra/opentofu" output -raw public_site_bucket)"
  distribution="$(tofu -chdir="${root}/infra/opentofu" output -raw cloudfront_distribution_id)"
  if [[ ! -f "${release}/previous/exporter.py" ]]; then
    cp -a "${runtime}/${module}" "${release}/previous/exporter.py"
    cp -a "${site}/operations.json" "${release}/previous/operations.json"
    [[ ! -f "${cache}" ]] || cp -a "${cache}" "${release}/previous/cache.json"
    aws s3 cp "s3://${bucket}/operations.json" "${release}/previous/s3-operations.json" --only-show-errors
  fi
  rollback_prod() {
    install -m 0644 "${release}/previous/exporter.py" "${runtime}/${module}"
    install -m 0644 "${release}/previous/operations.json" "${site}/operations.json"
    if [[ -f "${release}/previous/cache.json" ]]; then
      install -m 0644 "${release}/previous/cache.json" "${cache}"
    else
      rm -f "${cache}"
    fi
    aws s3 cp "${release}/previous/s3-operations.json" "s3://${bucket}/operations.json" \
      --content-type application/json --cache-control no-store --only-show-errors || true
    aws cloudfront create-invalidation --distribution-id "${distribution}" \
      --paths /operations.json --query Invalidation.Id --output text || true
  }
  trap rollback_prod ERR
  install -m 0644 "${release}/${module}" "${runtime}/${module}.pending"
  mv "${runtime}/${module}.pending" "${runtime}/${module}"
  for target in "${site}/operations.json" "${cache}"; do
    install -m 0644 "${snapshot}" "${target}.pending"
    mv "${target}.pending" "${target}"
  done
  aws s3 cp "${snapshot}" "s3://${bucket}/operations.json" \
    --content-type application/json --cache-control no-store --only-show-errors
  aws cloudfront create-invalidation --distribution-id "${distribution}" \
    --invalidation-batch "{\"Paths\":{\"Quantity\":1,\"Items\":[\"/operations.json\"]},\"CallerReference\":\"project-budget-${snapshot_sha}\"}" \
    --query Invalidation.Id --output text
  TALKINGBOATS_BROWSER_DEPENDENCY_ROOT="${root}" TALKINGBOATS_BUDGET_SMOKE_OUTPUT_DIR="${release}/smoke-failures" \
    TALKINGBOATS_BUDGET_SMOKE_BASE_URL=https://seattleboatradio.com \
    node "${release}/scripts/budget_browser_smoke.mjs" > "${release}/browser-smoke.json"
  trap - ERR
  install -m 0600 "${approval}" "${release}/production-approval.json"
  if [[ -f "${dropin}" ]] && grep -Fxq \
    "Environment=TALKINGBOATS_PROXY_PUBLIC_SITE_DIR=${dev_release}/generated-site" "${dropin}"; then
    rm -f "${dropin}"
  fi
  systemctl --user daemon-reload
  systemctl --user restart talkingboats-live-radio-proxy.service
fi
printf 'event=project_budget_ui_deployed environment=%s commit=%s artifact_sha256=%s\n' \
  "${action}" "${commit}" "${digest}"
