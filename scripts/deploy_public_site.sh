#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_public_site.sh dev|prod [public-site-dir]

Syncs a generated static site directory to the matching private S3 origin and
invalidates that environment's CloudFront distribution.

Examples:
  scripts/deploy_public_site.sh dev outputs/public-site
  scripts/deploy_public_site.sh prod outputs/public-site
EOF
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage >&2
  exit 2
fi

environment="$1"
site_dir="${2:-outputs/public-site}"
tofu_dir="infra/opentofu"

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

bucket="$(cd "${tofu_dir}" && tofu output -raw "${bucket_output}")"
distribution_id="$(cd "${tofu_dir}" && tofu output -raw "${distribution_output}")"
fqdn="$(cd "${tofu_dir}" && tofu output -raw "${fqdn_output}")"

echo "Deploying ${site_dir} to ${environment}: https://${fqdn}"
aws s3 sync "${site_dir}" "s3://${bucket}/" --delete
aws cloudfront create-invalidation \
  --distribution-id "${distribution_id}" \
  --paths '/*' \
  --output json
