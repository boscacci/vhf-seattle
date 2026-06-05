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
  "${airband_spool_root}/05A" \
  "${airband_spool_root}/06" \
  "${airband_spool_root}/09" \
  "${airband_spool_root}/10" \
  "${airband_spool_root}/13" \
  "${airband_spool_root}/14" \
  "${airband_spool_root}/16" \
  "${airband_spool_root}/22A" \
  "${airband_spool_root}/65A" \
  "${airband_spool_root}/66A" \
  "${airband_spool_root}/67" \
  "${airband_spool_root}/68" \
  "${airband_spool_root}/69" \
  "${airband_spool_root}/71" \
  "${airband_spool_root}/72" \
  "${airband_spool_root}/73" \
  "${airband_spool_root}/74" \
  "${airband_spool_root}/77" \
  "${airband_spool_root}/78A" \
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
install -m 0755 \
  "${repo_root}/deploy/pi/live-radio/talkingboats-ais-catcher" \
  /opt/talkingboats/bin/talkingboats-ais-catcher
install -m 0755 \
  "${repo_root}/deploy/pi/live-radio/talkingboats-live-hls-relay" \
  /opt/talkingboats/bin/talkingboats-live-hls-relay
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
install -m 0644 \
  "${repo_root}/deploy/systemd/talkingboats-ais-catcher.service.example" \
  /etc/systemd/system/talkingboats-ais-catcher.service
install -m 0644 \
  "${repo_root}/deploy/systemd/talkingboats-ais-forwarder.service.example" \
  /etc/systemd/system/talkingboats-ais-forwarder.service
install -m 0644 \
  "${repo_root}/deploy/systemd/talkingboats-live-hls-relay.service.example" \
  /etc/systemd/system/talkingboats-live-hls-relay.service
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
    printf 'TALKINGBOATS_AUDIO_FILTER_ENABLED=%q\n' "true"
    printf 'TALKINGBOATS_AUDIO_FILTER=%q\n' \
      "highpass=f=250,lowpass=f=3200,afftdn=nf=-28"
    printf 'TALKINGBOATS_LIVE_AUDIO_SQUELCH_ENABLED=%q\n' "true"
    printf 'TALKINGBOATS_LIVE_SQUELCH_LOOKAHEAD_SECONDS=%q\n' "1.0"
    printf 'TALKINGBOATS_LIVE_OUTPUT_FILTER=%q\n' "alimiter=limit=0.55"
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
    printf 'TALKINGBOATS_EDGE_UPLOAD_AUDIO_FILTER=%q\n' \
      "highpass=f=250,lowpass=f=3200,afftdn=nf=-28,acompressor=threshold=0.06:ratio=3:attack=8:release=180:makeup=4,loudnorm=I=-16:LRA=8:TP=-6"
    printf 'TALKINGBOATS_EDGE_UPLOAD_DELETE_AFTER_UPLOAD=%q\n' "false"
    printf 'TALKINGBOATS_EDGE_THRESHOLD_RMS=%q\n' "8000"
    printf 'TALKINGBOATS_EDGE_MIN_CLIP_SECONDS=%q\n' "1.0"
    printf 'TALKINGBOATS_EDGE_PRE_ROLL_SECONDS=%q\n' "0"
    printf 'TALKINGBOATS_EDGE_POST_ROLL_SECONDS=%q\n' "0.3"
    printf 'TALKINGBOATS_EDGE_MAX_TEMP_C=%q\n' "72"
    printf 'TALKINGBOATS_EDGE_RESUME_TEMP_C=%q\n' "66"
    printf 'TALKINGBOATS_EDGE_MAX_LOAD_PER_CPU=%q\n' "0.85"
    printf 'TALKINGBOATS_CLOUD_HLS_ENABLED=%q\n' "false"
    printf 'TALKINGBOATS_PUBLIC_SITE_BUCKET=%q\n' ""
    printf 'TALKINGBOATS_CLOUD_HLS_DIR=%q\n' "/opt/talkingboats/hls"
    printf 'TALKINGBOATS_CLOUD_HLS_S3_PREFIX=%q\n' "live"
    printf 'TALKINGBOATS_CLOUD_HLS_SEGMENT_SECONDS=%q\n' "2"
    printf 'TALKINGBOATS_CLOUD_HLS_LIST_SIZE=%q\n' "6"
    printf 'TALKINGBOATS_CLOUD_HLS_PUBLISH_INTERVAL_SECONDS=%q\n' "1"
    printf 'TALKINGBOATS_CLOUD_HLS_DEFAULT_CHANNEL=%q\n' "14"
    printf 'TALKINGBOATS_CLOUD_HLS_CHANNELS=%q\n' \
      "05A,06,09,10,13,14,16,22A,65A,66A,67,68,69,71,72,73,74,77,78A"
    printf 'TALKINGBOATS_CAPTURE_PROFILE=%q\n' "debug"
    printf 'TALKINGBOATS_CAPTURE_DEBUG_14_SECONDS=%q\n' "180"
    printf 'TALKINGBOATS_CAPTURE_DEBUG_14_THRESHOLD_RMS=%q\n' "5000"
    printf 'TALKINGBOATS_CAPTURE_DEBUG_14_MIN_CLIP_SECONDS=%q\n' "2.0"
    printf 'TALKINGBOATS_CAPTURE_DEBUG_14_POST_ROLL_SECONDS=%q\n' "0.4"
    printf 'TALKINGBOATS_CAPTURE_DEBUG_14_MAX_CLIP_SECONDS=%q\n' "30"
    printf 'TALKINGBOATS_CAPTURE_SLOT_COOLDOWN_SECONDS=%q\n' "5"
    printf 'TALKINGBOATS_AIRBAND_BINARY=%q\n' "/usr/local/bin/rtl_airband"
    printf 'TALKINGBOATS_AIRBAND_CONFIG_DIR=%q\n' "/etc/talkingboats"
    printf 'TALKINGBOATS_MULTICHANNEL_SPOOL_DIR=%q\n' "${airband_spool_root}"
    printf 'TALKINGBOATS_VOICE_DEVICE_INDEX=%q\n' "0"
    printf 'TALKINGBOATS_VOICE_SDR_SERIAL=%q\n' ""
    printf 'TALKINGBOATS_VOICE_SQUELCH_THRESHOLD=%q\n' "-35"
    printf 'TALKINGBOATS_VOICE_SQUELCH_SNR_THRESHOLD=%q\n' "20"
    printf 'TALKINGBOATS_AIS_SDR_SERIAL=%q\n' ""
    printf 'TALKINGBOATS_AIS_DEVICE_INDEX=%q\n' "1"
    printf 'TALKINGBOATS_AIS_WEB_PORT=%q\n' "8100"
    printf 'TALKINGBOATS_AIS_COMMUNITY_FEED=%q\n' "anonymous"
    printf 'TALKINGBOATS_AIS_SHARING_KEY=%q\n' ""
    printf 'TALKINGBOATS_AIS_STATION_NAME=%q\n' "Elliott Bay VHF"
    printf 'TALKINGBOATS_AIS_STATION_LINK=%q\n' "https://robertboscacci.com"
    printf 'TALKINGBOATS_AIS_LAT=%q\n' "47.6190158"
    printf 'TALKINGBOATS_AIS_LON=%q\n' "-122.3595353"
    printf 'TALKINGBOATS_AIS_SHARE_LOC=%q\n' "on"
    printf 'TALKINGBOATS_AIS_FRIENDS_HOST=%q\n' "ais.aisfriends.com"
    printf 'TALKINGBOATS_AIS_FRIENDS_UDP_PORT=%q\n' ""
    printf 'TALKINGBOATS_AIS_HTTP_INGEST_URL=%q\n' ""
    printf 'TALKINGBOATS_AIS_INGEST_TOKEN=%q\n' ""
    printf 'TALKINGBOATS_AIS_FORWARDER_HOST=%q\n' "127.0.0.1"
    printf 'TALKINGBOATS_AIS_FORWARDER_PORT=%q\n' "8110"
    printf 'TALKINGBOATS_AIS_HTTP_INTERVAL_SECONDS=%q\n' "1"
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

replace_env_if_value() {
  local key="$1"
  local old_value="$2"
  local new_value="$3"
  local quoted_new_value
  printf -v quoted_new_value '%q' "${new_value}"
  if grep -qx "${key}=${old_value}" "${env_file}"; then
    sed -i "s|^${key}=.*|${key}=${quoted_new_value}|" "${env_file}"
  fi
}

sed -i '/^TALKINGBOATS_CAPTURE_DEBUG_[W]X_/d' "${env_file}"

append_env_if_missing TALKINGBOATS_LIVE_CHANNEL "68"
append_env_if_missing TALKINGBOATS_AUDIO_FILTER_ENABLED "true"
append_env_if_missing TALKINGBOATS_AUDIO_FILTER \
  "highpass=f=250,lowpass=f=3200,afftdn=nf=-28"
append_env_if_missing TALKINGBOATS_LIVE_AUDIO_SQUELCH_ENABLED "true"
append_env_if_missing TALKINGBOATS_LIVE_SQUELCH_LOOKAHEAD_SECONDS "1.0"
append_env_if_missing TALKINGBOATS_LIVE_OUTPUT_FILTER "alimiter=limit=0.55"
append_env_if_missing TALKINGBOATS_EDGE_SPOOL_DIR "${spool_root}"
append_env_if_missing TALKINGBOATS_EDGE_RECORD_ENABLED "true"
append_env_if_missing TALKINGBOATS_EDGE_RECORD_DIR "${record_root}"
append_env_if_missing TALKINGBOATS_EDGE_RECORD_SEGMENT_SECONDS "300"
append_env_if_missing TALKINGBOATS_EDGE_RECORD_RETENTION_SECONDS "86400"
append_env_if_missing TALKINGBOATS_EDGE_RECORD_UPLOAD_ENABLED "false"
append_env_if_missing TALKINGBOATS_EDGE_RECORD_UPLOAD_QUEUE_SIZE "4"
append_env_if_missing TALKINGBOATS_EDGE_UPLOAD_ENABLED "false"
append_env_if_missing TALKINGBOATS_EDGE_UPLOAD_ENCODE_MP3 "true"
append_env_if_missing TALKINGBOATS_EDGE_UPLOAD_AUDIO_FILTER \
  "highpass=f=250,lowpass=f=3200,afftdn=nf=-28,acompressor=threshold=0.06:ratio=3:attack=8:release=180:makeup=4,loudnorm=I=-16:LRA=8:TP=-6"
append_env_if_missing TALKINGBOATS_EDGE_UPLOAD_DELETE_AFTER_UPLOAD "false"
append_env_if_missing TALKINGBOATS_CLOUD_HLS_ENABLED "false"
append_env_if_missing TALKINGBOATS_PUBLIC_SITE_BUCKET ""
append_env_if_missing TALKINGBOATS_CLOUD_HLS_DIR "/opt/talkingboats/hls"
append_env_if_missing TALKINGBOATS_CLOUD_HLS_S3_PREFIX "live"
append_env_if_missing TALKINGBOATS_CLOUD_HLS_SEGMENT_SECONDS "2"
append_env_if_missing TALKINGBOATS_CLOUD_HLS_LIST_SIZE "6"
append_env_if_missing TALKINGBOATS_CLOUD_HLS_PUBLISH_INTERVAL_SECONDS "1"
append_env_if_missing TALKINGBOATS_CLOUD_HLS_DEFAULT_CHANNEL "14"
append_env_if_missing TALKINGBOATS_CLOUD_HLS_CHANNELS \
  "05A,06,09,10,13,14,16,22A,65A,66A,67,68,69,71,72,73,74,77,78A"
append_env_if_missing TALKINGBOATS_EDGE_THRESHOLD_RMS "8000"
append_env_if_missing TALKINGBOATS_EDGE_MIN_CLIP_SECONDS "1.0"
append_env_if_missing TALKINGBOATS_EDGE_PRE_ROLL_SECONDS "0"
append_env_if_missing TALKINGBOATS_EDGE_POST_ROLL_SECONDS "0.3"
append_env_if_missing TALKINGBOATS_EDGE_MAX_TEMP_C "72"
append_env_if_missing TALKINGBOATS_EDGE_RESUME_TEMP_C "66"
append_env_if_missing TALKINGBOATS_EDGE_MAX_LOAD_PER_CPU "0.85"
append_env_if_missing TALKINGBOATS_CAPTURE_PROFILE "debug"
append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_14_SECONDS "180"
append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_14_THRESHOLD_RMS "5000"
append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_14_MIN_CLIP_SECONDS "2.0"
append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_14_POST_ROLL_SECONDS "0.4"
append_env_if_missing TALKINGBOATS_CAPTURE_DEBUG_14_MAX_CLIP_SECONDS "30"
append_env_if_missing TALKINGBOATS_CAPTURE_SLOT_COOLDOWN_SECONDS "5"
append_env_if_missing TALKINGBOATS_AIRBAND_BINARY "/usr/local/bin/rtl_airband"
append_env_if_missing TALKINGBOATS_AIRBAND_CONFIG_DIR "/etc/talkingboats"
append_env_if_missing TALKINGBOATS_MULTICHANNEL_SPOOL_DIR "${airband_spool_root}"
append_env_if_missing TALKINGBOATS_VOICE_DEVICE_INDEX "0"
append_env_if_missing TALKINGBOATS_VOICE_SDR_SERIAL ""
append_env_if_missing TALKINGBOATS_VOICE_SQUELCH_THRESHOLD "-35"
append_env_if_missing TALKINGBOATS_VOICE_SQUELCH_SNR_THRESHOLD "20"
append_env_if_missing TALKINGBOATS_AIS_SDR_SERIAL ""
append_env_if_missing TALKINGBOATS_AIS_DEVICE_INDEX "1"
append_env_if_missing TALKINGBOATS_AIS_WEB_PORT "8100"
append_env_if_missing TALKINGBOATS_AIS_COMMUNITY_FEED "anonymous"
append_env_if_missing TALKINGBOATS_AIS_SHARING_KEY ""
append_env_if_missing TALKINGBOATS_AIS_STATION_NAME "Elliott Bay VHF"
append_env_if_missing TALKINGBOATS_AIS_STATION_LINK "https://robertboscacci.com"
append_env_if_missing TALKINGBOATS_AIS_LAT "47.6190158"
append_env_if_missing TALKINGBOATS_AIS_LON "-122.3595353"
append_env_if_missing TALKINGBOATS_AIS_SHARE_LOC "on"
append_env_if_missing TALKINGBOATS_AIS_FRIENDS_HOST "ais.aisfriends.com"
append_env_if_missing TALKINGBOATS_AIS_FRIENDS_UDP_PORT ""
append_env_if_missing TALKINGBOATS_AIS_HTTP_INGEST_URL ""
append_env_if_missing TALKINGBOATS_AIS_INGEST_TOKEN ""
append_env_if_missing TALKINGBOATS_AIS_FORWARDER_HOST "127.0.0.1"
append_env_if_missing TALKINGBOATS_AIS_FORWARDER_PORT "8110"
append_env_if_missing TALKINGBOATS_AIS_HTTP_INTERVAL_SECONDS "1"
append_env_if_missing TALKINGBOATS_ICECAST_NETRC "/etc/talkingboats/icecast.netrc"
append_env_if_missing TALKINGBOATS_ICECAST_SOURCE_PASSWORD "$(generate_password)"
append_env_if_missing TALKINGBOATS_ICECAST_RELAY_PASSWORD "$(generate_password)"
append_env_if_missing TALKINGBOATS_ICECAST_ADMIN_PASSWORD "$(generate_password)"
replace_env_if_value TALKINGBOATS_EDGE_MIN_CLIP_SECONDS "0.7" "1.0"
replace_env_if_value TALKINGBOATS_AIS_LAT "47.6062" "47.6190158"
replace_env_if_value TALKINGBOATS_AIS_LON "-122.347" "-122.3595353"
replace_env_if_value TALKINGBOATS_EDGE_PRE_ROLL_SECONDS "0.7" "0"
replace_env_if_value TALKINGBOATS_EDGE_POST_ROLL_SECONDS "1.2" "0.3"
replace_env_if_value TALKINGBOATS_CAPTURE_DEBUG_14_THRESHOLD_RMS "3600" "5000"
replace_env_if_value TALKINGBOATS_CAPTURE_DEBUG_14_MIN_CLIP_SECONDS "1.2" "2.0"
replace_env_if_value TALKINGBOATS_CAPTURE_DEBUG_14_POST_ROLL_SECONDS "2.5" "0.4"
replace_env_if_value TALKINGBOATS_CAPTURE_DEBUG_14_MAX_CLIP_SECONDS "45" "30"
replace_env_if_value TALKINGBOATS_AIS_STATION_NAME "Elliott Bay VHF" "Elliott Bay VHF"
chmod 0600 "${env_file}"

set -a
# shellcheck source=/dev/null
. "${env_file}"
set +a

: "${TALKINGBOATS_ICECAST_SOURCE_PASSWORD:?missing source password}"
: "${TALKINGBOATS_ICECAST_RELAY_PASSWORD:?missing relay password}"
: "${TALKINGBOATS_ICECAST_ADMIN_PASSWORD:?missing admin password}"

if [[ -x "${TALKINGBOATS_AIRBAND_BINARY:-/usr/local/bin/rtl_airband}" ]]; then
  replace_env_if_value TALKINGBOATS_CAPTURE_PROFILE "debug" "voice_net_balanced"
  replace_env_if_value TALKINGBOATS_CAPTURE_PROFILE "elliott_bay" "voice_net_balanced"
fi

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

squelch_args=()
if [[ -n "${TALKINGBOATS_VOICE_SQUELCH_THRESHOLD:-}" ]]; then
  squelch_args+=(--squelch-threshold "${TALKINGBOATS_VOICE_SQUELCH_THRESHOLD}")
fi
if [[ -n "${TALKINGBOATS_VOICE_SQUELCH_SNR_THRESHOLD:-}" ]]; then
  squelch_args+=(--squelch-snr-threshold "${TALKINGBOATS_VOICE_SQUELCH_SNR_THRESHOLD}")
fi

PYTHONPATH="${app_root}/src" python3 -m talkingboats.capture_profiles \
  --profile voice_net_balanced \
  --output-root "${airband_spool_root}" \
  --device-index "${TALKINGBOATS_VOICE_DEVICE_INDEX:-0}" \
  --device-serial "${TALKINGBOATS_VOICE_SDR_SERIAL:-}" \
  "${squelch_args[@]}" \
  --icecast-host "${TALKINGBOATS_ICECAST_HOST:-127.0.0.1}" \
  --icecast-port "${TALKINGBOATS_ICECAST_PORT:-8000}" \
  --icecast-output "05A:/talkingboats-05a.mp3:Talking Boats VTS / Port Ops" \
  --icecast-output "06:/talkingboats-06.mp3:Talking Boats Intership Safety" \
  --icecast-output "09:/talkingboats-09.mp3:Talking Boats Calling / Commercial" \
  --icecast-output "10:/talkingboats-10.mp3:Talking Boats Commercial" \
  --icecast-output "13:/talkingboats-13.mp3:Talking Boats Bridge-to-bridge" \
  --icecast-output "14:${TALKINGBOATS_ICECAST_MOUNT:-/talkingboats-live.mp3}:Talking Boats VTS / Seattle Traffic" \
  --icecast-output "16:/talkingboats-16.mp3:Talking Boats Distress / Calling" \
  --icecast-output "22A:/talkingboats-22a.mp3:Talking Boats USCG Liaison" \
  --icecast-output "65A:/talkingboats-65a.mp3:Talking Boats Port Operations" \
  --icecast-output "66A:/talkingboats-66a.mp3:Talking Boats Port Operations" \
  --icecast-output "67:/talkingboats-67.mp3:Talking Boats Commercial / Bridge" \
  --icecast-output "68:/talkingboats-68.mp3:Talking Boats Recreational" \
  --icecast-output "69:/talkingboats-69.mp3:Talking Boats Non-commercial" \
  --icecast-output "71:/talkingboats-71.mp3:Talking Boats Non-commercial" \
  --icecast-output "72:/talkingboats-72.mp3:Talking Boats Ship-to-ship" \
  --icecast-output "73:/talkingboats-73.mp3:Talking Boats Port Operations" \
  --icecast-output "74:/talkingboats-74.mp3:Talking Boats Port Operations" \
  --icecast-output "77:/talkingboats-77.mp3:Talking Boats Ship-to-ship" \
  --icecast-output "78A:/talkingboats-78a.mp3:Talking Boats Non-commercial" \
  --icecast-source-password "${TALKINGBOATS_ICECAST_SOURCE_PASSWORD}" \
  > /etc/talkingboats/rtl_airband-voice-net-balanced.conf
chmod 0600 /etc/talkingboats/rtl_airband-voice-net-balanced.conf

if [[ -f /etc/icecast2/icecast.xml && ! -f /etc/icecast2/icecast.xml.talkingboats.bak ]]; then
  cp -a /etc/icecast2/icecast.xml /etc/icecast2/icecast.xml.talkingboats.bak
fi

cat > /etc/icecast2/icecast.xml <<EOF
<icecast>
  <location>LAN</location>
  <admin>rob@localhost</admin>
  <limits>
    <clients>48</clients>
    <sources>24</sources>
    <queue-size>524288</queue-size>
    <client-timeout>30</client-timeout>
    <header-timeout>15</header-timeout>
    <source-timeout>300</source-timeout>
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
    <mount-name>/talkingboats-05a.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-06.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-09.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-10.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-13.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>${TALKINGBOATS_ICECAST_MOUNT:-/talkingboats-live.mp3}</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-16.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-22a.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-65a.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-66a.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-67.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-68.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-69.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-71.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-72.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-73.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-74.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-77.mp3</mount-name>
    <public>0</public>
    <burst-size>65535</burst-size>
  </mount>
  <mount type="normal">
    <mount-name>/talkingboats-78a.mp3</mount-name>
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
systemctl enable talkingboats-spool-uploader.service
systemctl restart talkingboats-spool-uploader.service
if [[ "${TALKINGBOATS_CLOUD_HLS_ENABLED:-false}" == "true" && -n "${TALKINGBOATS_PUBLIC_SITE_BUCKET:-}" ]]; then
  systemctl enable talkingboats-live-hls-relay.service
  systemctl restart talkingboats-live-hls-relay.service
else
  systemctl disable --now talkingboats-live-hls-relay.service 2>/dev/null || true
fi
if [[ -n "${TALKINGBOATS_AIS_SDR_SERIAL:-}" || -n "${TALKINGBOATS_AIS_DEVICE_INDEX:-}" ]]; then
  systemctl enable talkingboats-ais-catcher.service
  systemctl restart talkingboats-ais-catcher.service
else
  systemctl disable --now talkingboats-ais-catcher.service 2>/dev/null || true
  echo "AIS services installed but disabled; set TALKINGBOATS_AIS_SDR_SERIAL or TALKINGBOATS_AIS_DEVICE_INDEX and rerun."
fi
if [[ -n "${TALKINGBOATS_AIS_HTTP_INGEST_URL:-}" && -n "${TALKINGBOATS_AIS_INGEST_TOKEN:-}" ]]; then
  systemctl enable talkingboats-ais-forwarder.service
  systemctl restart talkingboats-ais-forwarder.service
else
  systemctl disable --now talkingboats-ais-forwarder.service 2>/dev/null || true
  if [[ -n "${TALKINGBOATS_AIS_HTTP_INGEST_URL:-}" ]]; then
    echo "AIS forwarder installed but disabled; set TALKINGBOATS_AIS_INGEST_TOKEN and rerun." >&2
  fi
fi
systemctl enable talkingboats-profile-capture.service
systemctl restart talkingboats-profile-capture.service

echo "Talking Boats capture profile installed."
echo "The single browser UI is served by CloudFront from the public-site bucket."
