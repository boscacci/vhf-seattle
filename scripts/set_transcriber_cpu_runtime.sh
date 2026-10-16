#!/usr/bin/env bash
# Reversible operating limit, ordered after the installed release overrides.
set -Eeuo pipefail
action="${1:?usage: set_transcriber_cpu_runtime.sh gentle|release-default}"
[[ "$action" == gentle || "$action" == release-default ]] || exit 2
runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
[[ "$runtime" == /* && -d "$runtime" && $(stat -c '%u' "$runtime") == "$(id -u)" ]] || exit 2
unit=talkingboats-uploaded-clip-transcriber.service
directory="$runtime/systemd/user/$unit.d"
target="$directory/zzzzzz-gentle-cpu.conf"
expected=$'[Service]\nCPUQuota=300%\nCPUWeight=10'
# Never replace a different operator's override, including a symlink.
[[ ! -L "$target" ]] || exit 2
if [[ -e "$target" ]]; then
  [[ $(cat "$target") == "$expected" ]] || exit 2
fi
install -d -m 0700 "$directory"
prior=absent
[[ ! -f "$target" ]] || prior=gentle
pending="$(mktemp "$directory/.gentle-pending.XXXXXX")"
cleanup() { rm -f "$pending"; }
trap cleanup EXIT
rollback() {
  if [[ "$prior" == gentle ]]; then
    printf '%s\n' "$expected" > "$target"
  else rm -f "$target"; fi
  systemctl --user daemon-reload || true
}
trap rollback ERR
if [[ "$action" == gentle ]]; then
  printf '%s\n' "$expected" > "$pending"
  chmod 0644 "$pending"
  mv "$pending" "$target"
else
  rm -f "$target"
fi
systemctl --user daemon-reload
trap - ERR
printf 'event=transcriber_cpu_runtime_policy policy=%s worker_restart=false\n' "$action"
