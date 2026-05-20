from __future__ import annotations

import argparse
import json
import math
import random
import struct
import wave
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from talkingboats.schemas import Channel, ClipPresignRequest
from talkingboats.storage import raw_clip_key

SAMPLE_RATE = 8000
MAX_SIMULATED_CLIPS = 500


@dataclass(frozen=True)
class ChannelScript:
    channel: Channel
    label: str
    frequency_mhz: float
    tone_hz: int
    titles: tuple[str, ...]
    transcripts: tuple[str, ...]
    tags: tuple[str, ...]
    vessel_type: str


CHANNEL_SCRIPTS: dict[Channel, ChannelScript] = {
    "68": ChannelScript(
        channel="68",
        label="Fun Channel",
        frequency_mhz=156.425,
        tone_hz=620,
        titles=(
            "Dockside coordination",
            "Weekend flotilla check-in",
            "Marina approach question",
        ),
        transcripts=(
            "Reviewed synthetic clip: a small boat asks for room near the marina entrance.",
            "Reviewed synthetic clip: two pleasure boats coordinate a low-speed pass.",
            "Reviewed synthetic clip: a skipper confirms the dock assignment and ETA.",
        ),
        tags=("fun-channel", "small-boats", "reviewed-demo"),
        vessel_type="recreational",
    ),
    "14": ChannelScript(
        channel="14",
        label="Super Business Channel",
        frequency_mhz=156.700,
        tone_hz=420,
        titles=(
            "Seattle Traffic movement",
            "Harbor transit update",
            "Commercial vessel coordination",
        ),
        transcripts=(
            "Reviewed synthetic clip: Seattle Traffic coordinates a northbound harbor transit.",
            "Reviewed synthetic clip: a workboat reports position and confirms "
            "passing arrangements.",
            "Reviewed synthetic clip: traffic control acknowledges a commercial "
            "movement near the bay.",
        ),
        tags=("business-channel", "vts", "reviewed-demo"),
        vessel_type="cargo",
    ),
}


@dataclass(frozen=True)
class RadioSimulationConfig:
    output_dir: Path
    clip_count: int = 8
    seed: int = 68
    started_at: datetime = field(
        default_factory=lambda: datetime.now(UTC).replace(microsecond=0)
    )

    def __post_init__(self) -> None:
        if not 1 <= self.clip_count <= MAX_SIMULATED_CLIPS:
            raise ValueError(f"clip_count must be between 1 and {MAX_SIMULATED_CLIPS}")
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must include a timezone")


def generate_radio_fixture(config: RadioSimulationConfig) -> dict[str, Any]:
    output_dir = config.output_dir
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(config.seed)
    clips = []
    channel_counts = {"68": 0, "14": 0}
    vessel_type_counts: dict[str, int] = {}
    busiest_hours: dict[str, int] = {}

    for index in range(config.clip_count):
        channel: Channel = "68" if index % 2 == 0 else "14"
        script = CHANNEL_SCRIPTS[channel]
        started_at = config.started_at.astimezone(UTC) + timedelta(minutes=index * 7)
        duration_seconds = round(rng.uniform(4.0, 11.5), 1)
        clip_id = _clip_id(channel, started_at, index)
        audio_filename = f"{clip_id}.wav"
        approved_public = index % 3 != 2

        _write_synthetic_wav(
            audio_dir / audio_filename,
            duration_seconds=duration_seconds,
            tone_hz=script.tone_hz,
            seed=config.seed + index,
        )

        title_index = index % len(script.titles)
        transcript_index = index % len(script.transcripts)
        private_key = raw_clip_key(
            ClipPresignRequest(
                channel=channel,
                started_at=started_at,
                content_type="audio/wav",
                idempotency_key=f"{clip_id}:simulated-private-key",
                duration_seconds=duration_seconds,
            )
        )
        clip = {
            "id": clip_id,
            "approved_public": approved_public,
            "public_title": script.titles[title_index],
            "channel": channel,
            "channel_label": script.label,
            "frequency_mhz": script.frequency_mhz,
            "started_at": _format_utc(started_at),
            "duration_seconds": duration_seconds,
            "transcript_public": script.transcripts[transcript_index],
            "audio_public_filename": audio_filename,
            "interestingness_score": round(rng.uniform(0.58, 0.96), 3),
            "tags": list(script.tags),
            "ais_context": _fake_ais_context(rng, started_at),
            "vessel_context": [_fake_vessel_context(script, rng, index)],
            "private_s3_key": private_key,
            "receiver_id": f"simulated-rtl-channel-{channel}",
        }
        clips.append(clip)
        channel_counts[channel] += 1
        vessel_type_counts[script.vessel_type] = vessel_type_counts.get(script.vessel_type, 0) + 1
        hour = started_at.strftime("%H")
        busiest_hours[hour] = busiest_hours.get(hour, 0) + 1

    manifest = {
        "generated_at": _format_utc(config.started_at.astimezone(UTC)),
        "site": {
            "title": "Talking Boats",
            "subtitle": "Synthetic private fixture data for local Elliott Bay radio testing.",
        },
        "stats": {
            "busiest_hours": busiest_hours,
            "channel_counts": channel_counts,
            "vessel_type_counts": vessel_type_counts,
            "generated_at": _format_utc(config.started_at.astimezone(UTC)),
        },
        "clips": clips,
    }
    (output_dir / "private_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _clip_id(channel: Channel, started_at: datetime, index: int) -> str:
    return f"sim-ch{channel}-{started_at.strftime('%Y%m%dT%H%M%SZ')}-{index:03d}"


def _fake_ais_context(rng: random.Random, observed_at: datetime) -> dict[str, Any]:
    return {
        "lat": 47.6062 + rng.uniform(-0.015, 0.015),
        "lon": -122.3709 + rng.uniform(-0.018, 0.018),
        "speed_knots": round(rng.uniform(1.0, 13.0), 1),
        "course_degrees": round(rng.uniform(0, 359), 1),
        "observed_at": _format_utc(observed_at + timedelta(seconds=rng.randint(-45, 45))),
    }


def _fake_vessel_context(
    script: ChannelScript,
    rng: random.Random,
    index: int,
) -> dict[str, Any]:
    return {
        "mmsi": f"367{script.channel}{index:04d}",
        "name": f"SIM {script.label.upper()} {index + 1}",
        "vessel_type": script.vessel_type,
        "distance_nm": round(rng.uniform(0.2, 4.8), 2),
        "confidence": round(rng.uniform(0.42, 0.9), 2),
    }


def _write_synthetic_wav(
    path: Path,
    *,
    duration_seconds: float,
    tone_hz: int,
    seed: int,
) -> None:
    rng = random.Random(seed)
    frame_count = max(1, int(duration_seconds * SAMPLE_RATE))
    chunk_size = 1024
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        for frame_start in range(0, frame_count, chunk_size):
            chunk = bytearray()
            frame_end = min(frame_start + chunk_size, frame_count)
            for frame_index in range(frame_start, frame_end):
                t = frame_index / SAMPLE_RATE
                voice_like = math.sin(2 * math.pi * tone_hz * t)
                sub_tone = 0.35 * math.sin(2 * math.pi * (tone_hz / 2.7) * t)
                squelch = rng.uniform(-0.035, 0.035)
                sample = 0.42 * voice_like + 0.18 * sub_tone + squelch
                chunk.extend(struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 20000)))
            wav.writeframes(bytes(chunk))


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("datetime must include a timezone")
    return parsed.astimezone(UTC)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic fake VHF clips and private manifest data."
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/simulated-radio"))
    parser.add_argument("--clip-count", type=int, default=8)
    parser.add_argument("--seed", type=int, default=68)
    parser.add_argument("--started-at", type=_parse_utc)
    args = parser.parse_args()

    config = RadioSimulationConfig(
        output_dir=args.output_dir,
        clip_count=args.clip_count,
        seed=args.seed,
        started_at=args.started_at or datetime.now(UTC).replace(microsecond=0),
    )
    manifest = generate_radio_fixture(config)
    print(
        json.dumps(
            {
                "private_manifest": str(args.output_dir / "private_manifest.json"),
                "audio_dir": str(args.output_dir / "audio"),
                "clip_count": len(manifest["clips"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
