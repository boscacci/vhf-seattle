"""Bounded read-only radio workload audit and local Turbo capacity benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3

from talkingboats.channel_metadata import CHANNEL_METADATA
from talkingboats.clip_quality import is_quality_visible

CORE = ["14", "13", "16"]


def pacific_window(now: datetime) -> tuple[datetime, datetime]:
    end = now.astimezone(ZoneInfo("America/Los_Angeles")).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (end - timedelta(days=7)).astimezone(UTC), end.astimezone(UTC)


def rank_channels(rows: list[dict]) -> list[dict]:
    return sorted(
        (r for r in rows if r["channel"] not in {*CORE, "74"}),
        key=lambda r: (-r["audio_minutes"] * r["usable_fraction"], r["channel"]),
    )


def choose_channels(ranked: list[dict], *, count: int) -> list[str]:
    if count not in (6, 8) or len(ranked) < count - len(CORE):
        raise ValueError("selection requires six/eight channels and measured optional channels")
    return CORE + [r["channel"] for r in ranked[: count - len(CORE)]]


def audit(bucket: str, table: str, output: Path, work: Path) -> dict:
    start, end = pacific_window(datetime.now(UTC))
    s3 = boto3.client("s3", region_name="us-west-2")
    db = boto3.resource("dynamodb", region_name="us-west-2")
    objects = []
    for channel in CHANNEL_METADATA:
        day = start.date()
        while day <= end.date():
            token = None
            while True:
                args = {
                    "Bucket": bucket,
                    "Prefix": f"raw/channel={channel}/date={day}",
                    "MaxKeys": 1000,
                }
                if token:
                    args["ContinuationToken"] = token
                page = s3.list_objects_v2(**args)
                for obj in page.get("Contents", []):
                    match = re.search(r"/(\d{8}T\d{6}Z)-", obj["Key"])
                    if not match:
                        continue
                    at = datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                    if start <= at < end:
                        objects.append(
                            {
                                "key": obj["Key"],
                                "channel": channel,
                                "started_at": at.isoformat().replace("+00:00", "Z"),
                            }
                        )
                if len(objects) > 60000:
                    raise RuntimeError("audit exceeds 60,000-object safety bound")
                token = page.get("NextContinuationToken")
                if not token:
                    break
            day += timedelta(days=1)
        print(
            json.dumps(
                {"event": "channel_audit_inventory", "channel": channel, "objects": len(objects)}
            ),
            flush=True,
        )
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    checkpoint = work / "metadata-checkpoint.json"
    previous = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    if previous.get("window_start") != start.isoformat():
        previous = {}
    states = previous.get("states", {})
    capacity = float(previous.get("capacity", 0))
    objects_to_read = [r for r in objects if r["key"] not in states]
    for offset in range(0, len(objects_to_read), 100):
        keys = [
            {"pk": "clip#" + r["key"], "sk": "state"}
            for r in objects_to_read[offset : offset + 100]
        ]
        request = {
            table: {
                "Keys": keys,
                "ProjectionExpression": (
                    "#k, duration_seconds, quality_status, quality_score, audio_metrics"
                ),
                "ExpressionAttributeNames": {"#k": "key"},
            }
        }
        attempts = 0
        while request:
            page = db.batch_get_item(RequestItems=request, ReturnConsumedCapacity="TOTAL")
            capacity += sum(float(c["CapacityUnits"]) for c in page.get("ConsumedCapacity", []))
            if capacity > 30000:
                raise RuntimeError("audit exceeds 30,000 read-capacity-unit safety bound")
            for item in page.get("Responses", {}).get(table, []):
                states[item["key"]] = item
            pending = checkpoint.with_suffix(".pending")
            pending.write_text(
                json.dumps(
                    {"window_start": start.isoformat(), "capacity": capacity, "states": states},
                    default=float,
                )
            )
            pending.chmod(0o600)
            pending.replace(checkpoint)
            request = page.get("UnprocessedKeys", {})
            attempts += 1
            if request:
                if attempts >= 6:
                    raise RuntimeError("audit could not complete bounded metadata reads")
                time.sleep(min(2**attempts / 10, 2))
    rows = []
    missing = 0
    for channel in CHANNEL_METADATA:
        records = [r for r in objects if r["channel"] == channel]
        seconds = 0.0
        hours = Counter()
        usable, measured, contrasts = 0, 0, []
        for r in records:
            state = states.get(r["key"], {})
            duration = float(state.get("duration_seconds") or 0)
            if duration <= 0:
                missing += 1
            seconds += duration
            hours[r["started_at"][:13]] += duration
            r["duration_seconds"] = duration
            if state.get("quality_status") is not None:
                measured += 1
                usable += int(
                    is_quality_visible(state["quality_status"], state.get("quality_score"))
                )
            metrics = state.get("audio_metrics") or {}
            if (
                float(metrics.get("noise_floor_dbfs", -120)) > -100
                and "speech_contrast_db" in metrics
            ):
                contrasts.append(float(metrics["speech_contrast_db"]))
        rows.append(
            {
                "channel": channel,
                "incoming_clips": len(records),
                "audio_minutes": round(seconds / 60, 3),
                "usable_fraction": round(usable / measured, 4) if measured else 0,
                "quality_measured_clips": measured,
                "valid_contrast_samples": len(contrasts),
                "median_non_silent_contrast_db": sorted(contrasts)[len(contrasts) // 2]
                if contrasts
                else None,
                "hourly_audio_seconds": dict(hours),
            }
        )
    if missing:
        missing_records = [r for r in objects if r["duration_seconds"] <= 0]
        if len(missing_records) > 100:
            raise RuntimeError(f"audit has {missing} missing durations; resolve before selection")
        for r in missing_records:
            path = work / "duration-probe.mp3"
            s3.download_file(bucket, r["key"], str(path))
            path.chmod(0o600)
            duration = float(
                subprocess.check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        str(path),
                    ]
                )
            )
            states.setdefault(r["key"], {})["duration_seconds"] = duration
            r["duration_seconds"] = duration
            row = next(v for v in rows if v["channel"] == r["channel"])
            row["audio_minutes"] += duration / 60
            hour = r["started_at"][:13]
            row["hourly_audio_seconds"][hour] = row["hourly_audio_seconds"].get(hour, 0) + duration
            path.unlink()

    ranked = rank_channels(rows)
    result = {
        "schema_version": 1,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "source": "raw object inventory joined to clip-state duration; no transcription filter",
        "quality_caveat": "persisted quality is a proxy, not human intelligibility or RF SNR",
        "read_capacity_units": capacity,
        "channels": rows,
        "optional_ranking": [r["channel"] for r in ranked],
        "eight_channels": choose_channels(ranked, count=8),
        "six_channels": choose_channels(ranked, count=6),
    }
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    (work / "inventory.json").write_text(json.dumps(objects), encoding="utf-8")
    (work / "inventory.json").chmod(0o600)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def benchmark(bucket: str, output: Path, work: Path) -> dict:
    from faster_whisper import WhisperModel

    result = json.loads(output.read_text())
    records = json.loads((work / "inventory.json").read_text())
    random.Random(42).shuffle(records)
    selected = result["eight_channels"]
    samples = []
    for channel in selected:
        candidates = [
            r for r in records if r["channel"] == channel and 1 <= r["duration_seconds"] <= 60
        ]
        samples.extend(candidates[:10])
    if not samples:
        raise RuntimeError("no benchmark audio")
    model = WhisperModel("turbo", device="cpu", compute_type="int8", cpu_threads=2, num_workers=1)
    s3 = boto3.client("s3", region_name="us-west-2")
    checkpoint_path = work / "benchmark-checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {}
    by_channel = checkpoint.get("by_channel", {})
    completed = set(checkpoint.get("completed", []))
    warmed = False
    for record in samples:
        if hashlib.sha256(record["key"].encode()).hexdigest() in completed:
            continue
        path = work / (hashlib.sha256(record["key"].encode()).hexdigest() + ".mp3")
        if not path.exists():
            s3.download_file(bucket, record["key"], str(path))
            path.chmod(0o600)
        args = {
            "language": "en",
            "beam_size": 5,
            "vad_filter": False,
            "hotwords": "Seattle Traffic,VTS,Puget Sound",
        }
        if not warmed:
            list(model.transcribe(str(path), **args)[0])
            warmed = True
        begin = time.monotonic()
        segments, _ = model.transcribe(str(path), **args)
        list(segments)
        elapsed = time.monotonic() - begin
        row = by_channel.setdefault(
            record["channel"], {"audio_seconds": 0, "elapsed_seconds": 0, "clips": 0}
        )
        row["audio_seconds"] += record["duration_seconds"]
        row["elapsed_seconds"] += elapsed
        row["clips"] += 1
        completed.add(hashlib.sha256(record["key"].encode()).hexdigest())
        checkpoint_path.write_text(
            json.dumps({"by_channel": by_channel, "completed": sorted(completed)})
        )
        checkpoint_path.chmod(0o600)
        print(
            json.dumps(
                {
                    "event": "turbo_benchmark_clip",
                    "channel": record["channel"],
                    "elapsed_seconds": round(elapsed, 2),
                }
            ),
            flush=True,
        )
    checks = []
    for count in (8, 6):
        channels = result["eight_channels" if count == 8 else "six_channels"]
        hours = Counter()
        for channel in channels:
            rate = by_channel[channel]["elapsed_seconds"] / by_channel[channel]["audio_seconds"]
            row = next(r for r in result["channels"] if r["channel"] == channel)
            for hour, seconds in row["hourly_audio_seconds"].items():
                hours[hour] += seconds * rate
        peak = max(hours.values(), default=0)
        checks.append(
            {
                "channels": channels,
                "peak_hour_processing_seconds": round(peak, 3),
                "headroom": round(3600 / peak, 3) if peak else None,
                "passes": peak > 0 and peak * 1.5 <= 3600,
            }
        )
    passing = next((c for c in checks if c["passes"]), None)
    result["benchmark"] = {
        "model": "turbo",
        "cpu_threads": 2,
        "workers": 1,
        "compute_type": "int8",
        "beam_size": 5,
        "vad_filter": False,
        "samples": by_channel,
        "capacity_checks": checks,
    }
    result["active_channels"] = (passing or checks[-1])["channels"]
    result["turbo_capacity_passed"] = bool(passing)
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["audit", "benchmark"])
    p.add_argument("--bucket", required=True)
    p.add_argument("--table")
    p.add_argument("--output", type=Path, default=Path("config/channel-selection.json"))
    p.add_argument("--work", type=Path, default=Path("outputs/channel-audit"))
    a = p.parse_args()
    if a.action == "audit":
        if not a.table:
            p.error("--table is required for audit")
        audit(a.bucket, a.table, a.output, a.work)
    else:
        benchmark(a.bucket, a.output, a.work)


if __name__ == "__main__":
    main()
