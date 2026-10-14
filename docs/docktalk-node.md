# DockTalk alongside node

The Pi receives eighteen live channels and records nine: **14, 13, 16, 66A,
78A, 71, 22A, 77, and 65A**. Channels 05A, 06, 09, 10, 67, 68, 69, 72, and
73 have Icecast outputs only. Channel 74 stays excluded. Each live channel is
individually selectable in the app. **All recorded channels** and **Recorded
except Traffic** use saved clips from the nine recorded channels; they are
not an eighteen-channel live mixer. Live-only channels do not display historical
clip timestamps as current activity. Their existing archived clips stay readable.

## Receiver and recording boundary

The release restores the additional channel blocks from the private pre-pruning
receiver backup, preserves retained channel blocks, and removes file outputs for
live-only channels. Frequencies, gain, serial, sample rate, and squelch remain
unchanged. Both receiver generation and deployment preserve the output split.
The currently disabled cloud HLS relay stays disabled; the app uses direct MP3.

The approved production release persists a UTC activation boundary for each newly recorded channel (22A, 77, and 65A)
before enabling its recordings. It is stored in the existing private ASR state
volume and copied to the Pi. Uploads, spool discovery/pruning, normal processing,
and backlog counts exclude recordings on each added channel older than its boundary. Other pruned
channel backlogs remain excluded. Queue checkpoints include the channel policy
and activation identity; the six-channel checkpoint is preserved for rollback.
A retry keeps the original activation time and migration cursor.

The original recovery forecast remains a historical **six-channel, two-thread**
audit. It must not be interpreted as proof of the expanded profile's capacity.
The separate 22A diagnostic used ten audited recordings totaling 73.26 seconds
and took 59.19 seconds on warmed six-thread CPU int8 Turbo, with beam five,
full audio, and no production transcript writes. This small sample excludes
upload/download/preparation overhead and does not prove peak-hour capacity.
The existing continuous shared worker, six threads, and SSD storage stay intact.

## DockTalk identity and isolation

The immutable artifact includes the reviewed upstream installer with the digest
recorded in `config/docktalk.json`. A changed upstream response blocks a new
artifact build until it is reviewed. The upstream root script is packaged for
inspection; it is never executed. The repository client implements its alongside
claim, channel-plan, gzip/chunked HTTPS push, watchdog, and health-report protocol.
It provides no dedicated receiver, Docker, firmware, network-healing, VPN,
automatic software update, or inbound listener path.

The enrollment code lives in the established private runtime configuration,
mode 0600, outside Git. It is transferred through the existing authenticated SSH
path as a private file. Credentials never enter process arguments or logs.
Claim responses are bounded and parsed as literal assignments with an allowlist;
shell execution, duplicate/unknown fields, and incompatible modes are rejected.
The original response is retained privately for recovery before parsing. Once an
identity is saved, retries reuse it without claiming another node.

Root provisioning owns `/etc/docktalk`. The dedicated `docktalk` account can read
its private identity, approved loopback stream map, and validated plan.
It receives no receiver password, USB permission, home-directory access, or
write access to system configuration. The relay is bounded to 25% CPU and
512 MiB RAM, with independent stream retries and structured per-channel errors.
The map is generated from the accepted receiver configuration and matched to
DockTalk by frequency within 2 kHz. All eighteen channels must be covered by the
server plan; missing coverage fails installation without guessing mounts.

The root watchdog can restart only `docktalk-push.service` when DockTalk reports
stale reception after the startup grace period. It does not restart the receiver
or transcriber. Optional health reports are enabled by the operator's choice:
temperature, throttling, CPU frequency, uptime, and basic network status.
An upstream outage leaves local reception and transcription independent.

## Delivery and acceptance

Use the checked-in ASR release script to build one immutable artifact, deploy to
dev, and run Playwright. Dev exercises the expanded selector and live-only labels
with isolated additional-stream fixtures plus the six actual retained feeds.
It does not change the shared Pi or redeem the enrollment code.

After manual dev smoke, approve the release tag, exact artifact, and production
target once. Promotion applies the queue boundary, receiver outputs, app routing,
and node together. It verifies real eighteen-channel playback and observes the
node for at least thirty minutes. Acceptance requires eighteen fresh relay
channels, eighteen Icecast mounts, the correct nine recording outputs, fresh
server-confirmed reception, no new files on live-only channels, and Pi temperature
below 80 C. Failures invoke the release rollback and produce diagnostic logs.

Useful operator checks are `systemctl status docktalk-push`,
`journalctl -u docktalk-push`, and the private `/run/docktalk/health.json`.
Logs distinguish channel retries, partial relay health, plan-refresh failures,
stale server reception, and health-report failures without printing credentials.
Successful promotion retains the soak report with the release's private records.

Rollback disables the DockTalk relay and timers, restores the prior receiver,
spool modules, app sources and public shell, and restores worker startup settings.
It preserves the private node identity and activation boundary for a safe retry.
Historical raw audio, transcripts, corrections, and excluded backlog are retained.

Channels 77 and 65A are the next two optional channels in the seven-day quality
audit. Their combined measured recording volume was 32.02 audio minutes per day.
The continuous six-thread worker may accumulate daytime backlog and catch up
during quieter periods; this extension does not claim the old peak-capacity gate
has passed. Retried activation preserves existing timestamps and adds only missing
channel boundaries. The About page acknowledges DockTalk and the wider AIS-catcher
community, and Performance presents queue status in a single backlog chart.

## Registration recovery and deployment preflight

The alongside claim response may include a literal `PORT_ID`. It is validated as
an identifier alongside the required node, label, token, and mode fields; unknown
fields and executable shell remain rejected. The cached claim response stays
private and is reused after interrupted provisioning, without a second claim.

Before pausing shared services, production deployment reads DockTalk's channel
plan and requires coverage for all eighteen approved frequencies. A six-channel
server plan blocks deployment with the missing channel names in the operator log.
The DockTalk operator must expand the server-side plan; client registration does
not update that plan. Existing receiver and transcriber services remain running
when preflight fails.
