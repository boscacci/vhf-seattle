# Talking Boats

Talking Boats is a public/private split for an Elliott Bay VHF marine-radio and AIS
project.

- **Private side:** Raspberry Pi capture, raw audio, live radio, ingest API,
  transcription workers, Postgres/PostGIS, review tools.
- **Public side:** static CloudFront site at `talkingboats.robertboscacci.com`
  generated only from reviewed/sanitized data.

The public site never connects to the Pi, private API, Icecast stream, database, or
raw S3 bucket.

## First Build Target

- Fun channel: VHF 68, `156.425 MHz`
- Business channel: VHF 14, `156.700 MHz` Seattle Traffic / Puget Sound VTS
- AIS receiver: local AIS messages for vessel context
- Raw audio: private S3 bucket, `raw/` expires after 60 days
- Hall of Fame: promoted clips retained indefinitely
- Public site: static S3 origin behind CloudFront Origin Access Control

## Local Setup

Use the existing `dell` conda environment on the OptiPlex:

```bash
conda run -n dell python -m pip install -e ".[dev]"
conda run -n dell pytest
```

Run the private API locally:

```bash
cp config/examples/private-api.env.example .env
# edit .env, then export it in your shell
conda run -n dell uvicorn talkingboats.api:app --reload --host 0.0.0.0 --port 8034
```

Private operator UI:

```text
http://localhost:8034/operator/
```

The operator UI uses the operator token to create a short-lived private session
cookie, then plays live radio through the authenticated API proxy. Keep this UI on
LAN/Tailscale/VPN; do not expose it through the public CloudFront site.

## Fake Radio Simulator

Use the simulator while the SDR hardware is still in the mail. It creates small
synthetic WAV clips plus a private manifest shaped like reviewed VHF/AIS data.

```bash
conda run -n dell talkingboats-simulate-radio \
  --output-dir outputs/simulated-radio \
  --clip-count 8 \
  --seed 20260520 \
  --started-at 2026-05-20T19:12:00Z
```

The generated private manifest intentionally includes private-only fields such as
receiver IDs and raw S3 keys. The public exporter strips those fields before
anything can be published:

```bash
conda run -n dell talkingboats-export-public \
  --private-manifest outputs/simulated-radio/private_manifest.json \
  --site-source public-site \
  --output-dir outputs/public-site \
  --audio-source-dir outputs/simulated-radio/audio
```

## Manual Clip Upload

The Pi-side uploader can be tested with any local audio file before the SDR
pipeline exists. It asks the private API for a presigned S3 upload URL, then PUTs
the clip to that URL. The idempotency key is derived from the channel, timestamp,
and audio bytes so retries of the same clip land on the same raw object key.

```bash
export TALKINGBOATS_PRIVATE_API=http://optiplex.local:8034
export TALKINGBOATS_INGEST_TOKEN=replace-with-private-pi-ingest-token

conda run -n dell talkingboats-upload-clip \
  --channel 68 \
  --audio-path outputs/simulated-radio/audio/some-clip.wav \
  --started-at 2026-05-20T19:12:00Z
```

## Raspberry Pi Reflash

The Pi capture node is prepared from a clean Raspberry Pi OS Lite image. A true
reflash requires the microSD card to be attached to the OptiPlex; it cannot be
safely done over SSH while the Pi is booted from that same card.

Once the card is inserted, identify it with `lsblk`, then run:

```bash
sudo scripts/prepare_pi_sd.sh /dev/sdX
```

Optional Wi-Fi setup avoids storing the password in shell history:

```bash
read -rsp "Wi-Fi password: " WIFI_PASSWORD
printf '%s' "$WIFI_PASSWORD" > /tmp/talkingboats-wifi-pass
sudo scripts/prepare_pi_sd.sh /dev/sdX \
  --wifi-ssid "YourNetworkName" \
  --wifi-password-file /tmp/talkingboats-wifi-pass
rm /tmp/talkingboats-wifi-pass
```

The script writes Raspberry Pi OS Lite 32-bit, enables SSH with
`/home/rob/.ssh/id_ed25519.pub`, creates user `rob`, blacklists the DVB kernel
driver that conflicts with RTL-SDR, copies the project Pi config examples, and
installs first-boot packages for SDR capture.

Default image: Raspberry Pi OS Lite 32-bit, Debian Trixie, 21 Apr 2026. Override
with `RPI_IMAGE_URL` and `RPI_IMAGE_SHA256` if Raspberry Pi publishes a newer
image before we flash.

If an early card was flashed with the duplicate UID bootstrap bug, repair it
offline after inserting the card back into the OptiPlex:

```bash
sudo scripts/repair_pi_user_sd.sh /dev/sdc
```

## Public Export

The exporter turns reviewed private metadata into static files.

```bash
conda run -n dell talkingboats-export-public \
  --private-manifest examples/reviewed_clips.example.json \
  --site-source public-site \
  --output-dir outputs/public-site
```

`outputs/public-site` can be synced to the public S3 website bucket created by the
OpenTofu stack.

## AWS Infrastructure

Infrastructure lives in `infra/opentofu`.

```bash
cd infra/opentofu
tofu init
tofu plan
```

Do not run `tofu apply` until the bucket names, AWS profile, and Route 53 hosted
zone are confirmed. The stack creates paid AWS resources: S3 buckets, CloudFront,
ACM certificate validation records, Route 53 alias records, and an IAM policy for
the private server.

## Security Rules

- Raw audio bucket is private and has public access blocked.
- Public bucket is private and readable only by CloudFront OAC.
- The Pi does not get long-lived AWS credentials; it asks the private API for a
  short-lived presigned upload URL.
- Private live radio is authenticated and never exported to the public site.
- Public exports reject private URLs, raw S3 keys, receiver IDs, AWS account IDs,
  and unreviewed transcripts.
