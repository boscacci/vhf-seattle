from talkingboats.asr_experiments import dataset_summary, evaluate_predictions, promotion_decision


def test_partial_and_reverted_labels_do_not_count_toward_readiness():
    summary = dataset_summary(
        [
            {"reviewed": False, "duration_seconds": 600, "text": "Osprey"},
            {"reviewed": True, "reverted": True, "duration_seconds": 600},
        ]
    )
    assert summary["ready"] is False
    assert summary["minutes"] == {"train": 0, "validation": 0, "test": 0}


def test_candidate_must_beat_hints_without_inventing_more_names_or_exceeding_wer():
    baseline = {"entity_errors": 10, "invented_names": 1, "wer": 0.20}
    good = {"entity_errors": 8, "invented_names": 1, "wer": 0.205}
    assert promotion_decision(baseline, good, mentions=50, capacity_passed=True)["eligible"]
    assert not promotion_decision(baseline, good, mentions=49, capacity_passed=True)["eligible"]
    assert not promotion_decision(baseline, good, mentions=50, capacity_passed=False)["eligible"]
    assert not promotion_decision(
        baseline, {**good, "invented_names": 2}, mentions=50, capacity_passed=True
    )["eligible"]


def test_metrics_count_real_entity_mentions_and_word_errors():
    rows = [{"text": "Osprey northbound", "terms": ["Osprey"]}]
    good = evaluate_predictions(rows, ["Osprey northbound"], vocabulary=["Osprey", "Kingston"])
    bad = evaluate_predictions(rows, ["Kingston northbound"], vocabulary=["Osprey", "Kingston"])
    assert good["wer"] == 0 and good["entity_errors"] == 0
    assert bad["wer"] == 0.5 and bad["entity_errors"] == 1 and bad["invented_names"] == 1


def test_holdout_vocabulary_never_enters_training_hints():
    rows = [
        dict(
            reviewed=True,
            archive_status="ready",
            duration_seconds=30,
            channel="14",
            text=term,
            terms=[term],
            split=split,
        )
        for term, split in [("Osprey", "train"), ("Kingston", "validation"), ("Tacoma", "test")]
    ]
    assert dataset_summary(rows)["vocabulary"] == ["Osprey"]


def test_cancel_retains_checkpoint_and_stopped_worker_is_ineligible(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    from talkingboats import asr_experiments as experiments

    monkeypatch.setenv("TALKINGBOATS_ASR_OUTPUT_DIR", str(tmp_path))
    run_id = "a" * 32
    directory = experiments.run_directory(run_id)
    experiments.atomic_json(
        directory / "status.json", {"id": run_id, "status": "running", "eligible": True}
    )
    checkpoint = directory / "checkpoints" / "checkpoint-20"
    checkpoint.mkdir(parents=True)
    cancelled = experiments.cancel_run(run_id)
    assert cancelled["status"] == "cancelling" and not cancelled["eligible"]
    assert (directory / "cancel").exists() and checkpoint.exists()
    monkeypatch.setattr(
        experiments.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="failed\n")
    )
    stopped = experiments.list_runs()[0]
    assert stopped["status"] == "interrupted" and not stopped["eligible"]
    assert json.loads((directory / "status.json").read_text())["status"] == "interrupted"


def test_repeated_completed_dataset_reuses_immutable_run(tmp_path, monkeypatch):
    from talkingboats import asr_experiments as experiments

    monkeypatch.setenv("TALKINGBOATS_ASR_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(experiments, "dataset_summary", lambda rows: {"ready": True})

    class Result:
        stdout = "active"

    calls = []

    def dispatch(*args, **kwargs):
        calls.append(args[0])
        return Result()

    monkeypatch.setattr(experiments.subprocess, "run", dispatch)
    row = dict(id="fixture", revision=1, reviewed=True, archive_status="ready", channel="14")
    started = experiments.start_run([row])
    experiments.atomic_json(
        experiments.run_directory(started["id"]) / "status.json", {**started, "status": "completed"}
    )
    again = experiments.start_run([row])
    assert again["id"] == started["id"] and again["status"] == "completed"
    assert sum("start" in c for c in calls) == 1


def test_oversized_reviewed_audio_stays_pending_and_is_not_copied(monkeypatch):
    import boto3

    from talkingboats import asr_experiments as experiments

    class S3:
        def head_object(self, **kwargs):
            return {"ContentLength": 26 * 1024**2, "ETag": "fixture"}

        def copy_object(self, **kwargs):
            raise AssertionError("oversized audio must not be archived")

    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: S3())

    class Store:
        table = None

    row = {"id": "fixture", "key": "fixture.mp3", "archive_status": "pending"}
    experiments.archive_label(Store(), row, "fixture-bucket")
    assert row["archive_status"] == "pending"
