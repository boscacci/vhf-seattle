import tomllib
from pathlib import Path


def test_asr_feedback_training_extra_includes_audio_decoders() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    asr_train_deps = pyproject["project"]["optional-dependencies"]["asr-train"]

    assert any(dep.startswith("librosa") for dep in asr_train_deps)
    assert any(dep.startswith("soundfile") for dep in asr_train_deps)


def test_asr_feedback_nightly_script_uses_lock_and_restarts_transcriber() -> None:
    script = Path("scripts/train_asr_feedback_nightly.sh").read_text(encoding="utf-8")

    assert "TALKINGBOATS_ASR_FEEDBACK_LOCK_DIR" in script
    assert 'clip_store_backend="${TALKINGBOATS_CLIP_STORE_BACKEND:-dynamodb}"' in script
    assert "talkingboats-train-asr-feedback" in script
    assert "--min-corrections" in script
    assert "--base-model" in script
    assert "--quantization" in script
    assert "--restart-service" in script
    assert 'train_batch_size="${TALKINGBOATS_ASR_FEEDBACK_TRAIN_BATCH_SIZE:-1}"' in script
    assert (
        'gradient_accumulation_steps="${TALKINGBOATS_ASR_FEEDBACK_GRADIENT_ACCUMULATION_STEPS:-8}"'
        in script
    )
    assert "talkingboats-uploaded-clip-transcriber.service" in script
    assert "live-transcripts.sqlite3" not in script
    assert "--db-path" not in script


def test_asr_feedback_training_service_is_manual_only() -> None:
    service = Path("deploy/systemd/talkingboats-asr-feedback-train.service.example").read_text(
        encoding="utf-8"
    )

    assert "Description=Elliott Bay VHF ASR feedback training" in service
    assert "scripts/train_asr_feedback_nightly.sh" in service
    assert (
        "EnvironmentFile=-/home/rob/repos/elliott-bay-vhf-live-ais-deploy/.env" in service
    )
    assert "Nice=15" in service
    assert not Path("deploy/systemd/talkingboats-asr-feedback-train.timer.example").exists()


def test_uploaded_clip_transcriber_pins_capacity_tested_model() -> None:
    service = Path(
        "deploy/systemd/talkingboats-uploaded-clip-transcriber.service.example"
    ).read_text(encoding="utf-8")

    assert "outputs/asr-feedback/latest_model.env" not in service
    assert "Environment=TALKINGBOATS_TRANSCRIBE_MODEL=base.en" in service
    assert "Nice=10" in service
    assert "CPUWeight=25" in service
    assert "CPUQuota=200%" in service
    assert "IOSchedulingPriority=6" in service


def test_live_captions_use_processed_clip_queue_not_streaming_transcriber_service() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")
    docs = Path("docs/docker-orchestration.md").read_text(encoding="utf-8")

    assert not Path("deploy/systemd/talkingboats-live-transcriber.service.example").exists()
    assert "live-transcriber" not in compose
    assert "talkingboats-live-transcriber" not in docs
    assert "uploaded-clip-transcriber" in compose
