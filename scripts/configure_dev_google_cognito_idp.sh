#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tofu_dir="${TALKINGBOATS_TOFU_DIR:-${repo_root}/infra/opentofu}"
aws_region="${AWS_REGION:-us-west-2}"
google_oauth_secret_id="${TALKINGBOATS_GOOGLE_OAUTH_SECRET_ID:-talkingboats/dev/google-oauth-client}"

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

user_pool_id="$(tofu_output_raw dev_cognito_user_pool_id)"
mobile_client_id="$(tofu_output_raw dev_cognito_mobile_client_id)"
cognito_domain="$(tofu_output_raw dev_cognito_domain)"
google_redirect_uri="${cognito_domain}/oauth2/idpresponse"

google_oauth_client_id="${TALKINGBOATS_GOOGLE_OAUTH_CLIENT_ID:-}"
google_oauth_client_secret="${TALKINGBOATS_GOOGLE_OAUTH_CLIENT_SECRET:-}"

if [[ -z "${google_oauth_client_id}" || -z "${google_oauth_client_secret}" ]]; then
  secret_json="$(
    aws secretsmanager get-secret-value \
      --secret-id "${google_oauth_secret_id}" \
      --region "${aws_region}" \
      --query SecretString \
      --output text 2>/dev/null || true
  )"
  if [[ -n "${secret_json}" ]]; then
    google_oauth_client_id="${google_oauth_client_id:-$(jq -r '.client_id // empty' <<<"${secret_json}")}"
    google_oauth_client_secret="${google_oauth_client_secret:-$(jq -r '.client_secret // empty' <<<"${secret_json}")}"
  fi
  unset secret_json
fi

if [[ -z "${google_oauth_client_id}" || -z "${google_oauth_client_secret}" ]]; then
  echo "Missing Google OAuth client credentials." >&2
  echo "Set TALKINGBOATS_GOOGLE_OAUTH_CLIENT_ID and TALKINGBOATS_GOOGLE_OAUTH_CLIENT_SECRET," >&2
  echo "or store JSON with client_id/client_secret in AWS Secrets Manager secret:" >&2
  echo "  ${google_oauth_secret_id}" >&2
  echo "Google OAuth authorized redirect URI:" >&2
  echo "  ${google_redirect_uri}" >&2
  exit 1
fi

payload_dir="$(mktemp -d)"
trap 'rm -rf "${payload_dir}"' EXIT
create_payload="${payload_dir}/create-google-idp.json"
update_payload="${payload_dir}/update-google-idp.json"
client_description="${payload_dir}/describe-user-pool-client.json"
client_update_payload="${payload_dir}/update-user-pool-client.json"

jq -n \
  --arg user_pool_id "${user_pool_id}" \
  --arg client_id "${google_oauth_client_id}" \
  --arg client_secret "${google_oauth_client_secret}" \
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
  --arg client_id "${google_oauth_client_id}" \
  --arg client_secret "${google_oauth_client_secret}" \
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
  providers_json='["Google","COGNITO"]'
else
  providers_json='["Google"]'
fi

aws cognito-idp describe-user-pool-client \
  --user-pool-id "${user_pool_id}" \
  --client-id "${mobile_client_id}" \
  --region "${aws_region}" >"${client_description}"

jq \
  --arg user_pool_id "${user_pool_id}" \
  --arg client_id "${mobile_client_id}" \
  --argjson providers "${providers_json}" \
  '{
    UserPoolId: $user_pool_id,
    ClientId: $client_id,
    ClientName: .UserPoolClient.ClientName,
    RefreshTokenValidity: .UserPoolClient.RefreshTokenValidity,
    AccessTokenValidity: .UserPoolClient.AccessTokenValidity,
    IdTokenValidity: .UserPoolClient.IdTokenValidity,
    TokenValidityUnits: .UserPoolClient.TokenValidityUnits,
    ReadAttributes: .UserPoolClient.ReadAttributes,
    WriteAttributes: .UserPoolClient.WriteAttributes,
    ExplicitAuthFlows: .UserPoolClient.ExplicitAuthFlows,
    SupportedIdentityProviders: $providers,
    CallbackURLs: .UserPoolClient.CallbackURLs,
    LogoutURLs: .UserPoolClient.LogoutURLs,
    DefaultRedirectURI: .UserPoolClient.DefaultRedirectURI,
    AllowedOAuthFlows: .UserPoolClient.AllowedOAuthFlows,
    AllowedOAuthScopes: .UserPoolClient.AllowedOAuthScopes,
    AllowedOAuthFlowsUserPoolClient: .UserPoolClient.AllowedOAuthFlowsUserPoolClient,
    AnalyticsConfiguration: .UserPoolClient.AnalyticsConfiguration,
    PreventUserExistenceErrors: .UserPoolClient.PreventUserExistenceErrors,
    EnableTokenRevocation: .UserPoolClient.EnableTokenRevocation,
    EnablePropagateAdditionalUserContextData: .UserPoolClient.EnablePropagateAdditionalUserContextData,
    AuthSessionValidity: .UserPoolClient.AuthSessionValidity
  }
  | with_entries(select(.value != null))
  | if (.TokenValidityUnits? == {}) then del(.TokenValidityUnits) else . end' \
  "${client_description}" >"${client_update_payload}"

aws cognito-idp update-user-pool-client \
  --cli-input-json "file://${client_update_payload}" \
  --region "${aws_region}" >/dev/null

echo "Configured dev Cognito Google federation."
echo "Google OAuth authorized redirect URI:"
echo "  ${google_redirect_uri}"
