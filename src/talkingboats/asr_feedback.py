from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from talkingboats.clip_transcriber import ClipReader, S3ClipReader, UploadedClipStore

DEFAULT_BASE_MODEL = "openai/whisper-large-v3-turbo"
DEFAULT_BASELINE_MODEL = "turbo"
DEFAULT_MIN_CORRECTIONS = 20
DEFAULT_OUTPUT_DIR = Path("outputs/asr-feedback")
DEFAULT_RESTART_SERVICE = "talkingboats-uploaded-clip-transcriber.service"
NO_NEW_CORRECTIONS_REASON = "no new reviewed transcript corrections since last trained run"


class Trainer(Protocol):
    def __call__(
        self,
        config: AsrFeedbackConfig,
        run_dir: Path,
        dataset_path: Path,
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class AsrFeedbackConfig:
    db_path: Path | None = None
    output_dir: Path = DEFAULT_OUTPUT_DIR
    training_audio_dir: Path | None = None
    bucket: str | None = None
    aws_region: str = "us-west-2"
    base_model: str = DEFAULT_BASE_MODEL
    baseline_model: str = DEFAULT_BASELINE_MODEL
    min_corrections: int = DEFAULT_MIN_CORRECTIONS
    max_corrections: int | None = None
    epochs: float = 3.0
    train_batch_size: int = 1
    gradient_accumulation_steps: int = 8
    learning_rate: float = 1e-5
    warmup_steps: int = 20
    quantization: str = "int8"
    restart_service: str | None = DEFAULT_RESTART_SERVICE
    require_eval_improvement: bool = True
    freeze_encoder: bool = True
    gradient_checkpointing: bool = True
    save_checkpoints: bool = False


def run_nightly_training(
    config: AsrFeedbackConfig,
    *,
    correction_store: Any | None = None,
    clip_reader: ClipReader | None = None,
    trainer: Trainer | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if config.min_corrections <= 0:
        raise ValueError("min_corrections must be positive")
    if config.max_corrections is not None and config.max_corrections <= 0:
        raise ValueError("max_corrections must be positive")
    config.output_dir.mkdir(parents=True, exist_ok=True)
    store = correction_store or _correction_store(config.db_path, aws_region=config.aws_region)
    corrections = store.transcript_corrections_for_training()
    if config.max_corrections is not None:
        corrections = corrections[: config.max_corrections]
    if len(corrections) < config.min_corrections:
        result = {
            "status": "skipped",
            "reason": "not enough reviewed transcript corrections",
            "correction_count": len(corrections),
            "min_corrections": config.min_corrections,
            "generated_at": _format_utc(now or datetime.now(UTC)),
        }
        _write_status(config.output_dir, result)
        return result

    run_started_at = now or datetime.now(UTC)
    correction_fingerprint = _correction_fingerprint(corrections)
    previous_status = _read_status(config.output_dir)
    if _already_trained_fingerprint(previous_status, correction_fingerprint):
        result = {
            "status": "skipped",
            "reason": NO_NEW_CORRECTIONS_REASON,
            "correction_count": len(corrections),
            "correction_fingerprint": correction_fingerprint,
            "last_trained_at": _last_trained_at(previous_status),
            "generated_at": _format_utc(run_started_at),
        }
        _write_status(config.output_dir, result)
        return result

    run_id = run_started_at.strftime("%Y%m%dT%H%M%SZ")
    run_dir = config.output_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    reader = clip_reader or _s3_reader(config)
    training_audio_dir = config.training_audio_dir or (config.output_dir / "training-audio")
    dataset_path = materialize_training_dataset(
        corrections,
        run_dir=run_dir,
        clip_reader=reader,
        audio_archive_dir=training_audio_dir,
    )
    training_result = (trainer or train_whisper_checkpoint)(config, run_dir, dataset_path)
    ct2_model_dir = training_result.get("ct2_model_dir")
    eval_result = training_result.get("eval")
    promotion = _promotion_decision(config, training_result)
    latest_model_dir = None
    restart_result = None
    if ct2_model_dir and promotion["status"] == "promoted":
        latest_model_dir = _promote_latest_model(config.output_dir, Path(str(ct2_model_dir)))
        restart_result = _restart_transcriber(config.restart_service)
    result = {
        "status": "trained",
        "correction_count": len(corrections),
        "correction_fingerprint": correction_fingerprint,
        "dataset_path": str(dataset_path),
        "dataset_split_counts": _dataset_split_counts(dataset_path),
        "training_audio_dir": str(training_audio_dir),
        "run_dir": str(run_dir),
        "hf_model_dir": training_result.get("hf_model_dir"),
        "ct2_model_dir": ct2_model_dir,
        "eval": eval_result if isinstance(eval_result, dict) else None,
        "promotion": promotion,
        "latest_model_dir": str(latest_model_dir) if latest_model_dir else None,
        "restart": restart_result,
        "generated_at": _format_utc(run_started_at),
    }
    _write_status(config.output_dir, result)
    return result


def materialize_training_dataset(
    corrections: list[dict[str, object]],
    *,
    run_dir: Path,
    clip_reader: ClipReader,
    audio_archive_dir: Path | None = None,
) -> Path:
    audio_dir = run_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    if audio_archive_dir is not None:
        audio_archive_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = run_dir / "train.jsonl"
    with dataset_path.open("w", encoding="utf-8") as output:
        for index, correction in enumerate(_progress(corrections, "materializing ASR audio")):
            key = str(correction["key"])
            content_type = str(correction["content_type"])
            audio_path = (
                audio_dir
                / f"{index:05d}-{_short_hash(key)}{_suffix_for_content_type(content_type)}"
            )
            audio_archive = _archive_audio_for_training(
                key=key,
                content_type=content_type,
                correction=correction,
                clip_reader=clip_reader,
                audio_archive_dir=audio_archive_dir,
            )
            if audio_archive is None:
                clip_reader.download(key, audio_path)
            else:
                shutil.copyfile(audio_archive, audio_path)
            record = {
                "audio": str(audio_path),
                "text": str(correction["corrected_transcript"]),
                "original_text": str(correction["original_transcript"]),
                "channel": str(correction["channel"]),
                "started_at": str(correction["started_at"]),
                "duration_seconds": correction["duration_seconds"],
                "content_type": content_type,
                "key_hash": _short_hash(key),
                "include_in_training": bool(correction.get("include_in_training", True)),
                "training_quality": str(correction.get("training_quality") or "unknown"),
                "training_split": _training_split(correction),
                "training_flags": list(correction.get("training_flags") or []),
                "training_reason": correction.get("training_reason"),
            }
            if audio_archive is not None:
                record["audio_archive"] = str(audio_archive)
            output.write(json.dumps(record, sort_keys=True) + "\n")
    return dataset_path


def _archive_audio_for_training(
    *,
    key: str,
    content_type: str,
    correction: dict[str, object],
    clip_reader: ClipReader,
    audio_archive_dir: Path | None,
) -> Path | None:
    if audio_archive_dir is None:
        return None
    archive_path = _archive_audio_path(audio_archive_dir, key, content_type)
    if archive_path.exists():
        _write_archive_metadata_if_missing(archive_path, key=key, correction=correction)
        return archive_path
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = archive_path.with_name(f".{archive_path.name}.{os.getpid()}.tmp")
    try:
        clip_reader.download(key, temp_path)
        os.replace(temp_path, archive_path)
    finally:
        temp_path.unlink(missing_ok=True)
    _write_archive_metadata_if_missing(archive_path, key=key, correction=correction)
    return archive_path


def _archive_audio_path(audio_archive_dir: Path, key: str, content_type: str) -> Path:
    return audio_archive_dir / f"{_short_hash(key)}{_suffix_for_content_type(content_type)}"


def _write_archive_metadata_if_missing(
    archive_path: Path,
    *,
    key: str,
    correction: dict[str, object],
) -> None:
    metadata_path = archive_path.with_suffix(".json")
    if metadata_path.exists():
        return
    _atomic_write_text(
        metadata_path,
        json.dumps(
            {
                "audio_file": archive_path.name,
                "channel": correction.get("channel"),
                "content_type": correction.get("content_type"),
                "duration_seconds": correction.get("duration_seconds"),
                "ended_at": correction.get("ended_at"),
                "key_hash": _short_hash(key),
                "started_at": correction.get("started_at"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def train_whisper_checkpoint(
    config: AsrFeedbackConfig,
    run_dir: Path,
    dataset_path: Path,
) -> dict[str, object]:
    try:
        import torch
        from datasets import Audio, Dataset
        from transformers import (
            Seq2SeqTrainer,
            WhisperForConditionalGeneration,
            WhisperProcessor,
        )
    except ImportError as exc:
        raise RuntimeError(
            "ASR feedback training requires the optional asr-train dependencies: "
            "install elliott-bay-vhf[asr-train] in the training environment."
        ) from exc

    records = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines()]
    train_records = [
        record
        for record in records
        if str(record.get("training_split") or "train") in {"auto", "train"}
    ]
    if not train_records:
        raise RuntimeError("no train-split corrections are available for ASR feedback training")
    dataset = Dataset.from_list(
        [{"audio": record["audio"], "text": record["text"]} for record in train_records]
    ).cast_column("audio", Audio(sampling_rate=16000))
    processor = WhisperProcessor.from_pretrained(
        config.base_model,
        language="english",
        task="transcribe",
    )
    model = WhisperForConditionalGeneration.from_pretrained(config.base_model)
    model.config.forced_decoder_ids = None
    model.config.suppress_tokens = []
    if config.gradient_checkpointing:
        model.config.use_cache = False
    if config.freeze_encoder:
        model.freeze_encoder()

    def prepare_example(batch: dict[str, Any]) -> dict[str, Any]:
        audio = batch["audio"]
        batch["input_features"] = processor.feature_extractor(
            audio["array"],
            sampling_rate=audio["sampling_rate"],
        ).input_features[0]
        batch["labels"] = processor.tokenizer(batch["text"]).input_ids
        return batch

    train_dataset = dataset.map(
        prepare_example,
        remove_columns=dataset.column_names,
        desc="preparing Whisper features",
    )
    args = _training_arguments(config, run_dir / "checkpoints", torch)
    trainer = Seq2SeqTrainer(
        args=args,
        model=model,
        train_dataset=train_dataset,
        data_collator=WhisperDataCollator(processor),
        tokenizer=processor.feature_extractor,
    )
    trainer.train()
    hf_model_dir = run_dir / "model-hf"
    trainer.save_model(str(hf_model_dir))
    processor.save_pretrained(str(hf_model_dir))
    ct2_model_dir = run_dir / "model-ct2"
    _convert_to_ctranslate2(hf_model_dir, ct2_model_dir, quantization=config.quantization)
    return {"hf_model_dir": str(hf_model_dir), "ct2_model_dir": str(ct2_model_dir)}


@dataclass
class WhisperDataCollator:
    processor: Any

    def __call__(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        input_features = [{"input_features": feature["input_features"]} for feature in features]
        batch = self.processor.feature_extractor.pad(input_features, return_tensors="pt")
        label_features = [{"input_ids": feature["labels"]} for feature in features]
        labels_batch = self.processor.tokenizer.pad(label_features, return_tensors="pt")
        labels = labels_batch["input_ids"].masked_fill(labels_batch.attention_mask.ne(1), -100)
        batch["labels"] = labels
        return batch


def export_training_jsonl(db_path: Path, output_path: Path) -> dict[str, Any]:
    store = _correction_store(db_path)
    corrections = store.transcript_corrections_for_training()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        for correction in corrections:
            output.write(
                json.dumps(
                    {
                        "channel": correction["channel"],
                        "started_at": correction["started_at"],
                        "duration_seconds": correction["duration_seconds"],
                        "content_type": correction["content_type"],
                        "original_text": correction["original_transcript"],
                        "text": correction["corrected_transcript"],
                        "key_hash": _short_hash(str(correction["key"])),
                        "include_in_training": correction.get("include_in_training", True),
                        "training_quality": correction.get("training_quality", "unknown"),
                        "training_split": correction.get("training_split", "auto"),
                        "training_flags": correction.get("training_flags", []),
                        "training_reason": correction.get("training_reason"),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    return {
        "status": "exported",
        "correction_count": len(corrections),
        "output_path": str(output_path),
    }


def has_new_training_corrections(output_dir: Path, corrections: list[dict[str, object]]) -> bool:
    if not corrections:
        return False
    correction_fingerprint = _correction_fingerprint(corrections)
    return not _already_trained_fingerprint(_read_status(output_dir), correction_fingerprint)


def _correction_store(db_path: Path | None, *, aws_region: str | None = None):
    backend = os.getenv("TALKINGBOATS_CLIP_STORE_BACKEND")
    if backend == "dynamodb" or (backend is None and db_path is None):
        from talkingboats.dynamo_clip_store import dynamo_clip_store_from_env

        return dynamo_clip_store_from_env(aws_region=aws_region)
    if backend not in (None, "sqlite"):
        raise RuntimeError(f"unsupported TALKINGBOATS_CLIP_STORE_BACKEND: {backend}")
    if db_path is None:
        raise RuntimeError("db_path is required when TALKINGBOATS_CLIP_STORE_BACKEND is sqlite")
    return UploadedClipStore(db_path)


def _training_arguments(config: AsrFeedbackConfig, output_dir: Path, torch: Any) -> Any:
    from transformers import Seq2SeqTrainingArguments

    kwargs: dict[str, Any] = {
        "output_dir": str(output_dir),
        "per_device_train_batch_size": config.train_batch_size,
        "gradient_accumulation_steps": config.gradient_accumulation_steps,
        "learning_rate": config.learning_rate,
        "warmup_steps": config.warmup_steps,
        "num_train_epochs": config.epochs,
        "save_strategy": "epoch" if config.save_checkpoints else "no",
        "gradient_checkpointing": config.gradient_checkpointing,
        "logging_steps": 10,
        "report_to": [],
        "remove_unused_columns": False,
        "fp16": bool(torch.cuda.is_available()),
        "predict_with_generate": False,
        "dataloader_pin_memory": bool(torch.cuda.is_available()),
    }
    signature = inspect.signature(Seq2SeqTrainingArguments.__init__)
    eval_key = "eval_strategy" if "eval_strategy" in signature.parameters else "evaluation_strategy"
    kwargs[eval_key] = "no"
    return Seq2SeqTrainingArguments(**kwargs)


def _convert_to_ctranslate2(hf_model_dir: Path, ct2_model_dir: Path, *, quantization: str) -> None:
    converter = shutil.which("ct2-transformers-converter")
    if not converter:
        raise RuntimeError(
            "ct2-transformers-converter is required to produce a faster-whisper model directory"
        )
    subprocess.run(
        [
            converter,
            "--model",
            str(hf_model_dir),
            "--output_dir",
            str(ct2_model_dir),
            "--copy_files",
            "tokenizer.json",
            "preprocessor_config.json",
            "--quantization",
            quantization,
        ],
        check=True,
    )


def _s3_reader(config: AsrFeedbackConfig) -> S3ClipReader:
    if not config.bucket:
        raise ValueError("bucket is required when no clip_reader is supplied")
    return S3ClipReader(bucket=config.bucket, aws_region=config.aws_region)


def _promote_latest_model(output_dir: Path, model_dir: Path) -> Path:
    latest = output_dir / "latest-ct2"
    temp_link = output_dir / f".latest-ct2.{os.getpid()}"
    if temp_link.exists() or temp_link.is_symlink():
        temp_link.unlink()
    temp_link.symlink_to(model_dir.resolve(), target_is_directory=True)
    if latest.exists() and not latest.is_symlink():
        shutil.rmtree(latest)
    os.replace(temp_link, latest)
    _atomic_write_text(
        output_dir / "latest_model.env",
        f"TALKINGBOATS_TRANSCRIBE_MODEL={latest}\n",
    )
    return latest


def _promotion_decision(
    config: AsrFeedbackConfig,
    training_result: dict[str, object],
) -> dict[str, object]:
    if not training_result.get("ct2_model_dir"):
        return {
            "status": "skipped",
            "reason": "trainer did not produce a CTranslate2 model",
        }
    if not config.require_eval_improvement:
        return {
            "status": "promoted",
            "reason": "eval improvement gate disabled",
            "baseline_model": config.baseline_model,
        }
    eval_result = training_result.get("eval")
    if isinstance(eval_result, dict):
        try:
            baseline_wer = float(eval_result["baseline_wer"])
            candidate_wer = float(eval_result["candidate_wer"])
        except (KeyError, TypeError, ValueError):
            pass
        else:
            if candidate_wer < baseline_wer:
                return {
                    "status": "promoted",
                    "reason": "candidate eval improved baseline",
                    "baseline_model": str(
                        eval_result.get("baseline_model") or config.baseline_model
                    ),
                    "baseline_wer": baseline_wer,
                    "candidate_wer": candidate_wer,
                    "clip_count": eval_result.get("clip_count"),
                }
    return {
        "status": "skipped",
        "reason": "candidate eval did not prove improvement",
        "baseline_model": config.baseline_model,
    }


def _restart_transcriber(service_name: str | None) -> dict[str, object] | None:
    if not service_name:
        return None
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return {"service": service_name, "status": "skipped", "reason": "systemctl not found"}
    result = subprocess.run(
        [systemctl, "--user", "restart", service_name],
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "service": service_name,
        "status": "restarted" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
    }


def _write_status(output_dir: Path, result: dict[str, Any]) -> None:
    _atomic_write_text(
        output_dir / "training_status.json",
        json.dumps(result, indent=2, sort_keys=True) + "\n",
    )


def _read_status(output_dir: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads((output_dir / "training_status.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _already_trained_fingerprint(
    previous_status: dict[str, Any] | None,
    correction_fingerprint: str,
) -> bool:
    if not previous_status:
        return False
    previous_fingerprint = _previous_correction_fingerprint(previous_status)
    if previous_fingerprint != correction_fingerprint:
        return False
    if previous_status.get("status") == "trained":
        return True
    return (
        previous_status.get("status") == "skipped"
        and previous_status.get("reason") == NO_NEW_CORRECTIONS_REASON
    )


def _last_trained_at(previous_status: dict[str, Any] | None) -> str | None:
    if not previous_status:
        return None
    if previous_status.get("status") == "trained":
        generated_at = previous_status.get("generated_at")
        return str(generated_at) if generated_at else None
    last_trained_at = previous_status.get("last_trained_at")
    return str(last_trained_at) if last_trained_at else None


def _correction_fingerprint(corrections: list[dict[str, object]]) -> str:
    records = [_fingerprint_record_from_correction(correction) for correction in corrections]
    return _fingerprint_records(records)


def _fingerprint_record_from_correction(correction: dict[str, object]) -> dict[str, object]:
    return {
        "key_hash": _short_hash(str(correction["key"])),
        "started_at": str(correction["started_at"]),
        "content_type": str(correction["content_type"]),
        "duration_seconds": correction["duration_seconds"],
        "text": str(correction["corrected_transcript"]),
        "include_in_training": correction.get("include_in_training", True),
        "training_quality": correction.get("training_quality", "unknown"),
        "training_split": _training_split(correction),
        "training_flags": list(correction.get("training_flags") or []),
        "training_reason": correction.get("training_reason"),
    }


def _previous_correction_fingerprint(previous_status: dict[str, Any]) -> str | None:
    fingerprint = previous_status.get("correction_fingerprint")
    if isinstance(fingerprint, str) and fingerprint:
        return fingerprint
    dataset_path = previous_status.get("dataset_path")
    if not isinstance(dataset_path, str) or not dataset_path:
        return None
    try:
        records = [
            {
                "key_hash": str(record["key_hash"]),
                "started_at": str(record["started_at"]),
                "content_type": str(record["content_type"]),
                "duration_seconds": record["duration_seconds"],
                "text": str(record["text"]),
                "include_in_training": record.get("include_in_training", True),
                "training_quality": record.get("training_quality", "unknown"),
                "training_split": record.get("training_split", "auto"),
                "training_flags": list(record.get("training_flags") or []),
                "training_reason": record.get("training_reason"),
            }
            for record in (
                json.loads(line)
                for line in Path(dataset_path).read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        ]
    except (KeyError, OSError, json.JSONDecodeError):
        return None
    return _fingerprint_records(records)


def _fingerprint_records(records: list[dict[str, object]]) -> str:
    records.sort(key=lambda record: (str(record["key_hash"]), str(record["started_at"])))
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _training_split(correction: dict[str, object]) -> str:
    split = str(correction.get("training_split") or "auto")
    return "train" if split == "auto" else split


def _dataset_split_counts(dataset_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        split = str(record.get("training_split") or "train")
        counts[split] = counts.get(split, 0) + 1
    return dict(sorted(counts.items()))


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)


def _short_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _suffix_for_content_type(content_type: str) -> str:
    return {
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/aac": ".aac",
        "audio/flac": ".flac",
        "audio/m4a": ".m4a",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
    }.get(content_type, ".audio")


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _progress(items: list[dict[str, object]], description: str):
    try:
        from tqdm import tqdm
    except ImportError:
        return items
    return tqdm(items, desc=description, unit="clip")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export and train ASR feedback corrections.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    nightly = subparsers.add_parser("nightly", help="run the nightly correction fine-tune")
    _add_common_config_args(nightly)
    nightly.add_argument("--bucket", default=os.getenv("TALKINGBOATS_RAW_BUCKET"))
    nightly.add_argument(
        "--training-audio-dir",
        type=Path,
        default=(
            Path(value)
            if (value := os.getenv("TALKINGBOATS_ASR_FEEDBACK_TRAINING_AUDIO_DIR"))
            else None
        ),
    )
    nightly.add_argument("--max-corrections", type=int, default=None)
    nightly.add_argument(
        "--restart-service",
        default=os.getenv("TALKINGBOATS_ASR_RESTART_SERVICE", DEFAULT_RESTART_SERVICE),
    )
    nightly.add_argument("--skip-restart", action="store_true")
    nightly.add_argument("--promote-without-eval", action="store_true")
    nightly.set_defaults(
        freeze_encoder=_env_bool("TALKINGBOATS_ASR_FEEDBACK_FREEZE_ENCODER", True),
        gradient_checkpointing=_env_bool(
            "TALKINGBOATS_ASR_FEEDBACK_GRADIENT_CHECKPOINTING",
            True,
        ),
        save_checkpoints=_env_bool("TALKINGBOATS_ASR_FEEDBACK_SAVE_CHECKPOINTS", False),
    )
    nightly.add_argument("--freeze-encoder", dest="freeze_encoder", action="store_true")
    nightly.add_argument("--no-freeze-encoder", dest="freeze_encoder", action="store_false")
    nightly.add_argument(
        "--gradient-checkpointing",
        dest="gradient_checkpointing",
        action="store_true",
    )
    nightly.add_argument(
        "--no-gradient-checkpointing",
        dest="gradient_checkpointing",
        action="store_false",
    )
    nightly.add_argument("--save-checkpoints", dest="save_checkpoints", action="store_true")
    nightly.add_argument("--no-save-checkpoints", dest="save_checkpoints", action="store_false")

    export = subparsers.add_parser("export", help="export reviewed corrections as JSONL metadata")
    export.add_argument("--db-path", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "export":
        print(json.dumps(export_training_jsonl(args.db_path, args.output), sort_keys=True))
        return

    config = AsrFeedbackConfig(
        db_path=args.db_path,
        output_dir=args.output_dir,
        training_audio_dir=args.training_audio_dir,
        bucket=args.bucket,
        aws_region=args.aws_region,
        base_model=args.base_model,
        baseline_model=args.baseline_model,
        min_corrections=args.min_corrections,
        max_corrections=args.max_corrections,
        epochs=args.epochs,
        train_batch_size=args.train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        warmup_steps=args.warmup_steps,
        quantization=args.quantization,
        restart_service=None if args.skip_restart else args.restart_service,
        require_eval_improvement=not args.promote_without_eval,
        freeze_encoder=args.freeze_encoder,
        gradient_checkpointing=args.gradient_checkpointing,
        save_checkpoints=args.save_checkpoints,
    )
    print(json.dumps(run_nightly_training(config), sort_keys=True))


def _add_common_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--aws-region", default=os.getenv("AWS_REGION", "us-west-2"))
    parser.add_argument(
        "--base-model",
        default=os.getenv("TALKINGBOATS_ASR_FEEDBACK_BASE_MODEL", DEFAULT_BASE_MODEL),
    )
    parser.add_argument(
        "--baseline-model",
        default=os.getenv("TALKINGBOATS_ASR_FEEDBACK_BASELINE_MODEL", DEFAULT_BASELINE_MODEL),
    )
    parser.add_argument("--min-corrections", type=int, default=DEFAULT_MIN_CORRECTIONS)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--train-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--warmup-steps", type=int, default=20)
    parser.add_argument("--quantization", default="int8")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
