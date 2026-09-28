#!/usr/bin/env bash
set -Eeuo pipefail
artifact="${1:?dev-tested artifact required}"
commit="${TALKINGBOATS_RELEASE_COMMIT:?commit required}"
digest="${TALKINGBOATS_RELEASE_SHA256:?digest required}"
[[ "$commit" =~ ^[0-9a-f]{40}$ && "$digest" =~ ^[0-9a-f]{64}$ ]] || exit 2
[[ $(sha256sum "$artifact" | awk '{print $1}') == "$digest" ]]
target=rob@192.168.1.114
stage="$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$target" 'mktemp -d /tmp/talkingboats-pi-network.XXXXXX')"
[[ "$stage" =~ ^/tmp/talkingboats-pi-network\.[A-Za-z0-9]+$ ]] || exit 2
trap 'ssh -o BatchMode=yes "$target" "rm -rf -- ${stage}"' EXIT
scp -q -o BatchMode=yes "$artifact" "$target:$stage/release.tar.gz"
ssh -o BatchMode=yes "$target" \
  "test \"\$(sha256sum '$stage/release.tar.gz' | cut -d ' ' -f1)\" = '$digest' && tar -xzf '$stage/release.tar.gz' -C '$stage' && sudo -n env TALKINGBOATS_RELEASE_COMMIT='$commit' TALKINGBOATS_RELEASE_SHA256='$digest' bash '$stage/scripts/apply_pi_network_release.sh' '$stage'"
ssh -o BatchMode=yes "$target" \
  "sudo -n sha256sum --check --status '/opt/talkingboats/releases/pi-network/$commit/installed.sha256' && systemctl is-active talkingboats-network-recovery.timer && sudo -n journalctl -u talkingboats-network-recovery.service -n 4 --no-pager"
