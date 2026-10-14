"""Persist the approved activation once; never reset it on a deployment retry."""

import json
from datetime import UTC, datetime, timedelta

from talkingboats.asr_experiments import atomic_json
from talkingboats.recording_policy import (
    NEW_RECORDING_CHANNELS,
    NOT_ACTIVATED,
    activation_boundaries,
    activation_path,
)

path = activation_path()
values = activation_boundaries()
missing = [channel for channel in NEW_RECORDING_CHANNELS if values[channel] == NOT_ACTIVATED]
if missing:
    boundary = (
        (datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=1))
        .isoformat()
        .replace("+00:00", "Z")
    )
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    values.update({channel: boundary for channel in missing})
    atomic_json(path, values)
    path.chmod(0o600)
activation_boundaries()  # Existing state must also validate before enabling recording.
print(
    json.dumps(
        {
            "event": "recording_policy_activated",
            "new_channels": missing,
            "historical_backlog": "excluded",
        }
    )
)
