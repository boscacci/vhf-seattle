"""Configure private runtime settings without printing credentials."""

import json
import os
import secrets
import shlex
from pathlib import Path

config = Path.home() / ".config/talkingboats"
api = {}
for line in (config / "api.env").read_text().splitlines():
    key, sep, value = line.partition("=")
    if sep and key in {"TALKINGBOATS_DURABLE_EVENTS_TABLE", "TALKINGBOATS_PUBLIC_SITE_DIR"}:
        parts = shlex.split(value)
        api[key] = parts[0] if len(parts) == 1 else value
if not api.get("TALKINGBOATS_DURABLE_EVENTS_TABLE"):
    raise ValueError("resolve the existing corpus table before configuring feedback")
path = config / "asr.env"
previous = {}
if path.exists():
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep:
            previous[key] = value
storage = os.environ.get("TALKINGBOATS_ASR_STORAGE_ROOT")
if not storage:
    storage = (
        str(Path(previous["TALKINGBOATS_ASR_OUTPUT_DIR"]).parent)
        if previous.get("TALKINGBOATS_ASR_OUTPUT_DIR")
        else str(Path.home() / ".local/share/talkingboats/asr-storage")
    )
root = Path(storage).resolve()
if storage.startswith("/mnt/") and not Path("/mnt/" + storage.split("/")[2]).is_mount():
    raise ValueError("configured data volume is not mounted")
root.mkdir(parents=True, exist_ok=True, mode=0o700)
root.chmod(0o700)
selection = json.loads(
    (Path(__file__).resolve().parents[1] / "config/channel-selection.json").read_text()
)
serving_model = selection["serving_model"]
if serving_model == "large-v3-turbo":
    from faster_whisper.utils import download_model

    serving_model = download_model(
        "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        revision=selection["benchmark"]["model_revision"],
        cache_dir=str(root / "models"),
    )
values = {
    "TALKINGBOATS_ASR_OPERATOR_TOKEN": previous.get("TALKINGBOATS_ASR_OPERATOR_TOKEN")
    or secrets.token_urlsafe(32),
    "TALKINGBOATS_ASR_FEEDBACK_ENABLED": "true",
    "TALKINGBOATS_ASR_FEEDBACK_TABLE": api["TALKINGBOATS_DURABLE_EVENTS_TABLE"],
    "TALKINGBOATS_ASR_OUTPUT_DIR": str(root / "feedback"),
    "TALKINGBOATS_RECORDING_ACTIVATIONS_FILE": str(root / "feedback/channel-activations.json"),
    "TALKINGBOATS_ASR_MODEL_CACHE": str(root / "models"),
    "HF_HOME": str(root / "models"),
    "TMPDIR": str(root / "tmp"),
    "TALKINGBOATS_ASR_RELEASE_COMMIT": os.environ["TALKINGBOATS_ASR_RELEASE_COMMIT"],
    "TALKINGBOATS_ACTIVE_ASR_MODEL": selection["serving_model"],
    "TALKINGBOATS_TRANSCRIBE_MODEL": serving_model,
    "TALKINGBOATS_PUBLIC_SITE_DIR": api.get("TALKINGBOATS_PUBLIC_SITE_DIR")
    or str(Path.home() / "repos/elliott-bay-vhf/.runtime/live-ais-deploy/outputs/public-site"),
}
(root / "tmp").mkdir(exist_ok=True, mode=0o700)
for value in values.values():
    if "\n" in value or "\r" in value:
        raise ValueError("invalid runtime configuration")
pending = path.with_suffix(".pending")
fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write("".join(f"{k}={v}\n" for k, v in values.items()))
pending.replace(path)

# Refuse on-demand jobs when the explicitly configured removable/data mount is absent.
unit = Path.home() / ".config/systemd/user/talkingboats-asr-experiment@.service.d"
unit.mkdir(parents=True, exist_ok=True)
mount_guard = unit / "storage.conf"
if storage.startswith("/mnt/"):
    mount = "/mnt/" + storage.split("/")[2]
    mount_guard.write_text(f"[Unit]\nConditionPathIsMountPoint={mount}\n")
else:
    mount_guard.unlink(missing_ok=True)
