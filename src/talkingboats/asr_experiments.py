"""Bounded, explicit local experiments. This module never promotes a serving model."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_CONFIG = {
    "base_model": "openai/whisper-large-v3-turbo",
    "base_revision": "41f01f3fe87f28c78e2fbf8b568835947dd65ed9",
    "baseline_revision": "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
    "lora_rank": 8,
    "lora_alpha": 16,
    "dropout": 0.05,
    "epochs": 3,
    "learning_rate": 0.0001,
    "gradient_accumulation_steps": 8,
    "seed": 42,
    "quantization": "int8",
    "cpu_threads": 2,
    "beam_size": 5,
}

_RUNTIME_REQUIREMENTS = Path(__file__).resolve().parents[2] / "config/asr-training-requirements.txt"
DEFAULT_CONFIG["runtime_requirements_sha256"] = hashlib.sha256(
    _RUNTIME_REQUIREMENTS.read_bytes()
).hexdigest()


def root() -> Path:
    return Path(
        os.getenv(
            "TALKINGBOATS_ASR_OUTPUT_DIR",
            str(Path.home() / ".local/share/talkingboats/asr-feedback"),
        )
    )


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def eligible_labels(labels):
    return [
        r
        for r in labels
        if r.get("reviewed")
        and not r.get("reverted")
        and r.get("channel") != "74"
        and r.get("archive_status") == "ready"
    ]


def label_duration(r):
    return (
        float(r["end_seconds"]) - float(r.get("start_seconds") or 0)
        if r.get("end_seconds") is not None
        else float(r["duration_seconds"])
    )


def dataset_summary(labels):
    ready_labels = eligible_labels(labels)
    minutes = {
        split: round(sum(label_duration(r) for r in ready_labels if r["split"] == split) / 60, 3)
        for split in ["train", "validation", "test"]
    }
    mentions = sum(
        sum(
            len(re.findall(re.escape(normalize(t)), normalize(r.get("training_text") or r["text"])))
            for t in r.get("terms", [])
        )
        for r in ready_labels
        if r["split"] == "test"
    )
    targets = {"train": 30, "validation": 5, "test": 5}
    return {
        "minutes": minutes,
        "minimum_minutes": targets,
        "test_mentions": mentions,
        "minimum_test_mentions": 50,
        "reviewed_labels": len(ready_labels),
        "pending_archives": sum(
            r.get("reviewed") and r.get("archive_status") != "ready" for r in labels
        ),
        "vocabulary": sorted(
            {t for r in ready_labels if r["split"] == "train" for t in r.get("terms", [])}
        ),
        "effort_minutes": round(sum(float(r.get("effort_seconds") or 0) for r in labels) / 60, 2),
        "ready": all(minutes[s] >= n for s, n in targets.items()) and mentions >= 50,
    }


def list_runs():
    folder = root() / "runs"
    if not folder.exists():
        return []
    rows = [
        json.loads(p.read_text())
        for p in sorted(
            folder.glob("*/status.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:20]
    ]
    for row in rows:
        if row["status"] not in ("queued", "running", "cancelling"):
            continue
        unit = "talkingboats-asr-experiment@" + row["id"] + ".service"
        try:
            result = subprocess.run(
                ["systemctl", "--user", "show", unit, "--property=ActiveState", "--value"],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.stdout.strip() in ("failed", "inactive"):
            row.update(
                status="interrupted",
                eligible=False,
                reason="worker stopped; retained checkpoints can be resumed",
            )
            atomic_json(run_directory(row["id"]) / "status.json", row)
    return rows


def run_directory(run_id):
    if not re.fullmatch("[a-f0-9]{32}", run_id):
        raise ValueError("invalid experiment identifier")
    return root() / "runs" / run_id


def start_run(labels):
    summary = dataset_summary(labels)
    if not summary["ready"]:
        raise ValueError("more fully reviewed, archived training/validation/test audio is required")
    labels = sorted(eligible_labels(labels), key=lambda r: (r["id"], r["revision"]))
    fingerprint = hashlib.sha256(
        json.dumps({"labels": labels, "config": DEFAULT_CONFIG}, sort_keys=True).encode()
    ).hexdigest()
    run_id = fingerprint[:32]
    directory = run_directory(run_id)
    status_path = directory / "status.json"
    list_runs()  # Reconcile terminated workers before deciding whether this run is reusable.
    if status_path.exists():
        previous = json.loads(status_path.read_text())
        if previous["status"] not in ("failed", "interrupted", "cancelled"):
            return previous
    if not status_path.exists() and len(list((root() / "runs").glob("*/status.json"))) >= 20:
        raise ValueError(
            "experiment history limit reached; archive old runs before starting another"
        )
    if sum(p.stat().st_size for p in root().rglob("*") if p.is_file()) > 16 * 1024**3:
        raise ValueError("local artifact quota reached; archive old runs before starting another")
    atomic_json(directory / "dataset.json", labels)
    atomic_json(directory / "config.json", DEFAULT_CONFIG)
    status = {
        "id": run_id,
        "dataset_fingerprint": fingerprint,
        "source_release_commit": os.getenv("TALKINGBOATS_ASR_RELEASE_COMMIT"),
        "status": "queued",
        "eligible": False,
        "created_at": datetime.now(UTC).isoformat(),
        "summary": summary,
    }
    atomic_json(status_path, status)
    (directory / "cancel").unlink(missing_ok=True)
    try:
        subprocess.run(
            [
                "systemctl",
                "--user",
                "start",
                "--no-block",
                "talkingboats-asr-experiment@" + run_id + ".service",
            ],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        status.update(status="failed", reason="local experiment service is unavailable")
        atomic_json(status_path, status)
        raise ValueError(status["reason"]) from None
    return status


def cancel_run(run_id):
    directory = run_directory(run_id)
    path = directory / "status.json"
    if not path.exists():
        raise ValueError("experiment not found")
    status = json.loads(path.read_text())
    if status["status"] in ("completed", "failed", "cancelled"):
        return status
    (directory / "cancel").touch(mode=0o600)
    status.update(status="cancelling", eligible=False)
    atomic_json(path, status)
    return status


def normalize(text):
    return " ".join(re.findall(r"\w+", text.casefold()))


def word_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def occurrences(text, term):
    return len(re.findall(r"(?<!\w)" + re.escape(normalize(term)) + r"(?!\w)", normalize(text)))


def evaluate_predictions(rows, predictions, *, vocabulary):
    words = errors = entity_errors = mentions = invented = 0
    examples = []
    for row, prediction in zip(rows, predictions, strict=True):
        reference = normalize(row["text"]).split()
        words += len(reference)
        errors += word_distance(reference, normalize(prediction).split())
        for term in row.get("terms", []):
            count = occurrences(row["text"], term)
            mentions += count
            entity_errors += max(0, count - occurrences(prediction, term))
        invented += sum(
            max(0, occurrences(prediction, t) - occurrences(row["text"], t)) for t in vocabulary
        )
        if len(examples) < 12:
            examples.append(
                {
                    "channel": row.get("channel"),
                    "started_at": row.get("started_at"),
                    "reference": row["text"],
                    "prediction": prediction,
                    "terms": row.get("terms", []),
                }
            )
    return {
        "wer": errors / words if words else 0,
        "word_errors": errors,
        "reference_words": words,
        "entity_errors": entity_errors,
        "entity_mentions": mentions,
        "invented_names": invented,
        "insertion_scope": "annotated vocabulary only; not all hallucinations",
        "examples": examples,
    }


def promotion_decision(baseline, candidate, *, mentions, capacity_passed):
    gain = (
        (baseline["entity_errors"] - candidate["entity_errors"]) / baseline["entity_errors"]
        if baseline["entity_errors"]
        else 0
    )
    checks = {
        "enough_test_mentions": mentions >= 50,
        "entity_gain": gain >= 0.10,
        "no_more_name_insertions": candidate["invented_names"] <= baseline["invented_names"],
        "overall_wer": candidate["wer"] <= baseline["wer"] + 0.01,
        "capacity": capacity_passed,
    }
    return {
        "eligible": all(checks.values()),
        "checks": checks,
        "relative_entity_error_reduction": gain,
    }


def archive_label(store, row, bucket):
    """Archive after save in a background task; eligibility requires verified archival."""
    import boto3

    s3 = boto3.client("s3", region_name="us-west-2")
    try:
        source = s3.head_object(Bucket=bucket, Key=row["key"])
        if source["ContentLength"] > 25 * 1024 * 1024:
            raise ValueError("reviewed audio exceeds per-file limit")
        size = 0
        for page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix="asr-feedback/audio/"
        ):
            size += sum(o["Size"] for o in page.get("Contents", []))
        if size + source["ContentLength"] > 5 * 1024**3:
            raise ValueError("reviewed audio storage quota exceeded")
        archived_key = (
            "asr-feedback/audio/"
            + hashlib.sha256((row["key"] + source["ETag"]).encode()).hexdigest()
            + ".mp3"
        )
        s3.copy_object(
            Bucket=bucket,
            Key=archived_key,
            CopySource={"Bucket": bucket, "Key": row["key"]},
            CopySourceIfMatch=source["ETag"],
            MetadataDirective="COPY",
            TaggingDirective="REPLACE",
            Tagging="talkingboats-training=true",
        )
        s3.head_object(Bucket=bucket, Key=archived_key)
        store.table.update_item(
            Key={"pk": "asr#corrections", "sk": row["id"]},
            UpdateExpression="SET archive_status = :ready, archive_key = :key, source_etag = :etag",
            ConditionExpression="#rev = :rev",
            ExpressionAttributeNames={"#rev": "revision"},
            ExpressionAttributeValues={
                ":ready": "ready",
                ":key": archived_key,
                ":etag": source["ETag"],
                ":rev": row["revision"],
            },
        )
    except Exception as exc:
        import logging

        logging.getLogger(__name__).error(
            "event=asr_archive_failed clip_id=%s error_type=%s", row["id"], type(exc).__name__
        )
        # Do not mark a reviewed label ready when archival failed.


def execute_run(run_id):
    import signal

    def interrupted(signum, frame):
        raise InterruptedError("experiment interrupted by operator or resource limit")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    import boto3
    from faster_whisper import WhisperModel
    from huggingface_hub import snapshot_download

    directory = run_directory(run_id)
    status_path = directory / "status.json"
    status = json.loads(status_path.read_text())
    started = time.monotonic()

    def update(stage, **details):
        if (directory / "cancel").exists():
            raise InterruptedError("experiment cancelled")
        if time.monotonic() - started > 6900:
            raise InterruptedError("experiment time budget reached")
        status.update(
            status="running",
            stage=stage,
            elapsed_seconds=round(time.monotonic() - started),
            **details,
        )
        atomic_json(status_path, status)
        print(
            json.dumps({"event": "asr_experiment_stage", "id": run_id, "stage": stage}), flush=True
        )

    root().mkdir(parents=True, exist_ok=True)
    with (root() / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            status.update(
                status="failed", reason="another local experiment is running", eligible=False
            )
            atomic_json(status_path, status)
            return
        try:
            labels = json.loads((directory / "dataset.json").read_text())
            config = json.loads((directory / "config.json").read_text())
            update("materializing")
            s3 = boto3.client("s3", region_name="us-west-2")
            bucket = os.environ["TALKINGBOATS_RAW_BUCKET"]
            for row in labels:
                update("materializing")
                path = directory / (row["id"] + ".wav")
                if not path.exists():
                    raw = directory / "source.mp3"
                    s3.download_file(bucket, row["archive_key"], str(raw))
                    command = [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(raw),
                        "-ss",
                        str(row.get("start_seconds") or 0),
                        "-t",
                        str(label_duration(row)),
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        str(path),
                    ]
                    subprocess.run(command, check=True, capture_output=True)
                    raw.unlink()
                row["audio_path"] = str(path)
            for row in labels:
                row["text"] = row.get("training_text") or row["text"]
            train = [r for r in labels if r["split"] == "train"]
            validation = [r for r in labels if r["split"] == "validation"]
            test = [r for r in labels if r["split"] == "test"]
            vocabulary = sorted({t for r in train for t in r.get("terms", [])})
            update("training")
            candidate_path = train_candidate(config, directory, train, validation, update)
            update("evaluating")
            baseline_path = snapshot_download(
                "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                revision=config["baseline_revision"],
                cache_dir=os.getenv("TALKINGBOATS_ASR_MODEL_CACHE"),
            )
            metrics = {}
            for name, model_path, hints in [
                ("turbo", baseline_path, None),
                ("turbo_with_hints", baseline_path, ",".join(vocabulary)),
                ("candidate_with_hints", str(candidate_path), ",".join(vocabulary)),
            ]:
                model = WhisperModel(
                    model_path, device="cpu", compute_type="int8", cpu_threads=2, num_workers=1
                )
                predictions = []
                elapsed = 0
                for row in test:
                    update("evaluating", evaluating_model=name)
                    begin = time.monotonic()
                    segments, _ = model.transcribe(
                        row["audio_path"],
                        language="en",
                        beam_size=5,
                        vad_filter=False,
                        hotwords=hints,
                    )
                    predictions.append(" ".join(s.text.strip() for s in segments))
                    elapsed += time.monotonic() - begin
                metrics[name] = evaluate_predictions(test, predictions, vocabulary=vocabulary)
                metrics[name]["elapsed_seconds"] = elapsed
                metrics[name]["real_time_factor"] = elapsed / sum(label_duration(r) for r in test)
                del model
            selection = json.loads(
                (Path(__file__).resolve().parents[2] / "config/channel-selection.json").read_text()
            )
            hourly = Counter()
            for row in selection["channels"]:
                if row["channel"] in selection["active_channels"]:
                    hourly.update(row["hourly_audio_seconds"])
            candidate = metrics["candidate_with_hints"]
            capacity_passed = max(hourly.values()) * candidate["real_time_factor"] * 1.5 <= 3600
            decision = promotion_decision(
                metrics["turbo_with_hints"],
                candidate,
                mentions=candidate["entity_mentions"],
                capacity_passed=capacity_passed,
            )
            status.update(
                status="completed",
                stage="completed",
                metrics=metrics,
                promotion=decision,
                eligible=decision["eligible"],
                model_digest=model_digest(candidate_path),
                elapsed_seconds=round(time.monotonic() - started),
            )
        except InterruptedError as exc:
            status.update(
                status="cancelled" if (directory / "cancel").exists() else "interrupted",
                reason=str(exc),
                eligible=False,
            )
        except Exception as exc:
            status.update(status="failed", reason=type(exc).__name__, eligible=False)
            print(
                json.dumps(
                    {
                        "event": "asr_experiment_failed",
                        "id": run_id,
                        "error_type": type(exc).__name__,
                    }
                ),
                flush=True,
            )
        atomic_json(status_path, status)


def train_candidate(config, directory, train, validation, update):
    existing = directory / "model-ct2"
    identity_path = directory / "model_identity.json"
    if existing.exists():
        if (
            not identity_path.exists()
            or model_digest(existing) != json.loads(identity_path.read_text())["sha256"]
        ):
            raise ValueError("candidate artifact is incomplete or changed")
        return existing
    import torch
    from transformers import (
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
        TrainerCallback,
        WhisperForConditionalGeneration,
        WhisperProcessor,
    )

    from talkingboats.audio_analysis import decode_audio_file

    torch.set_num_threads(1)
    processor = WhisperProcessor.from_pretrained(
        config["base_model"],
        revision=config["base_revision"],
        cache_dir=os.getenv("TALKINGBOATS_ASR_MODEL_CACHE"),
        language="english",
        task="transcribe",
    )
    if processor.tokenizer.pad_token_id is None:
        processor.tokenizer.pad_token = processor.tokenizer.eos_token
    model = WhisperForConditionalGeneration.from_pretrained(
        config["base_model"],
        revision=config["base_revision"],
        cache_dir=os.getenv("TALKINGBOATS_ASR_MODEL_CACHE"),
    )
    model = configure_adapter(model, config)
    decoder_start_token_id = model.config.decoder_start_token_id

    def features(rows):
        return [
            {
                "input_features": processor.feature_extractor(
                    decode_audio_file(Path(r["audio_path"]), max_seconds=30), sampling_rate=16000
                ).input_features[0],
                "labels": processor.tokenizer(r["text"]).input_ids,
            }
            for r in rows
        ]

    def collate(rows):
        inputs = processor.feature_extractor.pad(
            [{"input_features": r["input_features"]} for r in rows], return_tensors="pt"
        )
        labels = processor.tokenizer.pad(
            [{"input_ids": r["labels"]} for r in rows], return_tensors="pt"
        )
        target_ids = labels["input_ids"].masked_fill(labels.attention_mask.ne(1), -100)
        if (target_ids[:, 0] == decoder_start_token_id).all():
            target_ids = target_ids[:, 1:]
        inputs["labels"] = target_ids
        return inputs

    class Progress(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            update("training", step=state.global_step, max_steps=state.max_steps)

    args = Seq2SeqTrainingArguments(
        output_dir=str(directory / "checkpoints"),
        use_cpu=True,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=config["gradient_accumulation_steps"],
        learning_rate=config["learning_rate"],
        num_train_epochs=config["epochs"],
        eval_strategy="steps",
        save_strategy="steps",
        eval_steps=20,
        save_steps=20,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        seed=config["seed"],
        data_seed=config["seed"],
        dataloader_num_workers=0,
        report_to=[],
        save_total_limit=2,
        remove_unused_columns=False,
        label_names=["labels"],
    )
    trainer = Seq2SeqTrainer(
        model=model,
        args=args,
        train_dataset=features(train),
        eval_dataset=features(validation),
        data_collator=collate,
        callbacks=[Progress()],
    )
    checkpoints = sorted(
        (directory / "checkpoints").glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[-1])
    )
    trainer.train(resume_from_checkpoint=str(checkpoints[-1]) if checkpoints else None)
    merged = model.merge_and_unload()
    hf_path = directory / "model-hf"
    merged.save_pretrained(hf_path)
    processor.save_pretrained(hf_path)
    del trainer, model, merged
    output = directory / "model-ct2"
    if output.exists():
        raise ValueError(
            "candidate artifact already exists; refusing to overwrite immutable weights"
        )
    subprocess.run(
        [
            "ct2-transformers-converter",
            "--model",
            str(hf_path),
            "--output_dir",
            str(output),
            "--copy_files",
            "tokenizer.json",
            "preprocessor_config.json",
            "--quantization",
            "int8",
        ],
        check=True,
    )
    atomic_json(identity_path, {"sha256": model_digest(output), "config": config})
    return output


def model_digest(path):
    digest = hashlib.sha256()
    for file in sorted(path.rglob("*")):
        if file.is_file():
            digest.update(str(file.relative_to(path)).encode())
            with file.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
    return digest.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_id")
    args = p.parse_args()
    execute_run(args.run_id)


def configure_adapter(model, config):
    from peft import LoraConfig, get_peft_model

    model.freeze_encoder()
    targets = [
        name
        for name, _ in model.named_modules()
        if name.startswith("model.decoder.") and name.endswith(("q_proj", "v_proj"))
    ]
    if not targets:
        raise ValueError("model has no Whisper decoder attention targets")
    adapted = get_peft_model(
        model,
        LoraConfig(
            r=config["lora_rank"],
            lora_alpha=config["lora_alpha"],
            lora_dropout=config["dropout"],
            target_modules=targets,
        ),
    )
    if any(p.requires_grad for name, p in adapted.named_parameters() if ".encoder." in name):
        raise ValueError("encoder must remain frozen")
    return adapted


if __name__ == "__main__":
    main()
