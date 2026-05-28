#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tofu_dir="${TALKINGBOATS_TOFU_DIR:-${repo_root}/infra/opentofu}"
aws_region="${AWS_REGION:-us-west-2}"

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to build AWS CLI payloads without exposing secrets in process arguments." >&2
  exit 1
fi

tofu_output_raw() {
  local output_name="$1"
  local value
  if ! value="$(cd "${tofu_dir}" && tofu output -raw "${output_name}" 2>&1)"; then
    echo "OpenTofu output '${output_name}' is unavailable in ${tofu_dir}." >&2
    echo "${value}" >&2
    exit 1
  fi
  printf '%s' "${value}"
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing ${name}." >&2
    echo "Create a Google OAuth web client, set ${name}, and rerun this script." >&2
    return 1
  fi
}

user_pool_id="$(tofu_output_raw dev_cognito_user_pool_id)"
mobile_client_id="$(tofu_output_raw dev_cognito_mobile_client_id)"
cognito_domain="$(tofu_output_raw dev_cognito_domain)"
google_redirect_uri="${cognito_domain}/oauth2/idpresponse"

if ! require_env TALKINGBOATS_GOOGLE_OAUTH_CLIENT_ID || ! require_env TALKINGBOATS_GOOGLE_OAUTH_CLIENT_SECRET; then
  echo "Google OAuth authorized redirect URI:" >&2
  echo "  ${google_redirect_uri}" >&2
  exit 1
fi

payload_dir="$(mktemp -d)"
trap 'rm -rf "${payload_dir}"' EXIT
create_payload="${payload_dir}/create-google-idp.json"
update_payload="${payload_dir}/update-google-idp.json"

jq -n \
  --arg user_pool_id "${user_pool_id}" \
  --arg client_id "${TALKINGBOATS_GOOGLE_OAUTH_CLIENT_ID}" \
  --arg client_secret "${TALKINGBOATS_GOOGLE_OAUTH_CLIENT_SECRET}" \
  '{
    UserPoolId: $user_pool_id,
    ProviderName: "Google",
    ProviderType: "Google",
    ProviderDetails: {
      client_id: $client_id,
      client_secret: $client_secret,
      authorize_scopes: "openid email profile"
    },
    AttributeMapping: {
      email: "email",
      username: "sub"
    }
  }' >"${create_payload}"

jq -n \
  --arg user_pool_id "${user_pool_id}" \
  --arg client_id "${TALKINGBOATS_GOOGLE_OAUTH_CLIENT_ID}" \
  --arg client_secret "${TALKINGBOATS_GOOGLE_OAUTH_CLIENT_SECRET}" \
  '{
    UserPoolId: $user_pool_id,
    ProviderName: "Google",
    ProviderDetails: {
      client_id: $client_id,
      client_secret: $client_secret,
      authorize_scopes: "openid email profile"
    },
    AttributeMapping: {
      email: "email",
      username: "sub"
    }
  }' >"${update_payload}"

if aws cognito-idp describe-identity-provider \
  --user-pool-id "${user_pool_id}" \
  --provider-name Google \
  --region "${aws_region}" >/dev/null 2>&1; then
  aws cognito-idp update-identity-provider \
    --cli-input-json "file://${update_payload}" \
    --region "${aws_region}" >/dev/null
else
  aws cognito-idp create-identity-provider \
    --cli-input-json "file://${create_payload}" \
    --region "${aws_region}" >/dev/null
fi

if [[ "${TALKINGBOATS_COGNITO_ALLOW_PASSWORD_FALLBACK:-false}" == "true" ]]; then
  aws cognito-idp update-user-pool-client \
    --user-pool-id "${user_pool_id}" \
    --client-id "${mobile_client_id}" \
    --supported-identity-providers Google COGNITO \
    --region "${aws_region}" >/dev/null
else
  aws cognito-idp update-user-pool-client \
    --user-pool-id "${user_pool_id}" \
    --client-id "${mobile_client_id}" \
    --supported-identity-providers Google \
    --region "${aws_region}" >/dev/null
fi

echo "Configured dev Cognito Google federation."
echo "Google OAuth authorized redirect URI:"
echo "  ${google_redirect_uri}"
