#!/usr/bin/env bash
set -Eeuo pipefail
release_root="${1:?release source required}"
commit="${2:?commit required}"
digest="${3:?digest required}"
action="${4:-apply}"
[[ "${action}" == apply || "${action}" == rollback ]] || exit 2
[[ "${commit}" =~ ^[a-f0-9]{40}$ && "${digest}" =~ ^[a-f0-9]{64}$ ]] || exit 2
target="${TALKINGBOATS_PI_DEPLOY_TARGET:-rob@192.168.1.114}"
[[ "${target}" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$ ]] || exit 2
stage="$(ssh -o BatchMode=yes -o ConnectTimeout=8 "${target}" 'mktemp -d /tmp/talkingboats-asr.XXXXXX')"
[[ "${stage}" == /tmp/talkingboats-asr.* ]] || exit 2
cleanup() { ssh -o BatchMode=yes "${target}" "find '${stage}' -depth -delete" >/dev/null 2>&1 || true; }
trap cleanup EXIT
scp -q "${release_root}/src/talkingboats/receiver_config.py" "${release_root}/src/talkingboats/channel_metadata.py" \
  "${release_root}/src/talkingboats/spool_uploader.py" "${release_root}/scripts/apply_asr_receiver.sh" "${target}:${stage}/"
channels="$(/home/rob/miniforge3/envs/dell/bin/python -c 'import json,sys; print(",".join(json.load(open(sys.argv[1]))["active_channels"]))' "${release_root}/config/channel-selection.json")"
ssh -o BatchMode=yes "${target}" "sudo -n bash '${stage}/apply_asr_receiver.sh' '${stage}' '${commit}' '${digest}' '${channels}' '${action}'"
