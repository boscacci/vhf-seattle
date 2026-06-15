# Performance Monitoring

The private dev app exposes a **Performance** tab at
`https://vhf-dev.robertboscacci.com`. It is intentionally dev-only and reachable
only from the tailnet. The tab reads `/api/live/performance`, which the live
radio proxy serves only for configured dev hostnames or the tailnet dev reverse
proxy path.

The payload is public-safe by design. It includes Ubuntu micro-computer
live-proxy telemetry and Raspberry Pi edge-radio telemetry, but it does not include LAN addresses,
tailnet hostnames, service names, process lists, environment variables, private
stream URLs, command lines, logs, tokens, cookies, or local filesystem paths.
The browser refreshes the Performance tab every 10 seconds while it is open, and
the tab's Refresh button forces a new snapshot. The proxy also samples telemetry
server-side every 5 seconds, so the chart history is available even if nobody has
kept the browser open. It keeps the last 6 hours at high granularity in memory
and persists one sample per minute to a local SQLite database for the last 24
hours. The tab can render the same host charts over 30 minutes, 6 hours, or 24
hours.

Each host snapshot includes CPU utilization, 1-minute load average, system
memory, filesystem capacity, and thermals. The Pi snapshot includes the
Raspberry Pi throttling flag when `vcgencmd` is available; the Ubuntu
micro-computer snapshot reports thermal data when Linux exposes it through
`/sys/class/thermal`. Disk reads collapse duplicate mounts on the same
filesystem.

The default SQLite file is `data/performance_telemetry.sqlite3` under the proxy
checkout. Override it with `TALKINGBOATS_PROXY_PERFORMANCE_HISTORY_DB_PATH` if a
systemd unit needs a different writable path. The sampling and retention knobs
are:

| Environment variable | Default |
| --- | --- |
| `TALKINGBOATS_PROXY_PERFORMANCE_SAMPLE_INTERVAL_SECONDS` | `5` |
| `TALKINGBOATS_PROXY_PERFORMANCE_MEMORY_HISTORY_SECONDS` | `21600` |
| `TALKINGBOATS_PROXY_PERFORMANCE_PERSIST_INTERVAL_SECONDS` | `60` |
| `TALKINGBOATS_PROXY_PERFORMANCE_PERSIST_HISTORY_SECONDS` | `86400` |

## Pressure Thresholds

The dashboard uses coarse status labels:

| Signal | OK | Watch | High |
| --- | --- | --- | --- |
| CPU load per core | `< 0.75` | `0.75-0.99` | `>= 1.00` |
| CPU utilization | `< 75%` | `75-89.9%` | `>= 90%` |
| Memory used | `< 75%` | `75-89.9%` | `>= 90%` |
| Disk used | `< 80%` | `80-89.9%` | `>= 90%` |
| Temperature | `< 70 C` | `70-84.9 C` | `>= 85 C` |

A `Watch` state is not a failure; it is a prompt to check whether a backfill,
transcription run, lexical refresh, or live audio task is expected to be busy.
`High` means the system is close enough to a resource limit that new long-running
work should wait until the cause is clear.

## Ubuntu Micro-Computer Checks

For a live read from the Ubuntu micro-computer (`optiplex` SSH alias):

```bash
ssh rob@optiplex 'uptime; df -h / /home /opt 2>/dev/null || df -h /; free -h'
ssh rob@optiplex 'systemctl --user --no-pager --plain --type=service --state=running | grep talkingboats'
```

Useful service resource detail:

```bash
ssh rob@optiplex '
for service in \
  talkingboats-api \
  talkingboats-live-radio-proxy \
  talkingboats-uploaded-clip-transcriber \
  talkingboats-lexical-refresh
do
  systemctl --user show "$service" --no-pager \
    -p ActiveState -p SubState -p MemoryCurrent -p CPUUsageNSec
done
'
```

The normal steady state should have ample disk, no swap pressure, and load well
below the CPU count. The uploaded-clip transcriber is expected to be the largest
memory consumer.

## Raspberry Pi Checks

The dev tab reads Pi telemetry by SSHing from the Ubuntu micro-computer to
`TALKINGBOATS_PROXY_RETUNE_SSH_TARGET` every dashboard refresh. If the SSH read
fails, the Pi card degrades to `Unknown` instead of blocking the rest of the
dashboard. Direct read-only checks are still useful when the receiver side feels
suspect:

```bash
ssh rob@192.168.1.114 'uptime; df -h / /opt 2>/dev/null || df -h /; free -h'
ssh rob@192.168.1.114 'vcgencmd measure_temp 2>/dev/null; vcgencmd get_throttled 2>/dev/null'
ssh rob@192.168.1.114 'systemctl --no-pager --plain --type=service --state=running | grep talkingboats'
```

The Pi edge capture already pauses heavier clip work when thermal or CPU load
crosses its configured guardrail. The default edge load guard is
`TALKINGBOATS_EDGE_MAX_LOAD_PER_CPU=0.85`.

## What To Do Under Pressure

- Disk `Watch`: inspect spool and output directories before starting backfills.
- Disk `High`: stop new exports/backfills, preserve current captures, and clean
  old generated outputs or completed spool files deliberately.
- CPU `Watch`: confirm whether transcription, BERTopic, or export work is
  expected. Avoid starting another heavy batch.
- CPU `High`: let the current batch finish or pause non-live work. Keep live
  stream and capture services prioritized.
- Thermals `High`: stop or quota non-live batch work first, especially the
  lexical refresh/export path. The example user service caps that refresh at
  `CPUQuota=150%` so it cannot consume the whole Ubuntu micro-computer while live services
  are running.
- Memory `Watch`: check transcriber model processes first.
- Memory `High`: stop optional analysis/backfill tasks before restarting live
  services.

Do not deploy to prod because the performance tab looks healthy. Prod promotion
still requires the normal dev smoke test and explicit prod intent.
