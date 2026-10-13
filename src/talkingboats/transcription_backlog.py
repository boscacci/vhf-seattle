"""One shared, bounded backlog history on the configured data volume."""

from __future__ import annotations

import fcntl
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def backlog_history(store, channels, directory: Path, *, now=None, indexed_channels=False):
    now = now or datetime.now(UTC)
    epoch = now.timestamp()
    channels = sorted(c for c in channels if c not in {"74", "WX"})
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    scope = ",".join(channels)
    with (directory / "backlog.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with sqlite3.connect(directory / "backlog.sqlite3") as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS snapshots (scope TEXT, epoch REAL, payload TEXT)"
            )
            row = db.execute(
                "SELECT epoch, payload FROM snapshots WHERE scope=? ORDER BY epoch DESC LIMIT 1",
                (scope,),
            ).fetchone()
            if row and epoch - row[0] < 300:
                payload = json.loads(row[1])
            else:
                try:
                    measurement = store.active_queue_snapshot(
                        channels, max_pages=30, indexed_channels=indexed_channels
                    )
                except Exception as exc:
                    logging.getLogger(__name__).error(
                        "event=transcription_backlog_failed error_type=%s", type(exc).__name__
                    )
                    measurement = {"complete": False}
                oldest = measurement.get("oldest_started_at")
                payload = {
                    "status": "ok" if measurement["complete"] else "unavailable",
                    "generatedAt": now.isoformat(),
                    "queued_clips": measurement.get("queued_clips")
                    if measurement["complete"]
                    else None,
                    "oldest_started_at": oldest,
                    "oldest_age_seconds": max(
                        0,
                        (
                            now - datetime.fromisoformat(oldest.replace("Z", "+00:00"))
                        ).total_seconds(),
                    )
                    if oldest
                    else None,
                    "channels": channels,
                    "scope": "Retained channels; pending uploads, queued and processing clips",
                }
                db.execute(
                    "INSERT INTO snapshots VALUES (?, ?, ?)", (scope, epoch, json.dumps(payload))
                )
                db.execute("DELETE FROM snapshots WHERE epoch < ?", (epoch - 7 * 86400,))
            rows = db.execute(
                "SELECT payload FROM snapshots WHERE scope=? AND epoch>=? ORDER BY epoch",
                (scope, epoch - 7 * 86400),
            ).fetchall()
    payload["history"] = [
        {"generatedAt": p["generatedAt"], "queuedClips": p["queued_clips"]}
        for row in rows
        if (p := json.loads(row[0])).get("status") == "ok"
    ][-2016:]
    return payload
