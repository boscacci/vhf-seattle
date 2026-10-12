import pytest

from talkingboats.receiver_config import channel_blocks, prune


def test_receiver_pruning_preserves_selected_frequency_squelch_and_escaped_password():
    config = (
        'devices:({ serial="VOICE"; gain=28; channels:('
        + ",".join(
            "{ freq="
            + str(frequency)
            + '; label="vhf-'
            + ch
            + '"; squelch_threshold=-35; outputs:({password="fixture\\"}only";}); }'
            for ch, frequency in [("14", 156700000), ("74", 156725000), ("16", 156800000)]
        )
        + ");});"
    )
    result = prune(config, ["14", "16"])
    assert [b[2] for b in channel_blocks(result)] == ["14", "16"]
    assert "squelch_threshold=-35" in result and "gain=28" in result
    assert "156725000" not in result
    assert 'fixture\\"}only' in result
    with pytest.raises(ValueError):
        prune(config, ["13"])
