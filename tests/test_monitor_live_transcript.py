from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "monitor_live_transcript.py"
spec = importlib.util.spec_from_file_location("monitor_live_transcript", SCRIPT_PATH)
assert spec is not None
monitor_live_transcript = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(monitor_live_transcript)
append_unique_entries = monitor_live_transcript.append_unique_entries


def test_append_unique_entries_deduplicates_and_skips_empty_text() -> None:
    payload = {
        "entries": [
            {"text": "Seattle Traffic test", "ended_at": "2026-05-24T20:00:01Z"},
            {"text": "Seattle Traffic test", "ended_at": "2026-05-24T20:00:01Z"},
            {"text": "", "ended_at": "2026-05-24T20:00:02Z"},
        ]
    }
    output = io.StringIO()

    written = append_unique_entries(
        payload=payload,
        seen=set(),
        fetched_at="2026-05-24T20:00:03Z",
        transcript=output,
    )

    lines = output.getvalue().splitlines()
    assert written == 1
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "ended_at": "2026-05-24T20:00:01Z",
        "fetched_at": "2026-05-24T20:00:03Z",
        "text": "Seattle Traffic test",
    }
