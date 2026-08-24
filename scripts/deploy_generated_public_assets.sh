#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_generated_public_assets.sh dev|prod [public-site-dir]

Promotes generated public artifacts to the matching private S3 origin and
invalidates the CloudFront paths that read those artifacts.

Examples:
  scripts/deploy_generated_public_assets.sh dev outputs/public-site
  scripts/deploy_generated_public_assets.sh prod outputs/public-site
EOF
}

tofu_output_raw() {
  local output_name="$1"
  local value
  if ! value="$(cd "${tofu_dir}" && tofu output -raw "${output_name}" 2>&1)"; then
    if [[ "${TALKINGBOATS_TOFU_OUTPUT_QUIET:-0}" != "1" ]]; then
      echo "OpenTofu output '${output_name}' is unavailable in ${tofu_dir}." >&2
      printf '%s\n' "${value}" >&2
    fi
    return 1
  fi
  if [[ -z "${value}" || "${value}" == *"No outputs found"* ]]; then
    if [[ "${TALKINGBOATS_TOFU_OUTPUT_QUIET:-0}" != "1" ]]; then
      echo "OpenTofu output '${output_name}' is unavailable in ${tofu_dir}." >&2
      if [[ -n "${value}" ]]; then
        printf '%s\n' "${value}" >&2
      fi
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
    dev) printf '%s' "${TALKINGBOATS_DEV_SITE_FQDN:-dev.seattleboatradio.com}" ;;
    prod) printf '%s' "${TALKINGBOATS_SITE_FQDN:-seattleboatradio.com}" ;;
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

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage >&2
  exit 2
fi

environment="$1"
site_dir="${2:-outputs/public-site}"
tofu_dir="${TALKINGBOATS_TOFU_DIR:-infra/opentofu}"

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

if [[ ! -f "${site_dir}/public_manifest.json" ]]; then
  echo "Generated manifest is missing: ${site_dir}/public_manifest.json" >&2
  exit 1
fi
if [[ ! -f "${site_dir}/recent_clips.json" ]]; then
  echo "Generated recent clip snapshot is missing: ${site_dir}/recent_clips.json" >&2
  exit 1
fi
if [[ ! -d "${site_dir}/clips" ]]; then
  echo "Generated clips directory is missing: ${site_dir}/clips" >&2
  exit 1
fi
if [[ ! -d "${site_dir}/analysis" ]]; then
  echo "Generated analysis directory is missing: ${site_dir}/analysis" >&2
  exit 1
fi

bucket="$(deploy_output_raw "${bucket_output}")"
distribution_id="$(deploy_output_raw "${distribution_output}")"
fqdn="$(deploy_output_raw "${fqdn_output}")"

echo "Deploying generated public artifacts from ${site_dir} to ${environment}: https://${fqdn}"
aws s3 cp "${site_dir}/public_manifest.json" "s3://${bucket}/public_manifest.json" \
  --content-type "application/json" \
  --cache-control "no-store"
aws s3 cp "${site_dir}/recent_clips.json" "s3://${bucket}/recent_clips.json" \
  --content-type "application/json" \
  --cache-control "no-store"
aws s3 sync "${site_dir}/clips" "s3://${bucket}/clips/" \
  --delete \
  --exclude "*" \
  --include "*.mp3"
aws s3 sync "${site_dir}/analysis" "s3://${bucket}/analysis/" \
  --delete \
  --exclude "*" \
  --include "lexical.json" \
  --include "search_index.json" \
  --include "topic_clusters.html"
aws cloudfront create-invalidation \
  --distribution-id "${distribution_id}" \
  --paths "/public_manifest.json" "/recent_clips.json" "/clips/*" "/analysis/*" \
  --output json
