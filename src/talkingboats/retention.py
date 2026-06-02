from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Any

from talkingboats.config import Settings
from talkingboats.storage import S3AudioStorage

ProgressReporter = Callable[[dict[str, int | bool]], None]


def tag_raw_audio_retention(
    *,
    storage: Any,
    clip_store: Any,
    page_size: int = 500,
    dry_run: bool = False,
    progress_every: int = 100,
    max_workers: int = 8,
    progress: ProgressReporter | None = None,
) -> dict[str, int | bool]:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if progress_every <= 0:
        raise ValueError("progress_every must be positive")
    if max_workers <= 0:
        raise ValueError("max_workers must be positive")

    featured_keys = _featured_clip_keys(clip_store=clip_store, page_size=page_size)
    raw_keys = list(storage.iter_raw_audio_keys(prefix="raw/"))
    result: dict[str, int | bool] = {
        "raw_object_count": len(raw_keys),
        "featured_key_count": len(featured_keys),
        "tagged_featured_count": 0,
        "tagged_unfeatured_count": 0,
        "dry_run": dry_run,
    }

    def apply_tag(key: str) -> bool:
        featured = key in featured_keys
        if not dry_run:
            storage.tag_raw_clip_featured(key, featured=featured)
        return featured

    if dry_run:
        for completed, key in enumerate(raw_keys, start=1):
            _count_tag_result(result, featured=apply_tag(key))
            if progress and completed % progress_every == 0:
                progress(result)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(apply_tag, key) for key in raw_keys]
            for completed, future in enumerate(as_completed(futures), start=1):
                _count_tag_result(result, featured=future.result())
                if progress and completed % progress_every == 0:
                    progress(result)

    if progress:
        progress(result)
    return result


def _count_tag_result(result: dict[str, int | bool], *, featured: bool) -> None:
    if featured:
        result["tagged_featured_count"] = int(result["tagged_featured_count"]) + 1
    else:
        result["tagged_unfeatured_count"] = int(result["tagged_unfeatured_count"]) + 1


def _featured_clip_keys(*, clip_store: Any, page_size: int) -> set[str]:
    keys: set[str] = set()
    offset = 0
    while True:
        clips = clip_store.recent_transcribed(
            limit=page_size,
            offset=offset,
            featured_only=True,
        )
        if not clips:
            return keys
        keys.update(str(clip.key) for clip in clips)
        if len(clips) < page_size:
            return keys
        offset += len(clips)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Tag existing raw S3 audio objects for the Talking Boats retention lifecycle."
    )
    parser.add_argument("--bucket", help="Raw audio bucket; defaults to TALKINGBOATS_RAW_BUCKET.")
    parser.add_argument("--aws-region", help="AWS region; defaults to TALKINGBOATS_AWS_REGION.")
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if args.aws_region:
        settings = replace(settings, aws_region=args.aws_region)
    if args.bucket:
        settings = replace(settings, raw_bucket=args.bucket)
    if not settings.raw_bucket:
        parser.error("--bucket or TALKINGBOATS_RAW_BUCKET is required")

    from talkingboats.dynamo_clip_store import dynamo_clip_store_from_env

    storage = S3AudioStorage(settings)
    clip_store = dynamo_clip_store_from_env(aws_region=settings.aws_region)

    def report(result: dict[str, int | bool]) -> None:
        print(
            "Tagged raw audio retention "
            f"{result['raw_object_count']} objects "
            f"({result['tagged_featured_count']} featured, "
            f"{result['tagged_unfeatured_count']} unfeatured)",
            file=sys.stderr,
            flush=True,
        )

    result = tag_raw_audio_retention(
        storage=storage,
        clip_store=clip_store,
        page_size=args.page_size,
        dry_run=args.dry_run,
        progress_every=args.progress_every,
        max_workers=args.max_workers,
        progress=report,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
