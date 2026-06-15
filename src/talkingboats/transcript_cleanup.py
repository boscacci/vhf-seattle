from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from talkingboats.clip_transcriber import (
    RecentTranscribedClip,
    UploadedClipStore,
    is_displayable_transcript,
)
from talkingboats.durable_events import durable_event_store_from_env
from talkingboats.dynamo_clip_store import dynamo_clip_store_from_env


@dataclass(frozen=True)
class NoiseTranscriptCleanupSummary:
    scanned: int = 0
    candidates: int = 0
    cleaned: int = 0
    dry_run: bool = True


class NoiseCleanupStore(Protocol):
    def iter_transcribed_raw(
        self,
        *,
        page_size: int,
        excluded_channels: tuple[str, ...] = (),
    ) -> Iterable[RecentTranscribedClip]: ...

    def mark_empty(self, key: str) -> None: ...


ProgressReporter = Callable[[str, dict[str, object]], None]


def cleanup_noise_transcripts(
    store: NoiseCleanupStore,
    *,
    dry_run: bool,
    page_size: int,
    limit: int | None = None,
    excluded_channels: tuple[str, ...] = (),
    progress: ProgressReporter | None = None,
) -> NoiseTranscriptCleanupSummary:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    scanned = 0
    candidates = 0
    cleaned = 0
    for clip in store.iter_transcribed_raw(
        page_size=page_size,
        excluded_channels=excluded_channels,
    ):
        if limit is not None and scanned >= limit:
            break
        scanned += 1
        if scanned % page_size == 0 and progress is not None:
            progress("progress", {"scanned": scanned, "candidates": candidates, "cleaned": cleaned})
        if is_displayable_transcript(clip.transcript):
            continue
        candidates += 1
        if progress is not None:
            progress(
                "candidate",
                {
                    "key": clip.key,
                    "channel": clip.channel,
                    "started_at": clip.started_at,
                    "dry_run": dry_run,
                },
            )
        if not dry_run:
            store.mark_empty(clip.key)
            cleaned += 1
    summary = NoiseTranscriptCleanupSummary(
        scanned=scanned,
        candidates=candidates,
        cleaned=cleaned,
        dry_run=dry_run,
    )
    if progress is not None:
        progress("summary", asdict(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mark known nonsense VHF transcript hallucinations empty."
    )
    parser.add_argument(
        "--clip-store-backend",
        choices=("dynamodb", "sqlite"),
        default="dynamodb",
    )
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--emit-candidates", action="store_true")
    args = parser.parse_args()

    if args.clip_store_backend == "sqlite":
        if args.db_path is None:
            raise SystemExit("--db-path is required for sqlite cleanup")
        store: NoiseCleanupStore = UploadedClipStore(
            args.db_path,
            event_store=durable_event_store_from_env(),
        )
    else:
        store = dynamo_clip_store_from_env(event_store=durable_event_store_from_env())
    cleanup_noise_transcripts(
        store,
        dry_run=not args.apply,
        page_size=args.page_size,
        limit=args.limit,
        progress=_json_event_reporter(emit_candidates=args.emit_candidates),
    )


def _json_event_reporter(*, emit_candidates: bool) -> ProgressReporter:
    def report(event: str, fields: dict[str, object]) -> None:
        if event == "candidate" and not emit_candidates:
            return
        print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)

    return report


if __name__ == "__main__":
    main()
