import json
import wave
from datetime import UTC, datetime

import pytest

from talkingboats.publish import sanitize_public_manifest
from talkingboats.simulator import RadioSimulationConfig, generate_radio_fixture


def test_simulator_writes_deterministic_audio_and_private_manifest(tmp_path):
    config = RadioSimulationConfig(
        output_dir=tmp_path,
        clip_count=4,
        seed=20260520,
        started_at=datetime(2026, 5, 20, 19, 12, tzinfo=UTC),
    )

    manifest = generate_radio_fixture(config)
    generated_again = generate_radio_fixture(config)

    assert manifest == generated_again
    assert (tmp_path / "private_manifest.json").exists()
    assert json.loads((tmp_path / "private_manifest.json").read_text(encoding="utf-8")) == manifest
    assert manifest["stats"]["channel_counts"] == {"68": 2, "14": 2}
    assert len(manifest["ais_tracks"]) == 4
    assert len(manifest["ais_tracks"][0]["points"]) >= 5

    first_audio = tmp_path / "audio" / manifest["clips"][0]["audio_public_filename"]
    assert first_audio.exists()
    with wave.open(str(first_audio), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 8000
        assert wav.getnframes() > 0


def test_simulator_fixture_can_drive_public_export_without_private_leaks(tmp_path):
    manifest = generate_radio_fixture(
        RadioSimulationConfig(
            output_dir=tmp_path,
            clip_count=6,
            seed=14,
            started_at=datetime(2026, 5, 20, 20, 0, tzinfo=UTC),
        )
    )

    public_manifest = sanitize_public_manifest(manifest)
    rendered = json.dumps(public_manifest)

    assert public_manifest["stats"]["clip_count"] == 4
    assert len(public_manifest["ais_tracks"]) > 0
    assert "receiver_id" not in json.dumps(public_manifest["ais_tracks"])
    assert "private_s3_key" not in json.dumps(public_manifest["ais_tracks"])
    assert "points" in public_manifest["ais_tracks"][0]
    assert "private_s3_key" not in rendered
    assert "receiver_id" not in rendered
    assert "raw/channel=" not in rendered
    assert {clip["channel"] for clip in public_manifest["clips"]} == {"68", "14"}


def test_simulator_rejects_unbounded_clip_counts(tmp_path):
    with pytest.raises(ValueError, match="clip_count"):
        RadioSimulationConfig(output_dir=tmp_path, clip_count=0)

    with pytest.raises(ValueError, match="clip_count"):
        RadioSimulationConfig(output_dir=tmp_path, clip_count=501)
