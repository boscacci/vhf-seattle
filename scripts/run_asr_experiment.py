"""Load the exact source artifact recorded when an experiment was requested."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

run_id = sys.argv[1]
if not re.fullmatch("[a-f0-9]{32}", run_id):
    raise ValueError("invalid experiment identifier")
root = Path(os.environ["TALKINGBOATS_ASR_OUTPUT_DIR"])
status = json.loads((root / "runs" / run_id / "status.json").read_text())
commit = status["source_release_commit"]
if not re.fullmatch("[a-f0-9]{40}", commit):
    raise ValueError("experiment has no immutable source identity")
source = Path.home() / ".local/share/talkingboats/releases/asr/dev" / commit
if (source / "release-commit").read_text().strip() != commit:
    raise ValueError("experiment source artifact is unavailable")
env = {**os.environ, "PYTHONPATH": str(source / "src")}
identity = hashlib.sha256(
    (source / "config/asr-training-requirements.txt").read_bytes()
).hexdigest()[:16]
python = root.parent / "training-env" / identity / "bin/python"
if not python.is_file():
    raise ValueError("experiment's pinned CPU environment is unavailable")
os.execve(str(python), [str(python), "-m", "talkingboats.asr_experiments", run_id], env)
