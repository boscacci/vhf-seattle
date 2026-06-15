<h1 align="center">Elliott Bay Marine VHF Monitor</h1>

<p align="center">
  <strong>
    Raspberry Pi marine VHF capture, home-lab processing, and public read-only monitoring for Elliott Bay.
  </strong>
</p>

<p align="center">
  <a href="https://vhf.robertboscacci.com">Production site</a> &middot;
  <a href="https://vhf-dev.robertboscacci.com">Dev site</a> &middot;
  <a href="https://robertboscacci.com/projects/elliott-bay-vhf/">Project post</a> &middot;
  <a href="docs/security-model.md">Security model</a> &middot;
  <a href="docs/deployment-hygiene.md">Deployment hygiene</a>
</p>

<p align="center">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-private%20API-009688?style=flat-square">
  <img alt="Raspberry Pi" src="https://img.shields.io/badge/Raspberry%20Pi-radio%20edge-C51A4A?style=flat-square">
  <img alt="OpenTofu" src="https://img.shields.io/badge/IaC-OpenTofu-FFDA18?style=flat-square">
  <img alt="AWS" src="https://img.shields.io/badge/AWS-S3%20%2B%20CloudFront%20%2B%20DynamoDB-232F3E?style=flat-square">
</p>

<p align="center">
  <img
    src="https://media.robertboscacci.com/photos/elliott-bay-vhf/topic-clusters.gif"
    alt="Animated transcript topic cluster view for Elliott Bay marine VHF transcripts."
    width="100%"
  >
</p>

## What It Does

This repo runs a home-lab marine radio pipeline for nearby Elliott Bay VHF
traffic. It captures live radio at the antenna, processes clips and transcripts
on a private home server, and publishes a public read-only web interface.

The public site includes:

- live HLS audio for monitored marine VHF channels;
- AIS vessel positions bounded to local waters;
- recent clips, transcripts, search, and Hall of Fame clips;
- transcript language analysis and topic clustering;
- a dev/operator path for transcript correction and telemetry.

Production browsers read only public surfaces. They do not connect directly to
the Raspberry Pi, Ubuntu micro-computer private API, LAN Icecast URLs, Tailscale/Funnel
origins, raw S3 objects, DynamoDB, receiver controls, or write-capable routes.

## Runtime Layers

| Layer | Runs On | Owns |
| --- | --- | --- |
| Radio edge | Raspberry Pi + RTL-SDR | VHF voice capture, AIS decode, HLS segment generation, activity detection, clip spooling, bounded local buffers |
| Home processing | Ubuntu micro-computer | Private API, presigned raw-audio uploads, transcription, transcript corrections, public exports, telemetry |
| AWS public edge | S3, CloudFront, DynamoDB, API Gateway/Lambda | Private static origins, public read-only delivery, durable clip state, AIS ingest, TLS, DNS |

The normal path is:

```text
antenna -> RTL-SDR -> Raspberry Pi -> private LAN -> Ubuntu micro-computer -> AWS public edge -> browser
```

## Architecture

<p align="center">
  <img
    src="https://media.robertboscacci.com/photos/elliott-bay-vhf/production-boundary.png"
    alt="Production boundary diagram for Elliott Bay VHF."
    width="100%"
  >
</p>

Current boundary decisions:

- Production CloudFront uses private S3 origins; it is not a production website
  origin back to the Ubuntu micro-computer.
- The Pi publishes outbound only, using scoped cloud resources.
- The Ubuntu micro-computer stays private/dev infrastructure for CPU-heavy and stateful work.
- Dev/operator paths can reach the Ubuntu micro-computer private API over the tailnet.
- SQLite is retained only for explicit legacy backfills, local fixtures, and
  separate realtime telemetry.

## Radio And Live Paths

Radio capture:

- RTLSDR-Airband monitors a 12-channel marine VHF profile: 05A, 06, 09, 13, 14,
  16, 22A, 67, 68, 69, 71, and 72.
- VHF 14 is the default live feed for Seattle Traffic / Puget Sound VTS.
- AIS-catcher runs on the Pi with either the dedicated AIS RTL-SDR or the
  dAISy-catcher serial receiver around 162 MHz.
- Major shout-out to [Adrian Studer](https://github.com/astuder) and
  [Jasper](https://github.com/jvde-github) for building the dAISy-catcher and
  mailing one over for this project.

Live audio:

- The Pi converts local Icecast output into short HLS playlists and segments.
- `talkingboats.hls_publisher` writes HLS objects to the public-site S3
  `live/` prefix.
- CloudFront serves `/live/current.m3u8`, `/live/channels.json`, and per-channel
  playlists such as `/live/channels/14/current.m3u8`.

AIS:

- AIS-catcher decodes vessel messages on the Pi.
- A local forwarder sends sanitized-bound input to API Gateway over outbound
  HTTPS.
- Lambda strips private fields and bounds the public payload to local waters.
- Public reads use `/ais/latest.json` and
  `wss://ais-live.robertboscacci.com/v1`.

## Processing Path

Clip processing:

- The Pi creates activity clips and sidecar metadata.
- The Pi asks the Ubuntu micro-computer private API for short-lived presigned upload URLs.
- Raw audio stays in private S3.
- DynamoDB stores clip events, transcripts, corrections, and serving read
  models.
- The Ubuntu micro-computer runs `faster-whisper`, review/correction workflows, lexical
  analysis, topic clustering, and public exports.

Default edge audio/transcription settings:

```bash
TALKINGBOATS_AUDIO_FILTER_ENABLED=true
TALKINGBOATS_TRANSCRIBE_SAMPLE_RATE_HZ=16000
TALKINGBOATS_TRANSCRIBE_BEAM_SIZE=5
TALKINGBOATS_TRANSCRIBE_HOTWORDS="Seattle Traffic,VTS,Puget Sound"
TALKINGBOATS_TRANSCRIBE_TRUST_EDGE_PREPROCESSED_AUDIO=true
```

Retention and export:

- Unstarred raw `raw/` audio expires after 90 days.
- Starred Hall of Fame clips are tagged for longer retention.
- Public exports strip private fields, raw keys, internal URLs, account IDs, and
  nondisplayable transcript artifacts.
- Playback controls are shown only when public audio can still be resolved.

## ASR Feedback Loop

<p align="center">
  <img
    src="https://media.robertboscacci.com/photos/elliott-bay-vhf/whisper-fine-tuning.png"
    alt="Whisper fine-tuning feedback loop diagram for Elliott Bay VHF."
    width="100%"
  >
</p>

Transcript corrections become supervised training examples by default:

- The operator UI saves original/corrected transcript pairs to DynamoDB, marks
  them for training by default with `good` quality metadata, and still allows a
  deliberate opt-out for odd clips.
- On dev, the tailnet-gated `/api/clips/corrections` endpoint lists reviewed
  corrections with playback-safe `audio_url` values; `/api/clips/corrections/export`
  remains limited to training-eligible examples.
- Manual ASR feedback training checks for enough reviewed corrections and skips
  unchanged datasets by fingerprint.
- Raw private S3 audio is archived locally and paired with corrected text into
  training JSONL so later retries do not depend on short-lived raw-object access.
- The configured Whisper checkpoint is fine-tuned, converted to CTranslate2,
  evaluated against the local baseline, and promoted through `latest-ct2` only
  when the candidate model improves transcription accuracy.

Default guardrails are defined in `src/talkingboats/asr_feedback.py`, including
the minimum reviewed correction count, base model, fingerprinting, model
promotion, and transcriber restart behavior.

## Local Setup

Use the existing `dell` conda environment on the Ubuntu micro-computer:

```bash
conda run -n dell python -m pip install -e ".[dev]"
conda run -n dell pytest
```

Install browser tooling for local smoke tests:

```bash
npm install
npm run browser:install
npm run browser:doctor
npm run smoke:browser
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

If you are on a MacBook or another client machine instead of the Ubuntu micro-computer, use
SSH to the Ubuntu micro-computer for service-state work, Pi systemd work, export jobs,
transcription workers, and OpenTofu operations. Direct static-site syncs from a
client machine are acceptable only for emergency static UI fixes where existing
manifests and clip objects are preserved.

## Deployment And Infrastructure

Infrastructure is managed with OpenTofu under `infra/opentofu`:

- separate dev/prod static-site buckets;
- separate dev/prod private raw-audio buckets;
- separate DynamoDB event tables;
- CloudFront Origin Access Control for private S3 origins;
- API Gateway/Lambda AIS ingest and WebSocket delivery;
- ACM certificates, Route 53 records, and scoped IAM policies.

Use OpenTofu, not Terraform:

```bash
cd infra/opentofu
tofu init
tofu fmt -recursive
tofu validate
tofu plan
```

Static site deploy helpers enforce branch and environment hygiene:

```bash
scripts/deploy_public_site.sh dev outputs/public-site
scripts/deploy_public_site.sh prod outputs/public-site
```

The scheduled lexical refresh rebuilds generated public artifacts, full-deploys
the dev export, and promotes only `public_manifest.json`, `clips/`, and
`analysis/` to prod so the public clips stay current without bypassing the
main-branch guard for shell changes.

## Useful Docs

- [Security model](docs/security-model.md)
- [Deployment hygiene](docs/deployment-hygiene.md)
- [Hardware guide](docs/hardware-guide.md)
- [Performance telemetry](docs/performance.md)
- [Durable event store](docs/durable-event-store.md)
- [Docker orchestration notes](docs/docker-orchestration.md)

## First Hardware Target

- VHF voice receiver: RTL-SDR near the antenna.
- AIS receiver: second RTL-SDR around 162 MHz.
- Edge computer: Raspberry Pi beside the radio hardware.
- Home server: Ubuntu micro-computer on the LAN.
- Public edge: AWS S3, CloudFront, DynamoDB, API Gateway/Lambda, ACM, and
  Route 53.
