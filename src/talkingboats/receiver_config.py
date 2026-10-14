"""Prune only channel blocks from deployed RTLSDR-Airband config; preserve receiver settings."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


def object_blocks(text):
    spans = []
    stack = []
    quoted = escaped = False
    for position, character in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
            continue
        if character == '"':
            quoted = True
        elif character == "{":
            stack.append(position)
        elif character == "}":
            if not stack:
                raise ValueError("unbalanced receiver configuration")
            start = stack.pop()
            body = text[start : position + 1]
            spans.append((start, position + 1, body))
    if stack or quoted:
        raise ValueError("unbalanced receiver configuration")
    return sorted(spans)


def channel_blocks(text):
    spans = []
    for start, end, body in object_blocks(text):
        if re.match(r"\{\s*freq\s*=", body):
            label = re.search(r'label\s*=\s*"vhf-([a-z0-9]+)"\s*;', body)
            if not label:
                raise ValueError("channel has no recognized marine label")
            spans.append((start, end, label[1].upper(), body))
    return spans


def configure_channels(current, template, live, recorded):
    from talkingboats.channel_metadata import CHANNEL_METADATA

    if "74" in live or len(set(live)) != len(live) or not set(recorded) <= set(live):
        raise ValueError("invalid live/recorded policy")
    current_blocks = channel_blocks(current)
    if not current_blocks:
        raise ValueError("no deployed receiver channels")
    existing = {row[2]: row[3] for row in current_blocks}
    original = {row[2]: row[3] for row in channel_blocks(template)}
    selected = []
    for channel in live:
        body = existing.get(channel, original.get(channel))
        if body is None:
            raise ValueError("missing receiver template channel")
        frequency = re.search(r"\bfreq\s*=\s*([0-9]+)", body)
        if not frequency or int(frequency[1]) != CHANNEL_METADATA[channel].frequency_hz:
            raise ValueError("receiver frequency does not match channel")
        outputs = [
            row
            for row in object_blocks(body)
            if re.match(r'\{\s*type\s*=\s*"(?:file|icecast)"', row[2])
        ]
        files = [row for row in outputs if re.match(r'\{\s*type\s*=\s*"file"', row[2])]
        streams = [row for row in outputs if re.match(r'\{\s*type\s*=\s*"icecast"', row[2])]
        if channel in recorded and not files and len(streams) == 1:
            template_files = [
                row[2]
                for row in object_blocks(original.get(channel, ""))
                if re.match(r'\{\s*type\s*=\s*"file"', row[2])
            ]
            if len(template_files) != 1:
                raise ValueError("missing recording output template")
            body = body[: streams[0][0]] + template_files[0] + "," + body[streams[0][0] :]
            selected.append(body)
            continue
        if len(streams) != 1 or (channel in recorded and len(files) != 1):
            raise ValueError("unexpected receiver output structure")
        if channel not in recorded:
            body = body[: outputs[0][0]] + streams[0][2] + body[outputs[-1][1] :]
        selected.append(body)
    return (
        current[: current_blocks[0][0]]
        + ",\n    ".join(selected)
        + current[current_blocks[-1][1] :]
    )


def prune(text, active):
    blocks = channel_blocks(text)
    if not blocks:
        raise ValueError("no receiver channels found")
    kept = [b for b in blocks if b[2] in active]
    if {b[2] for b in kept} != set(active) or len(kept) != len(set(active)):
        raise ValueError("receiver selection is missing or duplicated")
    # Deployed channels are contiguous libconfig records; reject unfamiliar structures.
    for left, right in zip(blocks, blocks[1:], strict=False):
        if text[left[1] : right[0]].strip().strip(",").strip():
            raise ValueError("unexpected configuration between receiver channels")
    result = text[: blocks[0][0]] + ",\n    ".join(b[3] for b in kept) + text[blocks[-1][1] :]
    if {b[2] for b in channel_blocks(result)} != set(active):
        raise ValueError("pruned configuration did not validate")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=Path)
    p.add_argument("--channels", required=True)
    p.add_argument("--write", action="store_true")
    p.add_argument("--live-channels")
    p.add_argument("--template", type=Path)
    a = p.parse_args()
    source = a.path.read_text()
    result = (
        configure_channels(
            source, a.template.read_text(), a.live_channels.split(","), a.channels.split(",")
        )
        if a.live_channels and a.template
        else prune(source, a.channels.split(","))
    )
    if a.write:
        temporary = a.path.with_suffix(".pending")
        temporary.write_text(result)
        temporary.chmod(0o600)
        temporary.replace(a.path)
    print("event=receiver_config_validated sha256=" + hashlib.sha256(result.encode()).hexdigest())


if __name__ == "__main__":
    main()
