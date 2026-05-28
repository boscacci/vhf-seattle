# Hardware Guide

## Apartment Layout

Keep the RF path short and move data over the LAN. The antenna and RTL-SDR sit
near the best window; the Raspberry Pi is the small edge computer beside them.
The OptiPlex stays where it belongs as the home server with more CPU, disk, and
stable services.

```mermaid
flowchart LR
  antenna["Window VHF antenna"]
  sdr["RTL-SDR<br/>marine VHF receiver"]
  pi["Raspberry Pi edge node<br/>rtl_fm, Icecast, activity clips"]
  lan["Private LAN / Wi-Fi"]
  optiplex["OptiPlex home server<br/>API, SQLite, transcription, export"]
  s3raw["Private S3 raw audio<br/>raw/ expires, hall-of-fame/ retained"]
  s3site["Private S3 public-site origin"]
  public["CloudFront public app<br/>vhf / vhf-dev"]

  antenna -->|RF at 156-162 MHz| sdr
  sdr -->|USB samples| pi
  pi -->|clip requests, status, live MP3| lan
  lan --> optiplex
  optiplex -->|presigned raw uploads| s3raw
  optiplex -->|sanitized exports| s3site
  s3site --> public
  public -->|read-only live API origin| optiplex
```

This layout is intentional. The Pi is not a weak substitute for the OptiPlex; it
is the right place for low-latency radio plumbing because it is physically close
to the antenna and SDR. The OptiPlex is the right place for local CPU-heavy and
stateful work: transcription, retry loops, SQLite, publishing, and the public
proxy. AWS is the durable/public edge, not the place where every radio decision
has to happen.

## Signal And Data Path

The normal path is:

```text
antenna -> RTL-SDR -> Raspberry Pi -> private LAN -> OptiPlex -> AWS public edge
```

- **RF and USB:** the antenna feeds the RTL-SDR, and the SDR feeds samples to the
  Raspberry Pi over USB. Keep this physically simple: short antenna jumpers,
  stable power, and enough ventilation.
- **Pi edge work:** the Pi runs `rtl_fm`, speech-band cleanup, squelch/gating,
  Icecast MP3 output, rolling WAV buffers, and activity clip detection. It can
  keep short retry/debug buffers locally under `/opt/talkingboats/spool`.
- **LAN handoff:** the Pi reaches the OptiPlex over private Wi-Fi/LAN. The
  current Pi is reached from the OptiPlex at `192.168.1.114`; mDNS names can be
  stale, so verify the live address before changing receiver or telemetry
  settings. The Pi asks the private API for presigned upload URLs instead of
  holding cloud credentials.
- **OptiPlex processing:** the OptiPlex records clip metadata in SQLite, retries
  pending uploads, transcribes clips, generates static exports, and exposes the
  read-only proxy that CloudFront can call.
- **Cloud public edge:** S3 stores raw private audio and sanitized public-site
  files. CloudFront and Route53 provide public `vhf` and `vhf-dev` domains with
  only read-only app, clip, status, and live-audio paths.

If a laptop is used for repo edits, remember that it is usually a control plane,
not the runtime host. The OptiPlex is where the live database, long-running
workers, and service environment normally live.

## First Parts List

- One RTL-SDR-class receiver with TCXO and SMA connector.
- One window-friendly VHF antenna to start.
- One Raspberry Pi close to the window to own the SDR and local Icecast stream.
- One OptiPlex or similar always-on LAN server for transcription and publishing.
- Quality Pi power supply. For Pi 3-class hardware, use a 5.1V / 2.5A micro-USB
  supply.
- Optional powered USB hub if the Pi reports undervoltage with two SDRs attached.

## Shopping Checklist

### RTL-SDR Receivers

Buy **two** receivers that match all of these:

- `RTL2832U` chipset.
- Tuner is one of: `R820T2`, `R860`, or `R828D`.
- Frequency coverage includes `156 MHz` marine VHF.
- Has a `TCXO` clock, ideally `0.5 ppm` or `1 ppm`.
- Antenna connector is real `SMA female`, not MCX.
- Metal case preferred.
- Works on Linux/Raspberry Pi with `rtl-sdr` tools.

Avoid:

- Generic white `DVB-T` TV sticks unless they explicitly say `TCXO` and list the
  tuner chip.
- Anything with only an `MCX` antenna connector.
- Expensive `Ham It Up` or HF upconverter bundles. They are for shortwave/HF and
  are not needed for 156-162 MHz marine monitoring.
- Used RTL-SDR Blog dongles priced above new official units unless they include
  accessories you actually need.

### Antenna

Apartment starter antenna:

- Telescoping scanner/VHF antenna, ideally adjustable to roughly `18 inches`.
- Connector can be `BNC`, `SMA`, or `SO-239`, but plan adapters to the SDR's
  `SMA female` input.
- Put it vertically in or near the window.

Better marine antenna if placement is easy:

- Marine VHF antenna for `156-162 MHz`, `50 ohm`.
- 3-foot whip is enough for an apartment/window experiment.
- Common connector is `PL-259`/`SO-239`, so budget for an adapter or short jumper
  to SMA.

### Power And USB

- Pi 3-class board: use a `5.1V 2.5A` micro-USB power supply.
- Pi 4-class board: use the official USB-C supply or equivalent.
- If the Pi shows undervoltage or SDRs vanish, add a powered USB hub with its own
  AC adapter.
- USB 2.0 is fine for this project; the SDR bandwidth is small.

### Connector Cheat Sheet

- SDR input: usually `SMA female`.
- Most small scanner antennas: often `BNC male`.
- Many marine antennas: `PL-259` plug or `SO-239` socket.
- Useful adapters/jumpers:
  - `BNC female to SMA male` for BNC scanner antennas into RTL-SDR dongles.
  - `SO-239/UHF female to SMA male` or a short RG316 jumper for marine antennas.
  - Short cables are better than rigid adapter stacks when the Pi is near a
    window and might get bumped.

## Channel Plan

- VHF 68, `156.425 MHz`: Fun Channel for pleasure-craft working traffic.
- VHF 14, `156.700 MHz`: Super Business Channel for Seattle Traffic / Puget Sound
  VTS.
- AIS has a browser map renderer and historical NOAA ERDDAP import helper, but
  it is not live-streaming into the dev payload yet.

## Local Compute Roles

Use the hardware for what it is good at:

- **Raspberry Pi:** edge capture, stream continuity, activity gating, short
  rolling buffers, and safe retry queues. Keep memory and CPU bounded.
- **OptiPlex:** Whisper/faster-whisper, SQLite, S3 interaction, publishing,
  lexical analysis, and public proxying. This is where the `dell` conda
  environment and live transcript DB normally live.
- **MacBook or other laptop:** development, emergency AWS/static-site operations,
  and browser checks. Do not assume it has the OptiPlex runtime state.
- **AWS:** private object storage, CloudFront, DNS, TLS, and public read-only
  delivery.

## Blog/Figma Diagram Notes

The Mermaid diagram above is the source of truth for a polished Figma/FigJam
diagram. Keep the public/private boundary visible: public viewers can see only
the read-only live app, exported clips, and current receiver audio, never radio
controls, write APIs, private database access, or the raw S3 archive.
