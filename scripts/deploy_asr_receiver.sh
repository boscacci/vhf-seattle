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
artifact="${HOME}/.local/share/talkingboats/release-candidates/asr/${commit}/release.tar.gz"
[[ $(sha256sum "${artifact}" | awk '{print $1}') == "${digest}" ]] || exit 2
stage="$(ssh -o BatchMode=yes -o ConnectTimeout=8 "${target}" 'mktemp -d /tmp/talkingboats-asr.XXXXXX')"
[[ "${stage}" =~ ^/tmp/talkingboats-asr\.[A-Za-z0-9]+$ ]] || exit 2
cleanup() { ssh -o BatchMode=yes "${target}" "sudo -n find '${stage}' -depth -delete" >/dev/null 2>&1 || true; }
trap cleanup EXIT
scp -q "${artifact}" "${target}:${stage}/release.tar.gz"
if [[ "${action}" == apply ]]; then
  claim="${HOME}/.config/talkingboats/docktalk-claim"
  [[ -f "${claim}" && $(stat -c '%a' "${claim}") == 600 ]] || { echo 'Private DockTalk claim file is required.' >&2; exit 2; }
  activation="$("${HOME}/miniforge3/envs/dell/bin/python" - <<'PY'
from pathlib import Path
values = dict(line.partition('=')[::2] for line in (Path.home()/'.config/talkingboats/asr.env').read_text().splitlines())
print(values['TALKINGBOATS_RECORDING_ACTIVATIONS_FILE'])
PY
)"
  scp -q "${claim}" "${target}:${stage}/docktalk-claim"
  scp -q "${activation}" "${target}:${stage}/channel-activations.json"
fi
ssh -o BatchMode=yes "${target}" "sudo -n python3 - '${stage}' '${commit}' '${digest}' '${action}'" <<'PY'
import hashlib, pathlib, subprocess, sys, tarfile
stage=pathlib.Path(sys.argv[1]);commit,digest,action=sys.argv[2:]
if hashlib.sha256((stage/'release.tar.gz').read_bytes()).hexdigest()!=digest:
    raise SystemExit('Receiver artifact identity mismatch')
with tarfile.open(stage/'release.tar.gz') as archive:
    for item in archive:
        path=pathlib.PurePosixPath(item.name)
        if path.is_absolute() or '..' in path.parts or item.issym() or item.islnk() or str(path) in {'docktalk-claim','channel-activations.json'}:
            raise SystemExit('Unsafe artifact member')
        if item.isfile():
            destination=stage/item.name
            destination.parent.mkdir(parents=True,exist_ok=True)
            with destination.open('wb') as out:
                out.write(archive.extractfile(item).read())
subprocess.run(['bash',str(stage/'scripts/apply_asr_receiver.sh'),str(stage),commit,digest,action],check=True)
PY
