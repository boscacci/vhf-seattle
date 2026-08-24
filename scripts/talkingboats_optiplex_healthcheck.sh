#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
probe_timeout_seconds="${TALKINGBOATS_OPTIPLEX_HEALTHCHECK_TIMEOUT_SECONDS:-15}"
probe_attempts="${TALKINGBOATS_OPTIPLEX_HEALTHCHECK_ATTEMPTS:-2}"
restart_wait_seconds="${TALKINGBOATS_OPTIPLEX_HEALTHCHECK_RESTART_WAIT_SECONDS:-3}"
transcriber_max_poll_age_minutes="${TALKINGBOATS_TRANSCRIBER_MAX_POLL_AGE_MINUTES:-10}"
pi_status_url="${TALKINGBOATS_OPTIPLEX_PI_STATUS_URL:-http://192.168.1.114:8050/current-status.json}"

log_event() {
  local event="$1"
  local unit="$2"
  local detail="$3"
  printf 'event=%s unit=%s detail=%s\n' "${event}" "${unit}" "${detail}"
}

unit_active_state() {
  systemctl --user show "$1" --property=ActiveState --value
}

active_lan_api_url() {
  local lan_address
  lan_address="$(/bin/bash "${repo_root}/scripts/talkingboats_lan_address.sh")" || return 1
  printf 'http://%s:8034/healthz' "${lan_address}"
}

restart_user_unit() {
  local unit="$1"
  local detail="$2"
  local state
  state="$(unit_active_state "${unit}")"
  if [[ "${state}" == "activating" || "${state}" == "deactivating" ]]; then
    log_event "talkingboats_optiplex_health_restart_deferred" "${unit}" "${state}"
    return 1
  fi
  log_event "talkingboats_optiplex_health_restart" "${unit}" "${detail}"
  systemctl --user reset-failed "${unit}" >/dev/null 2>&1 || true
  systemctl --user restart "${unit}"
  sleep "${restart_wait_seconds}"
}

ensure_user_unit() {
  local unit="$1"
  local state
  if systemctl --user is-active --quiet "${unit}"; then
    return 0
  fi
  state="$(unit_active_state "${unit}")"
  if [[ "${state}" == "activating" || "${state}" == "deactivating" ]]; then
    log_event "talkingboats_optiplex_health_restart_deferred" "${unit}" "${state}"
    return 1
  fi
  restart_user_unit "${unit}" "inactive"
  if systemctl --user is-active --quiet "${unit}"; then
    return 0
  fi
  log_event "talkingboats_optiplex_health_failed" "${unit}" "still_inactive"
  return 1
}

probe_url() {
  local url="$1"
  local attempt
  for attempt in $(seq 1 "${probe_attempts}"); do
    if curl --fail --silent --show-error --max-time "${probe_timeout_seconds}" "${url}" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

ensure_http_unit() {
  local unit="$1"
  local url="$2"
  ensure_user_unit "${unit}"
  if probe_url "${url}"; then
    return 0
  fi
  restart_user_unit "${unit}" "health_probe_failed"
  if probe_url "${url}"; then
    return 0
  fi
  log_event "talkingboats_optiplex_health_failed" "${unit}" "probe_failed_after_restart"
  return 1
}

ensure_edge_receiver_reachable() {
  if probe_url "${pi_status_url}"; then
    return 0
  fi
  log_event \
    "talkingboats_optiplex_health_failed" \
    "raspberry-pi-edge" \
    "edge_receiver_unreachable"
  return 1
}

ensure_transcriber_progress() {
  local unit="talkingboats-uploaded-clip-transcriber.service"
  local recent_log
  ensure_user_unit "${unit}" || return 1
  recent_log="$(
    journalctl --user -u "${unit}" \
      --since "${transcriber_max_poll_age_minutes} minutes ago" \
      --no-pager
  )"
  if grep -q "uploaded_clip_transcriber_poll" <<<"${recent_log}"; then
    return 0
  fi
  if grep -q "uploaded_clip_transcriber_start" <<<"${recent_log}"; then
    log_event \
      "talkingboats_optiplex_health_transcriber_startup_grace" \
      "${unit}" \
      "poll_pending_${transcriber_max_poll_age_minutes}m"
    return 0
  fi
  restart_user_unit "${unit}" "poll_stale_${transcriber_max_poll_age_minutes}m"
  log_event "talkingboats_optiplex_health_recovered" "${unit}" "restart_requested"
}

failures=0

if api_health_url="$(active_lan_api_url)"; then
  ensure_http_unit "talkingboats-api.service" "${api_health_url}" || failures=$((failures + 1))
else
  log_event "talkingboats_optiplex_health_failed" "talkingboats-api.service" "lan_address_unavailable"
  failures=$((failures + 1))
fi
ensure_http_unit "talkingboats-live-radio-proxy.service" "http://172.20.0.1:8095/healthz" || failures=$((failures + 1))
ensure_http_unit "talkingboats-public-live-radio-proxy.service" "http://127.0.0.1:8096/healthz" || failures=$((failures + 1))
ensure_edge_receiver_reachable || failures=$((failures + 1))
ensure_user_unit "vhf-dev-proxy.service" || failures=$((failures + 1))
ensure_transcriber_progress || failures=$((failures + 1))

if [[ "${failures}" -gt 0 ]]; then
  log_event "talkingboats_optiplex_health_degraded" "stack" "failures_${failures}"
  exit 1
fi
log_event "talkingboats_optiplex_health_ok" "stack" "all_checks_passed"
