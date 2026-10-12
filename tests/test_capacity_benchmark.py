import hashlib
import itertools
import json

import faster_whisper

from talkingboats import capacity_benchmark as capacity


def test_candidate_uses_verified_full_audio_and_hourly_workload_with_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("TALKINGBOATS_ASR_OUTPUT_DIR", str(tmp_path / "feedback"))
    work = tmp_path / "audit"
    work.mkdir()
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "active_channels": ["14", "13"],
                "channels": [
                    {"channel": c, "hourly_audio_seconds": {"busy": 1000}} for c in ["14", "13"]
                ],
            }
        )
    )
    records = [
        dict(key=f"raw/{c}/{n}.mp3", channel=c, duration_seconds=10)
        for c in ["14", "13"]
        for n in range(10)
    ]
    measured = []
    for row in records:
        source_id = hashlib.sha256(row["key"].encode()).hexdigest()
        measured.append(source_id)
        (work / (source_id + ".mp3")).write_bytes(row["key"].encode())
    (work / "inventory.json").write_text(json.dumps(records))
    (work / "benchmark-checkpoint.json").write_text(json.dumps({"completed": measured}))
    manifest = capacity.prepare_samples(selection, work, tmp_path)
    config = {
        "capacity_selection_sha256": capacity.digest(selection),
        "capacity_manifest_sha256": capacity.digest(manifest),
    }
    monkeypatch.setattr(capacity, "SELECTION_PATH", selection)
    calls = []

    class Model:
        def __init__(self, model, **kwargs):
            assert kwargs == dict(device="cpu", compute_type="int8", cpu_threads=2, num_workers=1)

        def transcribe(self, path, **kwargs):
            assert kwargs == dict(language="en", beam_size=5, vad_filter=False, hotwords="Osprey")
            calls.append(path)
            return iter([]), None

    monkeypatch.setattr(faster_whisper, "WhisperModel", Model)
    ticks = itertools.count(step=1)
    monkeypatch.setattr(capacity, "_clock", lambda: next(ticks))
    checkpoint = tmp_path / "run"
    checkpoint.mkdir()
    result = capacity.benchmark_candidate(
        config, "isolated-model", "Osprey", lambda *a, **k: None, checkpoint
    )
    assert result["passes"] and result["peak_hour_processing_seconds"] == 200
    assert (
        len(calls) == 21
    )  # One warm-up plus twenty complete recordings, not selected transcript ranges.
    assert capacity.benchmark_candidate(
        config, "isolated-model", "Osprey", lambda *a, **k: None, checkpoint
    )["passes"]
    assert len(calls) == 21
    for path in capacity.sample_directory(config["capacity_selection_sha256"]).glob("*.mp3"):
        path.write_bytes(b"changed input")
        break
    import pytest

    with pytest.raises(ValueError, match="audio identity changed"):
        capacity.benchmark_candidate(
            config, "isolated-model", "Osprey", lambda *a, **k: None, checkpoint
        )


def test_missing_representative_capacity_proof_keeps_candidates_ineligible(tmp_path, monkeypatch):
    monkeypatch.setenv("TALKINGBOATS_ASR_OUTPUT_DIR", str(tmp_path / "feedback"))
    result = capacity.benchmark_candidate(
        {"capacity_selection_sha256": "a" * 64}, "fixture", "", lambda *a, **k: None, tmp_path
    )
    assert result["passes"] is False
