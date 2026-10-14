from talkingboats.channel_metadata import ACTIVE_CAPTURE_CHANNELS, LIVE_STREAM_CHANNELS
from talkingboats.receiver_config import configure_channels


def test_eighteen_live_seven_recorded_without_74():
    assert set(ACTIVE_CAPTURE_CHANNELS) == {"14", "13", "16", "66A", "78A", "71", "22A"}
    assert len(LIVE_STREAM_CHANNELS) == 18 and "74" not in LIVE_STREAM_CHANNELS


def test_receiver_restores_stream_only_channels_and_preserves_retained_block():
    def block(hz, channel, mount):
        return (
            f'{{freq={hz};label="vhf-{channel}";outputs:('
            '{type="file";directory="private";},'
            f'{{type="icecast";mountpoint="{mount}";}});}}'
        )

    retained = block(156700000, "14", "talkingboats-live.mp3")
    extra = block(156300000, "06", "talkingboats-06.mp3")
    coast = block(157100000, "22a", "talkingboats-22a.mp3")
    current = "devices:({gain=28;channels:(" + retained + ");});"
    template = "devices:({gain=28;channels:(" + ",".join([retained, extra, coast]) + ");});"
    result = configure_channels(current, template, ["14", "06", "22A"], ["14", "22A"])
    assert retained in result and result.count('type="file"') == 2
    assert result.count('type="icecast"') == 3


def test_22a_requires_activation_and_old_audio_stays_ineligible(tmp_path, monkeypatch):
    from talkingboats.recording_policy import eligible, queue_checkpoint

    path = tmp_path / "activation.json"
    monkeypatch.setenv("TALKINGBOATS_RECORDING_ACTIVATIONS_FILE", str(path))
    assert eligible("14", "2026-01-01T00:00:00Z")
    assert not eligible("22A", "2026-10-13T00:00:00Z")
    before = queue_checkpoint(tmp_path)
    path.write_text('{"22A":"2026-10-13T12:00:00Z"}')
    assert not eligible("22A", "2026-10-12T23:00:00Z")
    assert eligible("22A", "2026-10-13T12:00:00Z")
    assert queue_checkpoint(tmp_path) != before


def test_channel_configuration_matches_recording_and_live_policy():
    import json
    from pathlib import Path

    from talkingboats.channel_metadata import LIVE_ONLY_CHANNELS

    values = json.loads(Path("config/channel-selection.json").read_text())
    assert values["active_channels"] == list(ACTIVE_CAPTURE_CHANNELS)
    assert set(values["live_only_channels"]) == set(LIVE_ONLY_CHANNELS)


def test_receiver_rejects_channel74_and_incomplete_template():
    import pytest

    with pytest.raises(ValueError):
        configure_channels("", "", ["74"], [])
    with pytest.raises(ValueError):
        configure_channels("", "", ["14"], ["14"])


def test_prior_queue_checkpoint_remains_unchanged(tmp_path, monkeypatch):
    import json

    from talkingboats.recording_policy import indexes_ready, queue_checkpoint

    old = tmp_path / "queue-index-cutover.json"
    old.write_text(
        json.dumps({"status_index": 3, "channels": ["14", "13", "16", "66A", "78A", "71"]})
    )
    original = old.read_bytes()
    monkeypatch.setenv("TALKINGBOATS_RECORDING_ACTIVATIONS_FILE", str(tmp_path / "activation.json"))
    assert indexes_ready(tmp_path)
    assert queue_checkpoint(tmp_path) != old
    (tmp_path / "activation.json").write_text('{"22A":"2026-10-14T01:00:00Z"}')
    assert not indexes_ready(tmp_path)
    assert old.read_bytes() == original
