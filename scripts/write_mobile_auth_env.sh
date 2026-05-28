#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tofu_dir="${TALKINGBOATS_TOFU_DIR:-${repo_root}/infra/opentofu}"
env_path="${1:-${repo_root}/mobile/.env.local}"
redirect_uri="${EXPO_PUBLIC_COGNITO_REDIRECT_URI:-exp://100.125.120.39:8083/--/auth/callback}"
default_allowed_email="${EXPO_PUBLIC_COGNITO_ALLOWED_EMAIL:-cinemarob1@gmail.com}"

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

tofu_output_raw_or_default() {
  local output_name="$1"
  local default_value="$2"
  local value
  if ! value="$(cd "${tofu_dir}" && tofu output -raw "${output_name}" 2>/dev/null)"; then
    printf '%s' "${default_value}"
    return
  fi
  printf '%s' "${value}"
}

cognito_domain="$(tofu_output_raw dev_cognito_domain)"
cognito_client_id="$(tofu_output_raw dev_cognito_mobile_client_id)"
allowed_email="$(tofu_output_raw_or_default dev_cognito_allowed_email "${default_allowed_email}")"

mkdir -p "$(dirname "${env_path}")"
umask 077

cat >"${env_path}" <<EOF
EXPO_PUBLIC_COGNITO_DOMAIN=${cognito_domain}
EXPO_PUBLIC_COGNITO_CLIENT_ID=${cognito_client_id}
EXPO_PUBLIC_COGNITO_ALLOWED_EMAIL=${allowed_email}
EXPO_PUBLIC_COGNITO_REDIRECT_URI=${redirect_uri}
EOF

echo "Wrote ${env_path}"
