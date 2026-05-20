#!/usr/bin/env bash
set -euo pipefail

device="${1:-}"
user_name="${2:-rob}"
ssh_key_path="${3:-/home/rob/.ssh/id_ed25519.pub}"

if [[ -z "${device}" || "${device}" == "-h" || "${device}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  sudo scripts/repair_pi_user_sd.sh /dev/sdX [user] [ssh-public-key]

Repairs a flashed Raspberry Pi OS card where the intended user collided with
the disabled default pi UID 1000 account.
EOF
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

if [[ ! -b "${device}" ]]; then
  echo "Not a block device: ${device}" >&2
  exit 1
fi

if [[ ! -r "${ssh_key_path}" ]]; then
  echo "SSH public key not found: ${ssh_key_path}" >&2
  exit 1
fi

if lsblk -nr -o MOUNTPOINTS "${device}" | grep -q .; then
  echo "Refusing to repair mounted device. Unmount partitions first: ${device}" >&2
  lsblk "${device}" >&2
  exit 1
fi

if [[ "${device}" =~ [0-9]$ ]]; then
  root_part="${device}p2"
else
  root_part="${device}2"
fi

mount_root="$(mktemp -d)"
cleanup() {
  umount "${mount_root}" 2>/dev/null || true
  rmdir "${mount_root}" 2>/dev/null || true
}
trap cleanup EXIT

mount "${root_part}" "${mount_root}"

password_hash="$(openssl passwd -6 "$(openssl rand -base64 36)")"
ssh_public_key="$(sed -n '1p' "${ssh_key_path}")"

existing_uid_1000="$(awk -F: '$3 == 1000 { print $1; exit }' "${mount_root}/etc/passwd")"
if [[ -n "${existing_uid_1000}" && "${existing_uid_1000}" != "${user_name}" ]]; then
  sed -i "s/^${existing_uid_1000}:x:1000:1000:[^:]*:[^:]*:[^:]*/${user_name}:x:1000:1000:Rob:\/home\/${user_name}:\/bin\/bash/" \
    "${mount_root}/etc/passwd"
  sed -i "s/^${existing_uid_1000}:[^:]*/${user_name}:${password_hash}/" \
    "${mount_root}/etc/shadow"
  sed -i "s/^${existing_uid_1000}:x:1000:/${user_name}:x:1000:/" "${mount_root}/etc/group"
  sed -i "s/^${existing_uid_1000}:[^:]*/${user_name}:!/" "${mount_root}/etc/gshadow"
fi

mkdir -p "${mount_root}/home/${user_name}/.ssh"
echo "${ssh_public_key}" > "${mount_root}/home/${user_name}/.ssh/authorized_keys"
chmod 700 "${mount_root}/home/${user_name}/.ssh"
chmod 600 "${mount_root}/home/${user_name}/.ssh/authorized_keys"
chown -R 1000:1000 "${mount_root}/home/${user_name}"

mkdir -p "${mount_root}/etc/sudoers.d"
cat > "${mount_root}/etc/sudoers.d/010_${user_name}-talkingboats" <<EOF
${user_name} ALL=(ALL) NOPASSWD:ALL
EOF
chmod 440 "${mount_root}/etc/sudoers.d/010_${user_name}-talkingboats"

sync
echo "Repaired UID 1000 user on ${device}: ${existing_uid_1000:-none} -> ${user_name}"
