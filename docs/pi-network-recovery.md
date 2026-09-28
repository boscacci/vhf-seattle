# Pi network recovery and persistent diagnostics

The receiver remains a Wi-Fi client with its existing DHCP reservation and saved
NetworkManager profile. This release changes only local recovery and logging;
it does not change APs, Wi-Fi credentials, capture services, or cloud publishing.

The root-owned timer checks every 60 seconds after a three-minute boot grace.
It probes the gateway through wlan0 and a TCP connection to the local API.
If either responds, Wi-Fi is left alone. An API outage alone, DNS failure, or
Internet outage cannot trigger reconnection. Both must fail on three consecutive
checks (roughly two to three minutes) before reactivating the saved Wi-Fi UUID.
Each activation is limited to 25 seconds; the whole service is limited to 40.
Attempts are persisted before nmcli runs, with five then ten minute backoff and
a maximum of three attempts per rolling hour, including across process restarts
and Pi reboots. A lock prevents overlapping invocations. A backward clock step
suppresses attempts until time catches up. Invalid state fails closed.

A prolonged router outage can therefore cause a few unnecessary reconnects,
but never an unbounded loop. There is no reboot, NetworkManager restart, cloud
probe, radio-wide reset, or destructive spool cleanup. The existing hardware
watchdog remains separate. A disconnected Wi-Fi interface can be recovered using
the UUID saved at installation, even when no active connection can be discovered.

Structured journal events include health, consecutive failures, budget exhaustion,
and activation success/failure. They omit SSIDs, MACs, credentials, and command
output. Persistent journald retains up to 14 days, targets a 128 MB maximum,
keeps 512 MB disk space free, and syncs every minute. Journald limits are subject
to active-file/rotation behavior; sudden power loss may lose the last buffered
messages. Existing system logs remain root/journal-group controlled on the Pi.
No prior-boot logs can be reconstructed retroactively.

## Release and verification

CI validates policy and execution with simulated failures, builds one archive of
the exact main commit, automatically deploys dev, runs Playwright, then records
a smoke-success marker containing its digest. There is no separate dev Pi;
network fault tests use deterministic mocked commands, not a home-network outage.
After the usual human dev smoke, select an annotated `pi-network/vX.Y.Z` tag on
that commit and dispatch **Deploy Pi network recovery release** from main.
One approval in the protected production environment promotes that same archive.
The workflow checks the smoke marker and verifies the SHA-256 before transfer
and on the Pi. The scoped installer snapshots previous files privately, records
installed hashes, starts the timer, and verifies on-disk persistent journal files.
Installer failure restores the prior files and timer state. Reapplying a completed
release checks hashes without overwriting its rollback snapshot.

Inspect:

```sh
systemctl status talkingboats-network-recovery.timer
sudo journalctl -u talkingboats-network-recovery.service --since '1 hour ago'
sudo journalctl --list-boots
sudo journalctl --disk-usage
sudo journalctl -b -1 -u NetworkManager -k
```

After a later planned reboot, verify that `journalctl --list-boots` retains the
previous boot. Do not deliberately disconnect the sole remote management link
just to test recovery; fault behavior is exercised in CI. Verify fresh public AIS
and successful uploads as well as local health. This release does not fix public
HLS authorization or the separate export read-budget failures.

## Rollback

Use the deployed commit/digest from the workflow (not an arbitrary revision).
On the Pi, run the saved installer with `rollback`:

```sh
sudo env TALKINGBOATS_RELEASE_COMMIT=COMMIT TALKINGBOATS_RELEASE_SHA256=DIGEST \
  bash /opt/talkingboats/releases/pi-network/COMMIT/apply.sh /unused rollback
```

This restores the previous configuration and timer state without reconnecting
Wi-Fi. Persisted logs and recovery counters are retained for diagnosis. If the
Wi-Fi profile is intentionally replaced, reinstall a new release while connected
to that profile to record its new UUID. Numeric probe targets currently match
this LAN; update the unit arguments in version control if the LAN is renumbered.
