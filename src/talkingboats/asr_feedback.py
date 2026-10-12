"""Private reviewed labels, immutable revisions, and public transcript overlays."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field, field_validator

from talkingboats.channel_metadata import CHANNEL_METADATA
from talkingboats.durable_events import to_dynamodb_item

MAX_LABELS = 2000


class RevisionConflict(ValueError):
    pass


class Correction(BaseModel):
    channel: str
    started_at: str
    text: str = Field(min_length=1, max_length=12000)
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9-]+$")
    expected_revision: int = Field(ge=0)
    reviewed: bool = False
    training_text: str | None = Field(default=None, min_length=1, max_length=12000)
    terms: list[str] = Field(default_factory=list, max_length=50)
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, gt=0)
    effort_seconds: float = Field(default=0, ge=0, le=7200)
    reverted: bool = False

    @field_validator("started_at")
    @classmethod
    def normalize_time(cls, value):
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise ValueError("clip time must include an offset")
        return at.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def validate(self, *, duration: float) -> None:
        if self.channel not in CHANNEL_METADATA or self.channel == "74":
            raise ValueError("channel is excluded or unknown")
        at = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise ValueError("clip time must include an offset")
        self.started_at = at.astimezone(UTC).isoformat().replace("+00:00", "Z")
        self.text = self.text.strip()
        if not self.text:
            raise ValueError("correction must contain audible text")
        self.terms = list(dict.fromkeys(t.strip() for t in self.terms if t.strip()))
        if any(len(t) > 100 or t.casefold() not in self.text.casefold() for t in self.terms):
            raise ValueError("annotated terms must occur in the corrected text")
        if (self.start_seconds is None) != (self.end_seconds is None):
            raise ValueError("both audio-range boundaries are required")
        begin = self.start_seconds or 0
        end = self.end_seconds if self.end_seconds is not None else duration
        if self.start_seconds is not None and not (0 <= begin < end <= duration):
            raise ValueError("range must be within the playable audio")
        if self.reviewed and self.start_seconds is not None:
            if not self.training_text or not self.training_text.strip():
                raise ValueError("reviewed ranges need their own exact range transcript")
            if any(t.casefold() not in self.training_text.casefold() for t in self.terms):
                raise ValueError("training terms must occur in the selected range transcript")
        if self.reviewed and (duration <= 0 or end - begin > 30):
            raise ValueError(
                "reviewed labels require a complete audio/text range of at most 30 seconds"
            )


def clip_id(channel: str, started_at: str) -> str:
    return hashlib.sha256(f"{channel}:{started_at}".encode()).hexdigest()


def split_day(started_at: str) -> str:
    day = (
        datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        .astimezone(ZoneInfo("America/Los_Angeles"))
        .date()
        .isoformat()
    )
    bucket = int(hashlib.sha256(("asr-v1:" + day).encode()).hexdigest()[:8], 16) % 100
    return "train" if bucket < 70 else "validation" if bucket < 85 else "test"


def isolated_recording_day(row) -> bool:
    """Keep exchanges near recording-day boundaries out of both training and hints."""
    try:
        stamp = row.get("started_at")
        if not isinstance(stamp, str):
            return False
        recorded = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if recorded.tzinfo is None:
            return False
        begin = recorded + timedelta(seconds=float(row.get("start_seconds") or 0))
        finish = recorded + timedelta(
            seconds=float(
                row["end_seconds"]
                if row.get("end_seconds") is not None
                else row["duration_seconds"]
            )
        )
        zone = ZoneInfo("America/Los_Angeles")
        recorded, begin, finish = (at.astimezone(zone) for at in (recorded, begin, finish))

        def seconds(at):
            return at.hour * 3600 + at.minute * 60 + at.second + at.microsecond / 1e6

        return (
            finish >= begin
            and begin.date() == finish.date() == recorded.date()
            and seconds(begin) >= 1800
            and seconds(finish) < 84600
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


class Corrections:
    def get(self, channel: str, started_at: str) -> dict | None:
        raise NotImplementedError

    def list(self) -> list[dict]:
        raise NotImplementedError

    def commit(self, label: Correction, row: dict) -> dict:
        raise NotImplementedError

    def save(self, label: Correction, *, original: str, key: str, duration: float) -> dict:
        label.validate(duration=duration)
        previous = self.get(label.channel, label.started_at)
        fingerprint = hashlib.sha256(
            json.dumps(label.model_dump(), sort_keys=True).encode()
        ).hexdigest()
        request = self.request(label)
        if request:
            if request.get("fingerprint") != fingerprint:
                raise RevisionConflict("request identifier was already used for a different edit")
            return request
        if previous and previous.get("request_id") == label.request_id:
            if previous.get("fingerprint") != fingerprint:
                raise RevisionConflict("request identifier was already used for a different edit")
            return previous
        if int((previous or {}).get("revision", 0)) != label.expected_revision:
            raise RevisionConflict("transcript changed; reload the latest correction")
        if not previous and len(self.list()) >= MAX_LABELS:
            raise ValueError("reviewed-label storage limit reached")
        from talkingboats.clip_search import DEFAULT_SEARCH_EMBEDDING_MODEL, embed_query

        embedding = (
            embed_query(label.text, DEFAULT_SEARCH_EMBEDDING_MODEL)
            if isinstance(self, DynamoCorrections)
            else []
        )
        row = {
            **label.model_dump(),
            "id": clip_id(label.channel, label.started_at),
            "revision": label.expected_revision + 1,
            "original": (previous or {}).get("original", original),
            "key": key,
            "duration_seconds": duration,
            "split": split_day(label.started_at),
            "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "fingerprint": fingerprint,
            "total_effort_seconds": float(
                (previous or {}).get("total_effort_seconds")
                or (previous or {}).get("effort_seconds")
                or 0
            )
            + label.effort_seconds,
            "embedding": embedding,
            "original_embedding": (previous or {}).get("original_embedding")
            or (
                embed_query(original, DEFAULT_SEARCH_EMBEDDING_MODEL)
                if isinstance(self, DynamoCorrections)
                else []
            ),
            "archive_status": "pending" if label.reviewed else "unreviewed",
        }
        return self.commit(label, row)

    def overlay(self, clips: list[dict]) -> list[dict]:
        heads = self.heads(clips)
        for clip in clips:
            row = heads.get(clip_id(str(clip.get("channel")), str(clip.get("started_at"))))
            if row:
                clip["correction_revision"] = row["revision"]
                if not row.get("reverted"):
                    for field in ("transcript", "transcript_public"):
                        if field in clip:
                            clip[field] = row["text"]
                    clip["segments"] = []
                    clip["human_corrected"] = True
        return clips

    def request(self, label: Correction) -> dict | None:
        return None

    def heads(self, clips: list[dict]) -> dict:
        return {
            clip_id(c["channel"], c["started_at"]): row
            for c in clips
            if (row := self.get(c["channel"], c["started_at"]))
        }


class MemoryCorrections(Corrections):
    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.history: list[dict] = []

    def get(self, channel, started_at):
        return self.rows.get(clip_id(channel, started_at))

    def list(self):
        return list(self.rows.values())

    def request(self, label):
        return next((r for r in self.history if r["request_id"] == label.request_id), None)

    def commit(self, label, row):
        self.rows[row["id"]] = row
        self.history.append(dict(row))
        return row


class DynamoCorrections(Corrections):
    def __init__(self, table_name: str, region="us-west-2", table=None, namespace="asr"):
        self.namespace = namespace
        self.table = table or boto3.resource("dynamodb", region_name=region).Table(table_name)
        self.table_name = table_name

    def get(self, channel, started_at):
        response = self.table.get_item(
            Key={"pk": self.namespace + "#corrections", "sk": clip_id(channel, started_at)},
            ConsistentRead=True,
        )
        return plain(response.get("Item"))

    def list(self):
        rows, key = [], None
        while True:
            args = {
                "KeyConditionExpression": Key("pk").eq(self.namespace + "#corrections"),
                "ConsistentRead": True,
                "Limit": 100,
            }
            if key:
                args["ExclusiveStartKey"] = key
            response = self.table.query(**args)
            rows.extend(plain(response.get("Items", [])))
            if len(rows) > MAX_LABELS:
                raise RuntimeError("correction inventory exceeds storage bound")
            key = response.get("LastEvaluatedKey")
            if not key:
                return rows

    def request(self, label):
        key = hashlib.sha256(label.request_id.encode()).hexdigest()
        return plain(
            self.table.get_item(
                Key={"pk": self.namespace + "#request", "sk": key}, ConsistentRead=True
            ).get("Item")
        )

    def heads(self, clips):
        ids = list(dict.fromkeys(clip_id(c["channel"], c["started_at"]) for c in clips))
        rows = {}
        for offset in range(0, len(ids), 100):
            keys = [
                {"pk": self.namespace + "#corrections", "sk": i} for i in ids[offset : offset + 100]
            ]
            if not keys:
                continue
            request = {self.table_name: {"Keys": keys, "ConsistentRead": True}}
            for _ in range(4):
                page = self.table.meta.client.batch_get_item(RequestItems=request)
                for row in plain(page.get("Responses", {}).get(self.table_name, [])):
                    rows[row["sk"]] = row
                request = page.get("UnprocessedKeys", {})
                if not request:
                    break
            if request:
                raise RuntimeError("correction overlay could not complete bounded reads")
        return rows

    def commit(self, label, row):
        serializer = TypeSerializer()

        def item(value):
            return {k: serializer.serialize(v) for k, v in to_dynamodb_item(value).items()}

        head = {"pk": self.namespace + "#corrections", "sk": row["id"], **row}
        condition = (
            "attribute_not_exists(pk)" if label.expected_revision == 0 else "#rev = :expected"
        )
        put = {"TableName": self.table_name, "Item": item(head), "ConditionExpression": condition}
        if label.expected_revision:
            put.update(
                ExpressionAttributeNames={"#rev": "revision"},
                ExpressionAttributeValues={":expected": {"N": str(label.expected_revision)}},
            )
        try:
            # Resource transaction hooks would double-serialize low-level attribute values.
            client = boto3.client("dynamodb", region_name=self.table.meta.client.meta.region_name)
            client.transact_write_items(
                TransactItems=[
                    {"Put": put},
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": item(
                                {
                                    "pk": self.namespace + "#history#" + row["id"],
                                    "sk": f"revision#{row['revision']:08d}",
                                    **row,
                                }
                            ),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": item(
                                {
                                    "pk": self.namespace + "#request",
                                    "sk": hashlib.sha256(label.request_id.encode()).hexdigest(),
                                    **row,
                                }
                            ),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": self.table_name,
                            "Key": item({"pk": self.namespace + "#revision", "sk": "current"}),
                            "UpdateExpression": "ADD #rev :one",
                            "ExpressionAttributeNames": {"#rev": "revision"},
                            "ExpressionAttributeValues": {":one": {"N": "1"}},
                        }
                    },
                ]
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "TransactionCanceledException":
                current = self.get(label.channel, label.started_at)
                if current and current.get("fingerprint") == row["fingerprint"]:
                    return current
                raise RevisionConflict("transcript changed; reload the latest correction") from exc
            raise
        return row


def plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    if isinstance(value, list):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    return value


def feedback_store_from_env():
    import os

    if os.getenv("TALKINGBOATS_ASR_FEEDBACK_ENABLED", "false").lower() != "true":
        return None
    table = os.getenv("TALKINGBOATS_ASR_FEEDBACK_TABLE") or os.getenv(
        "TALKINGBOATS_DURABLE_EVENTS_TABLE"
    )
    return (
        DynamoCorrections(table, os.getenv("TALKINGBOATS_AWS_REGION", "us-west-2"))
        if table
        else None
    )


def reviewed_hotwords(base: str | None) -> str | None:
    from collections import Counter

    feedback = feedback_store_from_env()
    if not feedback:
        return base
    counts = Counter(
        t
        for r in feedback.list()
        if r.get("reviewed")
        and not r.get("reverted")
        and r.get("split") == "train"
        and r.get("archive_status") == "ready"
        and isolated_recording_day(r)
        for t in r.get("terms", [])
    )
    terms = list(dict.fromkeys([*(base or "").split(","), *(t for t, _ in counts.most_common(50))]))
    result = ",".join(t.strip() for t in terms if t.strip())
    return result[:1200] or None
