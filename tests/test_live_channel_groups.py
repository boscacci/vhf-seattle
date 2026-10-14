"""Regression coverage for channel presets and newly recorded history boundaries."""

import json
import re
import subprocess
from pathlib import Path

from talkingboats.channel_metadata import ACTIVE_CAPTURE_CHANNELS
from talkingboats.recording_policy import activation_boundaries, eligible


def test_live_presets_filter_recent_clips_without_recording_labels():
    source = Path("public-site/assets/app.js").read_text()
    names = [
        "isEverythingLiveMode",
        "isAllButTrafficLiveMode",
        "isQueuedLiveMode",
        "queueChannelsForMode",
        "excludedQueueChannelsForMode",
        "isQueueClipAllowedForCurrentMode",
        "liveQueueRequestUrl",
    ]
    functions = "\n".join(
        re.search(rf"function {name}\([^\n]*\) \{{\n.*?\n\}}", source, re.S).group()
        for name in names
    )
    constants = "\n".join(
        line
        for line in source.splitlines()
        if line.startswith("const ")
        and any(
            name in line
            for name in [
                "recordedRadioChannels =",
                "everythingLiveChannel =",
                "allButTrafficLiveChannel =",
                "coastGuardLiveChannel =",
                "liveTrafficChannelIds =",
                "coastGuardChannelIds =",
            ]
        )
    )
    script = (
        constants
        + "\n"
        + functions
        + "\n"
        + r"""
const assert = require('node:assert/strict');
const apiUrl = path => 'https://example.test' + path;
const liveQueueUrl = 'https://example.test/api/clips/recent';
let selectedLiveChannel = everythingLiveChannel;
assert(isQueuedLiveMode());
assert(isQueueClipAllowedForCurrentMode({channel:'09'}));
assert(!isQueueClipAllowedForCurrentMode({channel:'73'}));
assert(!isQueueClipAllowedForCurrentMode({channel:'74'}));
assert.equal(queueChannelsForMode().length,13);
selectedLiveChannel = allButTrafficLiveChannel;
assert(!isQueueClipAllowedForCurrentMode({channel:'14'}));
assert(isQueueClipAllowedForCurrentMode({channel:'09'}));
assert.deepEqual(excludedQueueChannelsForMode().sort(),['05A','14']);
selectedLiveChannel = coastGuardLiveChannel;
assert(isQueuedLiveMode());
assert.deepEqual(queueChannelsForMode().sort(),['16','22A']);
assert(isQueueClipAllowedForCurrentMode({channel:'16'}));
assert(!isQueueClipAllowedForCurrentMode({channel:'09'}));
const requested = new URL(liveQueueRequestUrl()).searchParams.getAll('channels');
assert.deepEqual(requested.sort(),['16','22A']);
selectedLiveChannel = '06';
assert(!isQueuedLiveMode());
"""
    )
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    assert "All recorded channels" not in source
    assert "Live only" not in source


def test_four_non_port_channels_require_new_activation_without_resetting_existing(
    tmp_path, monkeypatch
):
    added = {"09", "67", "69", "72"}
    assert added <= set(ACTIVE_CAPTURE_CHANNELS)
    path = tmp_path / "activations.json"
    old = {c: "2026-10-13T12:00:00Z" for c in ("22A", "77", "65A")}
    path.write_text(json.dumps(old))
    monkeypatch.setenv("TALKINGBOATS_RECORDING_ACTIVATIONS_FILE", str(path))
    boundaries = activation_boundaries()
    for c in added:
        assert not eligible(c, "2026-10-14T12:00:00Z", boundaries)
    import runpy

    runpy.run_path("scripts/activate_recording_policy.py")
    activated = json.loads(path.read_text())
    assert all(activated[c] == old[c] for c in old)
    assert len({activated[c] for c in added}) == 1
    for c in added:
        assert eligible(c, activated[c])
        assert not eligible(c, "2026-10-13T12:00:00Z")
    original = path.read_bytes()
    runpy.run_path("scripts/activate_recording_policy.py")
    assert path.read_bytes() == original


def test_receiver_adds_four_file_outputs_and_preserves_existing_streams():
    from talkingboats.channel_metadata import CHANNEL_METADATA, LIVE_STREAM_CHANNELS
    from talkingboats.receiver_config import channel_blocks, configure_channels, object_blocks

    added = {"09", "67", "69", "72"}
    old_recorded = set(ACTIVE_CAPTURE_CHANNELS) - added

    def block(channel, recorded):
        outputs = f'{{type="icecast";mountpoint="talkingboats-{channel.lower()}.mp3";}}'
        if recorded:
            outputs += ',{type="file";directory="fixture";}'
        return (
            f'{{freq={CHANNEL_METADATA[channel].frequency_hz};label="vhf-{channel.lower()}";'
            f"squelch=-30;outputs:({outputs});}}"
        )

    current = (
        "devices:({gain=28;channels:("
        + ",".join(block(c, c in old_recorded) for c in LIVE_STREAM_CHANNELS)
        + ");});"
    )
    template = (
        "devices:({gain=28;channels:("
        + ",".join(block(c, True) for c in LIVE_STREAM_CHANNELS)
        + ");});"
    )
    result = configure_channels(current, template, LIVE_STREAM_CHANNELS, ACTIVE_CAPTURE_CHANNELS)
    before = {c: b for _, _, c, b in channel_blocks(current)}
    after = {c: b for _, _, c, b in channel_blocks(result)}
    assert set(after) == set(LIVE_STREAM_CHANNELS)
    recorded = {c for c, b in after.items() if 'type="file"' in b}
    assert recorded == set(ACTIVE_CAPTURE_CHANNELS)
    for c in LIVE_STREAM_CHANNELS:
        if c not in added:
            assert after[c] == before[c]
        assert "squelch=-30" in after[c]
        original_stream = [
            o for _, _, o in object_blocks(before[c]) if o.startswith('{type="icecast"')
        ]
        new_stream = [o for _, _, o in object_blocks(after[c]) if o.startswith('{type="icecast"')]
        assert new_stream == original_stream
