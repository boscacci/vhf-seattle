#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from collections.abc import MutableSet
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TextIO


def append_unique_entries(
    *,
    payload: dict[str, Any],
    seen: MutableSet[tuple[str | None, str | None]],
    fetched_at: str,
    transcript: TextIO,
) -> int:
    written = 0
    for entry in payload.get("entries", []):
        if not isinstance(entry, dict):
            continue
        key = (entry.get("ended_at"), entry.get("text"))
        if key in seen or not entry.get("text"):
            continue
        seen.add(key)
        transcript.write(json.dumps({"fetched_at": fetched_at, **entry}, sort_keys=True) + "\n")
        transcript.flush()
        written += 1
    return written


def fetch_json(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, str], *, timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def utc_now_label() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description="Persist live transcript snapshots for a window.")
    parser.add_argument("--transcript-url", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=float, default=7200)
    parser.add_argument("--poll-seconds", type=float, default=15)
    parser.add_argument("--retune-url")
    parser.add_argument("--return-channel")
    args = parser.parse_args()

    if args.duration_seconds <= 0:
        parser.error("--duration-seconds must be positive")
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    if bool(args.retune_url) != bool(args.return_channel):
        parser.error("--retune-url and --return-channel must be provided together")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    end_at = datetime.now(UTC) + timedelta(seconds=args.duration_seconds)
    seen: set[tuple[str | None, str | None]] = set()
    status_path = args.output_dir / "status.json"
    status_path.write_text(
        json.dumps(
            {
                "status": "running",
                "started_at": utc_now_label(),
                "planned_end_at": end_at.replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "transcript_url": args.transcript_url,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with (
        (args.output_dir / "transcript.jsonl").open("a", encoding="utf-8") as transcript,
        (args.output_dir / "snapshots.jsonl").open("a", encoding="utf-8") as snapshots,
    ):
        while datetime.now(UTC) < end_at:
            fetched_at = utc_now_label()
            try:
                payload = fetch_json(args.transcript_url, timeout_seconds=10)
                snapshots.write(
                    json.dumps({"fetched_at": fetched_at, "payload": payload}, sort_keys=True)
                    + "\n"
                )
                snapshots.flush()
                append_unique_entries(
                    payload=payload,
                    seen=seen,
                    fetched_at=fetched_at,
                    transcript=transcript,
                )
            except Exception as exc:  # noqa: BLE001 - monitoring should survive glitches.
                with (args.output_dir / "errors.jsonl").open("a", encoding="utf-8") as errors:
                    errors.write(
                        json.dumps(
                            {"at": fetched_at, "error": f"{type(exc).__name__}: {exc}"},
                            sort_keys=True,
                        )
                        + "\n"
                    )
            time.sleep(args.poll_seconds)

    return_retune: dict[str, Any] | None = None
    if args.retune_url and args.return_channel:
        try:
            return_retune = post_json(
                args.retune_url,
                {"id": args.return_channel},
                timeout_seconds=45,
            )
        except Exception as exc:  # noqa: BLE001 - preserve monitor result even if return fails.
            return_retune = {"error": f"{type(exc).__name__}: {exc}"}

    status_path.write_text(
        json.dumps(
            {
                "status": "complete",
                "completed_at": utc_now_label(),
                "unique_entries": len(seen),
                "return_retune": return_retune,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
