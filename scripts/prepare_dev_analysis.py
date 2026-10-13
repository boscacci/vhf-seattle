"""Build a bounded, isolated dev analysis snapshot from the existing public export."""

import argparse
import json
import os
import shutil
from pathlib import Path

from talkingboats.lexical_analysis import generate_lexical_analysis_from_public_manifest


def prepare(source: Path, target: Path):
    cached = target / "analysis/lexical.json"
    if cached.is_file():
        payload = json.loads(cached.read_text())
        if (
            payload.get("status") == "ok"
            and payload.get("source_clip_count", 0) > 0
            and "74" not in payload.get("channels", {})
        ):
            return payload
    # This isolated snapshot never replaces the shared archive/search index.
    payload = generate_lexical_analysis_from_public_manifest(
        public_manifest_path=source / "public_manifest.json",
        output_dir=target,
        limit=2500,
    )
    if payload["source_clip_count"] == 0 or "74" in payload["channels"]:
        raise ValueError("dev analysis must contain retained, intelligible transcripts")
    payload["source_scope"] = "Snapshot of up to 2,500 recent publicly exported clips"
    cached.write_text(json.dumps(payload, ensure_ascii=False))
    return payload


def promote_if_missing(snapshot: Path, site: Path):
    """Used only inside the approved production release; preserve a safe full cache."""
    from talkingboats.lexical_analysis import read_published_lexical_analysis

    if read_published_lexical_analysis(site / "analysis/lexical.json")["status"] == "ok":
        return
    if read_published_lexical_analysis(snapshot / "analysis/lexical.json")["status"] != "ok":
        raise ValueError("refusing to promote missing or excluded-channel analysis")
    for name in ["topic_clusters.html", "lexical.json"]:
        source = snapshot / "analysis" / name
        destination = site / "analysis" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".pending")
        shutil.copyfile(source, temporary)
        temporary.replace(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--promote-to", type=Path)
    args = parser.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    result = prepare(args.source, args.target)
    if args.promote_to:
        promote_if_missing(args.target, args.promote_to)
    print(
        json.dumps(
            {
                "event": "dev_analysis_prepared",
                "source_clip_count": result["source_clip_count"],
                "topics_status": result["topics"]["status"],
            }
        )
    )
