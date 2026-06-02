from __future__ import annotations

import hashlib
import re
from datetime import UTC
from typing import Any

import boto3
from botocore.exceptions import ClientError

from talkingboats.config import Settings
from talkingboats.schemas import ClipPresignRequest

SAFE_KEY_RE = re.compile(r"^(raw|hall-of-fame)/[A-Za-z0-9][A-Za-z0-9._=/+-]*$")

EXTENSIONS_BY_CONTENT_TYPE = {
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/m4a": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}
RAW_CLIP_FEATURED_TAG_KEY = "talkingboats-featured"


class S3AudioStorage:
    def __init__(self, settings: Settings, client=None) -> None:
        self.settings = settings
        self.client = client or boto3.client("s3", region_name=settings.aws_region)

    def presign_raw_upload(self, request: ClipPresignRequest) -> tuple[str, str]:
        if not self.settings.raw_bucket:
            raise RuntimeError("TALKINGBOATS_RAW_BUCKET is not configured")
        key = raw_clip_key(request)
        url = self.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.settings.raw_bucket,
                "Key": key,
                "ContentType": request.content_type,
                "Tagging": f"{RAW_CLIP_FEATURED_TAG_KEY}=false",
            },
            ExpiresIn=self.settings.raw_presign_seconds,
        )
        return key, url

    def tag_raw_clip_featured(self, key: str, *, featured: bool) -> None:
        if not is_allowed_audio_key(key):
            raise ValueError("playback key must be in raw/ or hall-of-fame/")
        if not self.settings.raw_bucket:
            raise RuntimeError("TALKINGBOATS_RAW_BUCKET is not configured")
        self.client.put_object_tagging(
            Bucket=self.settings.raw_bucket,
            Key=key,
            Tagging={
                "TagSet": [
                    {
                        "Key": RAW_CLIP_FEATURED_TAG_KEY,
                        "Value": "true" if featured else "false",
                    }
                ]
            },
        )

    def iter_raw_audio_keys(self, *, prefix: str = "raw/"):
        if not prefix.startswith("raw/"):
            raise ValueError("raw audio listing prefix must stay under raw/")
        if not self.settings.raw_bucket:
            raise RuntimeError("TALKINGBOATS_RAW_BUCKET is not configured")
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.settings.raw_bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item.get("Key")
                if isinstance(key, str) and is_allowed_audio_key(key):
                    yield key

    def presign_playback(self, key: str) -> str:
        if not is_allowed_audio_key(key):
            raise ValueError("playback key must be in raw/ or hall-of-fame/")
        if not self.settings.raw_bucket:
            raise RuntimeError("TALKINGBOATS_RAW_BUCKET is not configured")
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.settings.raw_bucket, "Key": key},
            ExpiresIn=self.settings.playback_presign_seconds,
        )

    def playback_exists(self, key: str) -> bool:
        if not is_allowed_audio_key(key):
            raise ValueError("playback key must be in raw/ or hall-of-fame/")
        if not self.settings.raw_bucket:
            raise RuntimeError("TALKINGBOATS_RAW_BUCKET is not configured")
        try:
            self.client.head_object(Bucket=self.settings.raw_bucket, Key=key)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "")
            status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status_code == 404 or code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise RuntimeError(f"playback object check failed: {code or status_code}") from exc
        return True

    def open_playback(self, key: str) -> Any:
        if not is_allowed_audio_key(key):
            raise ValueError("playback key must be in raw/ or hall-of-fame/")
        if not self.settings.raw_bucket:
            raise RuntimeError("TALKINGBOATS_RAW_BUCKET is not configured")
        try:
            response = self.client.get_object(Bucket=self.settings.raw_bucket, Key=key)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "")
            status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status_code == 404 or code in {"404", "NoSuchKey", "NotFound"}:
                raise FileNotFoundError(key) from exc
            raise RuntimeError(f"playback object read failed: {code or status_code}") from exc
        return response["Body"]


def raw_clip_key(request: ClipPresignRequest) -> str:
    started = request.started_at.astimezone(UTC)
    day = started.strftime("%Y-%m-%d")
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(request.idempotency_key.encode("utf-8")).hexdigest()[:20]
    extension = EXTENSIONS_BY_CONTENT_TYPE.get(request.content_type, ".bin")
    return f"raw/channel={request.channel}/date={day}/{stamp}-{digest}{extension}"


def is_allowed_audio_key(key: str) -> bool:
    if ".." in key or key.startswith("/") or "//" in key:
        return False
    return bool(SAFE_KEY_RE.match(key))
