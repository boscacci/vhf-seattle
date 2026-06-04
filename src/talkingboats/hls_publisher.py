from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PLAYLIST_CONTENT_TYPE = "application/vnd.apple.mpegurl"
SEGMENT_CACHE_CONTROL = "max-age=10"


def render_hls_public_paths(channels: list[str] | tuple[str, ...]) -> dict[str, object]:
    return {
        "default": "/live/current.m3u8",
        "channels": {
            channel: f"/live/channels/{channel}/current.m3u8" for channel in channels
        },
    }


@dataclass
class HlsPublisher:
    root_dir: Path
    bucket: str
    prefix: str = "live"
    s3_client: Any | None = None
    _published: dict[str, tuple[int, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.bucket:
            raise ValueError("bucket is required")
        if self.s3_client is None:
            self.s3_client = _boto3_client("s3")

    def publish_once(self) -> int:
        current_keys: set[str] = set()
        uploaded = 0
        for path in sorted(self._iter_hls_files()):
            key = self._key_for_path(path)
            current_keys.add(key)
            stat = path.stat()
            fingerprint = (stat.st_size, stat.st_mtime_ns)
            if self._published.get(key) == fingerprint:
                continue
            assert self.s3_client is not None
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=path.read_bytes(),
                ContentType=_content_type(path),
                CacheControl=_cache_control(path),
            )
            self._published[key] = fingerprint
            uploaded += 1

        for key in sorted(set(self._published) - current_keys):
            if not _is_segment_key(key):
                continue
            assert self.s3_client is not None
            self.s3_client.delete_object(Bucket=self.bucket, Key=key)
            self._published.pop(key, None)
        return uploaded

    def publish_forever(self, *, interval_seconds: float = 1.0) -> None:
        while True:
            uploaded = self.publish_once()
            print(
                json.dumps(
                    {"event": "hls_publish_tick", "uploaded": uploaded},
                    sort_keys=True,
                ),
                flush=True,
            )
            time.sleep(interval_seconds)

    def _iter_hls_files(self) -> list[Path]:
        if not self.root_dir.exists():
            return []
        return [
            path
            for path in self.root_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".m3u8", ".ts", ".m4s", ".aac", ".json"}
        ]

    def _key_for_path(self, path: Path) -> str:
        relative = path.relative_to(self.root_dir).as_posix()
        return "/".join(part.strip("/") for part in (self.prefix, relative) if part.strip("/"))


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".m3u8":
        return PLAYLIST_CONTENT_TYPE
    if suffix == ".ts":
        return "video/mp2t"
    if suffix == ".m4s":
        return "video/iso.segment"
    if suffix == ".aac":
        return "audio/aac"
    if suffix == ".json":
        return "application/json"
    return "application/octet-stream"


def _cache_control(path: Path) -> str:
    return "no-store" if path.suffix.lower() in {".m3u8", ".json"} else SEGMENT_CACHE_CONTROL


def _is_segment_key(key: str) -> bool:
    return Path(key).suffix.lower() in {".ts", ".m4s", ".aac"}


def _boto3_client(name: str) -> Any:
    import boto3

    return boto3.client(name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish Pi-generated HLS files to S3.")
    parser.add_argument("--root-dir", type=Path, default=Path("/opt/talkingboats/hls"))
    parser.add_argument("--bucket", default=os.getenv("TALKINGBOATS_PUBLIC_SITE_BUCKET"))
    parser.add_argument("--prefix", default=os.getenv("TALKINGBOATS_HLS_S3_PREFIX", "live"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    args = parser.parse_args()
    if not args.bucket:
        parser.error("--bucket or TALKINGBOATS_PUBLIC_SITE_BUCKET is required")
    publisher = HlsPublisher(root_dir=args.root_dir, bucket=args.bucket, prefix=args.prefix)
    if args.once:
        uploaded = publisher.publish_once()
        print(json.dumps({"event": "hls_publish_once", "uploaded": uploaded}, sort_keys=True))
    else:
        publisher.publish_forever(interval_seconds=args.interval_seconds)


if __name__ == "__main__":
    main()
