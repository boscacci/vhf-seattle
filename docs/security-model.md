# Security Model

## Public Boundary

`vhf.robertboscacci.com` is static-only. It serves recent exported clip metadata
and copied public audio files from a private S3 bucket through CloudFront Origin
Access Control.

Public artifacts must not contain:

- raw S3 object keys or presigned URLs;
- receiver IDs;
- internal/private network URLs;
- AWS account IDs or access key material;
- live-radio stream URLs.

## Read-Only Clip Console

The clip console can be public or Tailscale-served without a manual token. The
same `public-site/` UI either reads static exported clips or, on Tailscale,
reads recent transcripts plus short-lived playback URLs. It must not expose
write endpoints, retune controls, raw ingest presigning, private network URLs,
or arbitrary internal proxying.

## Private Boundary

The private API handles:

- Pi clip upload presigning;
- operator playback presigning;
- live-radio proxying;
- public recent-clip export generation.

Protect write/admin paths with LAN/Tailscale/VPN plus service-held credentials.
Do not require an operator to manually paste tokens into the browser.

## Retention

- `raw/`: short-lived raw audio, expired by S3 lifecycle after about 60 days.
- `hall-of-fame/`: manually promoted audio retained indefinitely.
- Transcripts and metadata: stored in the private database unless intentionally
  published through the sanitizer.
