#!/usr/bin/env bash
# Scoped installer: does not restart capture, NetworkManager, or the Wi-Fi connection.
set -Eeuo pipefail
[[ $(id -u) == 0 ]] || { echo 'root required' >&2; exit 2; }
release_root="${1:?release root required}"
commit="${TALKINGBOATS_RELEASE_COMMIT:?commit required}"
digest="${TALKINGBOATS_RELEASE_SHA256:?digest required}"
[[ "$commit" =~ ^[0-9a-f]{40}$ && "$digest" =~ ^[0-9a-f]{64}$ ]] || exit 2
release_dir="/opt/talkingboats/releases/pi-network/${commit}"
files=(opt/talkingboats/bin/network_recovery.py
       etc/talkingboats/network-recovery.env
       etc/systemd/system/talkingboats-network-recovery.service
       etc/systemd/system/talkingboats-network-recovery.timer
       etc/systemd/journald.conf.d/90-talkingboats-persistent.conf)
rollback() {
  systemctl disable --now talkingboats-network-recovery.timer || true
  systemctl stop talkingboats-network-recovery.service || true
  for file in "${files[@]}"; do rm -f "/${file}"; done
  tar -xpf "${release_dir}/previous.tar" -C /
  systemctl daemon-reload
  systemctl restart systemd-journald
  if [[ $(cat "${release_dir}/timer-enabled") == enabled ]]; then
    systemctl enable talkingboats-network-recovery.timer
  fi
  if [[ $(cat "${release_dir}/timer-active") == active ]]; then
    systemctl start talkingboats-network-recovery.timer
  fi
  rm -f "${release_dir}/installed"
}
if [[ "${2:-}" == rollback ]]; then
  [[ -f "${release_dir}/previous.tar" ]] || exit 2
  rollback
  exit
fi
if [[ -f "${release_dir}/installed" ]]; then
  [[ $(cat "${release_dir}/artifact-sha256") == "$digest" ]]
  sha256sum --check --status "${release_dir}/installed.sha256"
  systemctl is-active --quiet talkingboats-network-recovery.timer
  exit
fi
command -v nmcli >/dev/null
command -v ping >/dev/null
systemctl is-active --quiet NetworkManager
connection="$(nmcli -g GENERAL.CON-UUID device show wlan0)"
[[ "$connection" =~ ^[0-9a-f-]{36}$ ]] || { echo 'no active Wi-Fi profile' >&2; exit 2; }
python3 "${release_root}/deploy/pi/network_recovery.py" --connection "$connection" --probe-only
install -d -m 0700 "$release_dir"
if [[ ! -f "${release_dir}/previous.tar" ]]; then
  existing=()
  for file in "${files[@]}"; do [[ ! -f "/${file}" ]] || existing+=("$file"); done
  tar -cpf "${release_dir}/previous.tar" -C / --files-from /dev/null "${existing[@]}"
  (systemctl is-enabled talkingboats-network-recovery.timer || true) > "${release_dir}/timer-enabled"
  (systemctl is-active talkingboats-network-recovery.timer || true) > "${release_dir}/timer-active"
fi
trap rollback ERR
install -d /opt/talkingboats/bin /etc/talkingboats /etc/systemd/journald.conf.d
install -m 0755 "${release_root}/deploy/pi/network_recovery.py" /opt/talkingboats/bin/network_recovery.py
for unit in service timer; do
  install -m 0644 "${release_root}/deploy/systemd/talkingboats-network-recovery.${unit}.example" \
    "/etc/systemd/system/talkingboats-network-recovery.${unit}"
done
(umask 077; printf 'PI_WIFI_CONNECTION=%s\n' "$connection" > /etc/talkingboats/network-recovery.env)
install -m 0644 "${release_root}/deploy/pi/journald-persistent.conf" \
  /etc/systemd/journald.conf.d/90-talkingboats-persistent.conf
systemd-analyze verify /etc/systemd/system/talkingboats-network-recovery.{service,timer}
mkdir -p /var/log/journal
systemd-tmpfiles --create --prefix /var/log/journal
systemctl restart systemd-journald
journalctl --flush
systemctl daemon-reload
systemctl enable --now talkingboats-network-recovery.timer
systemctl start talkingboats-network-recovery.service
systemctl is-active --quiet talkingboats-network-recovery.timer
find /var/log/journal -name '*.journal' -print -quit | grep -q .
install -m 0700 "$0" "${release_dir}/apply.sh"
printf '%s\n' "$digest" > "${release_dir}/artifact-sha256"
sha256sum "${files[@]/#//}" > "${release_dir}/installed.sha256"
touch "${release_dir}/installed"
trap - ERR
printf 'event=pi_network_release_installed commit=%s artifact_sha256=%s\n' "$commit" "$digest"
