# Security Model

## Public Boundary

`vhf.robertboscacci.com` is public read-only. It serves static app assets and
published clip audio from a private S3 bucket through CloudFront Origin Access
Control, then routes read-only live API paths to the OptiPlex proxy through
Tailscale Funnel.

Public artifacts must not contain:

- raw S3 object keys or presigned URLs;
- receiver IDs;
- internal/private network URLs;
- AWS account IDs or access key material;
- private live-radio stream URLs.

## Compute Boundary

The trusted compute boundary is intentionally local-first:

- **Raspberry Pi:** trusted edge capture node on the private LAN. It may see raw
  RF audio and short local buffers, but it should not hold long-lived AWS
  credentials or expose public controls.
- **OptiPlex:** trusted home processing node. It owns the private API, SQLite
  clip database, transcription workers, retry loops, export jobs, and the
  read-only proxy used by CloudFront.
- **AWS:** durable storage and public edge. S3 receives raw objects only through
  presigned URLs or service-held credentials, and CloudFront exposes only
  sanitized static assets plus narrow read-only live/API routes.
- **Public browser:** untrusted. It can read published clips, recent public clip
  metadata, current status, and live audio, but it cannot retune the receiver,
  request arbitrary LAN URLs, presign uploads, or access private transcripts.

Doing useful work on the Pi and OptiPlex is the point of the system. Security
comes from narrow boundaries, short-lived upload URLs, sanitization, and
read-only public routes, not from pushing all computation into a cloud service.

## Read-Only Clip Console

The clip console is public without a manual token. The same `public-site/` UI
reads recent transcripts, short-lived playback URLs, live status, and the current
read-only live audio stream. It must not expose write endpoints, retune controls,
raw ingest presigning, private network URLs, or arbitrary internal proxying.
Playback URLs are intentionally short-lived. Browser code should refresh those
URLs through the public clip playback refresh route instead of embedding raw
object keys or depending on stale presigned links.

The performance telemetry endpoint is dev-only and gated by configured dev
hostnames or the tailnet dev reverse proxy path. Its public-safe response is a
whitelist of coarse CPU, memory, disk, and thermal health for the OptiPlex proxy
and Raspberry Pi receiver. It must not expose LAN addresses, tailnet hostnames,
service names, process lists, environment variables, internal URLs, tokens, or
arbitrary collector fields.

## Private Boundary

The private API handles:

- Pi clip upload presigning;
- operator playback presigning;
- live-radio proxying;
- public recent-clip export generation.

AIS-catcher stays outside the private API in this pass. The live proxy exposes
the Pi's AIS-catcher web viewer only to dev/local hosts and strips cookies and
authorization headers before forwarding requests.

The AIS-catcher viewer is a larger browser surface than the native clip console:
it runs third-party web UI code, loads map assets, and shows the approximate
receiver station when `TALKINGBOATS_AIS_SHARE_LOC=on`. Keep it off production
until it is isolated behind its own origin or reviewed as a same-origin embed.
Do not expose AIS-catcher control, metrics, or Prometheus paths publicly unless
they have an explicit read-only threat review.

Protect write/admin paths with LAN/Tailscale/VPN plus service-held credentials.
Transcript correction writes must arrive through the tailnet dev reverse proxy,
which marks them with `X-TalkingBoats-Tailnet-Dev: 1`. Do not require an
operator to manually paste tokens into the browser.

The Pi-to-OptiPlex LAN path is private infrastructure. If the Pi cannot reach
the OptiPlex, it should keep bounded local buffers and retry instead of failing
open to public endpoints. If the OptiPlex cannot reach AWS, it should preserve
local state and retry uploads/exports when connectivity returns.

## Retention

- `raw/`: short-lived raw audio, expired by S3 lifecycle after about 60 days.
- `hall-of-fame/`: manually promoted audio retained indefinitely.
- Transcripts and metadata: stored in the private database unless intentionally
  published through the sanitizer.
