from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import boto3

from talkingboats.channel_metadata import CHANNEL_METADATA
from talkingboats.clip_transcriber import (
    RecentTranscribedClip,
    TranscriptCorrection,
    UploadedClipRecord,
    UploadedClipSegment,
)
from talkingboats.durable_events import (
    DurableEventStore,
    NullDurableEventStore,
    stable_event_id,
    to_dynamodb_item,
)
from talkingboats.schemas import ClipPresignRequest

CLIP_STATE_SK = "state"
TRANSCRIBED_PK = "clips#transcribed"
CORRECTIONS_PK = "clip_corrections"
STATUS_PREFIX = "clip_status#"
CHANNEL_TRANSCRIBED_PREFIX = "clips#transcribed#channel#"


@dataclass(frozen=True)
class DynamoClipStoreConfig:
    table_name: str
    aws_region: str
    environment: str = "dev"


class DynamoUploadedClipStore:
    def __init__(
        self,
        config: DynamoClipStoreConfig,
        *,
        event_store: DurableEventStore | None = None,
        table: Any | None = None,
    ) -> None:
        self.config = config
        self.event_store = event_store or NullDurableEventStore()
        if table is None:
            resource = boto3.resource("dynamodb", region_name=config.aws_region)
            table = resource.Table(config.table_name)
        self.table = table

    def record_presigned_upload(self, *, key: str, request: ClipPresignRequest) -> None:
        existing = self._state_item(key)
        if existing and existing.get("status") != "pending":
            return
        item = {
            "pk": _clip_pk(key),
            "sk": CLIP_STATE_SK,
            "entity_type": "clip_state",
            "key": key,
            "channel": request.channel,
            "started_at": _format_utc(request.started_at),
            "ended_at": _format_utc(request.ended_at) if request.ended_at else None,
            "duration_seconds": request.duration_seconds,
            "content_type": request.content_type,
            "idempotency_key": request.idempotency_key,
            "status": "pending",
            "transcript": None,
            "error": None,
            "transcript_reviewed": False,
            "segments": [],
        }
        self._put_state(item, old_status=str(existing.get("status")) if existing else None)
        self.event_store.record_clip_event(
            "clip.presigned",
            key=key,
            observed_at=request.started_at,
            idempotency_key=request.idempotency_key,
            payload={
                "channel": request.channel,
                "started_at": item["started_at"],
                "ended_at": item["ended_at"],
                "duration_seconds": request.duration_seconds,
                "content_type": request.content_type,
                "idempotency_key": request.idempotency_key,
                "status": "pending",
            },
        )

    def pending_uploads(
        self,
        *,
        limit: int,
        retry_errors: bool = False,
    ) -> list[UploadedClipRecord]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        statuses = ["pending", "waiting_upload", "processing"]
        if retry_errors:
            statuses.append("error")
        records: list[UploadedClipRecord] = []
        for status in statuses:
            for item in self._query_items(_status_pk(status), scan_forward=False, limit=limit):
                state = self._state_item(str(item["key"]))
                if state:
                    records.append(_record_from_state(state))
        records.sort(key=lambda record: (record.started_at, record.key), reverse=True)
        return records[:limit]

    def get_clip(self, key: str) -> UploadedClipRecord | None:
        item = self._state_item(key)
        return _record_from_state(item) if item else None

    def mark_processing(self, key: str) -> None:
        self._set_status(key, status="processing", error=None, event_type="clip.processing")

    def mark_waiting_upload(self, key: str, error: str) -> None:
        self._set_status(
            key,
            status="waiting_upload",
            error=error,
            event_type="clip.waiting_upload",
        )

    def mark_failed(self, key: str, error: str) -> None:
        self._set_status(key, status="error", error=error, event_type="clip.failed")

    def mark_empty(self, key: str) -> None:
        item = self._state_item(key)
        if not item:
            return
        old_status = str(item.get("status"))
        item.update(
            {
                "status": "empty",
                "transcript": "",
                "display_transcript": "",
                "error": None,
                "segments": [],
                "transcript_reviewed": bool(item.get("transcript_reviewed")),
            }
        )
        self._put_state(item, old_status=old_status)
        self.event_store.record_clip_event(
            "clip.empty",
            key=key,
            observed_at=_parse_utc(str(item["started_at"])),
            idempotency_key=f"{key}:clip.empty:empty",
            payload=_event_payload(item, {"transcript": ""}),
        )

    def mark_transcribed(self, key: str, segments: Iterable[UploadedClipSegment]) -> None:
        item = self._state_item(key)
        if not item:
            return
        segment_payload = [_segment_payload(segment) for segment in segments]
        transcript = " ".join(str(segment["text"]) for segment in segment_payload)
        old_status = str(item.get("status"))
        item.update(
            {
                "status": "transcribed",
                "transcript": transcript,
                "display_transcript": item.get("corrected_transcript") or transcript,
                "error": None,
                "segments": segment_payload,
                "segment_count": len(segment_payload),
            }
        )
        self._put_state(item, old_status=old_status)
        transcribed_event_id = stable_event_id(transcript, segment_payload)
        self.event_store.record_clip_event(
            "clip.transcribed",
            key=key,
            observed_at=_parse_utc(str(item["started_at"])),
            idempotency_key=f"{key}:clip.transcribed:{transcribed_event_id}",
            payload=_event_payload(
                item,
                {
                    "transcript": transcript,
                    "segments": segment_payload,
                    "segment_count": len(segment_payload),
                },
            ),
        )

    def segments_for_clip(self, key: str) -> list[dict[str, str]]:
        item = self._state_item(key)
        if not item:
            return []
        return [
            {
                "text": str(segment.get("text") or ""),
                "started_at": str(segment.get("started_at") or ""),
                "ended_at": str(segment.get("ended_at") or ""),
            }
            for segment in _as_list(item.get("segments"))
        ]

    def recent_transcribed(
        self,
        *,
        limit: int,
        offset: int = 0,
        channel: str | None = None,
        channels: Iterable[str] | None = None,
        excluded_channels: tuple[str, ...] = (),
    ) -> list[RecentTranscribedClip]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        selected_channels = _unique_channels([channel] if channel else channels)
        if selected_channels:
            index_items: list[dict[str, Any]] = []
            for selected_channel in selected_channels:
                index_items.extend(
                    self._query_items(
                        _channel_transcribed_pk(selected_channel),
                        scan_forward=False,
                        limit=offset + limit,
                    )
                )
            index_items.sort(
                key=lambda item: (str(item["started_at"]), str(item["key"])),
                reverse=True,
            )
            index_items = index_items[offset : offset + limit]
        else:
            index_items = self._query_filtered_transcribed(
                limit=limit,
                offset=offset,
                excluded_channels={excluded.upper() for excluded in excluded_channels},
            )
        return [_recent_from_item(item) for item in index_items]

    def transcribed_clip_for_public_playback(
        self,
        *,
        channel: str,
        started_at: str,
        excluded_channels: tuple[str, ...] = (),
    ) -> RecentTranscribedClip | None:
        normalized = _format_utc(_parse_utc(started_at))
        if channel.upper() in {excluded.upper() for excluded in excluded_channels}:
            return None
        prefix = f"{normalized}#"
        rows = self._query_items(
            _channel_transcribed_pk(channel),
            sk_prefix=prefix,
            scan_forward=False,
            limit=5,
        )
        return _recent_from_item(rows[0]) if rows else None

    def correct_transcript(
        self,
        *,
        channel: str,
        started_at: str,
        corrected_transcript: str,
        reviewer: str | None = None,
        note: str | None = None,
        excluded_channels: tuple[str, ...] = (),
    ) -> TranscriptCorrection:
        corrected = " ".join(corrected_transcript.split())
        if not corrected:
            raise ValueError("corrected transcript must not be empty")
        clip = self.transcribed_clip_for_public_playback(
            channel=channel,
            started_at=started_at,
            excluded_channels=excluded_channels,
        )
        if clip is None:
            raise LookupError("clip not found")
        item = self._state_item(clip.key)
        if not item:
            raise LookupError("clip not found")
        original = str(item.get("original_transcript") or item.get("transcript") or clip.transcript)
        reviewer_text = reviewer.strip() if reviewer else item.get("reviewer")
        note_text = note.strip() if note else None
        item.update(
            {
                "original_transcript": original,
                "corrected_transcript": corrected,
                "display_transcript": corrected,
                "transcript_reviewed": True,
                "reviewer": reviewer_text,
                "note": note_text,
            }
        )
        self._put_state(item, old_status="transcribed")
        correction = TranscriptCorrection(
            key=clip.key,
            channel=str(item["channel"]),
            started_at=str(item["started_at"]),
            ended_at=_optional_str(item.get("ended_at")),
            duration_seconds=_optional_float(item.get("duration_seconds")),
            content_type=str(item["content_type"]),
            original_transcript=original,
            corrected_transcript=corrected,
            reviewer=_optional_str(reviewer_text),
            note=_optional_str(note_text),
        )
        correction_item = {
            "pk": CORRECTIONS_PK,
            "sk": f"{correction.started_at}#{correction.key}",
            "entity_type": "clip_correction",
            **asdict(correction),
        }
        self._put_item(correction_item)
        self.event_store.record_clip_event(
            "clip.transcript_corrected",
            key=correction.key,
            observed_at=_parse_utc(correction.started_at),
            idempotency_key=(
                f"{correction.key}:clip.transcript_corrected:"
                f"{stable_event_id(corrected, reviewer_text, note_text)}"
            ),
            payload={
                "channel": correction.channel,
                "started_at": correction.started_at,
                "ended_at": correction.ended_at,
                "duration_seconds": correction.duration_seconds,
                "content_type": correction.content_type,
                "original_transcript": correction.original_transcript,
                "corrected_transcript": correction.corrected_transcript,
                "reviewer": correction.reviewer,
                "note": correction.note,
            },
        )
        return correction

    def transcript_corrections_for_training(self) -> list[dict[str, object]]:
        return [
            {
                "key": item["key"],
                "channel": item["channel"],
                "started_at": item["started_at"],
                "ended_at": item.get("ended_at"),
                "duration_seconds": _optional_float(item.get("duration_seconds")),
                "content_type": item["content_type"],
                "original_transcript": item["original_transcript"],
                "corrected_transcript": item["corrected_transcript"],
                "reviewer": item.get("reviewer"),
                "note": item.get("note"),
            }
            for item in self._query_items(CORRECTIONS_PK, scan_forward=False)
        ]

    def transcribed_channel_counts(
        self,
        *,
        excluded_channels: tuple[str, ...] = (),
    ) -> dict[str, int]:
        excluded = {channel.upper() for channel in excluded_channels}
        counts: dict[str, int] = {}
        for channel in sorted(CHANNEL_METADATA, key=_channel_sort_key):
            if channel.upper() in excluded:
                continue
            count = self._query_count(_channel_transcribed_pk(channel))
            if count:
                counts[channel] = count
        return counts

    def stats(self) -> dict[str, Any]:
        states = [
            item
            for item in self._scan_items()
            if item.get("entity_type") == "clip_state"
        ]
        counts: dict[str, int] = {}
        channel_counts: dict[str, dict[str, int]] = {}
        for item in states:
            status = str(item.get("status") or "unknown")
            channel = str(item.get("channel") or "?")
            counts[status] = counts.get(status, 0) + 1
            channel_counts.setdefault(channel, {})[status] = (
                channel_counts.setdefault(channel, {}).get(status, 0) + 1
            )
        states.sort(
            key=lambda item: (
                str(item.get("started_at") or ""),
                str(item.get("key") or ""),
            ),
            reverse=True,
        )
        return {
            "counts": dict(sorted(counts.items())),
            "channel_counts": channel_counts,
            "transcript_correction_count": self._query_count(CORRECTIONS_PK),
            "recent": [
                {
                    "key": item["key"],
                    "channel": item["channel"],
                    "started_at": item["started_at"],
                    "status": item["status"],
                    "transcript": item.get("display_transcript") or item.get("transcript"),
                    "error": item.get("error"),
                }
                for item in states[:20]
            ],
        }

    def _set_status(self, key: str, *, status: str, error: str | None, event_type: str) -> None:
        item = self._state_item(key)
        if not item:
            return
        old_status = str(item.get("status"))
        item.update({"status": status, "error": error})
        self._put_state(item, old_status=old_status)
        self.event_store.record_clip_event(
            event_type,
            key=key,
            observed_at=_parse_utc(str(item["started_at"])),
            idempotency_key=f"{key}:{event_type}:{stable_event_id(status, error)}",
            payload=_event_payload(item, {"status": status, "error": error}),
        )

    def _put_state(self, item: dict[str, Any], *, old_status: str | None) -> None:
        key = str(item["key"])
        channel = str(item["channel"])
        started_at = str(item["started_at"])
        self._put_item(item)
        if old_status and old_status != item.get("status"):
            self._delete_item({"pk": _status_pk(old_status), "sk": _index_sk(started_at, key)})
        status = str(item.get("status"))
        if status in {"pending", "processing", "waiting_upload", "error"}:
            self._put_item(_index_item(_status_pk(status), item))
        if old_status == "transcribed" and status != "transcribed":
            self._delete_transcribed_indexes(channel, started_at, key)
        if status == "transcribed":
            self._put_item(_index_item(TRANSCRIBED_PK, item))
            self._put_item(_index_item(_channel_transcribed_pk(channel), item))

    def _delete_transcribed_indexes(self, channel: str, started_at: str, key: str) -> None:
        sk = _index_sk(started_at, key)
        self._delete_item({"pk": TRANSCRIBED_PK, "sk": sk})
        self._delete_item({"pk": _channel_transcribed_pk(channel), "sk": sk})

    def _state_item(self, key: str) -> dict[str, Any] | None:
        response = self.table.get_item(Key={"pk": _clip_pk(key), "sk": CLIP_STATE_SK})
        item = response.get("Item")
        return _from_dynamodb_item(item) if item else None

    def _query_items(
        self,
        pk: str,
        *,
        sk_prefix: str | None = None,
        scan_forward: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        expression = "pk = :pk"
        values: dict[str, Any] = {":pk": pk}
        if sk_prefix is not None:
            expression += " AND begins_with(sk, :sk_prefix)"
            values[":sk_prefix"] = sk_prefix
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": expression,
            "ExpressionAttributeValues": values,
            "ScanIndexForward": scan_forward,
        }
        if limit is not None:
            kwargs["Limit"] = limit
        items: list[dict[str, Any]] = []
        remaining = limit
        start_key: dict[str, Any] | None = None
        while True:
            page_kwargs = dict(kwargs)
            if start_key is not None:
                page_kwargs["ExclusiveStartKey"] = start_key
            if remaining is not None:
                page_kwargs["Limit"] = remaining
            response = self.table.query(**page_kwargs)
            items.extend(_from_dynamodb_item(item) for item in response.get("Items", []))
            if limit is not None:
                remaining = limit - len(items)
                if remaining <= 0:
                    break
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return items[:limit] if limit is not None else items

    def _query_count(self, pk: str) -> int:
        total = 0
        start_key: dict[str, Any] | None = None
        while True:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": "pk = :pk",
                "ExpressionAttributeValues": {":pk": pk},
                "Select": "COUNT",
            }
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            response = self.table.query(**kwargs)
            total += int(response.get("Count", 0))
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return total

    def _query_filtered_transcribed(
        self,
        *,
        limit: int,
        offset: int,
        excluded_channels: set[str],
    ) -> list[dict[str, Any]]:
        needed = limit + offset
        fetch_limit = max(needed + len(excluded_channels) * 20, needed)
        rows = self._query_items(TRANSCRIBED_PK, scan_forward=False, limit=fetch_limit)
        filtered = [
            row for row in rows if str(row.get("channel") or "").upper() not in excluded_channels
        ]
        return filtered[offset : offset + limit]

    def _scan_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        start_key: dict[str, Any] | None = None
        while True:
            kwargs: dict[str, Any] = {}
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            response = self.table.scan(**kwargs)
            items.extend(_from_dynamodb_item(item) for item in response.get("Items", []))
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return items

    def _put_item(self, item: dict[str, Any]) -> None:
        self.table.put_item(Item=to_dynamodb_item(item))

    def _delete_item(self, key: dict[str, str]) -> None:
        self.table.delete_item(Key=key)


def dynamo_clip_store_from_env(
    *,
    event_store: DurableEventStore | None = None,
    aws_region: str | None = None,
) -> DynamoUploadedClipStore:
    table_name = os.getenv("TALKINGBOATS_CLIP_STORE_DYNAMO_TABLE") or os.getenv(
        "TALKINGBOATS_DURABLE_EVENTS_TABLE"
    )
    if not table_name:
        raise RuntimeError(
            "TALKINGBOATS_CLIP_STORE_DYNAMO_TABLE or TALKINGBOATS_DURABLE_EVENTS_TABLE is required"
        )
    return DynamoUploadedClipStore(
        DynamoClipStoreConfig(
            table_name=table_name,
            aws_region=aws_region or os.getenv("TALKINGBOATS_AWS_REGION", "us-west-2"),
            environment=os.getenv("TALKINGBOATS_DURABLE_EVENTS_ENVIRONMENT", "dev"),
        ),
        event_store=event_store,
    )


def _clip_pk(key: str) -> str:
    return f"clip#{key}"


def _status_pk(status: str) -> str:
    return f"{STATUS_PREFIX}{status}"


def _channel_transcribed_pk(channel: str) -> str:
    return f"{CHANNEL_TRANSCRIBED_PREFIX}{channel}"


def _index_sk(started_at: str, key: str) -> str:
    return f"{started_at}#{key}"


def _index_item(pk: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "pk": pk,
        "sk": _index_sk(str(item["started_at"]), str(item["key"])),
        "entity_type": "clip_index",
        **{
            key: value
            for key, value in item.items()
            if key not in {"pk", "sk", "entity_type"}
        },
    }


def _record_from_state(item: dict[str, Any]) -> UploadedClipRecord:
    return UploadedClipRecord(
        key=str(item["key"]),
        channel=str(item["channel"]),
        started_at=str(item["started_at"]),
        ended_at=_optional_str(item.get("ended_at")),
        duration_seconds=_optional_float(item.get("duration_seconds")),
        content_type=str(item["content_type"]),
        idempotency_key=str(item["idempotency_key"]),
        status=str(item["status"]),
        transcript=_optional_str(item.get("transcript")),
        error=_optional_str(item.get("error")),
    )


def _recent_from_item(item: dict[str, Any]) -> RecentTranscribedClip:
    transcript = str(
        item.get("corrected_transcript")
        or item.get("display_transcript")
        or item.get("transcript")
        or ""
    )
    return RecentTranscribedClip(
        key=str(item["key"]),
        channel=str(item["channel"]),
        started_at=str(item["started_at"]),
        ended_at=_optional_str(item.get("ended_at")),
        duration_seconds=_optional_float(item.get("duration_seconds")),
        content_type=str(item["content_type"]),
        transcript=transcript,
        segments=[
            {
                "text": str(segment.get("text") or ""),
                "started_at": str(segment.get("started_at") or ""),
                "ended_at": str(segment.get("ended_at") or ""),
            }
            for segment in _as_list(item.get("segments"))
        ],
        transcript_reviewed=bool(item.get("transcript_reviewed")),
    )


def _segment_payload(segment: UploadedClipSegment) -> dict[str, object]:
    return {
        "text": segment.text,
        "started_at": segment.started_at,
        "ended_at": segment.ended_at,
        "relative_start_seconds": segment.relative_start_seconds,
        "relative_end_seconds": segment.relative_end_seconds,
    }


def _event_payload(item: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "channel": item.get("channel"),
        "started_at": item.get("started_at"),
        "ended_at": item.get("ended_at"),
        "duration_seconds": item.get("duration_seconds"),
        "content_type": item.get("content_type"),
        "idempotency_key": item.get("idempotency_key"),
        "status": item.get("status"),
        "error": item.get("error"),
        **extra,
    }


def _from_dynamodb_item(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {key: _from_dynamodb_item(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_dynamodb_item(item) for item in value]
    return value


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return parsed.astimezone(UTC)


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _as_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unique_channels(channels: Iterable[str] | None) -> list[str]:
    if channels is None:
        return []
    seen: set[str] = set()
    selected: list[str] = []
    for channel in channels:
        normalized = str(channel).strip()
        if normalized and normalized not in seen:
            selected.append(normalized)
            seen.add(normalized)
    return selected


def _channel_sort_key(channel: str) -> tuple[int, str]:
    numeric = "".join(character for character in channel if character.isdigit())
    return (int(numeric or 0), channel)
