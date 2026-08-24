from __future__ import annotations

from pathlib import Path

from talkingboats.api import app

RETIRED_TRAINING_PATHS = (
    "deploy/systemd/talkingboats-asr-feedback-train.service.example",
    "examples/reviewed_clips.example.json",
    "scripts/train_asr_feedback_nightly.sh",
    "src/talkingboats/asr_feedback.py",
    "src/talkingboats/asr_training_metadata.py",
    "tests/test_asr_feedback.py",
    "tests/test_asr_feedback_schedule.py",
)


def test_repo_has_no_asr_training_or_labeling_surface() -> None:
    for relative_path in RETIRED_TRAINING_PATHS:
        assert not Path(relative_path).exists(), relative_path

    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "asr-train" not in pyproject
    assert "talkingboats-train-asr-feedback" not in pyproject

    routes = {route.path for route in app.routes}
    assert "/api/asr-feedback/status" not in routes
    assert "/api/clips/corrections" not in routes
    assert "/api/clips/corrections/export" not in routes

    runtime_text = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (
            Path("src/talkingboats"),
            Path("public-site"),
            Path("deploy/systemd"),
            Path("scripts"),
        )
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".js", ".html", ".sh", ".example"}
    )
    for retired_term in (
        "asr_feedback",
        "ASR_FEEDBACK",
        "include_in_training",
        "training_quality",
        "training_split",
        "training_flags",
        "training_reason",
        "transcript_reviewed",
    ):
        assert retired_term not in runtime_text
