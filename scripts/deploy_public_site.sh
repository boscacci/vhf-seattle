#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_public_site.sh dev|prod [public-site-dir]

Syncs a generated static site directory to the matching private S3 origin and
invalidates that environment's CloudFront distribution.

Branch hygiene:
  dev  deploys are allowed from dev, main, codex/*, or feature/* branches.
  prod deploys are allowed only from main and require a clean worktree.

Set TALKINGBOATS_ALLOW_CROSS_ENV_DEPLOY=1 only for an intentional emergency
override, and record the reason in the deployment notes.

Examples:
  scripts/deploy_public_site.sh dev outputs/public-site
  scripts/deploy_public_site.sh prod outputs/public-site
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
        echo "Refusing dev deploy from branch '${branch}'." >&2
        echo "Use dev, main, codex/*, or feature/*, or set TALKINGBOATS_ALLOW_CROSS_ENV_DEPLOY=1." >&2
        exit 1
      fi
      ;;
    prod)
      if [[ "${branch}" != "${prod_expected_branch}" ]]; then
        echo "Refusing prod deploy from branch '${branch}'. Expected '${prod_expected_branch}'." >&2
        echo "Merge and smoke dev first, then deploy prod from main." >&2
        exit 1
      fi
      if worktree_is_dirty; then
        echo "Refusing prod deploy from dirty worktree." >&2
        echo "Commit or stash changes, or set TALKINGBOATS_ALLOW_CROSS_ENV_DEPLOY=1 for an emergency." >&2
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
site_dir="${2:-outputs/public-site}"
tofu_dir="infra/opentofu"
branch="$(current_git_branch)"

if [[ ! -d "${site_dir}" ]]; then
  echo "Static site directory does not exist: ${site_dir}" >&2
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

echo "Deploying ${site_dir} from ${branch} to ${environment}: https://${fqdn}"
aws s3 sync "${site_dir}" "s3://${bucket}/" --delete
aws cloudfront create-invalidation \
  --distribution-id "${distribution_id}" \
  --paths '/*' \
  --output json
