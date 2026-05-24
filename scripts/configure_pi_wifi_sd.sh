#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  sudo scripts/configure_pi_wifi_sd.sh /dev/sdX --wifi-ssid SSID [--country US]

Writes a NetworkManager Wi-Fi profile to an offline Raspberry Pi SD card. The
Wi-Fi password is read from a hidden prompt so it is not stored in shell history.
EOF
}

device="${1:-}"
if [[ -z "${device}" || "${device}" == "-h" || "${device}" == "--help" ]]; then
  usage
  exit 0
fi
shift

wifi_ssid=""
country="US"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wifi-ssid)
      wifi_ssid="$2"
      shift 2
      ;;
    --country)
      country="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo; mounting and editing the Pi SD card requires root." >&2
  exit 1
fi

if [[ -z "${wifi_ssid}" ]]; then
  echo "--wifi-ssid is required." >&2
  exit 2
fi

if [[ ! "${country}" =~ ^[A-Z]{2}$ ]]; then
  echo "--country must be a two-letter uppercase country code, for example US." >&2
  exit 2
fi

if [[ ! -b "${device}" ]]; then
  echo "Not a block device: ${device}" >&2
  exit 1
fi

if [[ "${device}" =~ [0-9]$ ]]; then
  boot_part="${device}p1"
  root_part="${device}p2"
else
  boot_part="${device}1"
  root_part="${device}2"
fi

if [[ ! -b "${boot_part}" || ! -b "${root_part}" ]]; then
  echo "Expected Pi partitions not found: ${boot_part}, ${root_part}" >&2
  exit 1
fi

root_parent="$(findmnt -n -o SOURCE / | sed 's/[0-9]*$//' | sed 's/p$//')"
if [[ "${device}" == "${root_parent}"* ]]; then
  echo "Refusing to edit root/system disk: ${device}" >&2
  exit 1
fi

if lsblk -nr -o MOUNTPOINTS "${device}" | grep -q .; then
  echo "Refusing to continue while target partitions are already mounted:" >&2
  lsblk -o NAME,MODEL,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINTS "${device}" >&2
  exit 1
fi

read -rsp "Wi-Fi password for ${wifi_ssid}: " wifi_password
printf '\n'
if [[ -z "${wifi_password}" ]]; then
  echo "Wi-Fi password cannot be empty." >&2
  exit 1
fi

mount_root="$(mktemp -d)"
mount_boot="$(mktemp -d)"
cleanup() {
  umount "${mount_boot}" 2>/dev/null || true
  umount "${mount_root}" 2>/dev/null || true
  rmdir "${mount_boot}" "${mount_root}" 2>/dev/null || true
}
trap cleanup EXIT

mount "${root_part}" "${mount_root}"
mount "${boot_part}" "${mount_boot}"

if [[ ! -f "${mount_root}/etc/os-release" ]]; then
  echo "Mounted root partition does not look like a Linux rootfs." >&2
  exit 1
fi

uuid="$(cat /proc/sys/kernel/random/uuid)"
nm_dir="${mount_root}/etc/NetworkManager/system-connections"
install -d -m 0700 "${nm_dir}"
profile="${nm_dir}/${wifi_ssid}.nmconnection"

cat > "${profile}" <<EOF
[connection]
id=${wifi_ssid}
uuid=${uuid}
type=wifi
interface-name=wlan0
autoconnect=true

[wifi]
mode=infrastructure
ssid=${wifi_ssid}

[wifi-security]
key-mgmt=wpa-psk
psk=${wifi_password}

[ipv4]
method=auto

[ipv6]
addr-gen-mode=default
method=auto
EOF
chmod 0600 "${profile}"
chown 0:0 "${profile}"
unset wifi_password

install -d -m 0755 "${mount_root}/etc/NetworkManager/conf.d"
cat > "${mount_root}/etc/NetworkManager/conf.d/90-talkingboats-wifi-country.conf" <<EOF
[device]
wifi.scan-rand-mac-address=no

[connection]
wifi.cloned-mac-address=preserve
EOF
chmod 0644 "${mount_root}/etc/NetworkManager/conf.d/90-talkingboats-wifi-country.conf"

install -d -m 0755 "${mount_root}/etc/default"
if [[ -f "${mount_root}/etc/default/crda" ]]; then
  if grep -q '^REGDOMAIN=' "${mount_root}/etc/default/crda"; then
    sed -i "s/^REGDOMAIN=.*/REGDOMAIN=${country}/" "${mount_root}/etc/default/crda"
  else
    printf 'REGDOMAIN=%s\n' "${country}" >> "${mount_root}/etc/default/crda"
  fi
else
  printf 'REGDOMAIN=%s\n' "${country}" > "${mount_root}/etc/default/crda"
fi
chmod 0644 "${mount_root}/etc/default/crda"

install -d -m 0755 "${mount_root}/etc/modprobe.d"
cat > "${mount_root}/etc/modprobe.d/talkingboats-cfg80211.conf" <<EOF
options cfg80211 ieee80211_regdom=${country}
EOF
chmod 0644 "${mount_root}/etc/modprobe.d/talkingboats-cfg80211.conf"

install -d -m 0755 "${mount_boot}"
cat > "${mount_boot}/firstrun_wifi_country" <<EOF
${country}
EOF
chmod 0644 "${mount_boot}/firstrun_wifi_country"

sync

echo "Configured Wi-Fi profile '${wifi_ssid}' and regulatory country '${country}' on ${device}."
echo "Profile path: /etc/NetworkManager/system-connections/${wifi_ssid}.nmconnection"
