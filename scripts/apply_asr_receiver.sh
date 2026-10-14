#!/usr/bin/env bash
set -Eeuo pipefail
stage="${1:?}"; commit="${2:?}"; digest="${3:?}"; action="${4:-apply}"
[[ "${commit}" =~ ^[a-f0-9]{40}$ && "${digest}" =~ ^[a-f0-9]{64}$ ]] || exit 2
config=/etc/talkingboats/rtl_airband-voice-net-balanced.conf
module=/opt/talkingboats/app/src/talkingboats
record="/opt/talkingboats/releases/asr/${commit}"
install -d -m 0700 "${record}"
restore_receiver() {
  systemctl disable --now docktalk-push.service docktalk-pushdog.timer docktalk-vitals.timer 2>/dev/null || true
  cp -a "${record}/receiver.conf" "${config}"
  cp -a "${record}/channel_metadata.py" "${record}/spool_uploader.py" "${module}/"
  if [[ -f "${record}/recording_policy.py" ]]; then cp -a "${record}/recording_policy.py" "${module}/"; fi
  cp -a "${record}/live-radio.env" /etc/talkingboats/live-radio.env
  if [[ -f "${record}/channel-activations.json" ]]; then
    cp -a "${record}/channel-activations.json" /etc/talkingboats/channel-activations.json
  fi
  systemctl restart talkingboats-profile-capture.service talkingboats-spool-uploader.service
  systemctl start talkingboats-pi-healthcheck.timer
}
if [[ "${action}" == rollback ]]; then
  [[ -f "${record}/receiver.conf" && $(cat "${record}/artifact.sha256") == "${digest}" ]] || exit 2
  systemctl stop talkingboats-pi-healthcheck.timer talkingboats-pi-healthcheck.service
  restore_receiver
  [[ ! -f "${record}/deployed" ]] || mv "${record}/deployed" "${record}/rolled-back"
  exit 0
fi
[[ "${action}" == apply ]] || exit 2
if [[ -f "${record}/deployed" ]]; then
  [[ $(cat "${record}/artifact.sha256") == "${digest}" ]] || exit 2
  exit 0
fi
# Preserve the first rollback snapshot even if a bounded release is retried.
if [[ ! -f "${record}/receiver.conf" ]]; then
  cp -a "${config}" "${record}/receiver.conf"
  cp -a "${module}/channel_metadata.py" "${module}/spool_uploader.py" "${record}/"
  cp -a /etc/talkingboats/live-radio.env "${record}/live-radio.env"
  [[ ! -f "${module}/recording_policy.py" ]] || cp -a "${module}/recording_policy.py" "${record}/"
  [[ ! -f /etc/talkingboats/channel-activations.json ]] || cp -a /etc/talkingboats/channel-activations.json "${record}/"
fi
printf '%s\n' "${digest}" > "${record}/artifact.sha256"
trap restore_receiver ERR
systemctl stop talkingboats-pi-healthcheck.timer talkingboats-pi-healthcheck.service
systemctl stop talkingboats-profile-capture.service talkingboats-spool-uploader.service
PYTHONPATH="${stage}/src" python3 - "${stage}" "${config}" "${record}" <<'PY'
import hashlib,json,sys
from pathlib import Path
from talkingboats.receiver_config import channel_blocks,configure_channels
from talkingboats.channel_metadata import ACTIVE_CAPTURE_CHANNELS,LIVE_STREAM_CHANNELS
stage,config,record=map(Path,sys.argv[1:])
policy=json.loads((stage/'config/channel-selection.json').read_text())
if set(policy['active_channels'])!=set(ACTIVE_CAPTURE_CHANNELS) or set(policy['live_only_channels'])!=set(LIVE_STREAM_CHANNELS)-set(ACTIVE_CAPTURE_CHANNELS):
    raise SystemExit('Receiver policy does not match artifact')
# Find the verified pre-pruning shape; credentials remain on the Pi.
templates=[p for p in Path('/opt/talkingboats/releases/asr').glob('*/receiver.conf')
           if set(LIVE_STREAM_CHANNELS)<= {b[2] for b in channel_blocks(p.read_text())}]
if not templates:
    raise SystemExit('No complete pre-pruning receiver template')
template=min(templates,key=lambda p:p.stat().st_mtime)
source=template.read_text()
(record/'template.sha256').write_text(hashlib.sha256(source.encode()).hexdigest()+'\n')
result=configure_channels(config.read_text(),source,LIVE_STREAM_CHANNELS,ACTIVE_CAPTURE_CHANNELS)
pending=config.with_suffix('.pending');pending.write_text(result);pending.chmod(0o600);pending.replace(config)
print('event=receiver_config_validated live=18 recorded=13')
PY
install -m 0644 "${stage}/src/talkingboats/"{channel_metadata,spool_uploader,recording_policy}.py "${module}/"
install -m 0644 "${stage}/channel-activations.json" /etc/talkingboats/channel-activations.json
python3 - <<'PY'
from pathlib import Path
path=Path('/etc/talkingboats/live-radio.env')
values={'TALKINGBOATS_ENFORCE_ACTIVE_CHANNELS':'true','TALKINGBOATS_RECORDING_ACTIVATIONS_FILE':'/etc/talkingboats/channel-activations.json'}
lines=[line for line in path.read_text().splitlines() if line.partition('=')[0] not in values]
lines += [f'{key}={value}' for key,value in values.items()]
path.write_text('\n'.join(lines)+'\n');path.chmod(0o600)
PY
systemctl restart talkingboats-profile-capture.service talkingboats-spool-uploader.service
systemctl is-active --quiet talkingboats-profile-capture.service talkingboats-spool-uploader.service
bash "${stage}/scripts/install_docktalk_alongside.sh" "${stage}" "${commit}" "${digest}"
systemctl start talkingboats-pi-healthcheck.timer
printf '%s\n' "${commit}" > "${record}/release-commit"
date -u +%Y-%m-%dT%H:%M:%SZ > "${record}/deployed"
trap - ERR
printf 'event=asr_receiver_deployed commit=%s live_channels=18 recorded_channels=13 digest=%s\n' "${commit}" "${digest}"
