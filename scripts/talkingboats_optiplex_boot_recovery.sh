#!/usr/bin/env bash
set -euo pipefail

critical_units=(
  talkingboats-api.service
  talkingboats-uploaded-clip-transcriber.service
  talkingboats-live-radio-proxy.service
  talkingboats-public-live-radio-proxy.service
  vhf-dev-proxy.service
)

critical_timers=(
  talkingboats-lexical-refresh.timer
  vhf-dev-cert-renew.timer
)

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

systemctl --user reset-failed "${critical_units[@]}" "${critical_timers[@]}" >/dev/null 2>&1 || true

exit_code=0
for unit in "${critical_units[@]}"; do
  start_user_unit "${unit}" "service" || exit_code=1
done

for timer in "${critical_timers[@]}"; do
  start_user_unit "${timer}" "timer" || exit_code=1
done

exit "${exit_code}"
