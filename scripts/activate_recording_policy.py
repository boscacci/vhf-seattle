"""Persist the approved activation once; never reset it on a deployment retry."""

import json
from datetime import UTC, datetime, timedelta

from talkingboats.asr_experiments import atomic_json
from talkingboats.recording_policy import activation_boundaries, activation_path

path = activation_path()
if not path.exists():
    boundary = (
        (datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=1))
        .isoformat()
        .replace("+00:00", "Z")
    )
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_json(path, {"22A": boundary})
    path.chmod(0o600)
activation_boundaries()  # Existing state must also validate before enabling recording.
print(
    json.dumps(
        {
            "event": "recording_policy_activated",
            "new_channel": "22A",
            "historical_backlog": "excluded",
        }
    )
)
