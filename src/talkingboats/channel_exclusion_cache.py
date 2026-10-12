"""Remove excluded channels from derived public caches while preserving raw history."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from talkingboats.lexical_analysis import public_analysis
from talkingboats.publish import sanitize_public_manifest, write_recent_clip_snapshot


def sanitize_caches(site: Path, backup: Path):
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    names = [
        "public_manifest.json",
        "recent_clips.json",
        "operations.json",
        "analysis/lexical.json",
        "analysis/search_index.json",
        "analysis/topic_clusters.html",
    ]
    for name in names:
        path = site / name
        if path.is_file() and not (backup / name).exists():
            (backup / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, backup / name)
            (backup / name).chmod(0o600)

    def write(name, payload):
        path = site / name
        temporary = path.with_suffix(".pending")
        with temporary.open("w") as stream:
            json.dump(payload, stream, ensure_ascii=False)
        temporary.replace(path)

    manifest_path = site / "public_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for clip in manifest.get("clips", []):
            clip["approved_public"] = True  # Input is the existing public-safe export.
        manifest = sanitize_public_manifest(manifest)
        write("public_manifest.json", manifest)
        write_recent_clip_snapshot(site, manifest)
    lexical_path = site / "analysis/lexical.json"
    if lexical_path.exists():
        previous = json.loads(lexical_path.read_text())
        safe = public_analysis(previous)
        if safe != previous:
            write("analysis/lexical.json", safe)
            (site / "analysis/topic_clusters.html").write_text(
                "<!doctype html><p>Analysis is being refreshed for the selected channels.</p>"
            )
    search_path = site / "analysis/search_index.json"
    if search_path.exists():
        index = json.loads(search_path.read_text())
        index["clips"] = [clip for clip in index.get("clips", []) if clip.get("channel") != "74"]
        index["source_clip_count"] = len(index["clips"])
        write("analysis/search_index.json", index)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    parser.add_argument("backup", type=Path)
    args = parser.parse_args()
    sanitize_caches(args.site, args.backup)
    print("event=asr_public_caches_sanitized excluded_channel=74 raw_history_preserved=true")


if __name__ == "__main__":
    main()
