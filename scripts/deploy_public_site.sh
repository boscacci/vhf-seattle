#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_public_site.sh dev|prod [public-site-dir]

Syncs a generated static site directory to the matching private S3 origin and
invalidates that environment's CloudFront distribution.

Branch hygiene:
  dev  deploys are allowed from dev, main, codex/*, or feature/* branches.
       Archive/no-git deploy copies are allowed for dev only.
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

tofu_output_raw() {
  local output_name="$1"
  local value
  if ! value="$(cd "${tofu_dir}" && tofu output -raw "${output_name}" 2>&1)"; then
    echo "OpenTofu output '${output_name}' is unavailable in ${tofu_dir}." >&2
    printf '%s\n' "${value}" >&2
    return 1
  fi
  if [[ -z "${value}" || "${value}" == *"No outputs found"* ]]; then
    echo "OpenTofu output '${output_name}' is unavailable in ${tofu_dir}." >&2
    if [[ -n "${value}" ]]; then
      printf '%s\n' "${value}" >&2
    fi
    return 1
  fi
  printf '%s' "${value}"
}

aws_account_id() {
  aws sts get-caller-identity --query Account --output text
}

cloudfront_distribution_for_alias() {
  local fqdn="$1"
  local distribution_id
  distribution_id="$(
    aws cloudfront list-distributions \
      --query "DistributionList.Items[?Aliases.Items && contains(Aliases.Items, '${fqdn}')].Id | [0]" \
      --output text
  )"
  if [[ -z "${distribution_id}" || "${distribution_id}" == "None" ]]; then
    echo "Could not find CloudFront distribution for alias ${fqdn}." >&2
    exit 1
  fi
  printf '%s' "${distribution_id}"
}

fallback_site_fqdn() {
  case "$1" in
    dev) printf '%s' "${TALKINGBOATS_DEV_SITE_FQDN:-vhf-dev.robertboscacci.com}" ;;
    prod) printf '%s' "${TALKINGBOATS_SITE_FQDN:-vhf.robertboscacci.com}" ;;
    *) return 1 ;;
  esac
}

fallback_output_raw() {
  local output_name="$1"
  local account_id
  case "${output_name}" in
    dev_site_fqdn)
      fallback_site_fqdn dev
      ;;
    site_fqdn)
      fallback_site_fqdn prod
      ;;
    dev_public_site_bucket)
      account_id="$(aws_account_id)"
      printf '%s' "${TALKINGBOATS_DEV_PUBLIC_SITE_BUCKET:-talkingboats-dev-talkingboats-${account_id}-public}"
      ;;
    public_site_bucket)
      account_id="$(aws_account_id)"
      printf '%s' "${TALKINGBOATS_PUBLIC_SITE_BUCKET:-talkingboats-talkingboats-${account_id}-public}"
      ;;
    dev_cloudfront_distribution_id)
      if [[ -n "${TALKINGBOATS_DEV_CLOUDFRONT_DISTRIBUTION_ID:-}" ]]; then
        printf '%s' "${TALKINGBOATS_DEV_CLOUDFRONT_DISTRIBUTION_ID}"
      else
        cloudfront_distribution_for_alias "$(fallback_site_fqdn dev)"
      fi
      ;;
    cloudfront_distribution_id)
      if [[ -n "${TALKINGBOATS_CLOUDFRONT_DISTRIBUTION_ID:-}" ]]; then
        printf '%s' "${TALKINGBOATS_CLOUDFRONT_DISTRIBUTION_ID}"
      else
        cloudfront_distribution_for_alias "$(fallback_site_fqdn prod)"
      fi
      ;;
    *)
      echo "No fallback mapping for OpenTofu output '${output_name}'." >&2
      exit 1
      ;;
  esac
}

deploy_output_raw() {
  local output_name="$1"
  local value
  if value="$(tofu_output_raw "${output_name}")"; then
    printf '%s' "${value}"
    return
  fi
  fallback_output_raw "${output_name}"
}

upload_route_indexes() {
  local source_dir="$1"
  local target_bucket="$2"
  local route_shell_path
  for route_shell_path in "${route_shell_paths[@]}"; do
    aws s3api put-object \
      --bucket "${target_bucket}" \
      --key "${route_shell_path}" \
      --body "${source_dir}/index.html" \
      --content-type "text/html" \
      --cache-control "no-store" \
      --output json
  done
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
      if [[ "${branch}" == "unknown" ]]; then
        echo "Allowing dev deploy from archive/no-git source." >&2
        return
      fi
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
tofu_dir="${TALKINGBOATS_TOFU_DIR:-infra/opentofu}"
branch="$(current_git_branch)"
route_index_paths=(
  "clips/index.html"
  "live/index.html"
  "ais/index.html"
  "analysis/index.html"
  "performance/index.html"
  "operator/index.html"
)
route_direct_paths=(
  "clips/"
  "clips"
  "live/"
  "live"
  "ais/"
  "ais"
  "analysis/"
  "analysis"
  "performance/"
  "performance"
  "operator/"
  "operator"
)
route_shell_paths=( "${route_index_paths[@]}" "${route_direct_paths[@]}" )

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

bucket="$(deploy_output_raw "${bucket_output}")"
distribution_id="$(deploy_output_raw "${distribution_output}")"
fqdn="$(deploy_output_raw "${fqdn_output}")"

echo "Deploying ${site_dir} from ${branch} to ${environment}: https://${fqdn}"
aws s3 sync "${site_dir}" "s3://${bucket}/" --delete
upload_route_indexes "${site_dir}" "${bucket}"
aws cloudfront create-invalidation \
  --distribution-id "${distribution_id}" \
  --paths '/*' \
  --output json
