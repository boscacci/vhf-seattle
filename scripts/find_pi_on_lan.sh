#!/usr/bin/env bash
set -euo pipefail

interface="${1:-eno1}"

echo "Scanning Raspberry Pi neighbors on ${interface}..."
ip -6 neigh show dev "${interface}" | awk '
  tolower($0) ~ /(b8:27:eb|dc:a6:32|d8:3a:dd|e4:5f:01|28:cd:c1|2c:cf:67)/ {
    print
  }
'

echo
echo "Reachable IPv4 hosts with SSH:"
for i in $(seq 1 254); do
  ip_addr="192.168.1.${i}"
  (
    if timeout 1 bash -c "cat < /dev/null > /dev/tcp/${ip_addr}/22" 2>/dev/null; then
      printf '%s ' "${ip_addr}"
      timeout 2 bash -c "exec 3<>/dev/tcp/${ip_addr}/22; head -n1 <&3" 2>/dev/null || true
    fi
  ) &
done
wait
