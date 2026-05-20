# Security Model

## Public Boundary

`talkingboats.robertboscacci.com` is static-only. It serves reviewed assets from a
private S3 bucket through CloudFront Origin Access Control.

Public artifacts must not contain:

- raw S3 object keys or presigned URLs;
- receiver IDs;
- internal/private network URLs;
- AWS account IDs or access key material;
- unreviewed transcripts;
- live-radio stream URLs.

## Private Boundary

The private API handles:

- Pi clip upload presigning;
- operator playback presigning;
- live-radio proxying;
- public export generation.

Protect it with LAN/Tailscale/VPN plus strong bearer-style header tokens. The
header tokens are intentionally simple for the first local build, but the network
boundary still matters.

## Retention

- `raw/`: short-lived raw audio, expired by S3 lifecycle after about 60 days.
- `hall-of-fame/`: manually promoted audio retained indefinitely.
- Transcripts and metadata: stored in the private database unless intentionally
  published through the sanitizer.
