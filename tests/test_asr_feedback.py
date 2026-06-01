from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from talkingboats.asr_feedback import AsrFeedbackConfig, run_nightly_training
from talkingboats.clip_transcriber import UploadedClipStore
from talkingboats.schemas import ClipPresignRequest


def test_nightly_training_skips_until_enough_corrections(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    _corrected_clip(store, index=0)

    result = run_nightly_training(
        AsrFeedbackConfig(
            db_path=db_path,
            output_dir=tmp_path / "asr",
            min_corrections=2,
        ),
        now=datetime(2026, 5, 31, 10, 0, tzinfo=UTC),
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "not enough reviewed transcript corrections"
    assert result["correction_count"] == 1
    status_path = tmp_path / "asr" / "training_status.json"
    assert json.loads(status_path.read_text())["status"] == "skipped"


def test_nightly_training_materializes_audio_and_promotes_model(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    _corrected_clip(store, index=0)
    _corrected_clip(store, index=1)
    downloads: list[str] = []

    class FakeReader:
        def download(self, key: str, output_path: Path) -> None:
            downloads.append(key)
            output_path.write_bytes(b"audio")

    def fake_trainer(
        config: AsrFeedbackConfig,
        run_dir: Path,
        dataset_path: Path,
    ) -> dict[str, str]:
        records = [json.loads(line) for line in dataset_path.read_text().splitlines()]
        assert [record["text"] for record in records] == [
            "PAN-PAN reviewed 1.",
            "PAN-PAN reviewed 0.",
        ]
        assert all(Path(record["audio"]).exists() for record in records)
        assert all("raw/channel" not in record["key_hash"] for record in records)
        model_dir = run_dir / "model-ct2"
        model_dir.mkdir()
        (model_dir / "model.bin").write_bytes(b"model")
        return {"ct2_model_dir": str(model_dir), "hf_model_dir": str(run_dir / "model-hf")}

    result = run_nightly_training(
        AsrFeedbackConfig(
            db_path=db_path,
            output_dir=tmp_path / "asr",
            min_corrections=2,
            restart_service=None,
        ),
        clip_reader=FakeReader(),
        trainer=fake_trainer,
        now=datetime(2026, 5, 31, 10, 0, tzinfo=UTC),
    )

    assert result["status"] == "trained"
    assert result["correction_count"] == 2
    assert downloads == [
        "raw/channel=14/date=2026-05-20/fake-1.mp3",
        "raw/channel=14/date=2026-05-20/fake-0.mp3",
    ]
    latest_model = tmp_path / "asr" / "latest-ct2"
    assert latest_model.exists()
    assert (latest_model / "model.bin").read_bytes() == b"model"
    env_text = (tmp_path / "asr" / "latest_model.env").read_text()
    assert f"TALKINGBOATS_TRANSCRIBE_MODEL={latest_model}" in env_text
    status = json.loads((tmp_path / "asr" / "training_status.json").read_text())
    assert status["status"] == "trained"


def _corrected_clip(store: UploadedClipStore, *, index: int) -> None:
    started_at = datetime(2026, 5, 20, 19, 12 + index, tzinfo=UTC)
    ended_at = started_at + timedelta(seconds=5)
    key = f"raw/channel=14/date=2026-05-20/fake-{index}.mp3"
    store.record_presigned_upload(
        key=key,
        request=ClipPresignRequest(
            channel="14",
            started_at=started_at,
            ended_at=ended_at,
            content_type="audio/mpeg",
            idempotency_key=f"radio-event-{index}",
            duration_seconds=5.0,
        ),
    )
    store.mark_transcribed(
        key,
        [
            _Segment(
                text=f"PON PON reviewed {index}.",
                started_at=started_at.isoformat().replace("+00:00", "Z"),
                ended_at=ended_at.isoformat().replace("+00:00", "Z"),
            )
        ],
    )
    store.correct_transcript(
        channel="14",
        started_at=started_at.isoformat().replace("+00:00", "Z"),
        corrected_transcript=f"PAN-PAN reviewed {index}.",
        reviewer="test",
    )


class _Segment:
    def __init__(self, *, text: str, started_at: str, ended_at: str) -> None:
        self.text = text
        self.started_at = started_at
        self.ended_at = ended_at
        self.relative_start_seconds = 0.0
        self.relative_end_seconds = 5.0
