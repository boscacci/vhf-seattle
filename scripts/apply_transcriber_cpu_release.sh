#!/usr/bin/env bash
set -Eeuo pipefail
root="${1:?artifact root required}"
commit="${TALKINGBOATS_RELEASE_COMMIT:?commit required}"
digest="${TALKINGBOATS_RELEASE_SHA256:?digest required}"
[[ "$commit" =~ ^[0-9a-f]{40}$ && "$digest" =~ ^[0-9a-f]{64}$ ]] || exit 2
[[ $(getconf _NPROCESSORS_ONLN) == 8 ]] || {
  echo 'This reviewed six-core policy requires the eight-core OptiPlex' >&2; exit 2;
}
unit=talkingboats-uploaded-clip-transcriber.service
source_file="$root/deploy/systemd/overrides/$unit.d/zzz-cpu-budget.conf"
[[ -f "$source_file" ]] || exit 2
base="${TALKINGBOATS_CPU_RELEASE_HOME:-${HOME}}"
record="$base/.local/share/talkingboats/releases/transcriber-cpu/$commit"
target="$base/.config/systemd/user/$unit.d/zzz-cpu-budget.conf"
if [[ -f "$record/artifact-sha256" ]]; then
  [[ $(cat "$record/artifact-sha256") == "$digest" ]] || exit 2
fi
install -d -m 0755 "$record" "$(dirname "$target")"
if [[ ! -f "$record/previous.conf" && ! -f "$record/previous-absent" ]]; then
  if [[ -f "$target" ]]; then cp -a "$target" "$record/previous.conf";
  else touch "$record/previous-absent"; fi
fi
rollback() {
  if [[ -f "$record/previous.conf" ]]; then
    install -m 0644 "$record/previous.conf" "$target"
  else rm -f "$target"; fi
  systemctl --user daemon-reload
}
trap rollback ERR
install -m 0644 "$source_file" "$target"
systemctl --user daemon-reload
# Do not interrupt an in-flight clip. Thread count changes on the next hourly batch.
printf '%s\n' "$digest" > "$record/artifact-sha256"
sha256sum "$target" > "$record/installed.sha256"
trap - ERR
printf 'event=transcriber_cpu_policy_installed commit=%s threads=6 cpu_quota_percent=600 effective=next_batch\n' "$commit"
