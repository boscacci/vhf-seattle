#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  sudo deploy/pi/install_live_radio.sh

Installs a LAN-only Talking Boats live radio smoke app on a Raspberry Pi.

Optional environment overrides before running:
  TALKINGBOATS_LIVE_FREQUENCY_HZ=156425000
  TALKINGBOATS_LIVE_LABEL="VHF 68"
  TALKINGBOATS_LIVE_GAIN=28
  TALKINGBOATS_LIVE_SQUELCH=0
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo; installing systemd units and Icecast config requires root." >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="/etc/talkingboats/live-radio.env"
app_root="/opt/talkingboats/app"
spool_root="/opt/talkingboats/spool/clips"
record_root="/opt/talkingboats/spool/continuous"
airband_spool_root="/opt/talkingboats/spool/airband"
service_user="${TALKINGBOATS_SERVICE_USER:-rob}"

install -d -m 0755 \
  /opt/talkingboats/bin \
  "${app_root}/src" \
  "${spool_root}" \
  "${record_root}" \
  "${airband_spool_root}/13" \
  "${airband_spool_root}/14" \
  /etc/talkingboats \
  /etc/systemd/system

rm -rf "${app_root}/src/talkingboats"
cp -a "${repo_root}/src/talkingboats" "${app_root}/src/talkingboats"
install -m 0755 \
  "${repo_root}/deploy/pi/live-radio/talkingboats-live-radio-stream" \
  /opt/talkingboats/bin/talkingboats-live-radio-stream
install -m 0755 \
  "${repo_root}/deploy/pi/live-radio/talkingboats-edge-live-radio-stream" \
  /opt/talkingboats/bin/talkingboats-edge-live-radio-stream
install -m 0755 \
  "${repo_root}/deploy/pi/live-radio/talkingboats-profile-capture" \
  /opt/talkingboats/bin/talkingboats-profile-capture
install -m 0644 \
  "${repo_root}/deploy/systemd/talkingboats-live-radio-stream.service.example" \
  /etc/systemd/system/talkingboats-live-radio-stream.service
install -m 0644 \
  "${repo_root}/deploy/systemd/talkingboats-edge-live-radio-stream.service.example" \
  /etc/systemd/system/talkingboats-edge-live-radio-stream.service
install -m 0644 \
  "${repo_root}/deploy/systemd/talkingboats-profile-capture.service.example" \
  /etc/systemd/system/talkingboats-profile-capture.service
install -m 0644 \
  "${repo_root}/deploy/systemd/talkingboats-spool-uploader.service.example" \
  /etc/systemd/system/talkingboats-spool-uploader.service
generate_password() {
  openssl rand -base64 36 | tr -d '\n' | tr '+/' '-_'
}

if [[ ! -f "${env_file}" ]]; then
  umask 077
  {
    printf 'TALKINGBOATS_LIVE_DEVICE=%q\n' "0"
    printf 'TALKINGBOATS_LIVE_CHANNEL=%q\n' "68"
    printf 'TALKINGBOATS_LIVE_FREQUENCY_HZ=%q\n' "${TALKINGBOATS_LIVE_FREQUENCY_HZ:-156425000}"
    printf 'TALKINGBOATS_LIVE_LABEL=%q\n' "${TALKINGBOATS_LIVE_LABEL:-VHF 68}"
    printf 'TALKINGBOATS_LIVE_GAIN=%q\n' "${TALKINGBOATS_LIVE_GAIN:-28}"
    printf 'TALKINGBOATS_LIVE_SQUELCH=%q\n' "${TALKINGBOATS_LIVE_SQUELCH:-20}"
    printf 'TALKINGBOATS_LIVE_SAMPLE_RATE=%q\n' "24000"
    printf 'TALKINGBOATS_LIVE_BITRATE=%q\n' "64k"
    printf 'TALKINGBOATS_AUDIO_FILTER_ENABLED=%q\n' "false"
    printf 'TALKINGBOATS_AUDIO_FILTER=%q\n' \
      "highpass=f=250,lowpass=f=3200,afftdn=nf=-28,dynaudnorm=f=150:g=12"
    printf 'TALKINGBOATS_ICECAST_HOST=%q\n' "127.0.0.1"
    printf 'TALKINGBOATS_ICECAST_PORT=%q\n' "8000"
    printf 'TALKINGBOATS_ICECAST_MOUNT=%q\n' "/talkingboats-live.mp3"
    printf 'TALKINGBOATS_ICECAST_NETRC=%q\n' "/etc/talkingboats/icecast.netrc"
    printf 'TALKINGBOATS_EDGE_SPOOL_DIR=%q\n' "${spool_root}"
    printf 'TALKINGBOATS_EDGE_RECORD_ENABLED=%q\n' "true"
    printf 'TALKINGBOATS_EDGE_RECORD_DIR=%q\n' "${record_root}"
    printf 'TALKINGBOATS_EDGE_RECORD_SEGMENT_SECONDS=%q\n' "300"
    printf 'TALKINGBOATS_EDGE_RECORD_RETENTION_SECONDS=%q\n' "86400"
    printf 'TALKINGBOATS_EDGE_RECORD_UPLOAD_ENABLED=%q\n' "false"
    printf 'TALKINGBOATS_EDGE_RECORD_UPLOAD_QUEUE_SIZE=%q\n' "4"
    printf 'TALKINGBOATS_EDGE_UPLOAD_ENABLED=%q\n' "false"
    printf 'TALKINGBOATS_EDGE_UPLOAD_ENCODE_MP3=%q\n' "true"
    printf 'TALKINGBOATS_EDGE_UPLOAD_DELETE_AFTER_UPLOAD=%q\n' "false"
    printf 'TALKINGBOATS_EDGE_THRESHOLD_RMS=%q\n' "8000"
    printf 'TALKINGBOATS_EDGE_MAX_TEMP_C=%q\n' "72"
    printf 'TALKINGBOATS_EDGE_RESUME_TEMP_C=%q\n' "66"
    printf 'TALKINGBOATS_EDGE_MAX_LOAD_PER_CPU=%q\n' "0.85"
    printf 'TALKINGBOATS_CAPTURE_PROFILE=%q\n' "debug"
    printf 'TALKINGBOATS_CAPTURE_DEBUG_WX_SECONDS=%q\n' "120"
    printf 'TALKINGBOATS_CAPTURE_DEBUG_14_SECONDS=%q\n' "480"
    printf 'TALKINGBOATS_CAPTURE_DEBUG_WX_THRESHOLD_RMS=%q\n' "2200"
    printf 'TALKINGBOATS_CAPTURE_SLOT_COOLDOWN_SECONDS=%q\n' "5"
    printf 'TALKINGBOATS_AIRBAND_BINARY=%q\n' "/usr/local/bin/rtl_airband"
    printf 'TALKINGBOATS_AIRBAND_CONFIG_DIR=%q\n' "/etc/talkingboats"
    printf 'TALKINGBOATS_MULTICHANNEL_SPOOL_DIR=%q\n' "${airband_spool_root}"
    printf 'TALKINGBOATS_ICECAST_SOURCE_PASSWORD=%q\n' "$(generate_password)"
    printf 'TALKINGBOATS_ICECAST_RELAY_PASSWORD=%q\n' "$(generate_password)"
    printf 'TALKINGBOATS_ICECAST_ADMIN_PASSWORD=%q\n' "$(generate_password)"
  } > "${env_file}"
fi

append_env_if_missing() {
  local key="$1"
  local value="$2"
  if ! grep -q "^${key}=" "${env_file}"; then
    printf '%s=%q\n' "${key}" "${value}" >> "${env_file}"
  fi
}

append_env_if_missing TALKINGBOATS_LIVE_CHANNEL "68"
append_env_if_missing TALKINGBOATS_AUDIO_FILTER_ENABLED "false"
append_env_if_missing TALKINGBOATS_AUDIO_FILTER \
  "highpass=f=250,lowpass=f=3200,afftdn=nf=-28,dynaudnorm=f=150:g=12"
append_env_if_missing TALKINGBOATS_EDGE_SPOOL_DIR "${spool_root}"
append_env_if_missing TALKINGBOATS_EDGE_RECORD_ENABLED "true"
append_env_if_missing TALKINGBOATS_EDGE_RECORD_DIR "${record_root}"
append_env_if_missing TALKINGBOATS_EDGE_RECORD_SEGMENT_SECONDS "300"
append_env_if_missing TALKINGBOATS_EDGE_RECORD_RETENTION_SECONDS "86400"
append_env_if_missing TALKINGBOATS_EDGE_RECORD_UPLOAD_ENABLED "false"
append_env_if_missing TALKINGBOATS_EDGE_RECORD_UPLOAD_QUEUE_SIZE "4"
append_env_if_missing TALKINGBOATS_EDGE_UPLOAD_ENABLED "false"
append_env_if_missing TALKINGBOATS_EDGE_UPLOAD_ENCODE_MP3 "true"
append_env_if_missing TALKINGBOATS_EDGE_UPLOAD_DELETE_AFTER_UPLOAD "false"
append_env_if_missing TALKINGBOATS_EDGE_THRESHOLD_RMS "8000"
append_env_if_missing TALKINGBOATS_EDGE_MAX_TEMP_C "72"
append_env_if_missing TALKINGBOATS_EDGE_RESUME_TEMP_C "66"
append_env_if_missing TALKINGBOATS_EDGE_MAX_LOAD_PER_CPU "0.85"
append_env_if_missing TALKINGBOATS_CAPTURE_PROFILE "debug"
append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_WX_SECONDS "120"
append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_14_SECONDS "480"
append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_WX_THRESHOLD_RMS "2200"
append_env_if_missing TALKINGBOATS_CAPTURE_SLOT_COOLDOWN_SECONDS "5"
append_env_if_missing TALKINGBOATS_AIRBAND_BINARY "/usr/local/bin/rtl_airband"
append_env_if_missing TALKINGBOATS_AIRBAND_CONFIG_DIR "/etc/talkingboats"
append_env_if_missing TALKINGBOATS_MULTICHANNEL_SPOOL_DIR "${airband_spool_root}"
append_env_if_missing TALKINGBOATS_ICECAST_NETRC "/etc/talkingboats/icecast.netrc"
append_env_if_missing TALKINGBOATS_ICECAST_SOURCE_PASSWORD "$(generate_password)"
append_env_if_missing TALKINGBOATS_ICECAST_RELAY_PASSWORD "$(generate_password)"
append_env_if_missing TALKINGBOATS_ICECAST_ADMIN_PASSWORD "$(generate_password)"
chmod 0600 "${env_file}"

set -a
# shellcheck source=/dev/null
. "${env_file}"
set +a

: "${TALKINGBOATS_ICECAST_SOURCE_PASSWORD:?missing source password}"
: "${TALKINGBOATS_ICECAST_RELAY_PASSWORD:?missing relay password}"
: "${TALKINGBOATS_ICECAST_ADMIN_PASSWORD:?missing admin password}"

icecast_netrc="${TALKINGBOATS_ICECAST_NETRC:-/etc/talkingboats/icecast.netrc}"
umask 077
cat > "${icecast_netrc}" <<EOF
machine ${TALKINGBOATS_ICECAST_HOST:-127.0.0.1} login source password ${TALKINGBOATS_ICECAST_SOURCE_PASSWORD}
EOF
if getent group audio >/dev/null; then
  chgrp audio "${icecast_netrc}"
  chmod 0640 "${icecast_netrc}"
else
  chmod 0600 "${icecast_netrc}"
fi

if id "${service_user}" >/dev/null 2>&1; then
  chown -R "${service_user}:audio" /opt/talkingboats/spool
  chmod 0775 /opt/talkingboats/spool "${spool_root}" "${record_root}" "${airband_spool_root}"
fi

PYTHONPATH="${app_root}/src" python3 -m talkingboats.capture_profiles \
  --profile elliott_bay \
  --output-root "${airband_spool_root}" \
  > /etc/talkingboats/rtl_airband-elliott-bay.conf
chmod 0644 /etc/talkingboats/rtl_airband-elliott-bay.conf

if [[ -f /etc/icecast2/icecast.xml && ! -f /etc/icecast2/icecast.xml.talkingboats.bak ]]; then
  cp -a /etc/icecast2/icecast.xml /etc/icecast2/icecast.xml.talkingboats.bak
fi

cat > /etc/icecast2/icecast.xml <<EOF
<icecast>
  <location>LAN</location>
  <admin>rob@localhost</admin>
  <limits>
    <clients>12</clients>
    <sources>2</sources>
    <queue-size>524288</queue-size>
    <client-timeout>30</client-timeout>
    <header-timeout>15</header-timeout>
    <source-timeout>10</source-timeout>
    <burst-on-connect>1</burst-on-connect>
    <burst-size>65535</burst-size>
  </limits>
  <authentication>
    <source-password>${TALKINGBOATS_ICECAST_SOURCE_PASSWORD}</source-password>
    <relay-password>${TALKINGBOATS_ICECAST_RELAY_PASSWORD}</relay-password>
    <admin-user>admin</admin-user>
    <admin-password>${TALKINGBOATS_ICECAST_ADMIN_PASSWORD}</admin-password>
  </authentication>
  <hostname>talkingboats-pi.local</hostname>
  <listen-socket>
    <port>${TALKINGBOATS_ICECAST_PORT:-8000}</port>
  </listen-socket>
  <http-headers>
    <header name="Access-Control-Allow-Origin" value="*" />
  </http-headers>
  <mount type="normal">
    <mount-name>${TALKINGBOATS_ICECAST_MOUNT:-/talkingboats-live.mp3}</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <fileserve>1</fileserve>
  <paths>
    <basedir>/usr/share/icecast2</basedir>
    <logdir>/var/log/icecast2</logdir>
    <webroot>/usr/share/icecast2/web</webroot>
    <adminroot>/usr/share/icecast2/admin</adminroot>
    <alias source="/" destination="/status.xsl"/>
  </paths>
  <logging>
    <accesslog>access.log</accesslog>
    <errorlog>error.log</errorlog>
    <loglevel>3</loglevel>
    <logsize>10000</logsize>
  </logging>
  <security>
    <chroot>0</chroot>
  </security>
</icecast>
EOF

if getent group icecast >/dev/null; then
  chgrp icecast /etc/icecast2/icecast.xml
  chmod 0640 /etc/icecast2/icecast.xml
else
  chmod 0644 /etc/icecast2/icecast.xml
fi

if [[ -f /etc/default/icecast2 ]]; then
  if grep -q '^ENABLE=' /etc/default/icecast2; then
    sed -i 's/^ENABLE=.*/ENABLE=true/' /etc/default/icecast2
  else
    printf '\nENABLE=true\n' >> /etc/default/icecast2
  fi
fi

systemctl daemon-reload
systemctl enable icecast2.service
systemctl restart icecast2.service
systemctl disable --now talkingboats-live-radio-stream.service 2>/dev/null || true
systemctl disable --now talkingboats-edge-live-radio-stream.service 2>/dev/null || true
systemctl enable --now talkingboats-spool-uploader.service
systemctl enable --now talkingboats-profile-capture.service

echo "Talking Boats capture profile installed."
echo "The single browser UI is served by the OptiPlex/public-site clip app."
