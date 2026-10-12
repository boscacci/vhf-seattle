#!/usr/bin/env bash
set -Eeuo pipefail
stage="${1:?}"; commit="${2:?}"; digest="${3:?}"; channels="${4:?}"; action="${5:-apply}"
[[ "${commit}" =~ ^[a-f0-9]{40}$ && "${digest}" =~ ^[a-f0-9]{64}$ && "${channels}" =~ ^[A-Z0-9,]+$ ]] || exit 2
config=/etc/talkingboats/rtl_airband-voice-net-balanced.conf
module=/opt/talkingboats/app/src/talkingboats
record="/opt/talkingboats/releases/asr/${commit}"
install -d -m 0700 "${record}"
if [[ "${action}" == rollback ]]; then
  [[ -f "${record}/receiver.conf" && -f "${record}/artifact.sha256" ]] || exit 2
  [[ "$(cat "${record}/artifact.sha256")" == "${digest}" ]] || exit 2
  systemctl stop talkingboats-pi-healthcheck.timer talkingboats-pi-healthcheck.service
  cp -a "${record}/receiver.conf" "${config}"
  cp -a "${record}/channel_metadata.py" "${record}/spool_uploader.py" "${module}/"
  cp -a "${record}/live-radio.env" /etc/talkingboats/live-radio.env
  systemctl restart talkingboats-profile-capture.service talkingboats-spool-uploader.service
  systemctl start talkingboats-pi-healthcheck.timer
  mv "${record}/deployed" "${record}/rolled-back"
  exit 0
fi
[[ "${action}" == apply ]] || exit 2
if [[ -f "${record}/deployed" ]]; then
  [[ "$(cat "${record}/artifact.sha256")" == "${digest}" ]] || exit 2
  exit 0
fi
cp -a "${config}" "${record}/receiver.conf"
cp -a "${module}/channel_metadata.py" "${module}/spool_uploader.py" "${record}/"
cp -a /etc/talkingboats/live-radio.env "${record}/live-radio.env"
rollback() {
  cp -a "${record}/receiver.conf" "${config}"
  cp -a "${record}/channel_metadata.py" "${record}/spool_uploader.py" "${module}/"
  cp -a "${record}/live-radio.env" /etc/talkingboats/live-radio.env
  systemctl restart talkingboats-profile-capture.service talkingboats-spool-uploader.service || true
  systemctl start talkingboats-pi-healthcheck.timer || true
}
printf '%s\n' "${digest}" > "${record}/artifact.sha256"
trap rollback ERR
systemctl stop talkingboats-pi-healthcheck.timer talkingboats-pi-healthcheck.service
python3 "${stage}/receiver_config.py" "${config}" --channels "${channels}" --write
install -m 0644 "${stage}/channel_metadata.py" "${stage}/spool_uploader.py" "${module}/"
python3 - "${channels}" <<'PY'
import sys
from pathlib import Path
path=Path('/etc/talkingboats/live-radio.env')
values={'TALKINGBOATS_CLOUD_HLS_CHANNELS':sys.argv[1], 'TALKINGBOATS_ENFORCE_ACTIVE_CHANNELS':'true'}
lines=[line for line in path.read_text().splitlines() if line.partition('=')[0] not in values]
lines += [f'{key}={value}' for key,value in values.items()]
path.write_text('\n'.join(lines)+'\n')
path.chmod(0o600)
PY
systemctl restart talkingboats-profile-capture.service talkingboats-spool-uploader.service
systemctl is-active --quiet talkingboats-profile-capture.service talkingboats-spool-uploader.service
systemctl start talkingboats-pi-healthcheck.timer
printf '%s\n' "${digest}" > "${record}/artifact.sha256"
printf '%s\n' "${commit}" > "${record}/release-commit"
date -u +%Y-%m-%dT%H:%M:%SZ > "${record}/deployed"
trap - ERR
printf 'event=asr_receiver_deployed commit=%s channels=%s digest=%s\n' "${commit}" "${channels}" "${digest}"
