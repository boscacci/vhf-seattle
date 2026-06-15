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
    _corrected_clip(store, index=0, include_in_training=True)

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


def test_nightly_training_can_use_cloud_corrections_without_sqlite(tmp_path: Path) -> None:
    store = FakeCorrectionStore(
        [
            _correction_payload(
                key="raw/channel=14/date=2026-05-20/cloud-0.mp3",
                corrected_transcript="PAN-PAN reviewed cloud 0.",
            ),
            _correction_payload(
                key="raw/channel=14/date=2026-05-20/cloud-1.mp3",
                corrected_transcript="PAN-PAN reviewed cloud 1.",
            ),
        ]
    )
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
            "PAN-PAN reviewed cloud 0.",
            "PAN-PAN reviewed cloud 1.",
        ]
        model_dir = run_dir / "model-ct2"
        model_dir.mkdir()
        (model_dir / "model.bin").write_bytes(b"model")
        return {"ct2_model_dir": str(model_dir)}

    result = run_nightly_training(
        AsrFeedbackConfig(
            db_path=None,
            output_dir=tmp_path / "asr",
            min_corrections=2,
            restart_service=None,
        ),
        correction_store=store,
        clip_reader=FakeReader(),
        trainer=fake_trainer,
        now=datetime(2026, 5, 31, 10, 0, tzinfo=UTC),
    )

    assert result["status"] == "trained"
    assert downloads == [
        "raw/channel=14/date=2026-05-20/cloud-0.mp3",
        "raw/channel=14/date=2026-05-20/cloud-1.mp3",
    ]


def test_nightly_training_materializes_audio_and_promotes_model(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    _corrected_clip(store, index=0, include_in_training=True)
    _corrected_clip(store, index=1, include_in_training=True)
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
        assert config.freeze_encoder is True
        assert config.gradient_checkpointing is True
        assert config.save_checkpoints is False
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
    assert result["promotion"]["status"] == "skipped"
    assert result["promotion"]["reason"] == "candidate eval did not prove improvement"
    assert downloads == [
        "raw/channel=14/date=2026-05-20/fake-1.mp3",
        "raw/channel=14/date=2026-05-20/fake-0.mp3",
    ]
    assert not (tmp_path / "asr" / "latest-ct2").exists()
    status = json.loads((tmp_path / "asr" / "training_status.json").read_text())
    assert status["status"] == "trained"
    assert len(status["correction_fingerprint"]) == 64
    assert status["promotion"]["status"] == "skipped"


def test_nightly_training_promotes_when_local_eval_improves_baseline(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    _corrected_clip(store, index=0, include_in_training=True)
    _corrected_clip(store, index=1, include_in_training=True)

    class FakeReader:
        def download(self, key: str, output_path: Path) -> None:
            output_path.write_bytes(f"audio for {key}".encode())

    def fake_trainer(
        config: AsrFeedbackConfig,
        run_dir: Path,
        dataset_path: Path,
    ) -> dict[str, object]:
        model_dir = run_dir / "model-ct2"
        model_dir.mkdir()
        (model_dir / "model.bin").write_bytes(b"model")
        return {
            "ct2_model_dir": str(model_dir),
            "eval": {
                "baseline_wer": 0.32,
                "candidate_wer": 0.21,
                "clip_count": 12,
                "baseline_model": "turbo",
            },
        }

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

    latest_model = tmp_path / "asr" / "latest-ct2"
    assert result["promotion"]["status"] == "promoted"
    assert result["latest_model_dir"] == str(latest_model)
    assert (latest_model / "model.bin").read_bytes() == b"model"
    assert f"TALKINGBOATS_TRANSCRIBE_MODEL={latest_model}" in (
        tmp_path / "asr" / "latest_model.env"
    ).read_text()


def test_nightly_training_archives_audio_and_reuses_it_when_source_expires(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "clips.sqlite3"
    output_dir = tmp_path / "asr"
    store = UploadedClipStore(db_path)
    _corrected_clip(store, index=0, include_in_training=True)
    _corrected_clip(store, index=1, include_in_training=True)
    downloads: list[str] = []

    class ArchivingReader:
        def download(self, key: str, output_path: Path) -> None:
            downloads.append(key)
            output_path.write_bytes(f"audio for {key}".encode())

    def fake_trainer(
        config: AsrFeedbackConfig,
        run_dir: Path,
        dataset_path: Path,
    ) -> dict[str, object]:
        records = [json.loads(line) for line in dataset_path.read_text().splitlines()]
        assert all(Path(record["audio_archive"]).exists() for record in records)
        model_dir = run_dir / "model-ct2"
        model_dir.mkdir()
        (model_dir / "model.bin").write_bytes(b"model")
        return {"ct2_model_dir": str(model_dir)}

    first = run_nightly_training(
        AsrFeedbackConfig(
            db_path=db_path,
            output_dir=output_dir,
            min_corrections=2,
            restart_service=None,
        ),
        clip_reader=ArchivingReader(),
        trainer=fake_trainer,
        now=datetime(2026, 5, 31, 10, 0, tzinfo=UTC),
    )
    assert first["status"] == "trained"
    assert len(downloads) == 2
    archive_files = sorted((output_dir / "training-audio").glob("*.mp3"))
    assert len(archive_files) == 2

    store.correct_transcript(
        channel="14",
        started_at="2026-05-20T19:12:00Z",
        corrected_transcript="PAN-PAN reviewed zero after source expiry.",
        reviewer="test",
        include_in_training=True,
        training_quality="good",
    )

    class ExpiredSourceReader:
        def download(self, key: str, output_path: Path) -> None:
            raise FileNotFoundError(key)

    second = run_nightly_training(
        AsrFeedbackConfig(
            db_path=db_path,
            output_dir=output_dir,
            min_corrections=2,
            restart_service=None,
        ),
        clip_reader=ExpiredSourceReader(),
        trainer=fake_trainer,
        now=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
    )

    assert second["status"] == "trained"
    assert len(list((output_dir / "training-audio").glob("*.json"))) == 2


def test_nightly_training_skips_when_labeled_dataset_matches_last_trained_run(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "clips.sqlite3"
    output_dir = tmp_path / "asr"
    store = UploadedClipStore(db_path)
    _corrected_clip(store, index=0, include_in_training=True)
    _corrected_clip(store, index=1, include_in_training=True)
    trainer_calls = 0

    class FakeReader:
        def download(self, key: str, output_path: Path) -> None:
            output_path.write_bytes(f"audio for {key}".encode())

    def fake_trainer(
        config: AsrFeedbackConfig,
        run_dir: Path,
        dataset_path: Path,
    ) -> dict[str, str]:
        nonlocal trainer_calls
        trainer_calls += 1
        model_dir = run_dir / "model-ct2"
        model_dir.mkdir()
        (model_dir / "model.bin").write_bytes(f"model-{trainer_calls}".encode())
        return {"ct2_model_dir": str(model_dir)}

    first = run_nightly_training(
        AsrFeedbackConfig(
            db_path=db_path,
            output_dir=output_dir,
            min_corrections=2,
            restart_service=None,
        ),
        clip_reader=FakeReader(),
        trainer=fake_trainer,
        now=datetime(2026, 5, 31, 10, 0, tzinfo=UTC),
    )
    second = run_nightly_training(
        AsrFeedbackConfig(
            db_path=db_path,
            output_dir=output_dir,
            min_corrections=2,
            restart_service=None,
        ),
        clip_reader=FakeReader(),
        trainer=fake_trainer,
        now=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
    )

    assert first["status"] == "trained"
    assert second["status"] == "skipped"
    assert second["reason"] == "no new reviewed transcript corrections since last trained run"
    assert second["correction_count"] == 2
    assert second["last_trained_at"] == "2026-05-31T10:00:00Z"
    assert second["correction_fingerprint"] == first["correction_fingerprint"]
    assert trainer_calls == 1
    assert len(list((output_dir / "runs").iterdir())) == 1


def test_nightly_training_retrains_when_reviewed_correction_changes(tmp_path: Path) -> None:
    db_path = tmp_path / "clips.sqlite3"
    output_dir = tmp_path / "asr"
    store = UploadedClipStore(db_path)
    _corrected_clip(store, index=0, include_in_training=True)
    _corrected_clip(store, index=1, include_in_training=True)
    trainer_calls = 0

    class FakeReader:
        def download(self, key: str, output_path: Path) -> None:
            output_path.write_bytes(f"audio for {key}".encode())

    def fake_trainer(
        config: AsrFeedbackConfig,
        run_dir: Path,
        dataset_path: Path,
    ) -> dict[str, str]:
        nonlocal trainer_calls
        trainer_calls += 1
        model_dir = run_dir / "model-ct2"
        model_dir.mkdir()
        (model_dir / "model.bin").write_bytes(f"model-{trainer_calls}".encode())
        return {"ct2_model_dir": str(model_dir)}

    first = run_nightly_training(
        AsrFeedbackConfig(
            db_path=db_path,
            output_dir=output_dir,
            min_corrections=2,
            restart_service=None,
        ),
        clip_reader=FakeReader(),
        trainer=fake_trainer,
        now=datetime(2026, 5, 31, 10, 0, tzinfo=UTC),
    )
    store.correct_transcript(
        channel="14",
        started_at="2026-05-20T19:12:00Z",
        corrected_transcript="PAN-PAN reviewed zero with a better label.",
        reviewer="test",
    )
    second = run_nightly_training(
        AsrFeedbackConfig(
            db_path=db_path,
            output_dir=output_dir,
            min_corrections=2,
            restart_service=None,
        ),
        clip_reader=FakeReader(),
        trainer=fake_trainer,
        now=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
    )

    assert first["status"] == "trained"
    assert second["status"] == "trained"
    assert second["correction_fingerprint"] != first["correction_fingerprint"]
    assert trainer_calls == 2


def test_nightly_training_skips_when_old_status_dataset_matches_current_labels(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "clips.sqlite3"
    output_dir = tmp_path / "asr"
    store = UploadedClipStore(db_path)
    _corrected_clip(store, index=0, include_in_training=True)
    _corrected_clip(store, index=1, include_in_training=True)
    trainer_calls = 0

    class FakeReader:
        def download(self, key: str, output_path: Path) -> None:
            output_path.write_bytes(f"audio for {key}".encode())

    def fake_trainer(
        config: AsrFeedbackConfig,
        run_dir: Path,
        dataset_path: Path,
    ) -> dict[str, str]:
        nonlocal trainer_calls
        trainer_calls += 1
        model_dir = run_dir / "model-ct2"
        model_dir.mkdir()
        (model_dir / "model.bin").write_bytes(f"model-{trainer_calls}".encode())
        return {"ct2_model_dir": str(model_dir)}

    first = run_nightly_training(
        AsrFeedbackConfig(
            db_path=db_path,
            output_dir=output_dir,
            min_corrections=2,
            restart_service=None,
        ),
        clip_reader=FakeReader(),
        trainer=fake_trainer,
        now=datetime(2026, 5, 31, 10, 0, tzinfo=UTC),
    )
    status_path = output_dir / "training_status.json"
    old_status = json.loads(status_path.read_text(encoding="utf-8"))
    old_status.pop("correction_fingerprint")
    status_path.write_text(json.dumps(old_status), encoding="utf-8")

    second = run_nightly_training(
        AsrFeedbackConfig(
            db_path=db_path,
            output_dir=output_dir,
            min_corrections=2,
            restart_service=None,
        ),
        clip_reader=FakeReader(),
        trainer=fake_trainer,
        now=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
    )

    assert first["status"] == "trained"
    assert second["status"] == "skipped"
    assert second["reason"] == "no new reviewed transcript corrections since last trained run"
    assert trainer_calls == 1


def _corrected_clip(
    store: UploadedClipStore,
    *,
    index: int,
    include_in_training: bool = False,
) -> None:
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
        include_in_training=include_in_training,
        training_quality="good" if include_in_training else "unknown",
    )


def _correction_payload(*, key: str, corrected_transcript: str) -> dict[str, object]:
    return {
        "key": key,
        "channel": "14",
        "started_at": "2026-05-20T19:12:00Z",
        "ended_at": "2026-05-20T19:12:05Z",
        "duration_seconds": 5.0,
        "content_type": "audio/mpeg",
        "original_transcript": "PON PON reviewed cloud.",
        "corrected_transcript": corrected_transcript,
        "reviewer": "test",
        "note": None,
    }


class FakeCorrectionStore:
    def __init__(self, corrections: list[dict[str, object]]) -> None:
        self.corrections = corrections

    def transcript_corrections_for_training(self) -> list[dict[str, object]]:
        return self.corrections


class _Segment:
    def __init__(self, *, text: str, started_at: str, ended_at: str) -> None:
        self.text = text
        self.started_at = started_at
        self.ended_at = ended_at
        self.relative_start_seconds = 0.0
        self.relative_end_seconds = 5.0
