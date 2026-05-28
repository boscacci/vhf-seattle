#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_static_shell.sh dev|prod [site-source-dir]

Uploads only the checked-in static browser shell to the selected public-site
bucket and invalidates the shell paths. It does not remove remote-only files,
so generated clips, analysis artifacts, and manifests already in the bucket are
preserved.

Examples:
  scripts/deploy_static_shell.sh dev public-site
  scripts/deploy_static_shell.sh prod public-site
EOF
}

current_git_branch() {
  git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown"
}

worktree_is_dirty() {
  ! git diff --quiet 2>/dev/null ||
    ! git diff --cached --quiet 2>/dev/null ||
    [[ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ]]
}

enforce_branch_hygiene() {
  local environment="$1"
  local branch="$2"
  local prod_expected_branch="main"
  local dev_allowed_branch_regex="^(dev|main|codex/.+|feature/.+)$"

  if [[ "${TALKINGBOATS_ALLOW_CROSS_ENV_DEPLOY:-}" == "1" ]]; then
    echo "WARNING: bypassing branch/environment deploy guard." >&2
    return
  fi

  case "${environment}" in
    dev)
      if [[ ! "${branch}" =~ ${dev_allowed_branch_regex} ]]; then
        echo "Refusing dev shell deploy from branch '${branch}'." >&2
        exit 1
      fi
      ;;
    prod)
      if [[ "${branch}" != "${prod_expected_branch}" ]]; then
        echo "Refusing prod shell deploy from branch '${branch}'. Expected '${prod_expected_branch}'." >&2
        exit 1
      fi
      if worktree_is_dirty; then
        echo "Refusing prod shell deploy from dirty worktree." >&2
        exit 1
      fi
      ;;
  esac
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage >&2
  exit 2
fi

environment="$1"
site_source="${2:-public-site}"
tofu_dir="infra/opentofu"
branch="$(current_git_branch)"
invalidate_paths=( "/" "/index.html" "/assets/*" "/favicon.svg" )

if [[ ! -d "${site_source}" ]]; then
  echo "Static shell source does not exist: ${site_source}" >&2
  exit 1
fi

case "${environment}" in
  dev)
    bucket_output="dev_public_site_bucket"
    distribution_output="dev_cloudfront_distribution_id"
    fqdn_output="dev_site_fqdn"
    ;;
  prod)
    bucket_output="public_site_bucket"
    distribution_output="cloudfront_distribution_id"
    fqdn_output="site_fqdn"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

enforce_branch_hygiene "${environment}" "${branch}"

bucket="$(cd "${tofu_dir}" && tofu output -raw "${bucket_output}")"
distribution_id="$(cd "${tofu_dir}" && tofu output -raw "${distribution_output}")"
fqdn="$(cd "${tofu_dir}" && tofu output -raw "${fqdn_output}")"

echo "Deploying static shell ${site_source} from ${branch} to ${environment}: https://${fqdn}"
aws s3 sync "${site_source}" "s3://${bucket}/"
aws cloudfront create-invalidation \
  --distribution-id "${distribution_id}" \
  --paths "${invalidate_paths[@]}" \
  --output json
