from pathlib import Path


def test_asr_feedback_nightly_script_uses_lock_and_restarts_transcriber() -> None:
    script = Path("scripts/train_asr_feedback_nightly.sh").read_text(encoding="utf-8")

    assert "TALKINGBOATS_ASR_FEEDBACK_LOCK_DIR" in script
    assert "talkingboats-train-asr-feedback" in script
    assert "--min-corrections" in script
    assert "--base-model" in script
    assert "--quantization" in script
    assert "--restart-service" in script
    assert "talkingboats-uploaded-clip-transcriber.service" in script


def test_asr_feedback_systemd_timer_runs_nightly() -> None:
    service = Path("deploy/systemd/talkingboats-asr-feedback-train.service.example").read_text(
        encoding="utf-8"
    )
    timer = Path("deploy/systemd/talkingboats-asr-feedback-train.timer.example").read_text(
        encoding="utf-8"
    )

    assert "Description=Elliott Bay VHF ASR feedback training" in service
    assert "scripts/train_asr_feedback_nightly.sh" in service
    assert "EnvironmentFile=-/home/rob/repos/elliott-bay-vhf/.env" in service
    assert "Nice=15" in service
    assert "OnCalendar=*-*-* 03:20:00" in timer
    assert "Persistent=true" in timer
    assert "Unit=talkingboats-asr-feedback-train.service" in timer


def test_uploaded_clip_transcriber_can_load_promoted_feedback_model() -> None:
    service = Path(
        "deploy/systemd/talkingboats-uploaded-clip-transcriber.service.example"
    ).read_text(encoding="utf-8")

    assert (
        "EnvironmentFile=-/home/rob/repos/elliott-bay-vhf/outputs/asr-feedback/latest_model.env"
        in service
    )
    assert "Nice=10" in service
    assert "CPUWeight=25" in service
    assert "CPUQuota=125%" in service
    assert "IOSchedulingPriority=6" in service
