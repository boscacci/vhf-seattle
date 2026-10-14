#!/usr/bin/env bash
# Called only by the approved shared Pi release. Credentials never enter argv or logs.
set -Eeuo pipefail
stage="${1:?}"; commit="${2:?}"; digest="${3:?}"
[[ "${commit}" =~ ^[a-f0-9]{40}$ && "${digest}" =~ ^[a-f0-9]{64}$ ]] || exit 2
[[ $(id -u) == 0 && $(uname -m) == aarch64 ]] || exit 2
record="/opt/talkingboats/docktalk/releases/${commit}"
python3 - "${stage}" <<'PY'
import hashlib,json,sys
from pathlib import Path
stage=Path(sys.argv[1]);spec=json.loads((stage/'config/docktalk.json').read_text())
if spec['mode'] != 'alongside' or spec['version'] != '2' or not spec['health_reports']:
    raise SystemExit('Unsupported node policy')
if hashlib.sha256((stage/'vendor/docktalk-installer.sh').read_bytes()).hexdigest()!=spec['installer_sha256']:
    raise SystemExit('Reviewed upstream installer identity mismatch')
PY
getent group docktalk >/dev/null || groupadd --system docktalk
id docktalk >/dev/null 2>&1 || useradd --system --gid docktalk --home-dir /nonexistent --shell /usr/sbin/nologin docktalk
python3 - <<'PYCHECK'
import grp,pwd
user=pwd.getpwnam('docktalk');group=grp.getgrnam('docktalk')
if not 100 <= user.pw_uid < 1000 or user.pw_gid!=group.gr_gid or user.pw_shell!='/usr/sbin/nologin':
    raise SystemExit('DockTalk must use a dedicated unprivileged system account')
if set(group.gr_mem)-{'docktalk'} or any(u.pw_gid==group.gr_gid and u.pw_name!='docktalk' for u in pwd.getpwall()):
    raise SystemExit('DockTalk credential group has unexpected members')
PYCHECK
install -d -m 0755 "${record}/talkingboats"
install -m 0644 "${stage}/src/talkingboats/"{docktalk,receiver_config,channel_metadata}.py "${record}/talkingboats/"
install -m 0644 "${stage}/src/talkingboats/__init__.py" "${record}/talkingboats/"
install -d -o root -g docktalk -m 0750 /etc/docktalk
PYTHONPATH="${record}" python3 -m talkingboats.docktalk map --receiver-config /etc/talkingboats/rtl_airband-voice-net-balanced.conf
PYTHONPATH="${record}" python3 -m talkingboats.docktalk provision --claim-file "${stage}/docktalk-claim"
for path in node.json streams.json plan.txt; do
  chown root:docktalk "/etc/docktalk/${path}"
  chmod 0640 "/etc/docktalk/${path}"
done
ln -sfn "${record}" /opt/talkingboats/docktalk/current
for unit in docktalk-push.service docktalk-pushdog.service docktalk-pushdog.timer docktalk-vitals.service docktalk-vitals.timer; do
  install -m 0644 "${stage}/deploy/pi/${unit}" "/etc/systemd/system/${unit}"
done
systemctl daemon-reload
systemctl enable docktalk-push.service docktalk-pushdog.timer docktalk-vitals.timer
systemctl restart docktalk-push.service
systemctl start docktalk-pushdog.timer docktalk-vitals.timer
systemctl is-active --quiet docktalk-push.service
printf '%s\n' "${digest}" > "${record}/artifact.sha256"
printf 'event=docktalk_alongside_installed commit=%s channels=18 credentials=private\n' "${commit}"
