#!/usr/bin/env bash
set -euo pipefail

PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"
export PATH
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-${AWS_REGION}}"
export AWS_REGION AWS_DEFAULT_REGION

usage() {
  cat <<'EOF'
Usage: scripts/deploy_ais_cloud.sh [extra tofu apply args...]

Deploys the cloud AIS ingest/websocket stack without putting the raw ingest
token in OpenTofu state:

1. Reuse the existing Secrets Manager token, unless rotation is requested.
2. Otherwise generate a long random token locally.
3. Pass only its SHA-256 digest into OpenTofu.
4. Store the raw token in Secrets Manager, encrypted by the OpenTofu-managed KMS key.

Set TALKINGBOATS_ROTATE_AIS_INGEST_TOKEN=1 to force a new token.
Set TALKINGBOATS_AIS_INGEST_SECRET_NAME to read a non-default existing secret
before OpenTofu outputs are available.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null; then
    echo "Required command not found: ${command_name}" >&2
    exit 1
  fi
}

aws_cli_available() {
  command -v aws >/dev/null && aws --version >/dev/null 2>&1
}

tofu_output_raw_or_empty() {
  local output_name="$1"
  local value
  if value="$(tofu -chdir="${tofu_dir}" output -raw "${output_name}" 2>/dev/null)"; then
    printf '%s' "${value}"
  fi
}

default_secret_name() {
  printf '%s' "${TALKINGBOATS_AIS_INGEST_SECRET_NAME:-talkingboats-talkingboats-ais-ingest-token}"
}

existing_secret_token() {
  local secret_name="$1"
  if aws_cli_available; then
    aws secretsmanager get-secret-value \
      --secret-id "${secret_name}" \
      --query SecretString \
      --output text 2>/dev/null || true
    return
  fi
  "${python_bin}" - "${secret_name}" <<'PY'
import sys

import boto3
from botocore.exceptions import ClientError

secret_id = sys.argv[1]
try:
    value = boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)
except ClientError as exc:
    if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
        raise SystemExit(0)
    raise
print(value.get("SecretString", ""), end="")
PY
}

generate_token() {
  openssl rand -base64 48 | tr -d '\n'
}

sha256_hex() {
  local value="$1"
  printf '%s' "${value}" | shasum -a 256 | awk '{print $1}'
}

put_secret_value() {
  local secret_name="$1"
  local secret_string="$2"
  local secret_file
  secret_file="$(mktemp)"
  chmod 0600 "${secret_file}"
  printf '%s' "${secret_string}" > "${secret_file}"
  if aws_cli_available; then
    if ! aws secretsmanager put-secret-value \
      --secret-id "${secret_name}" \
      --secret-string "file://${secret_file}" \
      --output json >/dev/null; then
      rm -f "${secret_file}"
      return 1
    fi
  else
    if ! "${python_bin}" - "${secret_name}" "${secret_file}" <<'PY'
import pathlib
import sys

import boto3

secret_id = sys.argv[1]
secret_file = pathlib.Path(sys.argv[2])
boto3.client("secretsmanager").put_secret_value(
    SecretId=secret_id,
    SecretString=secret_file.read_text(encoding="utf-8"),
)
PY
    then
      rm -f "${secret_file}"
      return 1
    fi
  fi
  rm -f "${secret_file}"
}

require_command openssl
require_command shasum
require_command tofu

tofu_dir="${TALKINGBOATS_TOFU_DIR:-infra/opentofu}"
python_bin="${TALKINGBOATS_PYTHON:-python3}"
if ! aws_cli_available; then
  require_command "${python_bin}"
fi
rotate="${TALKINGBOATS_ROTATE_AIS_INGEST_TOKEN:-0}"
secret_name="$(tofu_output_raw_or_empty ais_ingest_secret_name)"
if [[ -z "${secret_name}" ]]; then
  secret_name="$(default_secret_name)"
fi

token=""
if [[ "${rotate}" != "1" ]]; then
  token="$(existing_secret_token "${secret_name}")"
  if [[ "${token}" == "None" ]]; then
    token=""
  fi
fi

if [[ -z "${token}" ]]; then
  token="$(generate_token)"
fi

token_sha256="$(sha256_hex "${token}")"
export TF_VAR_ais_ingest_token_sha256="${token_sha256}"

echo "Deploying AIS cloud stack with token digest only in OpenTofu state."
tofu -chdir="${tofu_dir}" init
tofu -chdir="${tofu_dir}" apply -auto-approve "$@"

deployed_secret_name="$(tofu -chdir="${tofu_dir}" output -raw ais_ingest_secret_name)"
kms_key_arn="$(tofu -chdir="${tofu_dir}" output -raw ais_ingest_secret_kms_key_arn)"
put_secret_value "${deployed_secret_name}" "${token}"

echo "Stored AIS ingest token in Secrets Manager secret: ${deployed_secret_name}"
echo "Secret is encrypted with KMS key: ${kms_key_arn}"
