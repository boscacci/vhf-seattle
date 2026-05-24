# Seattle Marine Radio

Seattle Marine Radio captures Elliott Bay marine VHF, transcribes useful chunks,
publishes recent clips, and exposes live receiver audio only through Tailscale.

- **Private side:** Raspberry Pi capture, raw audio, ingest API, transcription
  workers, and the clip SQLite database.
- **Public side:** one dark browser UI in `public-site/`, deployed at
  `vhf.robertboscacci.com` for static clips and served through Tailscale for
  fresh DB reads plus live receiver audio.

The public static deploy contains copied clip audio and sanitized transcript
metadata. It never exposes the Pi, private API, Icecast stream, database, raw S3
keys, or presigned URLs.

## Architecture

```mermaid
flowchart LR
    antenna["Elliott Bay VHF antenna"] -->|"RF audio"| pi["Raspberry Pi SDR capture"]
    pi -->|"Presigned clip uploads"| api["OptiPlex private API"]
    pi -->|"Current MP3 stream"| proxy["Tailnet live proxy"]
    api -->|"Raw clip objects"| raw["Private raw-audio S3"]
    worker["Uploaded clip transcriber"] -->|"Downloads audio"| raw
    worker -->|"Writes transcripts"| db["SQLite clip DB"]
    api -->|"Reads recent clips"| db
    exporter["Public site exporter"] -->|"Reads reviewed clips"| db
    exporter -->|"Copies sanitized audio and manifest"| publicS3["Private public-site S3"]
    publicS3 -->|"Origin access only"| cdn["CloudFront"]
    dns["Route53"] -->|"vhf / vhf-dev aliases"| cdn
    browser["Public browser"] -->|"Static clip review"| cdn
    tailnet["Tailscale browser"] -->|"Live monitor and fresh clips"| proxy
    proxy -->|"Read-only clip API"| api
```

I attempted to generate the same diagram in FigJam through the Figma connector,
but the connector token was expired in this session. The Mermaid source above is
kept in-repo so GitHub renders it without relying on a separate design tool.

## First Build Target

- Fun channel: VHF 68, `156.425 MHz`
- Business channel: VHF 14, `156.700 MHz` Seattle Traffic / Puget Sound VTS
- Raw audio: private S3 bucket, `raw/` expires after 60 days
- Prod public site: static S3 origin behind CloudFront Origin Access Control at
  `vhf.robertboscacci.com`
- Dev public site: separate static S3 origin and CloudFront distribution at
  `vhf-dev.robertboscacci.com`

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

Shared radio UI through the private API:

```text
http://localhost:8034/operator/
```

The browser UI shows recent transcribed clips and a separate live-monitor tab.
When served through the tailnet proxy it reads `/api/clips/recent` and
`/api/live/current.mp3`; when deployed statically it reads `public_manifest.json`
and copied public audio files. The live monitor in the public static page points
at the Tailscale HTTPS endpoint, so it works for authenticated tailnet devices
without exposing LAN services.

## Fake Radio Simulator

Use the simulator for local exporter tests. It creates small synthetic WAV clips
plus a private manifest shaped like public clip data.

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

## Pi Live Radio Smoke

After an RTL-SDR and antenna are plugged into the Pi, verify the dongle:

```bash
ssh rob@talkingboats-pi.local rtl_test -t
```

Install the capture services from a repo checkout on the Pi:

```bash
sudo deploy/pi/install_live_radio.sh
```

The installer creates a root-only `/etc/talkingboats/live-radio.env`, configures
Icecast with generated local source credentials, and starts:

- `talkingboats-edge-live-radio-stream.service`: one `rtl_fm` process teed
  through the Pi edge detector and then to Icecast MP3.
- `talkingboats-profile-capture.service`: default debug profile that alternates
  NOAA and VHF 14 for fast transcription feedback.
- `talkingboats-spool-uploader.service`: uploads completed multichannel spool
  files when durable upload env vars are present.

For a continuous signal check, override the frequency before the first install,
for example a local NOAA weather channel:

```bash
sudo env TALKINGBOATS_LIVE_FREQUENCY_HZ=162550000 \
  TALKINGBOATS_LIVE_LABEL="NOAA Weather" \
  deploy/pi/install_live_radio.sh
```

## Pi Edge Processing

Keep the cheap, real-time radio work on the Pi:

- SDR demodulation with `rtl_fm`.
- Live mono MP3 encoding for debug streaming.
- RMS activity detection on raw PCM before encoding.
- Bounded clip spooling under `/opt/talkingboats/spool/clips`.
- Continuous rolling WAV recording under `/opt/talkingboats/spool/continuous`.
- Clip sidecar metadata: channel, UTC timestamps, duration, sample rate, RMS, peak.
- Thermal/load guardrails before optional heavier work.

Keep heavier or stateful work on the OptiPlex:

- Private API, S3 presigning, database, transcription, publishing.
- Backfills and reprocessing of already-spooled clips.

The edge stream service uses one SDR pipeline:

```text
rtl_fm -> ffmpeg cleanup -> talkingboats-edge-capture --tee-stdout -> ffmpeg -> Icecast
```

The systemd unit also sets `Nice=5`, lower I/O priority, and `CPUQuota=85%`.
Tune thresholds in `/etc/talkingboats/live-radio.env`:

```bash
TALKINGBOATS_EDGE_THRESHOLD_RMS=8000
TALKINGBOATS_EDGE_MIN_CLIP_SECONDS=0.7
TALKINGBOATS_EDGE_POST_ROLL_SECONDS=1.2
TALKINGBOATS_EDGE_MAX_CLIP_SECONDS=45
TALKINGBOATS_EDGE_RECORD_ENABLED=true
TALKINGBOATS_EDGE_RECORD_SEGMENT_SECONDS=300
TALKINGBOATS_EDGE_RECORD_RETENTION_SECONDS=86400
TALKINGBOATS_EDGE_RECORD_UPLOAD_ENABLED=false
TALKINGBOATS_EDGE_UPLOAD_ENABLED=false
TALKINGBOATS_EDGE_UPLOAD_ENCODE_MP3=true
TALKINGBOATS_LIVE_SQUELCH=20
TALKINGBOATS_EDGE_MAX_TEMP_C=72
TALKINGBOATS_EDGE_RESUME_TEMP_C=66
TALKINGBOATS_EDGE_MAX_LOAD_PER_CPU=0.85
```

The debug profile overrides NOAA to reduce tiny forecast fragments:

```bash
TALKINGBOATS_CAPTURE_DEBUG_WX_MIN_CLIP_SECONDS=4
TALKINGBOATS_CAPTURE_DEBUG_WX_POST_ROLL_SECONDS=4.5
TALKINGBOATS_CAPTURE_DEBUG_WX_MAX_CLIP_SECONDS=30
```

The default local rolling buffer is five-minute WAV segments with 24-hour
retention. Raw audio uploaded to the private S3 `raw/` prefix is governed by the
OpenTofu lifecycle rule and expires after 60 days; the Pi-local buffer is only a
short retry/debug cache so it cannot grow without bound.

Enable durable activity-clip upload only after the private API is reachable from
the Pi and `TALKINGBOATS_INGEST_TOKEN` is configured in
`/etc/talkingboats/live-radio.env`:

```bash
sudo sed -i 's/^TALKINGBOATS_EDGE_UPLOAD_ENABLED=.*/TALKINGBOATS_EDGE_UPLOAD_ENABLED=true/' \
  /etc/talkingboats/live-radio.env
sudo systemctl restart talkingboats-edge-live-radio-stream.service
```

When the private API has `TALKINGBOATS_CLIP_DB_PATH` set, every presigned
activity upload is recorded in SQLite before the Pi PUTs the object to S3. Run
the uploaded clip transcriber on the OptiPlex to retry pending uploads and store
per-clip transcript segments:

```bash
conda run -n dell talkingboats-transcribe-uploaded-clips \
  --db-path /home/rob/.local/share/talkingboats/live-transcripts.sqlite3 \
  --bucket talkingboats-raw-audio \
  --poll-seconds 30
```

The worker writes `uploaded_clips` and `uploaded_clip_segments` rows in the same
SQLite file used by live captions. Missing S3 objects stay in `waiting_upload`
and are retried later, so API presign success and actual object upload can remain
eventually consistent.

The uploaded-clip transcriber keeps VAD off by default so it can hear through
short NOAA pauses, then drops individual Whisper segments below
`TALKINGBOATS_TRANSCRIBE_MIN_SEGMENT_AVG_LOGPROB=-0.6` so static-only clips do
not get promoted as stock phrases like "Thank you." Set the value much lower,
such as `-10`, when deliberately auditing weak-signal audio.

NOAA/speech cleanup is on by default and runs before the edge detector, so
uploaded clips and live debug audio use the same filtered PCM. The default chain
does not include dynamic normalization because that can raise static before the
activity gate. Turn cleanup off only for an A/B test:

```bash
sudo sed -i 's/^TALKINGBOATS_AUDIO_FILTER_ENABLED=.*/TALKINGBOATS_AUDIO_FILTER_ENABLED=false/' \
  /etc/talkingboats/live-radio.env
sudo systemctl restart talkingboats-edge-live-radio-stream.service
```

Default filter chain:

```bash
TALKINGBOATS_AUDIO_FILTER_ENABLED=true
TALKINGBOATS_AUDIO_FILTER=highpass=f=250,lowpass=f=3200,afftdn=nf=-28
```

## Live Transcription

Install the optional open-source transcriber dependencies on the OptiPlex:

```bash
conda run -n dell python -m pip install -e ".[transcribe]"
conda install -n dell -y -c conda-forge ffmpeg
```

Run captions from the OptiPlex against the Pi Icecast stream:

```bash
conda run -n dell talkingboats-live-transcriber \
  --stream-url http://talkingboats-pi.local:8000/talkingboats-live.mp3 \
  --host 0.0.0.0 \
  --port 8055 \
  --model-size turbo \
  --device cpu \
  --compute-type int8
```

The transcriber uses `faster-whisper` with Whisper `turbo` by default because it
is a practical open-source CPU path for this hardware. If an `ffmpeg` binary is
available it downsamples live audio to 16 kHz mono and applies the same speech
cleanup filter before transcription; otherwise it falls back to pulling short MP3
chunks from Icecast and decoding them through PyAV/faster-whisper. It serves:

```text
http://optiplex.local:8055/api/live-transcript
```

For a single tailnet-authenticated browser origin, run the OptiPlex proxy and
point Tailscale Serve at it:

```bash
conda run -n dell talkingboats-live-radio-proxy \
  --host 100.124.5.39 \
  --port 8095
tailscale serve --bg --https=10000 http://100.124.5.39:8095
```

The proxy serves the same `public-site/` UI, forwards only the read-only
recent-clip API call to the private API, and exposes a read-only current receiver
stream at:

```text
https://optiplex.tailbea63b.ts.net:10000/api/live/current.mp3
```

`/api/live/current.mp3` probes the known Pi Icecast mounts and connects to the
first active one, which is useful while the debug profile alternates between
NOAA and VHF 14. Caption and retune endpoints remain off by default; enable them
explicitly with `TALKINGBOATS_PROXY_ENABLE_DEBUG_ENDPOINTS=true` on a
Tailscale-only service.

The simple `talkingboats-live-radio-stream.service` remains installed as an
escape hatch, but the installer disables it so only one process owns the SDR.

## Public Export

The primary exporter turns the recent transcribed clip DB into a static site with
copied public audio files.

```bash
conda run -n dell talkingboats-export-public \
  --clip-db-path /home/rob/.local/share/talkingboats/live-transcripts.sqlite3 \
  --raw-bucket "$(cd infra/opentofu && tofu output -raw raw_audio_bucket)" \
  --site-source public-site \
  --output-dir outputs/public-site
```

The older private-manifest mode remains for local simulator tests only.

Deploy dev first, then prod after the public checks look right:

```bash
scripts/deploy_public_site.sh dev outputs/public-site
scripts/deploy_public_site.sh prod outputs/public-site
```

Public URLs:

- Dev: `https://vhf-dev.robertboscacci.com`
- Prod: `https://vhf.robertboscacci.com`

## AWS Infrastructure

Infrastructure lives in `infra/opentofu`.

```bash
cd infra/opentofu
tofu init
tofu plan
```

Do not run `tofu apply` until the bucket names, AWS profile, and Route 53 hosted
zone are confirmed. The stack creates paid AWS resources: separate dev/prod S3
buckets, CloudFront distributions, ACM certificate validation records, Route 53
alias records, and IAM policies for private server publishing.

## Security Rules

- Raw audio buckets are private and have public access blocked.
- Public buckets are private and readable only by their matching CloudFront OAC.
- The Pi does not get long-lived AWS credentials; it asks the private API for a
  short-lived presigned upload URL.
- Live radio is available through Tailscale Serve only; public static hosting
  never exposes a LAN Icecast URL.
- Public exports reject private URLs, raw S3 keys, receiver IDs, AWS account IDs,
  and unreviewed transcripts.
