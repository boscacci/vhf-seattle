# Deployment Hygiene

This project has separate dev and prod public edges. Keep the code flow and the
AWS resources separate unless an emergency override is intentional and recorded.

## Branch Policy

- `dev`: integration branch for `https://dev.seattleboatradio.com`. Use this
  for normal validation before promotion. Short-lived `codex/*` or `feature/*`
  branches may deploy to dev while a change is being tested.
- `main`: production branch for `https://seattleboatradio.com`. Prod deploys
  should come from `main` only, after dev has been smoke tested.

First-time branch setup, if the remote only has `main`:

```bash
git fetch origin
git switch -c dev origin/main
git push -u origin dev
```

Normal flow:

```bash
git switch dev
git merge --ff-only codex/my-change
scripts/deploy_public_site.sh dev outputs/public-site

git switch main
git merge --ff-only dev
scripts/deploy_public_site.sh prod outputs/public-site
```

The deploy helper enforces the branch policy by default. It allows dev deploys
from `dev`, `main`, `codex/*`, or `feature/*`, and allows prod deploys only from
`main` with a clean worktree. For a deliberate emergency, set
`TALKINGBOATS_ALLOW_CROSS_ENV_DEPLOY=1` and record why in the operator notes.

Generated public artifacts have a narrower path. The lightweight public clip
refresh runs every 15 minutes, rebuilds `outputs/public-site`, verifies the
exact `public_manifest.json` is visible on dev, then uses
`scripts/deploy_generated_public_assets.sh prod outputs/public-site` to promote
only `public_manifest.json`, `clips/`, and the existing `analysis/` artifacts
to prod. The six-hour lexical refresh shares the same export lock, replaces the
analysis artifacts, performs the same dev validation, and then promotes. This
keeps public clip/audio/analysis data current from the always-on processing host
without allowing an archive deploy copy to change the production app shell.

## Resource Policy

OpenTofu owns durable AWS resources in `infra/opentofu`.
Use the `tofu` CLI only; this repo should not depend on the HashiCorp Terraform
CLI. The HCL `terraform { ... }` block and `.terraform.lock.hcl` filename remain
because OpenTofu intentionally keeps those compatibility points.

| Concern | Dev | Prod |
| --- | --- | --- |
| Branch | `dev`, `codex/*`, `feature/*` | `main` |
| Browser hostname | `dev.seattleboatradio.com` over Tailscale | `seattleboatradio.com` public |
| Static origin | `dev_public_site_bucket` output | `public_site_bucket` output |
| Raw audio | `dev_raw_audio_bucket` output | `raw_audio_bucket` output |
| CloudFront | disabled legacy dev distribution | `cloudfront_distribution_id` output |
| IAM policy | `dev_server_iam_policy_arn` output | `server_iam_policy_arn` output |

Dev and prod buckets, distributions, certificates, and server IAM policies carry
explicit `Environment` tags. Public buckets stay private. Prod is readable only
through CloudFront Origin Access Control; dev is served from the Ubuntu micro-computer
tailnet deployment.

Production clip audio must remain same-origin at `/api/clips/audio`. The public
read-only proxy resolves the private API's signed redirect server-side, accepts
only HTTPS AWS S3 targets, strips viewer credentials, forwards only a bounded
single byte range, caps the buffered clip at 25 MiB, and returns `no-store`.
Do not add the public hostname to a dev bucket CORS allowlist as a shortcut; that
would conceal an environment-routing error and weaken the dev/prod boundary.

The current production/private API operational environment still selects the
dev raw-audio bucket because that bucket contains the active historical corpus.
This is recorded migration debt, not the intended steady state in the resource
table above. Move ingest, private API playback, and historical objects to the
production raw bucket as one reconciled, reversible migration; do not switch
the API bucket alone or old and newly uploaded clips will fail playback.

Route53 points `dev.seattleboatradio.com` at the Ubuntu micro-computer Tailscale address,
not at CloudFront. The Ubuntu micro-computer runs the `deploy/optiplex/vhf-dev-proxy`
front-door container on the tailnet `80/443` addresses. That container owns the
shared Tailnet TLS front door: SNI routes Gotify and Laundry traffic to local Caddy,
while `dev.seattleboatradio.com` terminates on local `9443`, redirects HTTP to
HTTPS, and injects `X-TalkingBoats-Tailnet-Dev: 1` before write-capable operator
requests reach the dev live proxy on `172.20.0.1:8095`. Keep
`vhf-dev-proxy.service` enabled in the lingered `rob` user manager so the container
is restored after scheduled or unscheduled Ubuntu reboots. Pi-hole may serve its
admin UI on alternate ports, but it must not bind the Ubuntu micro-computer tailnet `80/443`
front door. The public Funnel path uses a separate read-only live proxy
without tailnet dev routes, so spoofed viewer headers cannot reach write routes.
Do not reintroduce browser bearer-token auth for the transcript feedback loop.

The dev proxy uses `talkingboats-api-dev.service` on loopback port `8035` and
loads application code from the working checkout through `PYTHONPATH`. The
shared production/private API remains on `8034`; do not restart it for a dev
deploy. Install
`deploy/systemd/talkingboats-live-radio-proxy-dev.conf.example` as the final
drop-in for the dev-only proxy so cursor/API changes can be tested without
changing the public proxy on `8096`.

## Blackout Recovery

The Pi and Ubuntu micro-computer should recover without an operator login after
a neighborhood power loss. Critical systemd services set `StartLimitIntervalSec=0`
so early boot failures from slow network, Docker, Icecast, SDR, or AWS readiness
do not permanently trip systemd's start limiter.

The Pi install deploys `talkingboats-pi-boot-recovery.service`, which resets
failed state and starts the enabled radio services after `network-online.target`.
It starts Icecast, the receiver status web service on `:8050`, AIS capture,
profile capture, the spool uploader, and any enabled gated relays. Disabled
optional relays stay disabled.

The receiver status service is intentionally small: it serves
`/opt/talkingboats/live-radio/current-status.json` on
`http://192.168.1.114:8050/current-status.json` for the OptiPlex live proxy.
The profile capture wrapper rewrites that JSON when it starts, including after
a blackout recovery restart, so the live monitor does not fall back to stale
receiver state from an older debug profile.

The OptiPlex deploy should keep `loginctl enable-linger rob` active and enable
`talkingboats-optiplex-boot-recovery.service` in the `rob` user manager. That
service resets failed state and starts the private API, uploaded-clip
transcriber, dev and public live proxies, the dev Tailnet proxy, and the refresh
timers. `talkingboats-lexical-refresh.timer` uses both `OnBootSec=15min` and
`OnStartupSec=15min` so generated public/search artifacts refresh after either a
machine reboot or a delayed user-manager start.

The private API resolves the current IPv4 address on `eth0` within
`TALKINGBOATS_LAN_NETWORK` before binding its LAN-only listener. The uploaded-clip
transcriber and lexical refresh also use that bounded resolver and wait for DNS
resolution of DynamoDB. This prevents a DHCP lease change or temporary LAN
outage from creating an API bind-loop or AWS/DNS restart storm.

The Pi health timer probes `TALKINGBOATS_PRIVATE_API/healthz` after confirming
that the spool uploader is running. It reports an unreachable private API but
does not restart the uploader in a tight loop. Configure that endpoint as a
stable, resolvable name (or a DHCP reservation); a literal DHCP address must be
updated whenever the OptiPlex lease changes.

The same health timer treats more than 240 completed multichannel spool files
within two minutes as an SDR capture flood. It restarts profile capture, emits
structured restart and recovery events, and applies a five-minute cooldown so
a bad tuner state cannot overwhelm the uploader without creating a restart
loop. Override the window, limit, or cooldown with
`TALKINGBOATS_PI_SPOOL_FLOOD_WINDOW_MINUTES`,
`TALKINGBOATS_PI_SPOOL_FLOOD_MAX_FILES`, and
`TALKINGBOATS_PI_SPOOL_FLOOD_COOLDOWN_MINUTES` when receiver traffic is
materially different.

The spool uploader discards completed clips shorter than one second before
requesting an upload. These subsecond squelch artifacts cannot produce useful
transcripts and would otherwise consume both network and transcription
capacity. Override the threshold with
`TALKINGBOATS_SPOOL_MIN_DURATION_SECONDS` only after reviewing receiver output.
Clips whose duration cannot be probed are retained and uploaded.

The uploader also discards a same-second capture batch when more than three
distinct channels open together. Marine transmissions on independent
frequencies cannot produce that pattern; it indicates a wideband interference
burst. Override the limit with
`TALKINGBOATS_SPOOL_MAX_SYNCHRONOUS_CHANNELS`, or set it to `0` to disable the
guard while diagnosing the receiver.

Production uploader polls process at most 20 candidates so a noisy backlog
cannot pin the sequential uploader to one batch for more than a few minutes.
Each new poll selects the newest stable clips first.

Profile capture also has a 24-hour runtime limit. Because its service uses
`Restart=always`, systemd reinitializes the SDR once per day instead of leaving
the tuner and its USB state alive indefinitely.

`talkingboats-mdns-advertiser.service` publishes `optiplex.local` only on the
OptiPlex LAN interface and re-registers it if DHCP assigns a new address. Keep
the Pi uploader pointed to `http://optiplex.local:8034`; it must resolve and
pass `/healthz` before treating a capture pipeline as healthy.

## Operator Checklist

Before dev deploy:

- Confirm the target is `dev`.
- Confirm the branch is `dev`, `main`, `codex/*`, or `feature/*`.
- Run the relevant tests for the changed area.
- Smoke `https://dev.seattleboatradio.com` from a tailnet-connected device.

Before prod deploy:

- Merge the tested dev change into `main`.
- Confirm `git status --short` is empty.
- Run the relevant tests again from `main`.
- Deploy with `scripts/deploy_public_site.sh prod outputs/public-site`.
- Smoke `https://seattleboatradio.com`.

Before generated artifact promotion:

- Confirm `outputs/public-site/public_manifest.json` has the expected
  `generated_at` and newest clip timestamp.
- Deploy with `scripts/deploy_generated_public_assets.sh prod outputs/public-site`.
- Smoke `https://seattleboatradio.com/public_manifest.json` and a recent
  non-traffic clip page.

After apartment power loss:

- From the OptiPlex, confirm `192.168.1.114` answers SSH.
- Confirm Icecast at `http://192.168.1.114:8000/status-json.xsl`.
- Confirm receiver status at
  `http://192.168.1.114:8050/current-status.json`.
- Confirm AIS at `http://192.168.1.114:8100/`.
- Confirm prod `/api/clips/recent?limit=1` has a post-recovery timestamp after
  the transcriber catches up.
