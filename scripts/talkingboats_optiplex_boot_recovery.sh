#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

critical_units=(
  talkingboats-api.service
  talkingboats-uploaded-clip-transcriber.service
  talkingboats-live-radio-proxy.service
  talkingboats-public-live-radio-proxy.service
  vhf-dev-proxy.service
)

critical_timers=(
  talkingboats-lexical-refresh.timer
  talkingboats-public-clip-refresh.timer
  vhf-dev-cert-renew.timer
)

search_warm_timeout_seconds="${TALKINGBOATS_SEARCH_WARM_TIMEOUT_SECONDS:-30}"

log_event() {
  local event="$1"
  local unit="$2"
  local status="$3"
  printf 'event=%s unit=%s status=%s\n' "${event}" "${unit}" "${status}"
}

start_user_unit() {
  local unit="$1"
  local kind="$2"

  if ! systemctl --user is-enabled "${unit}" >/dev/null 2>&1; then
    log_event "talkingboats_boot_recovery_${kind}_skipped" "${unit}" "not_enabled"
    return 0
  fi

  for attempt in 1 2 3; do
    if systemctl --user start "${unit}"; then
      log_event "talkingboats_boot_recovery_${kind}_started" "${unit}" "ok"
      return 0
    fi
    log_event "talkingboats_boot_recovery_${kind}_retry" "${unit}" "attempt_${attempt}"
    sleep 10
  done

  log_event "talkingboats_boot_recovery_${kind}_failed" "${unit}" "failed"
  return 1
}

warm_public_search() {
  local search_warm_url="${TALKINGBOATS_SEARCH_WARM_URL:-}"
  local lan_address
  if [[ -z "${search_warm_url}" ]]; then
    if ! lan_address="$(/bin/bash "${script_dir}/talkingboats_lan_address.sh")"; then
      log_event "talkingboats_boot_recovery_search_warm_failed" "talkingboats-api.service" "lan_address_unavailable"
      return 1
    fi
    search_warm_url="http://${lan_address}:8034/api/clips/search?q=seattle+traffic&limit=1&recency=24h"
  fi
  for attempt in 1 2 3; do
    if curl --fail --silent --show-error --max-time "${search_warm_timeout_seconds}" \
      "${search_warm_url}" >/dev/null; then
      log_event "talkingboats_boot_recovery_search_warm" "talkingboats-api.service" "ok"
      return 0
    fi
    log_event \
      "talkingboats_boot_recovery_search_warm_retry" \
      "talkingboats-api.service" \
      "attempt_${attempt}"
    sleep 5
  done
  log_event "talkingboats_boot_recovery_search_warm_failed" "talkingboats-api.service" "degraded"
  return 1
}

systemctl --user reset-failed "${critical_units[@]}" "${critical_timers[@]}" >/dev/null 2>&1 || true

exit_code=0
for unit in "${critical_units[@]}"; do
  start_user_unit "${unit}" "service" || exit_code=1
done

for timer in "${critical_timers[@]}"; do
  start_user_unit "${timer}" "timer" || exit_code=1
done

warm_public_search || true

exit "${exit_code}"
