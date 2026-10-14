"""Activation boundaries keep newly enabled recording channels out of old backlog."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from talkingboats.channel_metadata import ACTIVE_CAPTURE_CHANNELS

NOT_ACTIVATED = "9999-12-31T00:00:00Z"


def activation_path() -> Path:
    return Path(
        os.getenv(
            "TALKINGBOATS_RECORDING_ACTIVATIONS_FILE",
            str(Path.home() / ".config/talkingboats/channel-activations.json"),
        )
    )


def activation_boundaries() -> dict[str, str]:
    path = activation_path()
    values = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(values, dict) or set(values) - {"22A"}:
        raise ValueError("invalid recording activation policy")
    for value in values.values():
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("recording activation requires a timezone")
    return {"22A": values.get("22A", NOT_ACTIVATED)}


def eligible(channel: str, started_at: str, boundaries=None) -> bool:
    boundary = (boundaries if boundaries is not None else activation_boundaries()).get(channel)
    if boundary is None:
        return True
    return datetime.fromisoformat(started_at.replace("Z", "+00:00")) >= datetime.fromisoformat(
        boundary.replace("Z", "+00:00")
    )


def queue_policy_identity() -> str:
    policy = {"channels": list(ACTIVE_CAPTURE_CHANNELS), "since": activation_boundaries()}
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()


def queue_checkpoint(directory: Path) -> Path:
    return directory / f"queue-index-cutover-{queue_policy_identity()}.json"


def indexes_ready(directory: Path) -> bool:
    path = queue_checkpoint(directory)
    if path.exists():
        p = json.loads(path.read_text())
        return p.get("status_index") == 3 and p.get("policy_identity") == queue_policy_identity()
    if activation_boundaries()["22A"] == NOT_ACTIVATED:
        legacy = directory / "queue-index-cutover.json"
        if legacy.exists():
            p = json.loads(legacy.read_text())
            return p.get("status_index") == 3 and set(p.get("channels", [])) == set(
                ACTIVE_CAPTURE_CHANNELS
            ) - {"22A"}
    return False
