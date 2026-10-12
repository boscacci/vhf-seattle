"""Immutable full-audio samples for representative candidate throughput checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import time
from collections import Counter
from pathlib import Path

_clock = time.monotonic
SELECTION_PATH = Path(__file__).resolve().parents[2] / "config/channel-selection.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_directory(selection_sha):
    from talkingboats.asr_experiments import root

    return root().parent / "capacity-samples" / selection_sha


def prepare_samples(selection_path, audit_work, storage):
    from talkingboats.asr_experiments import atomic_json

    selection = json.loads(selection_path.read_text())
    records = json.loads((audit_work / "inventory.json").read_text())
    measured = set(json.loads((audit_work / "benchmark-checkpoint.json").read_text())["completed"])
    random.Random(42).shuffle(records)
    selection_sha = digest(selection_path)
    directory = storage / "capacity-samples" / selection_sha
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    samples = []
    size = 0
    for channel in selection["active_channels"]:
        chosen = [
            r for r in records if r["channel"] == channel and 1 <= r["duration_seconds"] <= 60
        ][:10]
        if len(chosen) != 10:
            raise ValueError("each retained channel needs ten audited full-audio samples")
        for row in chosen:
            source_id = hashlib.sha256(row["key"].encode()).hexdigest()
            path = audit_work / (source_id + ".mp3")
            if source_id not in measured or not path.is_file() or path.stat().st_size == 0:
                raise ValueError(
                    "restore the audited benchmark sample before preparing capacity checks"
                )
            size += path.stat().st_size
            if size > 256 * 1024**2:
                raise ValueError("capacity sample storage quota exceeded")
            audio_sha = digest(path)
            target = directory / (audio_sha + ".mp3")
            if target.exists() and digest(target) != audio_sha:
                raise ValueError("capacity sample identity changed")
            if not target.exists():
                shutil.copyfile(path, target)
                target.chmod(0o600)
            samples.append(
                {
                    "channel": channel,
                    "duration_seconds": row["duration_seconds"],
                    "source_id": source_id,
                    "sha256": audio_sha,
                    "file": target.name,
                }
            )
    manifest = {"selection_sha256": selection_sha, "samples": samples}
    target = directory / "manifest.json"
    if target.exists() and json.loads(target.read_text()) != manifest:
        raise ValueError("refusing to overwrite an immutable capacity dataset")
    atomic_json(target, manifest)
    return target


def benchmark_candidate(config, candidate, hints, update, checkpoint_dir):
    from faster_whisper import WhisperModel

    from talkingboats.asr_experiments import atomic_json

    selection_sha = config["capacity_selection_sha256"]
    directory = sample_directory(selection_sha)
    manifest_path = directory / "manifest.json"
    if not config.get("capacity_manifest_sha256") or not manifest_path.is_file():
        return {
            "passes": False,
            "reason": "Representative full-audio capacity proof is unavailable.",
        }
    if digest(manifest_path) != config["capacity_manifest_sha256"]:
        raise ValueError("capacity dataset identity changed")
    manifest = json.loads(manifest_path.read_text())
    if manifest["selection_sha256"] != selection_sha:
        raise ValueError("capacity samples belong to a different channel profile")
    selection_path = SELECTION_PATH
    if digest(selection_path) != selection_sha:
        raise ValueError("hourly workload identity changed")
    selection = json.loads(selection_path.read_text())
    counts = Counter(r["channel"] for r in manifest["samples"])
    if counts != Counter({c: 10 for c in selection["active_channels"]}):
        raise ValueError("capacity samples do not cover every retained channel")
    for row in manifest["samples"]:
        path = directory / row["file"]
        if (
            path.name != row["sha256"] + ".mp3"
            or path.parent != directory
            or digest(path) != row["sha256"]
        ):
            raise ValueError("capacity audio identity changed")
    timing_path = checkpoint_dir / "capacity-timings.json"
    timings = json.loads(timing_path.read_text()) if timing_path.exists() else {}
    model = WhisperModel(
        str(candidate), device="cpu", compute_type="int8", cpu_threads=2, num_workers=1
    )
    warmed = False
    for n, row in enumerate(manifest["samples"]):
        update(
            "benchmarking_capacity", benchmark_clip=n + 1, benchmark_clips=len(manifest["samples"])
        )
        if row["source_id"] in timings:
            continue
        path = directory / row["file"]
        args = dict(language="en", beam_size=5, vad_filter=False, hotwords=hints)
        if not warmed:
            list(model.transcribe(str(path), **args)[0])
            warmed = True
        began = _clock()
        list(model.transcribe(str(path), **args)[0])
        timings[row["source_id"]] = _clock() - began
        atomic_json(timing_path, timings)
    totals = {}
    for row in manifest["samples"]:
        item = totals.setdefault(row["channel"], {"audio_seconds": 0, "elapsed_seconds": 0})
        item["audio_seconds"] += row["duration_seconds"]
        item["elapsed_seconds"] += timings[row["source_id"]]
    hours = Counter()
    for row in selection["channels"]:
        if row["channel"] in totals:
            rate = (
                totals[row["channel"]]["elapsed_seconds"] / totals[row["channel"]]["audio_seconds"]
            )
            hours.update(
                {hour: seconds * rate for hour, seconds in row["hourly_audio_seconds"].items()}
            )
    peak = max(hours.values(), default=0)
    return {
        "passes": peak > 0 and peak * 1.5 <= 3600,
        "peak_hour_processing_seconds": peak,
        "headroom": 3600 / peak if peak else None,
        "samples": totals,
        "selection_sha256": selection_sha,
        "manifest_sha256": config["capacity_manifest_sha256"],
        "cpu_threads": 2,
        "cpu_quota_cores": 1,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--audit-work", type=Path, required=True)
    parser.add_argument("--storage", type=Path, required=True)
    args = parser.parse_args()
    path = prepare_samples(args.selection, args.audit_work, args.storage)
    print(json.dumps({"event": "asr_capacity_samples_prepared", "manifest_sha256": digest(path)}))


if __name__ == "__main__":
    main()
