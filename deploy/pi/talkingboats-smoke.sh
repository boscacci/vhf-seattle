#!/usr/bin/env bash
set -euo pipefail

echo "== host"
hostnamectl

echo
echo "== network"
ip -brief addr

echo
echo "== storage"
df -h /

echo
echo "== memory"
free -h

echo
echo "== temperature"
vcgencmd measure_temp 2>/dev/null || true

echo
echo "== sdr packages"
command -v rtl_test
command -v rtl_fm
command -v ffmpeg

echo
echo "== usb"
lsusb

echo
echo "== rtl-sdr probe"
rtl_test -t 2>&1 | sed -n '1,80p' || true

echo
echo "== kernel blacklist"
cat /etc/modprobe.d/talkingboats-rtlsdr-blacklist.conf

echo
echo "== project config"
find /opt/talkingboats -maxdepth 2 -type f -print | sort
