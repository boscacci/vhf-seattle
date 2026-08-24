# Raspberry Pi Edge Outage — 2026-07-31

Status: **production restored 2026-08-02; initiating trigger remains unknown**

Severity: SEV-2 for the public live radio/AIS service. The static site and the
OptiPlex-hosted API remained available, but the single radio edge stopped
supplying live audio clips and AIS messages.

## Summary

The Raspberry Pi at `192.168.1.114` stopped sending clip-ingest requests at
04:05:27 UTC and stopped updating the public AIS snapshot at 04:06:07 UTC. AIS
Friends and the AWS public-clip freshness alarm both detected the outage after
their one-hour thresholds. At 18:07 UTC the Pi still answered Ethernet address
resolution at its expected MAC address, but it did not answer ICMP, SSH,
Icecast, receiver-status, or AIS-catcher requests. A full LAN scan did not find
the Pi at another address.

This establishes a host-level edge outage, not an AIS Friends delivery fault or
an isolated AIS-catcher failure. A physical power cycle at approximately
18:13 UTC on August 1 restored the edge. The recovered Pi has only the current,
volatile journal; no previous boot is available. The current boot has no failed
units, no throttling flags, ample memory/disk, and healthy capture, upload, and
AIS processes. Those observations prove recovery but do **not** establish why
the prior boot became non-responsive. Do not relabel the initiating trigger as
OOM, thermal, SD-card, power, or network failure without evidence that no
longer exists.

Recovery also exposed five independent defects: the production browser shell
lagged the tested dev shell; the AWS AIS sanitizer rejected valid public numeric
values beginning with `10.`; and the promoted shell's same-origin audio route
redirected browsers to the dev raw-audio bucket, where CORS correctly rejected
the production origin. The static deploy could also pair current custom-player
JavaScript with a cached pre-player stylesheet because the stylesheet did not
force revalidation and the shared asset version had not changed. Finally, the
search renderer appended a second player after the shared clip-card renderer
had already added one. Each was corrected and validated separately rather than
being attributed to the Pi outage.

A later search investigation exposed three more independent defects. Recency
and result-count controls changed request state without re-rendering their
selected state; semantic search always returned the requested number of clips
even when every score was weak; and scalar Python scoring repeatedly traversed
a 385 MiB, 54,020-clip embedding index. The two API workers also duplicated the
expanded index and model in memory. These were search defects, not evidence
about the initiating Pi outage.

## Impact

- AIS Friends marked `Elliott Bay VHF` offline.
- `ais/latest.json` stopped at `2026-07-31T04:06:07Z` with nine cached vessels.
- New voice clips stopped at the edge; the last published clip ended at
  04:04:52 UTC.
- The OptiPlex transcriber continued draining already-uploaded work. Those
  successful polls did not mean edge ingest was healthy.
- The static public site and the OptiPlex API/proxy processes remained up.

## Timeline

All times are UTC unless noted.

| Time | Event |
| --- | --- |
| 2026-07-31 04:04:52 | Last clip in the production public manifest ended. |
| 2026-07-31 04:05:27 | Last successful Pi request to `POST /api/ingest/clips/presign`. |
| 2026-07-31 04:06:07 | Last public AIS snapshot generation/message time. |
| 2026-07-31 05:07:28 | AWS public-clip freshness alarm entered `ALARM` at 3,697 seconds. |
| 2026-07-31 05:07 | AIS Friends sent “Your station is offline” (22:07 PDT on July 30). |
| 2026-07-31 18:03 | Public-clip age reached 50,497 seconds and remained in `ALARM`. |
| 2026-07-31 18:06:42 | OptiPlex healthcheck incorrectly logged `all_checks_passed`; it checked only local processes. |
| 2026-07-31 18:07–18:16 | LAN, service, public snapshot, journal, and CloudWatch checks isolated the Pi as the common failure point. |
| 2026-08-01 18:13 (approx.) | User physically power-cycled the Pi; time is reconstructed from monotonic uptime because the Pi has no RTC. |
| 2026-08-01 18:27:47 | Production public-clip freshness alarm returned to `OK`. |
| 2026-08-02 00:04–00:11 | Fresh production clips and AIS snapshots plus healthy Pi services confirmed edge recovery. Previous-boot journal was unavailable. |
| 2026-08-02 00:15–00:17 | Tested dev static shell promoted to production; CloudFront invalidation `I3VSXKMK6TW593SGGE6LG7KOOP` completed. |
| 2026-08-02 00:20 | AIS ingest/websocket Lambda package updated in place; valid speeds such as `10.2` no longer trigger the private-network guard. |
| 2026-08-02 00:23–00:27 | Production smoke exposed the audio redirect/CORS failure; bounded same-origin audio relay passed dev and production mobile SLO probes. |
| 2026-08-02 00:28–00:29 | AIS freshness metric/alarm deployed and invoked; alarm entered `OK` on a 0-second age datapoint. |
| 2026-08-02 01:26–01:31 | Mobile player cache skew reproduced; shared asset key and stylesheet revalidation fix passed dev, production, and audio-progress checks. |
| 2026-08-02 02:44–02:52 | Duplicate search players reproduced and removed; all ten production `Wenatchee` results rendered one working player on mobile and desktop. |
| 2026-08-02 04:07–04:29 | Search state, low-confidence results, and latency reproduced; compact scoring and one-worker warmup passed dev and production checks. |

## Evidence and diagnosis

Two independent workloads on the same Pi stopped within 40 seconds:

- clip upload requests to the private OptiPlex API; and
- AIS HTTPS/UDP forwarding from AIS-catcher.

The expected Raspberry Pi MAC (`e4:5f:01:78:39:77`) remained associated with
`192.168.1.114`, which argues against a DHCP address change. The host did not
answer TCP ports 22, 8000, 8050, or 8100, and a subnet scan found no replacement
address. This argues against a failure confined to one systemd unit.

There was no terminal clip-rate spike in the available API evidence: 1,660
presign requests occurred from 00:00 through the outage, 122 in the last
31 minutes, and 30 after 04:00. That is far below the Pi's configured flood
recovery threshold of more than 240 completed clips in two minutes. Clip load
may still be a contributing factor, but the OptiPlex logs do not support calling
it the trigger.

## Detection gap

The AWS public-clip monitor correctly alarmed after one hour. AIS Friends also
alerted. The recurring OptiPlex healthcheck was falsely green because it proved
only that the OptiPlex API, proxies, and transcriber were running; it did not
probe the upstream Pi receiver. This extended ambiguity during triage.

The Pi's current boot journal is volatile and `journalctl --list-boots` contains
only boot `0`. Consequently, the requested previous-boot evidence did not
survive the power cycle. Current-state checks found:

- all four edge units active with zero failed units;
- approximately 3 GiB memory available, 8% root-disk utilization, and no swap;
- `vcgencmd get_throttled=0x0`;
- receiver status, Icecast, and AIS-catcher ports reachable; and
- fresh clips and AIS snapshots reaching production.

The Pi manager already reports an active 60-second runtime watchdog. The three
edge services report `OOMPolicy=stop`; the profile capture also has its 24-hour
runtime recycle. The proposed percentage memory ceilings are not installed:
all three units still report unlimited `MemoryHigh` and `MemoryMax`.

## Remediation and hardening

Deployed during recovery:

1. The scheduled AWS monitor now reads both `public_manifest.json` and
   `ais/latest.json`, emits `LatestPublicClipAgeSeconds` and
   `LatestAisMessageAgeSeconds`, and treats a stale or missing datapoint as
   breaching. The new `talkingboats-talkingboats-prod-ais-stale` alarm entered
   `OK` at 00:29:16 UTC on a 0-second age datapoint.
2. The recurring OptiPlex healthcheck now probes the Pi receiver-status
   endpoint and reports `edge_receiver_unreachable` without restarting healthy
   local services. A manual production run completed with `all_checks_passed`.
3. The AIS public-safety check now walks field names and string values
   structurally. It still rejects private IP addresses, S3 paths, tailnet names,
   and secret-bearing fields, while public numeric values such as speed `10.2`
   no longer create false-positive Lambda 500s.
4. Production clip audio is relayed through the read-only public proxy instead
   of exposing a cross-origin signed redirect. The relay strips viewer
   credentials, accepts only HTTPS AWS S3 targets, forwards a bounded single
   byte range, caps responses at 25 MiB, returns `Cache-Control: no-store`, and
   emits structured status, size, and latency logs. The dev bucket CORS policy
   was not weakened.
5. The dev-tested static shell was promoted without deleting or replacing
   generated clips, manifests, analysis, playlists, or AIS data. Root,
   `assets/app.js`, `assets/styles.css`, and route entry points match the tested
   source hashes after the completed CloudFront invalidation.
6. The shell deploy now uploads `assets/styles.css` with `Cache-Control:
   no-store`, and the HTML uses one rotated version key for both player assets.
   A regression test prevents the deploy from reverting the stylesheet header.
7. Search results now rely on the player already created by the shared clip-card
   renderer. Source and browser regression checks require exactly one player,
   play button, and audio element per result.
8. Recency and result-count controls now re-render immediately, while a new
   search aborts any older in-flight request. The visible selection and
   `aria-pressed` state therefore match the request that will populate results.
9. Semantic matches below cosine score `0.35` are omitted, so a 24-hour search
   with no meaningful `Wenatchee` match renders one explicit empty state instead
   of unrelated low-score clips.
10. Search builds one compact NumPy matrix per process and uses vectorized
    scoring in a worker thread. Production now runs one systemd-managed worker
    and warms search after every restart. Structured logs record status,
    recency, limit, count, query length, and latency without recording the query.

Prepared but not installed on the Pi:

- percentage-based `MemoryHigh`/`MemoryMax` limits for AIS-catcher, profile
  capture, and the spool uploader; and
- the repository's explicit five-minute reboot-watchdog configuration.

These Pi changes must be released from a clean, reviewed artifact rather than
by running the broad installer from this unrelated dirty worktree.

## Safe recovery procedure

The physical power cycle is complete and authenticated remote access is
restored. For a future outage, preserve evidence before running an installer or
performing another reboot:

```bash
ssh rob@192.168.1.114 'uptime; last -x | head -n 20'
ssh rob@192.168.1.114 'sudo journalctl -b -1 -k --no-pager | tail -n 400'
ssh rob@192.168.1.114 'sudo journalctl -b -1 --no-pager -u talkingboats-pi-healthcheck.service -u talkingboats-profile-capture.service -u talkingboats-spool-uploader.service -u talkingboats-ais-catcher.service | tail -n 800'
ssh rob@192.168.1.114 'free -h; df -h / /opt; vcgencmd get_throttled 2>/dev/null || true'
ssh rob@192.168.1.114 'systemctl --failed --no-pager; systemctl show talkingboats-profile-capture.service talkingboats-spool-uploader.service talkingboats-ais-catcher.service -p Result -p NRestarts -p MemoryCurrent -p MemoryPeak'
```

Look specifically for OOM kills, kernel lockups, I/O or filesystem errors,
undervoltage/throttling flags, USB/SDR resets, watchdog events, and clean versus
unclean shutdown evidence. Redact secrets before retaining or sharing logs. A
persistent journal must be configured and verified before another incident or
the previous-boot commands will again have no evidence to read.

After evidence capture, install only a reviewed version-controlled artifact
through the repository's release path. Validate:

```bash
curl -fsS http://192.168.1.114:8050/current-status.json | jq .
curl -fsS http://192.168.1.114:8100/api/stat.json | jq .
curl -fsS https://seattleboatradio.com/ais/latest.json \
  | jq '{generated_at, vessels: (.vessels | length)}'
TALKINGBOATS_SLO_BASE_URL=https://seattleboatradio.com \
  node scripts/live_slo_probe.mjs
```

Require a new clip, a newer AIS `generated_at`, decodable live audio, healthy Pi
units, and both AWS freshness alarms in `OK`. AIS Friends recovery is useful
external confirmation but is not a substitute for those checks.

## Recovery validation evidence

- Production shell invalidation: `I3VSXKMK6TW593SGGE6LG7KOOP`, completed.
- Mobile-player cache-hardening invalidation: `IC8UYHAK9D6UNXVTKNJXN1W0N6`,
  completed.
- Search-player invalidation: `I456OLGKOA6WH2JXWZXYU4FVQI`, completed.
- Search-state/performance invalidation: `I9ENOOQ21W2KQG7UUCYM3DX6VX`,
  completed.
- SHA-256 after invalidation: root/route shell
  `998a9b205923465cd81194ce957b3e7f7886fa1da3385f826435e75272132594`,
  app JavaScript
  `a46ada6c32bd26de32feb582d5a8976561d5a617f4f44d3ce51644263dd60127`,
  stylesheet
  `61a5072cd86a68aaf1830085b6abc10a9beddf039bd4987262808d0fb5d2d995`.
- Production returned `Cache-Control: no-store` for the stylesheet. Mobile and
  desktop browser probes measured the play target at 72 by 56 pixels, observed
  MP3 HTTP 200/206 responses, and proved playback time advanced with no browser
  errors. The production SLO probe passed with mobile clips ready in 681 ms.
- The exact production `Wenatchee` search returned ten matches. Mobile and
  desktop probes found one player per result and proved the first result's
  audio advanced with no console, page, or media errors.
- Before the search fix, a 7-day `Wenatchee` search took 6,584 ms and the
  24-hour request filled ten slots with unrelated scores of 0.211–0.263 while
  still displaying `7d` as selected. After the fix, warm end-to-end searches
  completed in 437–597 ms, the 24-hour response contained zero results, and
  mobile and desktop displayed `24h` as selected during and after the request.
  The reusable `npm run smoke:search` probe delays the 24-hour response by
  500 ms so it deterministically checks the in-flight visual and ARIA state.
- The original two-worker API used approximately 3.97 GB with a 4.74 GB peak.
  The compact single-worker service used 1.28 GB with a 1.39 GB peak and
  reported zero systemd restarts. A warm 24-hour backend
  query logged 21 ms. The two old workers had exited, but no kernel evidence
  supports labeling those exits as OOM kills.
- Post-invalidation production hashes: root shell
  `a61f41c948fb95d4645a6829d2b165b835e36126d29e4ca8d7e7e8ac75e2ccbb`,
  app JavaScript
  `b28b202a2de07b3f091e72545fe63af4daa57b4a0a32f75f301031102ce23392`,
  and stylesheet
  `61a5072cd86a68aaf1830085b6abc10a9beddf039bd4987262808d0fb5d2d995`.
- AIS Lambda code SHA-256:
  `fN3B7mBgcfp7k+lSY/Uqgakr2DQYIyNdEMvJozuC+xc=`; AWS reported `Active` and
  `LastUpdateStatus=Successful`.
- Immediate AIS soak after the Lambda update: 214 starts/214 ends and zero
  Lambda error events; the Pi forwarder logged 216 HTTP 200 responses and zero
  HTTP 500 responses in the same interval.
- Production manifest observed 3,000 clips with a new post-recovery clip; AIS
  snapshots continued advancing with multiple vessels.
- A production `/api/clips/audio` request returned HTTP 200 with no redirect;
  Mutagen decoded the 48 kHz MPEG audio payload successfully.
- The first production SLO run after restarting the proxy had no browser errors
  but one cold API p95 of 1,564 ms against a 1,500 ms budget. The immediate warm
  rerun passed: API p95s 898–1,234 ms, mobile clip ready in 735 ms, load-more in
  1,387 ms, and no console/page errors.
- `talkingboats-talkingboats-prod-public-clips-stale` is `OK` since
  18:27:47 UTC on August 1. `talkingboats-talkingboats-prod-ais-stale` is `OK`
  since 00:29:16 UTC on August 2.
- Focused validation passed: 60 proxy/AIS tests and 35 monitor/IaC tests. The
  final post-recovery full suite passed all 446 tests. Ruff, Markdown lint,
  shell/JavaScript syntax checks, `git diff --check`, the full local browser
  smoke, the production search smoke, and the production SLO probe also passed.

## Follow-up

- [x] Power-cycle the Pi once and attempt previous-boot evidence capture.
- [x] Keep the initiating trigger `unknown`; the previous-boot journal is absent.
- [x] Restore fresh clip and AIS ingest and verify the existing clip alarm is `OK`.
- [x] Promote the dev-tested shell and pass a production mobile/browser SLO probe.
- [x] Fix and deploy the AIS numeric false positive; verify 214 consecutive Lambda
  invocations and 216 Pi forwarder responses with zero errors immediately after
  deployment.
- [x] Deploy the independent AIS freshness alarm and verify it enters `OK`.
- [x] Deploy the Pi reachability check to the recurring OptiPlex health timer.
- [x] Prevent current player JavaScript from loading with a stale stylesheet.
- [x] Render exactly one working player in every transcript-search result.
- [x] Make search controls reflect the active request immediately and cancel
  stale requests.
- [x] Suppress low-confidence semantic matches and vectorize production search.
- [x] Warm the one-worker search runtime after each API restart.
- [ ] Enable and validate persistent journald storage on the Pi.
- [ ] Commit/review the hardening without absorbing unrelated dirty-tree work.
- [ ] Add CI that tests the exact commit and produces an immutable Pi deployment artifact.
- [ ] Automatically deploy that artifact to a separate dev/staging Pi when one exists.
- [ ] Install the memory ceilings from the same reviewed artifact; validate under realistic SDR load before production.
- [ ] Separate production API/database/raw-audio storage from the current dev bucket without losing historical playback.
- [ ] Replace break-glass host deployment with build-once immutable CI artifacts and an auditable production approval.
- [ ] Evaluate a remotely controllable, fail-safe power path only if it cannot create reboot loops or expose the LAN.

## What went well

- AIS Friends and the AWS clip-age alarm detected the outage at the intended
  one-hour threshold.
- Independent clip and AIS timestamps made the shared edge failure clear.
- Existing public artifacts remained available rather than being overwritten
  with empty data.
- Dev and production SLO probes caught both functional browser failures and a
  transient cold-start latency miss before the recovery was declared complete.
- The bounded OpenTofu plans changed only the intended Lambda/alarm resources
  and performed no destroys.

## What did not go well

- There was no out-of-band recovery path after SSH and all Pi services stopped.
- The local healthcheck emitted a false `all_checks_passed` result during a
  complete upstream outage.
- Volatile Pi journald storage erased the previous boot evidence needed to
  identify the initiating trigger.
- Production was serving an older shell, while its live API still selected the
  dev raw-audio bucket. Promotion exposed that hidden environment coupling as a
  browser CORS failure.
- The shell deploy forced HTML and JavaScript revalidation but omitted the
  stylesheet, so a previously cached CSS response could collapse the custom
  player layout on mobile.
- The repository has no checked-in CI workflow for testing and promoting Pi,
  proxy, shell, or OpenTofu changes. The user-approved break-glass recovery is
  therefore less auditable than the required normal release path.
