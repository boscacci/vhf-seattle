#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  sudo scripts/prepare_pi_sd.sh /dev/sdX [options]

Options:
  --hostname NAME          Hostname to set on the Pi. Default: talkingboats-pi
  --user NAME              Linux user to create. Default: rob
  --ssh-key PATH           Public SSH key to authorize. Default: /home/rob/.ssh/id_ed25519.pub
  --wifi-ssid SSID         Optional Wi-Fi SSID to configure with NetworkManager.
  --wifi-password-file P   File containing Wi-Fi password. Avoid passing secrets on the command line.
  --yes                    Skip interactive device confirmation.

This destroys the target block device.
EOF
}

device="${1:-}"
if [[ -z "${device}" || "${device}" == "-h" || "${device}" == "--help" ]]; then
  usage
  exit 0
fi
shift || true

hostname="talkingboats-pi"
user_name="rob"
ssh_key_path="/home/rob/.ssh/id_ed25519.pub"
wifi_ssid=""
wifi_password_file=""
assume_yes="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hostname)
      hostname="$2"
      shift 2
      ;;
    --user)
      user_name="$2"
      shift 2
      ;;
    --ssh-key)
      ssh_key_path="$2"
      shift 2
      ;;
    --wifi-ssid)
      wifi_ssid="$2"
      shift 2
      ;;
    --wifi-password-file)
      wifi_password_file="$2"
      shift 2
      ;;
    --yes)
      assume_yes="true"
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo; flashing and mounting block devices require root." >&2
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

if [[ -n "${wifi_ssid}" && -z "${wifi_password_file}" ]]; then
  echo "--wifi-password-file is required when --wifi-ssid is set." >&2
  exit 1
fi

if [[ -n "${wifi_password_file}" && ! -r "${wifi_password_file}" ]]; then
  echo "Wi-Fi password file not readable: ${wifi_password_file}" >&2
  exit 1
fi

root_parent="$(findmnt -n -o SOURCE / | sed 's/[0-9]*$//' | sed 's/p$//')"
if [[ "${device}" == "${root_parent}"* ]]; then
  echo "Refusing to flash root/system disk: ${device}" >&2
  exit 1
fi

if lsblk -nr -o MOUNTPOINTS "${device}" | grep -q .; then
  echo "Refusing to flash mounted device. Unmount partitions first: ${device}" >&2
  lsblk "${device}" >&2
  exit 1
fi

echo "Target device:"
lsblk -o NAME,MODEL,SIZE,TYPE,MOUNTPOINTS,RM,TRAN "${device}"

if [[ "${assume_yes}" != "true" ]]; then
  read -r -p "Type ${device} to permanently erase and flash it: " confirmation
  if [[ "${confirmation}" != "${device}" ]]; then
    echo "Confirmation did not match; aborting."
    exit 1
  fi
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image_dir="${repo_root}/outputs/pi-images"
mkdir -p "${image_dir}"

image_url="${RPI_IMAGE_URL:-https://downloads.raspberrypi.com/raspios_lite_armhf/images/raspios_lite_armhf-2026-04-21/2026-04-21-raspios-trixie-armhf-lite.img.xz}"
image_sha256="${RPI_IMAGE_SHA256:-f393b8bc3fc49aef49ddc5d5af124333002f34e4b23ede439789145e5280d210}"
image_name="$(basename "${image_url}")"
image_path="${image_dir}/${image_name}"
sha_file="${image_dir}/${image_name}.sha256"
printf '%s  %s\n' "${image_sha256}" "${image_name}" > "${sha_file}"

if [[ ! -f "${image_path}" ]]; then
  echo "Downloading ${image_name}..."
  curl -fL "${image_url}" -o "${image_path}.tmp"
  mv "${image_path}.tmp" "${image_path}"
fi

echo "Verifying image checksum..."
(
  cd "${image_dir}"
  sha256sum -c "${sha_file}"
)

echo "Writing image to ${device}..."
xzcat "${image_path}" | dd of="${device}" bs=4M conv=fsync status=progress
sync
partprobe "${device}" || true
sleep 3

if [[ "${device}" =~ [0-9]$ ]]; then
  boot_part="${device}p1"
  root_part="${device}p2"
else
  boot_part="${device}1"
  root_part="${device}2"
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

ssh_public_key="$(sed -n '1p' "${ssh_key_path}")"
random_password="$(openssl rand -base64 36)"
password_hash="$(openssl passwd -6 "${random_password}")"
unset random_password

echo "Configuring hostname, SSH, user, and project bootstrap..."
echo "${hostname}" > "${mount_root}/etc/hostname"
sed -i "s/^127\\.0\\.1\\.1.*/127.0.1.1\t${hostname}/" "${mount_root}/etc/hosts"

touch "${mount_boot}/ssh"
mkdir -p "${mount_root}/etc/ssh/sshd_config.d"
cat > "${mount_root}/etc/ssh/sshd_config.d/10-talkingboats.conf" <<'EOF'
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
EOF

existing_uid_1000="$(awk -F: '$3 == 1000 { print $1; exit }' "${mount_root}/etc/passwd")"
if [[ -n "${existing_uid_1000}" && "${existing_uid_1000}" != "${user_name}" ]]; then
  sed -i "s/^${existing_uid_1000}:x:1000:1000:[^:]*:[^:]*:[^:]*/${user_name}:x:1000:1000:Rob:\/home\/${user_name}:\/bin\/bash/" \
    "${mount_root}/etc/passwd"
  sed -i "s/^${existing_uid_1000}:[^:]*/${user_name}:${password_hash}/" \
    "${mount_root}/etc/shadow"
  if grep -q "^${existing_uid_1000}:x:1000:" "${mount_root}/etc/group"; then
    sed -i "s/^${existing_uid_1000}:x:1000:/${user_name}:x:1000:/" "${mount_root}/etc/group"
  fi
  if grep -q "^${existing_uid_1000}:" "${mount_root}/etc/gshadow"; then
    sed -i "s/^${existing_uid_1000}:[^:]*/${user_name}:!/" "${mount_root}/etc/gshadow"
  fi
elif ! grep -q "^${user_name}:" "${mount_root}/etc/passwd"; then
  echo "${user_name}:x:1000:1000:Rob:/home/${user_name}:/bin/bash" >> "${mount_root}/etc/passwd"
  echo "${user_name}:${password_hash}:19900:0:99999:7:::" >> "${mount_root}/etc/shadow"
  echo "${user_name}:x:1000:" >> "${mount_root}/etc/group"
  echo "${user_name}:!::" >> "${mount_root}/etc/gshadow"
else
  sed -i "s/^${user_name}:x:[0-9]*:[0-9]*:[^:]*:[^:]*:[^:]*/${user_name}:x:1000:1000:Rob:\/home\/${user_name}:\/bin\/bash/" \
    "${mount_root}/etc/passwd"
  sed -i "s/^${user_name}:[^:]*/${user_name}:${password_hash}/" "${mount_root}/etc/shadow"
fi

for group in adm dialout cdrom sudo audio video plugdev users input render netdev spi i2c gpio; do
  if grep -q "^${group}:" "${mount_root}/etc/group"; then
    sed -i "s/^\\(${group}:x:[0-9]*:\\)\\(.*\\)$/\\1\\2,${user_name}/; s/:,/:/" "${mount_root}/etc/group"
  fi
done

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

mkdir -p "${mount_root}/opt/talkingboats/config"
cp "${repo_root}/deploy/pi/talkingboats-capture.env.example" \
  "${mount_root}/opt/talkingboats/config/talkingboats-capture.env.example"
cp "${repo_root}/deploy/pi/talkingboats-rtl-airband.conf.example" \
  "${mount_root}/opt/talkingboats/config/talkingboats-rtl-airband.conf.example"

cat > "${mount_root}/etc/modprobe.d/talkingboats-rtlsdr-blacklist.conf" <<'EOF'
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
EOF

if [[ -n "${wifi_ssid}" ]]; then
  wifi_password="$(cat "${wifi_password_file}")"
  uuid="$(cat /proc/sys/kernel/random/uuid)"
  mkdir -p "${mount_root}/etc/NetworkManager/system-connections"
  cat > "${mount_root}/etc/NetworkManager/system-connections/${wifi_ssid}.nmconnection" <<EOF
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
  chmod 600 "${mount_root}/etc/NetworkManager/system-connections/${wifi_ssid}.nmconnection"
fi

cat > "${mount_root}/opt/talkingboats/firstboot.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
log=/var/log/talkingboats-firstboot.log
exec > >(tee -a "${log}") 2>&1

echo "Talking Boats first boot started at $(date -Is)"
apt-get update
install_packages() {
  apt-get install -y \
    ca-certificates \
    chrony \
    cmake \
    curl \
    ffmpeg \
    git \
    icecast2 \
    jq \
    libusb-1.0-0-dev \
    pkg-config \
    python3-pip \
    python3-venv \
    rtl-sdr
}

if ! install_packages; then
  echo "Initial package install failed; refreshing apt metadata and retrying."
  apt-get clean
  apt-get update
  install_packages
fi

install -d -m 0755 /opt/talkingboats/bin /opt/talkingboats/state /opt/talkingboats/logs
systemctl disable talkingboats-firstboot.service
echo "Talking Boats first boot completed at $(date -Is)"
EOF
chmod 755 "${mount_root}/opt/talkingboats/firstboot.sh"

cat > "${mount_root}/etc/systemd/system/talkingboats-firstboot.service" <<'EOF'
[Unit]
Description=Talking Boats first boot package setup
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/talkingboats/firstboot.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

mkdir -p "${mount_root}/etc/systemd/system/multi-user.target.wants"
ln -sf /etc/systemd/system/talkingboats-firstboot.service \
  "${mount_root}/etc/systemd/system/multi-user.target.wants/talkingboats-firstboot.service"

sync
echo
echo "Prepared ${device} for ${hostname}."
echo "Boot it in the Raspberry Pi, then try:"
echo "  ssh ${user_name}@${hostname}.local"
echo "or find it with:"
echo "  scripts/find_pi_on_lan.sh ${interface:-eno1}"
