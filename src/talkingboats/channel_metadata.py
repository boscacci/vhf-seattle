from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelMetadata:
    channel: str
    label: str
    frequency_mhz: float

    @property
    def frequency_hz(self) -> int:
        return round(self.frequency_mhz * 1_000_000)


CHANNEL_METADATA = {
    "05A": ChannelMetadata("05A", "VTS / Port Ops", 156.250),
    "13": ChannelMetadata("13", "Bridge-to-bridge", 156.650),
    "14": ChannelMetadata("14", "VTS / Seattle Traffic", 156.700),
    "16": ChannelMetadata("16", "Distress / Calling", 156.800),
    "22A": ChannelMetadata("22A", "USCG Liaison", 157.100),
    "66A": ChannelMetadata("66A", "Port Operations", 156.325),
    "68": ChannelMetadata("68", "Recreational", 156.425),
    "69": ChannelMetadata("69", "Non-commercial", 156.475),
    "71": ChannelMetadata("71", "Non-commercial", 156.575),
    "72": ChannelMetadata("72", "Ship-to-ship", 156.625),
    "74": ChannelMetadata("74", "Port Operations", 156.725),
}
PUBLIC_MONITORED_CHANNELS = ("13", "14")


def channel_label(channel: str | None) -> str | None:
    if not channel:
        return None
    metadata = CHANNEL_METADATA.get(channel)
    return metadata.label if metadata else None


def channel_label_map(channels: Iterable[str] | None = None) -> dict[str, str]:
    if channels is None:
        return {channel: metadata.label for channel, metadata in CHANNEL_METADATA.items()}
    return {
        channel: metadata.label
        for channel in channels
        if (metadata := CHANNEL_METADATA.get(channel)) is not None
    }


def public_monitored_channel_labels(channels: Iterable[str] | None = None) -> dict[str, str]:
    labels = channel_label_map(PUBLIC_MONITORED_CHANNELS)
    labels.update(channel_label_map(channels))
    return labels
