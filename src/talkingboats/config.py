from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from talkingboats.channel_metadata import CHANNEL_METADATA

DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT = 3000


@dataclass(frozen=True)
class LiveChannel:
    channel: str
    label: str
    frequency_mhz: float
    stream_url: str | None

    @property
    def enabled(self) -> bool:
        return bool(self.stream_url)


@dataclass(frozen=True)
class Settings:
    aws_region: str
    raw_bucket: str
    public_bucket: str | None
    ingest_token: str | None
    raw_presign_seconds: int
    playback_presign_seconds: int
    public_site_dir: Path
    public_base_url: str
    live_channels: dict[str, LiveChannel]
    clip_db_path: Path | None = None
    durable_events_table: str | None = None
    durable_events_environment: str = "dev"
    durable_events_required: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            aws_region=os.getenv("TALKINGBOATS_AWS_REGION", "us-west-2"),
            raw_bucket=os.getenv("TALKINGBOATS_RAW_BUCKET", ""),
            public_bucket=os.getenv("TALKINGBOATS_PUBLIC_BUCKET"),
            ingest_token=os.getenv("TALKINGBOATS_INGEST_TOKEN"),
            raw_presign_seconds=_env_int("TALKINGBOATS_RAW_PRESIGN_SECONDS", 900),
            playback_presign_seconds=_env_int("TALKINGBOATS_PLAYBACK_PRESIGN_SECONDS", 300),
            public_site_dir=Path(os.getenv("TALKINGBOATS_PUBLIC_SITE_DIR", "outputs/public-site")),
            public_base_url=os.getenv(
                "TALKINGBOATS_PUBLIC_BASE_URL",
                "https://vhf.robertboscacci.com",
            ),
            clip_db_path=Path(os.environ["TALKINGBOATS_CLIP_DB_PATH"])
            if os.getenv("TALKINGBOATS_CLIP_DB_PATH")
            else None,
            durable_events_table=os.getenv("TALKINGBOATS_DURABLE_EVENTS_TABLE"),
            durable_events_environment=os.getenv("TALKINGBOATS_DURABLE_EVENTS_ENVIRONMENT", "dev"),
            durable_events_required=_env_bool("TALKINGBOATS_DURABLE_EVENTS_REQUIRED", False),
            live_channels={
                "13": _live_channel_from_metadata("13", os.getenv("TALKINGBOATS_LIVE_13_URL")),
                "14": LiveChannel(
                    channel="14",
                    label=CHANNEL_METADATA["14"].label,
                    frequency_mhz=CHANNEL_METADATA["14"].frequency_mhz,
                    stream_url=os.getenv("TALKINGBOATS_LIVE_14_URL"),
                ),
                "16": _live_channel_from_metadata("16", os.getenv("TALKINGBOATS_LIVE_16_URL")),
                "68": _live_channel_from_metadata("68", os.getenv("TALKINGBOATS_LIVE_68_URL")),
            },
        )


def _live_channel_from_metadata(channel: str, stream_url: str | None) -> LiveChannel:
    metadata = CHANNEL_METADATA[channel]
    return LiveChannel(
        channel=metadata.channel,
        label=metadata.label,
        frequency_mhz=metadata.frequency_mhz,
        stream_url=stream_url,
    )


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}
