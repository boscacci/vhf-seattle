# Docker Orchestration

This repo can run the Ubuntu micro-computer-side services in Docker Compose once
the current dev path is stable. The Raspberry Pi SDR capture stays on the Pi for
now because it owns USB devices, Icecast, and local radio service units.

## Why This Helps

The current deployment depends on whichever conda environment is active on the
host. Compose pins the Python runtime, system packages such as `ffmpeg`, and
Python extras in one image so the API, proxy, uploaded-clip transcriber, and
analysis job run from the same dependency set.

## Setup

Install Docker Engine with the Docker Compose v2 plugin on the Ubuntu
micro-computer. The commands below expect `docker compose`, not the legacy
`docker-compose` binary.

Create the ignored runtime env file from the checked-in example:

```bash
cp config/optiplex.env.example config/optiplex.env
```

Fill in the empty token and bucket values from the existing host secret source.
Do not commit `config/optiplex.env`.

Build and start the always-on services:

```bash
docker compose up -d --build private-api live-proxy
```

Start the processed-clip transcription queue when the model/runtime is ready:

```bash
docker compose --profile transcribe up -d uploaded-clip-transcriber
```

Run the analysis/export job on demand:

```bash
docker compose --profile jobs run --rm lexical-refresh
```

## Cutover Plan

1. Keep the existing systemd services running while the image builds.
2. Start Compose on alternate ports or stop one matching systemd service at a
   time.
3. Smoke `/api/live/channels`, `/api/live/performance`, and the private API.
4. Move Tailscale Funnel to the Compose `live-proxy` port only after the smoke
   checks pass.
5. Disable the matching systemd user unit after the Compose service has survived
   a restart.

The deployment scripts are still valid. `scripts/deploy_static_shell.sh` is the
fast path for UI-only changes, while `scripts/refresh_lexical_analysis.sh` is the
full analysis/export path.
