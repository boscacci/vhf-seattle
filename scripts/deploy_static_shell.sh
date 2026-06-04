#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_static_shell.sh dev|prod [site-source-dir]

Uploads only the checked-in static browser shell to the selected public-site
bucket and invalidates the shell paths. It does not remove remote-only files,
so generated clips, analysis artifacts, and manifests already in the bucket are
preserved.

Dev shell deploys also sync the OptiPlex tailnet deploy copy by default, because
`vhf-dev.robertboscacci.com` is served from that tailnet host. Set
`TALKINGBOATS_SKIP_TAILNET_DEV_SYNC=1` to skip that extra sync.

Dev shell deploys also allow archive/no-git deploy copies. Prod shell deploys
still require the main branch and a clean worktree.

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

upload_shell_entrypoint() {
  local source_dir="$1"
  local target_bucket="$2"

  aws s3api put-object \
    --bucket "${target_bucket}" \
    --key "index.html" \
    --body "${source_dir}/index.html" \
    --content-type "text/html" \
    --cache-control "no-store" \
    --output json

  if [[ -f "${source_dir}/assets/app.js" ]]; then
    aws s3api put-object \
      --bucket "${target_bucket}" \
      --key "assets/app.js" \
      --body "${source_dir}/assets/app.js" \
      --content-type "text/javascript" \
      --cache-control "no-store" \
      --output json
  fi
}

delete_retired_route_indexes() {
  local target_bucket="$1"
  local retired_route_path
  for retired_route_path in "${retired_route_paths[@]}"; do
    aws s3 rm "s3://${target_bucket}/${retired_route_path}" || true
  done
}

sync_tailnet_dev_static_shell() {
  local source_dir="$1"
  local target="${TALKINGBOATS_DEV_TAILNET_SSH_TARGET:-optiplex}"
  local target_dir="${TALKINGBOATS_DEV_TAILNET_PUBLIC_SITE_DIR:-/home/rob/repos/elliott-bay-vhf-live-ais-deploy/public-site}"

  if [[ "${environment}" != "dev" || "${TALKINGBOATS_SKIP_TAILNET_DEV_SYNC:-0}" == "1" ]]; then
    return
  fi
  if ! command -v rsync >/dev/null; then
    echo "rsync is required for tailnet dev static shell sync." >&2
    exit 1
  fi
  echo "Syncing static shell to tailnet dev copy: ${target}:${target_dir}"
  rsync -az "${sync_excludes[@]}" "${source_dir}/" "${target}:${target_dir}/"
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
        echo "Allowing dev shell deploy from archive/no-git source." >&2
        return
      fi
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
tofu_dir="${TALKINGBOATS_TOFU_DIR:-infra/opentofu}"
branch="$(current_git_branch)"
route_index_paths=(
  "clips/index.html"
  "hall-of-fame/index.html"
  "search/index.html"
  "live/index.html"
  "ais/index.html"
  "map/index.html"
  "analysis/index.html"
)
route_direct_paths=(
  "clips/"
  "clips"
  "hall-of-fame/"
  "hall-of-fame"
  "search/"
  "search"
  "live/"
  "live"
  "ais/"
  "ais"
  "map/"
  "map"
  "analysis/"
  "analysis"
)
dev_only_route_index_paths=(
  "performance/index.html"
  "operator/index.html"
)
dev_only_route_direct_paths=(
  "performance/"
  "performance"
  "operator/"
  "operator"
)
retired_route_paths=(
  "fine-tuning/index.html"
  "fine-tuning/"
  "fine-tuning"
)
prod_retired_route_paths=(
  "performance/index.html"
  "performance/"
  "performance"
  "operator/index.html"
  "operator/"
  "operator"
)
route_shell_paths=( "${route_index_paths[@]}" "${route_direct_paths[@]}" )
if [[ "${environment}" == "dev" ]]; then
  route_shell_paths+=(
    "${dev_only_route_index_paths[@]}"
    "${dev_only_route_direct_paths[@]}"
  )
else
  retired_route_paths+=( "${prod_retired_route_paths[@]}" )
fi
invalidate_paths=(
  "/"
  "/index.html"
  "/assets/*"
  "/favicon.svg"
  "/clips"
  "/clips/*"
  "/hall-of-fame"
  "/hall-of-fame/*"
  "/search"
  "/search/*"
  "/live"
  "/live/*"
  "/ais"
  "/ais/*"
  "/map"
  "/map/*"
  "/analysis"
  "/analysis/"
  "/analysis/index.html"
  "/performance"
  "/performance/*"
  "/fine-tuning"
  "/fine-tuning/*"
  "/operator"
  "/operator/*"
)
sync_excludes=(
  --exclude "public_manifest.json"
  --exclude "clips/*"
  --exclude "analysis/*"
  --exclude "live/current.m3u8"
  --exclude "live/channels.json"
  --exclude "live/channels/*"
  --exclude "ais/latest.json"
)

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

bucket="$(deploy_output_raw "${bucket_output}")"
distribution_id="$(deploy_output_raw "${distribution_output}")"
fqdn="$(deploy_output_raw "${fqdn_output}")"

echo "Deploying static shell ${site_source} from ${branch} to ${environment}: https://${fqdn}"
aws s3 sync "${site_source}" "s3://${bucket}/" "${sync_excludes[@]}"
upload_shell_entrypoint "${site_source}" "${bucket}"
sync_tailnet_dev_static_shell "${site_source}"
upload_route_indexes "${site_source}" "${bucket}"
delete_retired_route_indexes "${bucket}"
aws cloudfront create-invalidation \
  --distribution-id "${distribution_id}" \
  --paths "${invalidate_paths[@]}" \
  --output json
