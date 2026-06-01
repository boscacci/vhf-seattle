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

DEFAULT_BASE_MODEL = "openai/whisper-small.en"
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
    ) -> dict[str, str]: ...


@dataclass(frozen=True)
class AsrFeedbackConfig:
    db_path: Path
    output_dir: Path = DEFAULT_OUTPUT_DIR
    bucket: str | None = None
    aws_region: str = "us-west-2"
    base_model: str = DEFAULT_BASE_MODEL
    min_corrections: int = DEFAULT_MIN_CORRECTIONS
    max_corrections: int | None = None
    epochs: float = 3.0
    train_batch_size: int = 4
    gradient_accumulation_steps: int = 2
    learning_rate: float = 1e-5
    warmup_steps: int = 20
    quantization: str = "int8"
    restart_service: str | None = DEFAULT_RESTART_SERVICE


def run_nightly_training(
    config: AsrFeedbackConfig,
    *,
    clip_reader: ClipReader | None = None,
    trainer: Trainer | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if config.min_corrections <= 0:
        raise ValueError("min_corrections must be positive")
    if config.max_corrections is not None and config.max_corrections <= 0:
        raise ValueError("max_corrections must be positive")
    config.output_dir.mkdir(parents=True, exist_ok=True)
    store = _correction_store(config.db_path, aws_region=config.aws_region)
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
    dataset_path = materialize_training_dataset(corrections, run_dir=run_dir, clip_reader=reader)
    training_result = (trainer or train_whisper_checkpoint)(config, run_dir, dataset_path)
    ct2_model_dir = training_result.get("ct2_model_dir")
    latest_model_dir = (
        _promote_latest_model(config.output_dir, Path(ct2_model_dir))
        if ct2_model_dir
        else None
    )
    restart_result = _restart_transcriber(config.restart_service) if latest_model_dir else None
    result = {
        "status": "trained",
        "correction_count": len(corrections),
        "correction_fingerprint": correction_fingerprint,
        "dataset_path": str(dataset_path),
        "run_dir": str(run_dir),
        "hf_model_dir": training_result.get("hf_model_dir"),
        "ct2_model_dir": ct2_model_dir,
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
) -> Path:
    audio_dir = run_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = run_dir / "train.jsonl"
    with dataset_path.open("w", encoding="utf-8") as output:
        for index, correction in enumerate(_progress(corrections, "materializing ASR audio")):
            key = str(correction["key"])
            content_type = str(correction["content_type"])
            audio_path = (
                audio_dir
                / f"{index:05d}-{_short_hash(key)}{_suffix_for_content_type(content_type)}"
            )
            clip_reader.download(key, audio_path)
            record = {
                "audio": str(audio_path),
                "text": str(correction["corrected_transcript"]),
                "original_text": str(correction["original_transcript"]),
                "channel": str(correction["channel"]),
                "started_at": str(correction["started_at"]),
                "duration_seconds": correction["duration_seconds"],
                "content_type": content_type,
                "key_hash": _short_hash(key),
            }
            output.write(json.dumps(record, sort_keys=True) + "\n")
    return dataset_path


def train_whisper_checkpoint(
    config: AsrFeedbackConfig,
    run_dir: Path,
    dataset_path: Path,
) -> dict[str, str]:
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
    dataset = Dataset.from_list(
        [{"audio": record["audio"], "text": record["text"]} for record in records]
    ).cast_column("audio", Audio(sampling_rate=16000))
    processor = WhisperProcessor.from_pretrained(
        config.base_model,
        language="english",
        task="transcribe",
    )
    model = WhisperForConditionalGeneration.from_pretrained(config.base_model)
    model.config.forced_decoder_ids = None
    model.config.suppress_tokens = []

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


def _correction_store(db_path: Path, *, aws_region: str | None = None):
    if os.getenv("TALKINGBOATS_CLIP_STORE_BACKEND", "sqlite") == "dynamodb":
        from talkingboats.dynamo_clip_store import dynamo_clip_store_from_env

        return dynamo_clip_store_from_env(aws_region=aws_region)
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
        "save_strategy": "epoch",
        "logging_steps": 10,
        "report_to": [],
        "remove_unused_columns": False,
        "fp16": bool(torch.cuda.is_available()),
        "predict_with_generate": False,
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
    records = [
        {
            "key_hash": _short_hash(str(correction["key"])),
            "started_at": str(correction["started_at"]),
            "content_type": str(correction["content_type"]),
            "duration_seconds": correction["duration_seconds"],
            "text": str(correction["corrected_transcript"]),
        }
        for correction in corrections
    ]
    return _fingerprint_records(records)


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
    nightly.add_argument("--max-corrections", type=int, default=None)
    nightly.add_argument(
        "--restart-service",
        default=os.getenv("TALKINGBOATS_ASR_RESTART_SERVICE", DEFAULT_RESTART_SERVICE),
    )
    nightly.add_argument("--skip-restart", action="store_true")

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
        bucket=args.bucket,
        aws_region=args.aws_region,
        base_model=args.base_model,
        min_corrections=args.min_corrections,
        max_corrections=args.max_corrections,
        epochs=args.epochs,
        train_batch_size=args.train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        warmup_steps=args.warmup_steps,
        quantization=args.quantization,
        restart_service=None if args.skip_restart else args.restart_service,
    )
    print(json.dumps(run_nightly_training(config), sort_keys=True))


def _add_common_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--aws-region", default=os.getenv("AWS_REGION", "us-west-2"))
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument("--min-corrections", type=int, default=DEFAULT_MIN_CORRECTIONS)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--train-batch-size", type=int, default=4)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--warmup-steps", type=int, default=20)
    parser.add_argument("--quantization", default="int8")


if __name__ == "__main__":
    main()
