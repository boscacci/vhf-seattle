"""Prune only channel blocks from deployed RTLSDR-Airband config; preserve receiver settings."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


def channel_blocks(text):
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
            if re.match(r"\{\s*freq\s*=", body):
                label = re.search(r'label\s*=\s*"vhf-([a-z0-9]+)"\s*;', body)
                if not label:
                    raise ValueError("channel has no recognized marine label")
                spans.append((start, position + 1, label[1].upper(), body))
    if stack or quoted:
        raise ValueError("unbalanced receiver configuration")
    return sorted(spans)


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
    a = p.parse_args()
    source = a.path.read_text()
    result = prune(source, a.channels.split(","))
    if a.write:
        temporary = a.path.with_suffix(".pending")
        temporary.write_text(result)
        temporary.chmod(0o600)
        temporary.replace(a.path)
    print("event=receiver_config_validated sha256=" + hashlib.sha256(result.encode()).hexdigest())


if __name__ == "__main__":
    main()
