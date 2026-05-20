from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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
    operator_token: str | None
    ingest_token: str | None
    raw_presign_seconds: int
    playback_presign_seconds: int
    public_site_dir: Path
    public_base_url: str
    live_channels: dict[str, LiveChannel]

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            aws_region=os.getenv("TALKINGBOATS_AWS_REGION", "us-west-2"),
            raw_bucket=os.getenv("TALKINGBOATS_RAW_BUCKET", ""),
            public_bucket=os.getenv("TALKINGBOATS_PUBLIC_BUCKET"),
            operator_token=os.getenv("TALKINGBOATS_OPERATOR_TOKEN"),
            ingest_token=os.getenv("TALKINGBOATS_INGEST_TOKEN"),
            raw_presign_seconds=_env_int("TALKINGBOATS_RAW_PRESIGN_SECONDS", 900),
            playback_presign_seconds=_env_int("TALKINGBOATS_PLAYBACK_PRESIGN_SECONDS", 300),
            public_site_dir=Path(os.getenv("TALKINGBOATS_PUBLIC_SITE_DIR", "outputs/public-site")),
            public_base_url=os.getenv(
                "TALKINGBOATS_PUBLIC_BASE_URL",
                "https://talkingboats.robertboscacci.com",
            ),
            live_channels={
                "68": LiveChannel(
                    channel="68",
                    label="Fun Channel",
                    frequency_mhz=156.425,
                    stream_url=os.getenv("TALKINGBOATS_LIVE_68_URL"),
                ),
                "14": LiveChannel(
                    channel="14",
                    label="Super Business Channel",
                    frequency_mhz=156.700,
                    stream_url=os.getenv("TALKINGBOATS_LIVE_14_URL"),
                ),
            },
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
