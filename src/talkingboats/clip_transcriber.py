from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import tempfile
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.exceptions import ClientError

from talkingboats.asr_training_metadata import (
    is_training_eligible,
    normalize_training_flags,
    normalize_training_quality,
    normalize_training_split,
    validate_training_metadata,
)
from talkingboats.audio_processing import (
    DEFAULT_SPEECH_AUDIO_FILTER,
    DEFAULT_TRANSCRIBE_BEAM_SIZE,
    DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ,
    prepared_transcription_audio,
)
from talkingboats.durable_events import (
    DurableEventStore,
    NullDurableEventStore,
    durable_event_store_from_env,
    stable_event_id,
)
from talkingboats.schemas import ClipPresignRequest

_DISPLAYED_TRANSCRIPT_SQL = (
    "COALESCE(uploaded_clip_transcript_corrections.corrected_transcript, "
    "uploaded_clips.transcript)"
)
_DISPLAYABLE_TRANSCRIPT_SQL = (
    f"talkingboats_transcript_displayable({_DISPLAYED_TRANSCRIPT_SQL}) = 1"
)
DEFAULT_TRANSCRIBE_VAD_FILTER = True
DEFAULT_TRANSCRIBE_VAD_MIN_SILENCE_DURATION_MS = 500
DEFAULT_TRANSCRIBE_VAD_SPEECH_PAD_MS = 400


class ClipNotAvailable(RuntimeError):
    """Raised when a presigned upload has not appeared in object storage yet."""


class ClipReader(Protocol):
    def download(self, key: str, output_path: Path) -> None: ...


@dataclass(frozen=True)
class UploadedClipRecord:
    key: str
    channel: str
    started_at: str
    ended_at: str | None
    duration_seconds: float | None
    content_type: str
    idempotency_key: str
    status: str
    transcript: str | None
    error: str | None


@dataclass(frozen=True)
class RecentTranscribedClip:
    key: str
    channel: str
    started_at: str
    ended_at: str | None
    duration_seconds: float | None
    content_type: str
    transcript: str
    segments: list[dict[str, str]]
    transcript_reviewed: bool = False
    featured: bool = False
    featured_at: str | None = None
    include_in_training: bool = False
    training_quality: str = "unknown"
    training_split: str = "auto"
    training_flags: tuple[str, ...] = ()
    training_reason: str | None = None


@dataclass(frozen=True)
class ClipFeature:
    key: str
    channel: str
    started_at: str
    ended_at: str | None
    duration_seconds: float | None
    content_type: str
    featured: bool
    featured_at: str | None
    featured_by: str | None
    note: str | None


@dataclass(frozen=True)
class TranscriptCorrection:
    key: str
    channel: str
    started_at: str
    ended_at: str | None
    duration_seconds: float | None
    content_type: str
    original_transcript: str
    corrected_transcript: str
    reviewer: str | None
    note: str | None
    include_in_training: bool = False
    training_quality: str = "unknown"
    training_split: str = "auto"
    training_flags: tuple[str, ...] = ()
    training_reason: str | None = None


@dataclass(frozen=True)
class UploadedClipSegment:
    text: str
    started_at: str
    ended_at: str
    relative_start_seconds: float
    relative_end_seconds: float


@dataclass
class ProcessSummary:
    processed: int = 0
    transcribed: int = 0
    empty: int = 0
    waiting_upload: int = 0
    failed: int = 0


class UploadedClipStore:
    def __init__(self, path: Path, *, event_store: DurableEventStore | None = None) -> None:
        self.path = path
        self.event_store = event_store or NullDurableEventStore()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def record_presigned_upload(self, *, key: str, request: ClipPresignRequest) -> None:
        now = _format_utc(datetime.now(UTC))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO uploaded_clips (
                    key,
                    channel,
                    started_at,
                    ended_at,
                    duration_seconds,
                    content_type,
                    idempotency_key,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    key,
                    request.channel,
                    _format_utc(request.started_at),
                    _format_utc(request.ended_at) if request.ended_at else None,
                    request.duration_seconds,
                    request.content_type,
                    request.idempotency_key,
                    now,
                    now,
                ),
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
        placeholders = ",".join("?" for _ in statuses)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    key,
                    channel,
                    started_at,
                    ended_at,
                    duration_seconds,
                    content_type,
                    idempotency_key,
                    status,
                    transcript,
                    error
                FROM uploaded_clips
                WHERE status IN ({placeholders})
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (*statuses, limit),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def get_clip(self, key: str) -> UploadedClipRecord | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                """
                SELECT
                    key,
                    channel,
                    started_at,
                    ended_at,
                    duration_seconds,
                    content_type,
                    idempotency_key,
                    status,
                    transcript,
                    error
                FROM uploaded_clips
                WHERE key = ?
                """,
                (key,),
            ).fetchone()
        return _row_to_record(row) if row else None

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
        now = _format_utc(datetime.now(UTC))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                UPDATE uploaded_clips
                SET status = 'empty',
                    transcript = '',
                    error = NULL,
                    processed_at = ?,
                    updated_at = ?
                WHERE key = ?
                """,
                (now, now, key),
            )
            connection.execute("DELETE FROM uploaded_clip_segments WHERE clip_key = ?", (key,))
        self._record_clip_event(
            "clip.empty",
            key=key,
            extra_payload={"transcript": ""},
            idempotency_seed="empty",
        )

    def mark_transcribed(self, key: str, segments: Iterable[UploadedClipSegment]) -> None:
        segment_list = list(segments)
        transcript = " ".join(segment.text for segment in segment_list)
        if not is_displayable_transcript(transcript):
            self.mark_empty(key)
            return
        now = _format_utc(datetime.now(UTC))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                UPDATE uploaded_clips
                SET status = 'transcribed',
                    transcript = ?,
                    error = NULL,
                    processed_at = ?,
                    updated_at = ?
                WHERE key = ?
                """,
                (transcript, now, now, key),
            )
            connection.execute("DELETE FROM uploaded_clip_segments WHERE clip_key = ?", (key,))
            connection.executemany(
                """
                INSERT INTO uploaded_clip_segments (
                    clip_key,
                    text,
                    started_at,
                    ended_at,
                    relative_start_seconds,
                    relative_end_seconds
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        key,
                        segment.text,
                        segment.started_at,
                        segment.ended_at,
                        segment.relative_start_seconds,
                        segment.relative_end_seconds,
                    )
                    for segment in segment_list
                ],
            )
        segment_payload = [_segment_payload(segment) for segment in segment_list]
        self._record_clip_event(
            "clip.transcribed",
            key=key,
            extra_payload={
                "transcript": transcript,
                "segments": segment_payload,
                "segment_count": len(segment_payload),
            },
            idempotency_seed=stable_event_id(transcript, segment_payload),
        )

    def segments_for_clip(self, key: str) -> list[dict[str, str]]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT text, started_at, ended_at
                FROM uploaded_clip_segments
                WHERE clip_key = ?
                ORDER BY relative_start_seconds ASC, id ASC
                """,
                (key,),
            ).fetchall()
        return [
            {"text": text, "started_at": started_at, "ended_at": ended_at}
            for text, started_at, ended_at in rows
        ]

    def recent_transcribed(
        self,
        *,
        limit: int,
        offset: int = 0,
        channel: str | None = None,
        channels: Iterable[str] | None = None,
        excluded_channels: tuple[str, ...] = (),
        featured_only: bool = False,
        reviewed_only: bool = False,
    ) -> list[RecentTranscribedClip]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        filters = [
            "uploaded_clips.status = 'transcribed'",
            "uploaded_clips.transcript IS NOT NULL",
            "trim(uploaded_clips.transcript) != ''",
            _DISPLAYABLE_TRANSCRIPT_SQL,
        ]
        params: list[object] = []
        selected_channels = _unique_channels([channel] if channel else channels)
        if selected_channels:
            placeholders = ", ".join("?" for _ in selected_channels)
            filters.append(f"channel IN ({placeholders})")
            params.extend(selected_channels)
        if excluded_channels:
            placeholders = ", ".join("?" for _ in excluded_channels)
            filters.append(f"channel NOT IN ({placeholders})")
            params.extend(excluded_channels)
        if featured_only:
            filters.append("uploaded_clip_features.clip_key IS NOT NULL")
        if reviewed_only:
            filters.append("uploaded_clip_transcript_corrections.clip_key IS NOT NULL")
        params.extend([limit, offset])
        where_clause = "\n                    AND ".join(filters)
        order_clause = (
            "uploaded_clip_features.featured_at DESC, "
            "uploaded_clips.started_at DESC, "
            "uploaded_clips.id DESC"
            if featured_only
            else "uploaded_clips.started_at DESC, uploaded_clips.id DESC"
        )
        with _connect_upload_db(self.path) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    uploaded_clips.key,
                    uploaded_clips.channel,
                    uploaded_clips.started_at,
                    uploaded_clips.ended_at,
                    uploaded_clips.duration_seconds,
                    uploaded_clips.content_type,
                    COALESCE(
                        uploaded_clip_transcript_corrections.corrected_transcript,
                        uploaded_clips.transcript
                    ) AS displayed_transcript,
                    uploaded_clip_transcript_corrections.corrected_transcript IS NOT NULL,
                    uploaded_clip_features.featured_at,
                    uploaded_clip_transcript_corrections.include_in_training,
                    uploaded_clip_transcript_corrections.training_quality,
                    uploaded_clip_transcript_corrections.training_split,
                    uploaded_clip_transcript_corrections.training_flags,
                    uploaded_clip_transcript_corrections.training_reason
                FROM uploaded_clips
                LEFT JOIN uploaded_clip_transcript_corrections
                    ON uploaded_clip_transcript_corrections.clip_key = uploaded_clips.key
                LEFT JOIN uploaded_clip_features
                    ON uploaded_clip_features.clip_key = uploaded_clips.key
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
                """,
                tuple(params),
            ).fetchall()
        clips = []
        for (
            key,
            channel,
            started_at,
            ended_at,
            duration_seconds,
            content_type,
            transcript,
            transcript_reviewed,
            featured_at,
            include_in_training,
            training_quality,
            training_split,
            training_flags,
            training_reason,
        ) in rows:
            clips.append(
                RecentTranscribedClip(
                    key=key,
                    channel=channel,
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_seconds=duration_seconds,
                    content_type=content_type,
                    transcript=transcript,
                    segments=self.segments_for_clip(key),
                    transcript_reviewed=bool(transcript_reviewed),
                    featured=featured_at is not None,
                    featured_at=featured_at,
                    include_in_training=bool(include_in_training),
                    training_quality=normalize_training_quality(training_quality),
                    training_split=normalize_training_split(training_split),
                    training_flags=tuple(_parse_training_flags(training_flags)),
                    training_reason=training_reason,
                )
            )
        return clips

    def iter_transcribed_raw(
        self,
        *,
        page_size: int,
        excluded_channels: tuple[str, ...] = (),
    ) -> Iterable[RecentTranscribedClip]:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        base_filters = [
            "uploaded_clips.status = 'transcribed'",
            "uploaded_clips.transcript IS NOT NULL",
            "trim(uploaded_clips.transcript) != ''",
        ]
        base_params: list[object] = []
        if excluded_channels:
            placeholders = ", ".join("?" for _ in excluded_channels)
            base_filters.append(f"uploaded_clips.channel NOT IN ({placeholders})")
            base_params.extend(excluded_channels)
        cursor: tuple[str, int] | None = None
        while True:
            filters = list(base_filters)
            params = list(base_params)
            if cursor is not None:
                filters.append(
                    """
                    (
                        uploaded_clips.started_at < ?
                        OR (uploaded_clips.started_at = ? AND uploaded_clips.id < ?)
                    )
                    """
                )
                params.extend([cursor[0], cursor[0], cursor[1]])
            where_clause = "\n                    AND ".join(filters)
            with sqlite3.connect(self.path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        uploaded_clips.id,
                        uploaded_clips.key,
                        uploaded_clips.channel,
                        uploaded_clips.started_at,
                        uploaded_clips.ended_at,
                        uploaded_clips.duration_seconds,
                        uploaded_clips.content_type,
                        COALESCE(
                            uploaded_clip_transcript_corrections.corrected_transcript,
                            uploaded_clips.transcript
                        ) AS displayed_transcript,
                        uploaded_clip_transcript_corrections.corrected_transcript IS NOT NULL,
                        uploaded_clip_features.featured_at,
                        uploaded_clip_transcript_corrections.include_in_training,
                        uploaded_clip_transcript_corrections.training_quality,
                        uploaded_clip_transcript_corrections.training_split,
                        uploaded_clip_transcript_corrections.training_flags,
                        uploaded_clip_transcript_corrections.training_reason
                    FROM uploaded_clips
                    LEFT JOIN uploaded_clip_transcript_corrections
                        ON uploaded_clip_transcript_corrections.clip_key = uploaded_clips.key
                    LEFT JOIN uploaded_clip_features
                        ON uploaded_clip_features.clip_key = uploaded_clips.key
                    WHERE {where_clause}
                    ORDER BY uploaded_clips.started_at DESC, uploaded_clips.id DESC
                    LIMIT ?
                    """,
                    (*params, page_size),
                ).fetchall()
            if not rows:
                break
            cursor = (str(rows[-1][3]), int(rows[-1][0]))
            for (
                _row_id,
                key,
                channel,
                started_at,
                ended_at,
                duration_seconds,
                content_type,
                transcript,
                transcript_reviewed,
                featured_at,
                include_in_training,
                training_quality,
                training_split,
                training_flags,
                training_reason,
            ) in rows:
                yield RecentTranscribedClip(
                    key=key,
                    channel=channel,
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_seconds=duration_seconds,
                    content_type=content_type,
                    transcript=transcript,
                    segments=self.segments_for_clip(key),
                    transcript_reviewed=bool(transcript_reviewed),
                    featured=featured_at is not None,
                    featured_at=featured_at,
                    include_in_training=bool(include_in_training),
                    training_quality=normalize_training_quality(training_quality),
                    training_split=normalize_training_split(training_split),
                    training_flags=tuple(_parse_training_flags(training_flags)),
                    training_reason=training_reason,
                )

    def transcribed_clip_for_public_playback(
        self,
        *,
        channel: str,
        started_at: str,
        excluded_channels: tuple[str, ...] = (),
    ) -> RecentTranscribedClip | None:
        try:
            normalized_started_at = _format_utc(_parse_utc(started_at))
        except ValueError:
            return None
        if channel.upper() in {excluded.upper() for excluded in excluded_channels}:
            return None
        filters = [
            "uploaded_clips.status = 'transcribed'",
            "uploaded_clips.transcript IS NOT NULL",
            "trim(uploaded_clips.transcript) != ''",
            _DISPLAYABLE_TRANSCRIPT_SQL,
            "channel = ?",
            "started_at = ?",
        ]
        params: list[object] = [channel, normalized_started_at]
        if excluded_channels:
            placeholders = ", ".join("?" for _ in excluded_channels)
            filters.append(f"channel NOT IN ({placeholders})")
            params.extend(excluded_channels)
        where_clause = "\n                    AND ".join(filters)
        with _connect_upload_db(self.path) as connection:
            row = connection.execute(
                f"""
                SELECT
                    uploaded_clips.key,
                    uploaded_clips.channel,
                    uploaded_clips.started_at,
                    uploaded_clips.ended_at,
                    uploaded_clips.duration_seconds,
                    uploaded_clips.content_type,
                    COALESCE(
                        uploaded_clip_transcript_corrections.corrected_transcript,
                        uploaded_clips.transcript
                    ) AS displayed_transcript,
                    uploaded_clip_transcript_corrections.corrected_transcript IS NOT NULL,
                    uploaded_clip_features.featured_at,
                    uploaded_clip_transcript_corrections.include_in_training,
                    uploaded_clip_transcript_corrections.training_quality,
                    uploaded_clip_transcript_corrections.training_split,
                    uploaded_clip_transcript_corrections.training_flags,
                    uploaded_clip_transcript_corrections.training_reason
                FROM uploaded_clips
                LEFT JOIN uploaded_clip_transcript_corrections
                    ON uploaded_clip_transcript_corrections.clip_key = uploaded_clips.key
                LEFT JOIN uploaded_clip_features
                    ON uploaded_clip_features.clip_key = uploaded_clips.key
                WHERE {where_clause}
                ORDER BY uploaded_clips.id DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        if row is None:
            return None
        (
            key,
            channel,
            started_at,
            ended_at,
            duration_seconds,
            content_type,
            transcript,
            transcript_reviewed,
            featured_at,
            include_in_training,
            training_quality,
            training_split,
            training_flags,
            training_reason,
        ) = row
        return RecentTranscribedClip(
            key=key,
            channel=channel,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            content_type=content_type,
            transcript=transcript,
            segments=self.segments_for_clip(key),
            transcript_reviewed=bool(transcript_reviewed),
            featured=featured_at is not None,
            featured_at=featured_at,
            include_in_training=bool(include_in_training),
            training_quality=normalize_training_quality(training_quality),
            training_split=normalize_training_split(training_split),
            training_flags=tuple(_parse_training_flags(training_flags)),
            training_reason=training_reason,
        )

    def set_clip_featured(
        self,
        *,
        channel: str,
        started_at: str,
        featured: bool,
        featured_by: str | None = None,
        note: str | None = None,
        excluded_channels: tuple[str, ...] = (),
    ) -> ClipFeature:
        clip = self._raw_transcribed_clip(
            channel=channel,
            started_at=started_at,
            excluded_channels=excluded_channels,
        )
        if clip is None:
            raise LookupError("clip not found")
        now = _format_utc(datetime.now(UTC))
        featured_by_text = featured_by.strip() if featured_by else None
        note_text = note.strip() if note else None
        featured_at: str | None = None
        with sqlite3.connect(self.path) as connection:
            if featured:
                existing = connection.execute(
                    """
                    SELECT featured_at
                    FROM uploaded_clip_features
                    WHERE clip_key = ?
                    """,
                    (clip.key,),
                ).fetchone()
                featured_at = existing[0] if existing else now
                connection.execute(
                    """
                    INSERT INTO uploaded_clip_features (
                        clip_key,
                        featured_at,
                        featured_by,
                        note,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(clip_key) DO UPDATE SET
                        featured_by = excluded.featured_by,
                        note = excluded.note,
                        updated_at = excluded.updated_at
                    """,
                    (clip.key, featured_at, featured_by_text, note_text, now, now),
                )
            else:
                connection.execute(
                    "DELETE FROM uploaded_clip_features WHERE clip_key = ?",
                    (clip.key,),
                )
        feature = ClipFeature(
            key=clip.key,
            channel=clip.channel,
            started_at=clip.started_at,
            ended_at=clip.ended_at,
            duration_seconds=clip.duration_seconds,
            content_type=clip.content_type,
            featured=featured,
            featured_at=featured_at,
            featured_by=featured_by_text,
            note=note_text,
        )
        event_type = "clip.featured" if featured else "clip.unfeatured"
        self.event_store.record_clip_event(
            event_type,
            key=feature.key,
            observed_at=_parse_utc(feature.started_at),
            idempotency_key=(
                f"{feature.key}:{event_type}:"
                f"{stable_event_id(feature.featured, feature.featured_by, feature.note)}"
            ),
            payload={
                "channel": feature.channel,
                "started_at": feature.started_at,
                "ended_at": feature.ended_at,
                "duration_seconds": feature.duration_seconds,
                "content_type": feature.content_type,
                "featured": feature.featured,
                "featured_at": feature.featured_at,
                "featured_by": feature.featured_by,
                "note": feature.note,
            },
        )
        return feature

    def correct_transcript(
        self,
        *,
        channel: str,
        started_at: str,
        corrected_transcript: str,
        reviewer: str | None = None,
        note: str | None = None,
        include_in_training: bool | None = None,
        training_quality: str | None = None,
        training_split: str | None = None,
        training_flags: Iterable[str] | None = None,
        training_reason: str | None = None,
        excluded_channels: tuple[str, ...] = (),
    ) -> TranscriptCorrection:
        corrected = " ".join(corrected_transcript.split())
        if not corrected:
            raise ValueError("corrected transcript must not be empty")
        clip = self._raw_transcribed_clip(
            channel=channel,
            started_at=started_at,
            excluded_channels=excluded_channels,
        )
        if clip is None:
            raise LookupError("clip not found")
        now = _format_utc(datetime.now(UTC))
        reviewer_text = reviewer.strip() if reviewer else None
        note_text = note.strip() if note else None
        with sqlite3.connect(self.path) as connection:
            existing = connection.execute(
                """
                SELECT
                    original_transcript,
                    reviewer,
                    include_in_training,
                    training_quality,
                    training_split,
                    training_flags,
                    training_reason
                FROM uploaded_clip_transcript_corrections
                WHERE clip_key = ?
                """,
                (clip.key,),
            ).fetchone()
            original_transcript = existing[0] if existing else clip.transcript
            stored_reviewer = (
                reviewer_text if reviewer_text is not None else (existing[1] if existing else None)
            )
            stored_include = (
                bool(include_in_training)
                if include_in_training is not None
                else bool(existing[2])
                if existing
                else True
            )
            if training_quality is not None:
                stored_quality_value = training_quality
            elif existing and existing[3] != "unknown":
                stored_quality_value = existing[3]
            elif stored_include:
                stored_quality_value = "good"
            else:
                stored_quality_value = existing[3] if existing else None
            stored_quality = normalize_training_quality(stored_quality_value)
            stored_split_value = (
                training_split
                if training_split is not None
                else (existing[4] if existing else None)
            )
            stored_split = normalize_training_split(stored_split_value)
            stored_flags = normalize_training_flags(
                training_flags
                if training_flags is not None
                else _parse_training_flags(existing[5] if existing else None)
            )
            stored_reason = (
                training_reason.strip()
                if training_reason is not None and training_reason.strip()
                else (existing[6] if existing and training_reason is None else None)
            )
            validate_training_metadata(
                include_in_training=stored_include,
                training_quality=stored_quality,
                training_flags=stored_flags,
            )
            connection.execute(
                """
                INSERT INTO uploaded_clip_transcript_corrections (
                    clip_key,
                    original_transcript,
                    corrected_transcript,
                    reviewer,
                    note,
                    include_in_training,
                    training_quality,
                    training_split,
                    training_flags,
                    training_reason,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(clip_key) DO UPDATE SET
                    corrected_transcript = excluded.corrected_transcript,
                    reviewer = excluded.reviewer,
                    note = excluded.note,
                    include_in_training = excluded.include_in_training,
                    training_quality = excluded.training_quality,
                    training_split = excluded.training_split,
                    training_flags = excluded.training_flags,
                    training_reason = excluded.training_reason,
                    updated_at = excluded.updated_at
                """,
                (
                    clip.key,
                    original_transcript,
                    corrected,
                    stored_reviewer,
                    note_text,
                    int(stored_include),
                    stored_quality,
                    stored_split,
                    json.dumps(stored_flags, sort_keys=True),
                    stored_reason,
                    now,
                    now,
                ),
            )
        correction = TranscriptCorrection(
            key=clip.key,
            channel=clip.channel,
            started_at=clip.started_at,
            ended_at=clip.ended_at,
            duration_seconds=clip.duration_seconds,
            content_type=clip.content_type,
            original_transcript=original_transcript,
            corrected_transcript=corrected,
            reviewer=stored_reviewer,
            note=note_text,
            include_in_training=stored_include,
            training_quality=stored_quality,
            training_split=stored_split,
            training_flags=tuple(stored_flags),
            training_reason=stored_reason,
        )
        correction_event_id = stable_event_id(
            corrected,
            stored_reviewer,
            note_text,
            stored_include,
            stored_quality,
            stored_split,
            stored_flags,
            stored_reason,
        )
        self.event_store.record_clip_event(
            "clip.transcript_corrected",
            key=correction.key,
            observed_at=_parse_utc(correction.started_at),
            idempotency_key=(
                f"{correction.key}:clip.transcript_corrected:{correction_event_id}"
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
                "include_in_training": correction.include_in_training,
                "training_quality": correction.training_quality,
                "training_split": correction.training_split,
                "training_flags": list(correction.training_flags),
                "training_reason": correction.training_reason,
            },
        )
        return correction

    def remove_transcript_correction(
        self,
        *,
        channel: str,
        started_at: str,
        excluded_channels: tuple[str, ...] = (),
    ) -> TranscriptCorrection:
        clip = self._raw_transcribed_clip(
            channel=channel,
            started_at=started_at,
            excluded_channels=excluded_channels,
        )
        if clip is None:
            raise LookupError("clip not found")
        with sqlite3.connect(self.path) as connection:
            existing = connection.execute(
                """
                SELECT
                    original_transcript,
                    corrected_transcript,
                    reviewer,
                    note,
                    include_in_training,
                    training_quality,
                    training_split,
                    training_flags,
                    training_reason
                FROM uploaded_clip_transcript_corrections
                WHERE clip_key = ?
                """,
                (clip.key,),
            ).fetchone()
            if existing is None:
                raise LookupError("transcript correction not found")
            connection.execute(
                "DELETE FROM uploaded_clip_transcript_corrections WHERE clip_key = ?",
                (clip.key,),
            )
        (
            original_transcript,
            corrected_transcript,
            reviewer,
            note,
            include_in_training,
            training_quality,
            training_split,
            training_flags,
            training_reason,
        ) = existing
        correction = TranscriptCorrection(
            key=clip.key,
            channel=clip.channel,
            started_at=clip.started_at,
            ended_at=clip.ended_at,
            duration_seconds=clip.duration_seconds,
            content_type=clip.content_type,
            original_transcript=original_transcript,
            corrected_transcript=corrected_transcript,
            reviewer=reviewer,
            note=note,
            include_in_training=bool(include_in_training),
            training_quality=normalize_training_quality(training_quality),
            training_split=normalize_training_split(training_split),
            training_flags=tuple(_parse_training_flags(training_flags)),
            training_reason=training_reason,
        )
        self.event_store.record_clip_event(
            "clip.transcript_correction_removed",
            key=correction.key,
            observed_at=_parse_utc(correction.started_at),
            idempotency_key=(
                f"{correction.key}:clip.transcript_correction_removed:"
                f"{stable_event_id(correction.corrected_transcript, correction.reviewer)}"
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
                "include_in_training": False,
            },
        )
        return correction

    def transcript_corrections(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT
                    uploaded_clips.key,
                    uploaded_clips.channel,
                    uploaded_clips.started_at,
                    uploaded_clips.ended_at,
                    uploaded_clips.duration_seconds,
                    uploaded_clips.content_type,
                    uploaded_clip_transcript_corrections.original_transcript,
                    uploaded_clip_transcript_corrections.corrected_transcript,
                    uploaded_clip_transcript_corrections.reviewer,
                    uploaded_clip_transcript_corrections.note,
                    uploaded_clip_transcript_corrections.include_in_training,
                    uploaded_clip_transcript_corrections.training_quality,
                    uploaded_clip_transcript_corrections.training_split,
                    uploaded_clip_transcript_corrections.training_flags,
                    uploaded_clip_transcript_corrections.training_reason
                FROM uploaded_clip_transcript_corrections
                JOIN uploaded_clips
                    ON uploaded_clips.key = uploaded_clip_transcript_corrections.clip_key
                ORDER BY uploaded_clip_transcript_corrections.updated_at DESC,
                    uploaded_clip_transcript_corrections.id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [_correction_from_sqlite_row(row) for row in rows]

    def transcript_correction_count(self) -> int:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT count(*) FROM uploaded_clip_transcript_corrections"
            ).fetchone()
        return int(row[0]) if row else 0

    def transcript_corrections_for_training(self) -> list[dict[str, object]]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT
                    uploaded_clips.key,
                    uploaded_clips.channel,
                    uploaded_clips.started_at,
                    uploaded_clips.ended_at,
                    uploaded_clips.duration_seconds,
                    uploaded_clips.content_type,
                    uploaded_clip_transcript_corrections.original_transcript,
                    uploaded_clip_transcript_corrections.corrected_transcript,
                    uploaded_clip_transcript_corrections.reviewer,
                    uploaded_clip_transcript_corrections.note,
                    uploaded_clip_transcript_corrections.include_in_training,
                    uploaded_clip_transcript_corrections.training_quality,
                    uploaded_clip_transcript_corrections.training_split,
                    uploaded_clip_transcript_corrections.training_flags,
                    uploaded_clip_transcript_corrections.training_reason
                FROM uploaded_clip_transcript_corrections
                JOIN uploaded_clips
                    ON uploaded_clips.key = uploaded_clip_transcript_corrections.clip_key
                WHERE uploaded_clip_transcript_corrections.include_in_training = 1
                ORDER BY uploaded_clip_transcript_corrections.updated_at DESC,
                    uploaded_clip_transcript_corrections.id DESC
                """
            ).fetchall()
        corrections = []
        for row in rows:
            correction = _correction_from_sqlite_row(row)
            flags = list(correction["training_flags"])
            quality = str(correction["training_quality"])
            if not is_training_eligible(
                include_in_training=bool(correction["include_in_training"]),
                training_quality=quality,
                training_flags=flags,
            ):
                continue
            correction["include_in_training"] = True
            corrections.append(correction)
        return corrections

    def _raw_transcribed_clip(
        self,
        *,
        channel: str,
        started_at: str,
        excluded_channels: tuple[str, ...] = (),
    ) -> RecentTranscribedClip | None:
        try:
            normalized_started_at = _format_utc(_parse_utc(started_at))
        except ValueError:
            return None
        if channel.upper() in {excluded.upper() for excluded in excluded_channels}:
            return None
        filters = [
            "status = 'transcribed'",
            "transcript IS NOT NULL",
            "trim(transcript) != ''",
            "channel = ?",
            "started_at = ?",
        ]
        params: list[object] = [channel, normalized_started_at]
        if excluded_channels:
            placeholders = ", ".join("?" for _ in excluded_channels)
            filters.append(f"channel NOT IN ({placeholders})")
            params.extend(excluded_channels)
        where_clause = "\n                    AND ".join(filters)
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                f"""
                SELECT
                    key,
                    channel,
                    started_at,
                    ended_at,
                    duration_seconds,
                    content_type,
                    transcript
                FROM uploaded_clips
                WHERE {where_clause}
                ORDER BY id DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        if row is None:
            return None
        key, channel, started_at, ended_at, duration_seconds, content_type, transcript = row
        return RecentTranscribedClip(
            key=key,
            channel=channel,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            content_type=content_type,
            transcript=transcript,
            segments=self.segments_for_clip(key),
        )

    def transcribed_channel_counts(
        self,
        *,
        excluded_channels: tuple[str, ...] = (),
        featured_only: bool = False,
        reviewed_only: bool = False,
    ) -> dict[str, int]:
        channel_filter = ""
        params: tuple[object, ...] = ()
        if excluded_channels:
            placeholders = ", ".join("?" for _ in excluded_channels)
            channel_filter = f"AND uploaded_clips.channel NOT IN ({placeholders})"
            params = tuple(excluded_channels)
        feature_join = (
            "JOIN uploaded_clip_features ON uploaded_clip_features.clip_key = uploaded_clips.key"
            if featured_only
            else ""
        )
        reviewed_filter = (
            "AND uploaded_clip_transcript_corrections.clip_key IS NOT NULL"
            if reviewed_only
            else ""
        )
        with _connect_upload_db(self.path) as connection:
            rows = connection.execute(
                f"""
                SELECT uploaded_clips.channel, count(*)
                FROM uploaded_clips
                {feature_join}
                LEFT JOIN uploaded_clip_transcript_corrections
                    ON uploaded_clip_transcript_corrections.clip_key = uploaded_clips.key
                WHERE uploaded_clips.status = 'transcribed'
                    AND uploaded_clips.transcript IS NOT NULL
                    AND trim(uploaded_clips.transcript) != ''
                    AND {_DISPLAYABLE_TRANSCRIPT_SQL}
                    {channel_filter}
                    {reviewed_filter}
                GROUP BY uploaded_clips.channel
                ORDER BY uploaded_clips.channel
                """,
                params,
            ).fetchall()
        return {channel: count for channel, count in rows}

    def transcribed_clip_count(
        self,
        *,
        channel: str | None = None,
        channels: Iterable[str] | None = None,
        excluded_channels: tuple[str, ...] = (),
        featured_only: bool = False,
        reviewed_only: bool = False,
    ) -> int:
        filters = [
            "uploaded_clips.status = 'transcribed'",
            "uploaded_clips.transcript IS NOT NULL",
            "trim(uploaded_clips.transcript) != ''",
            _DISPLAYABLE_TRANSCRIPT_SQL,
        ]
        params: list[object] = []
        selected_channels = _unique_channels([channel] if channel else channels)
        if selected_channels:
            placeholders = ", ".join("?" for _ in selected_channels)
            filters.append(f"uploaded_clips.channel IN ({placeholders})")
            params.extend(selected_channels)
        if excluded_channels:
            placeholders = ", ".join("?" for _ in excluded_channels)
            filters.append(f"uploaded_clips.channel NOT IN ({placeholders})")
            params.extend(excluded_channels)
        feature_join = (
            "JOIN uploaded_clip_features ON uploaded_clip_features.clip_key = uploaded_clips.key"
            if featured_only
            else ""
        )
        if reviewed_only:
            filters.append("uploaded_clip_transcript_corrections.clip_key IS NOT NULL")
        where_clause = "\n                    AND ".join(filters)
        with _connect_upload_db(self.path) as connection:
            row = connection.execute(
                f"""
                SELECT count(*)
                FROM uploaded_clips
                {feature_join}
                LEFT JOIN uploaded_clip_transcript_corrections
                    ON uploaded_clip_transcript_corrections.clip_key = uploaded_clips.key
                WHERE {where_clause}
                """,
                tuple(params),
            ).fetchone()
        return int(row[0]) if row else 0

    def received_clip_count(self) -> int:
        with _connect_upload_db(self.path) as connection:
            row = connection.execute("SELECT count(*) FROM uploaded_clips").fetchone()
        return int(row[0]) if row else 0

    def stats(self) -> dict[str, Any]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT status, count(*) FROM uploaded_clips GROUP BY status ORDER BY status"
            ).fetchall()
            channel_rows = connection.execute(
                """
                SELECT channel, status, count(*)
                FROM uploaded_clips
                GROUP BY channel, status
                ORDER BY channel, status
                """
            ).fetchall()
            recent = connection.execute(
                """
                SELECT key, channel, started_at, status, transcript, error
                FROM uploaded_clips
                ORDER BY updated_at DESC, id DESC
                LIMIT 20
                """
            ).fetchall()
            correction_count = connection.execute(
                "SELECT count(*) FROM uploaded_clip_transcript_corrections"
            ).fetchone()[0]
            featured_count = connection.execute(
                "SELECT count(*) FROM uploaded_clip_features"
            ).fetchone()[0]
        channel_counts: dict[str, dict[str, int]] = {}
        for channel, status, count in channel_rows:
            channel_counts.setdefault(channel, {})[status] = count
        return {
            "counts": {status: count for status, count in rows},
            "channel_counts": channel_counts,
            "transcript_correction_count": correction_count,
            "featured_clip_count": featured_count,
            "recent": [
                {
                    "key": key,
                    "channel": channel,
                    "started_at": started_at,
                    "status": status,
                    "transcript": transcript,
                    "error": error,
                }
                for key, channel, started_at, status, transcript, error in recent
            ],
        }

    def _set_status(
        self,
        key: str,
        *,
        status: str,
        error: str | None,
        event_type: str,
    ) -> None:
        now = _format_utc(datetime.now(UTC))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                UPDATE uploaded_clips
                SET status = ?,
                    error = ?,
                    updated_at = ?
                WHERE key = ?
                """,
                (status, error, now, key),
            )
        self._record_clip_event(
            event_type,
            key=key,
            extra_payload={"status": status, "error": error},
            idempotency_seed=stable_event_id(status, error),
        )

    def _record_clip_event(
        self,
        event_type: str,
        *,
        key: str,
        extra_payload: dict[str, Any],
        idempotency_seed: str,
    ) -> None:
        record = self.get_clip(key)
        if record is None:
            return
        self.event_store.record_clip_event(
            event_type,
            key=key,
            observed_at=_parse_utc(record.started_at),
            idempotency_key=f"{key}:{event_type}:{idempotency_seed}",
            payload={
                "channel": record.channel,
                "started_at": record.started_at,
                "ended_at": record.ended_at,
                "duration_seconds": record.duration_seconds,
                "content_type": record.content_type,
                "idempotency_key": record.idempotency_key,
                "status": record.status,
                "error": record.error,
                **extra_payload,
            },
        )

    def _init_schema(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS uploaded_clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    channel TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_seconds REAL,
                    content_type TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    transcript TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    processed_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploaded_clips_status_created
                ON uploaded_clips(status, created_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploaded_clips_status_channel_started
                ON uploaded_clips(status, channel, started_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploaded_clips_status_started
                ON uploaded_clips(status, started_at DESC, id DESC)
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_uploaded_clips_idempotency_key
                ON uploaded_clips(idempotency_key)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS uploaded_clip_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clip_key TEXT NOT NULL,
                    text TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    relative_start_seconds REAL NOT NULL,
                    relative_end_seconds REAL NOT NULL,
                    FOREIGN KEY(clip_key) REFERENCES uploaded_clips(key)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploaded_clip_segments_clip_key
                ON uploaded_clip_segments(clip_key)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS uploaded_clip_transcript_corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clip_key TEXT NOT NULL UNIQUE,
                    original_transcript TEXT NOT NULL,
                    corrected_transcript TEXT NOT NULL,
                    reviewer TEXT,
                    note TEXT,
                    include_in_training INTEGER NOT NULL DEFAULT 0,
                    training_quality TEXT NOT NULL DEFAULT 'unknown',
                    training_split TEXT NOT NULL DEFAULT 'auto',
                    training_flags TEXT NOT NULL DEFAULT '[]',
                    training_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(clip_key) REFERENCES uploaded_clips(key)
                )
                """
            )
            _ensure_column(
                connection,
                "uploaded_clip_transcript_corrections",
                "include_in_training",
                "INTEGER NOT NULL DEFAULT 0",
            )
            _ensure_column(
                connection,
                "uploaded_clip_transcript_corrections",
                "training_quality",
                "TEXT NOT NULL DEFAULT 'unknown'",
            )
            _ensure_column(
                connection,
                "uploaded_clip_transcript_corrections",
                "training_split",
                "TEXT NOT NULL DEFAULT 'auto'",
            )
            _ensure_column(
                connection,
                "uploaded_clip_transcript_corrections",
                "training_flags",
                "TEXT NOT NULL DEFAULT '[]'",
            )
            _ensure_column(
                connection,
                "uploaded_clip_transcript_corrections",
                "training_reason",
                "TEXT",
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploaded_clip_transcript_corrections_updated
                ON uploaded_clip_transcript_corrections(updated_at DESC, id DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS uploaded_clip_features (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clip_key TEXT NOT NULL UNIQUE,
                    featured_at TEXT NOT NULL,
                    featured_by TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(clip_key) REFERENCES uploaded_clips(key)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploaded_clip_features_featured_at
                ON uploaded_clip_features(featured_at DESC, id DESC)
                """
            )


class S3ClipReader:
    def __init__(self, *, bucket: str, aws_region: str, client: Any | None = None) -> None:
        if not bucket:
            raise ValueError("bucket is required")
        self.bucket = bucket
        self.client = client or boto3.client("s3", region_name=aws_region)

    def download(self, key: str, output_path: Path) -> None:
        try:
            self.client.download_file(self.bucket, key, str(output_path))
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise ClipNotAvailable(f"{key} is not available in S3 yet") from exc
            raise


def process_pending_uploads_once(
    *,
    store: UploadedClipStore,
    clip_reader: ClipReader,
    model: Any,
    limit: int,
    retry_errors: bool = False,
    vad_filter: bool = DEFAULT_TRANSCRIBE_VAD_FILTER,
    vad_parameters: dict[str, int] | None = None,
    min_segment_avg_logprob: float | None = -0.6,
    audio_filter: str | None = DEFAULT_SPEECH_AUDIO_FILTER,
    sample_rate_hz: int = DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ,
    beam_size: int = DEFAULT_TRANSCRIBE_BEAM_SIZE,
    hotwords: str | None = None,
    ffmpeg_path: str | None = None,
    ffmpeg_runner: Any | None = None,
    trust_edge_preprocessed_audio: bool = False,
) -> ProcessSummary:
    if beam_size <= 0:
        raise ValueError("beam_size must be positive")
    summary = ProcessSummary()
    for record in store.pending_uploads(limit=limit, retry_errors=retry_errors):
        summary.processed += 1
        store.mark_processing(record.key)
        suffix = _suffix_for_content_type(record.content_type)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            audio_path = Path(handle.name)
        try:
            clip_reader.download(record.key, audio_path)
            prepare_kwargs: dict[str, Any] = {
                "sample_rate_hz": sample_rate_hz,
                "audio_filter": _audio_filter_for_record(
                    record,
                    audio_filter=audio_filter,
                    trust_edge_preprocessed_audio=trust_edge_preprocessed_audio,
                ),
                "ffmpeg_path": ffmpeg_path,
            }
            if ffmpeg_runner is not None:
                prepare_kwargs["runner"] = ffmpeg_runner
            with prepared_transcription_audio(audio_path, **prepare_kwargs) as prepared_audio_path:
                segments = transcribe_audio_file(
                    model=model,
                    audio_path=prepared_audio_path,
                    record=record,
                    vad_filter=vad_filter,
                    vad_parameters=vad_parameters or _default_vad_parameters(),
                    min_segment_avg_logprob=min_segment_avg_logprob,
                    beam_size=beam_size,
                    hotwords=hotwords,
                )
            if segments:
                store.mark_transcribed(record.key, segments)
                summary.transcribed += 1
            else:
                store.mark_empty(record.key)
                summary.empty += 1
        except ClipNotAvailable as exc:
            store.mark_waiting_upload(record.key, str(exc))
            summary.waiting_upload += 1
        except Exception as exc:  # noqa: BLE001 - keep background worker retryable.
            store.mark_failed(record.key, f"{type(exc).__name__}: {exc}")
            summary.failed += 1
        finally:
            audio_path.unlink(missing_ok=True)
    return summary


def transcribe_audio_file(
    *,
    model: Any,
    audio_path: Path,
    record: UploadedClipRecord,
    vad_filter: bool = DEFAULT_TRANSCRIBE_VAD_FILTER,
    vad_parameters: dict[str, int] | None = None,
    min_segment_avg_logprob: float | None = -0.6,
    beam_size: int = DEFAULT_TRANSCRIBE_BEAM_SIZE,
    hotwords: str | None = None,
) -> list[UploadedClipSegment]:
    if beam_size <= 0:
        raise ValueError("beam_size must be positive")
    kwargs: dict[str, Any] = {
        "language": "en",
        "beam_size": beam_size,
        "vad_filter": vad_filter,
        "condition_on_previous_text": False,
    }
    if hotwords:
        kwargs["hotwords"] = hotwords
    if vad_filter and vad_parameters:
        kwargs["vad_parameters"] = vad_parameters
    segments, _ = model.transcribe(str(audio_path), **kwargs)
    clip_started = _parse_utc(record.started_at)
    rendered: list[UploadedClipSegment] = []
    for segment in segments:
        text = " ".join(str(getattr(segment, "text", "")).split())
        if not text:
            continue
        if not _transcript_has_alnum(text):
            continue
        avg_logprob = getattr(segment, "avg_logprob", None)
        if (
            min_segment_avg_logprob is not None
            and avg_logprob is not None
            and float(avg_logprob) < min_segment_avg_logprob
        ):
            continue
        relative_start = float(getattr(segment, "start", 0.0))
        relative_end = float(getattr(segment, "end", relative_start))
        rendered.append(
            UploadedClipSegment(
                text=text,
                started_at=_format_utc(clip_started + timedelta(seconds=relative_start)),
                ended_at=_format_utc(clip_started + timedelta(seconds=relative_end)),
                relative_start_seconds=relative_start,
                relative_end_seconds=relative_end,
            )
        )
    if rendered and not is_displayable_transcript(" ".join(segment.text for segment in rendered)):
        return []
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Transcribe completed Talking Boats clip uploads into the configured clip store."
        )
    )
    parser.add_argument("--db-path", type=Path, default=_default_db_path())
    parser.add_argument("--bucket", default=os.getenv("TALKINGBOATS_RAW_BUCKET", ""))
    parser.add_argument("--aws-region", default=os.getenv("TALKINGBOATS_AWS_REGION", "us-west-2"))
    parser.add_argument("--model-size", default=os.getenv("TALKINGBOATS_TRANSCRIBE_MODEL", "turbo"))
    parser.add_argument("--device", default=os.getenv("TALKINGBOATS_TRANSCRIBE_DEVICE", "cpu"))
    parser.add_argument(
        "--compute-type",
        default=os.getenv("TALKINGBOATS_TRANSCRIBE_COMPUTE_TYPE", "int8"),
    )
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument(
        "--vad-filter",
        action="store_true",
        default=_env_bool("TALKINGBOATS_TRANSCRIBE_VAD_FILTER", DEFAULT_TRANSCRIBE_VAD_FILTER),
        help="Enable faster-whisper VAD. On by default to suppress RF-gated static tails.",
    )
    parser.add_argument(
        "--vad-min-silence-duration-ms",
        type=int,
        default=_env_int(
            "TALKINGBOATS_TRANSCRIBE_VAD_MIN_SILENCE_DURATION_MS",
            DEFAULT_TRANSCRIBE_VAD_MIN_SILENCE_DURATION_MS,
        ),
    )
    parser.add_argument(
        "--vad-speech-pad-ms",
        type=int,
        default=_env_int(
            "TALKINGBOATS_TRANSCRIBE_VAD_SPEECH_PAD_MS",
            DEFAULT_TRANSCRIBE_VAD_SPEECH_PAD_MS,
        ),
    )
    parser.add_argument(
        "--min-segment-avg-logprob",
        type=float,
        default=_env_float("TALKINGBOATS_TRANSCRIBE_MIN_SEGMENT_AVG_LOGPROB", -0.6),
        help=(
            "Drop individual Whisper segments below this average log probability. "
            "Set very low, such as -10, to keep all segments."
        ),
    )
    parser.add_argument("--audio-filter", default=os.getenv("TALKINGBOATS_TRANSCRIBE_AUDIO_FILTER"))
    parser.add_argument("--no-audio-filter", action="store_true")
    parser.add_argument(
        "--trust-edge-preprocessed-audio",
        action="store_true",
        default=_env_bool("TALKINGBOATS_TRANSCRIBE_TRUST_EDGE_PREPROCESSED_AUDIO", False),
        help=(
            "Skip Ubuntu micro-computer ffmpeg cleanup for edge-encoded MP3 uploads. "
            "Use when the Pi already applied the upload speech filter."
        ),
    )
    parser.add_argument(
        "--sample-rate-hz",
        type=int,
        default=_env_int(
            "TALKINGBOATS_TRANSCRIBE_SAMPLE_RATE_HZ",
            DEFAULT_TRANSCRIBE_SAMPLE_RATE_HZ,
        ),
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=_env_int("TALKINGBOATS_TRANSCRIBE_BEAM_SIZE", DEFAULT_TRANSCRIBE_BEAM_SIZE),
    )
    parser.add_argument("--hotwords", default=os.getenv("TALKINGBOATS_TRANSCRIBE_HOTWORDS"))
    args = parser.parse_args()

    clip_store_backend = os.getenv("TALKINGBOATS_CLIP_STORE_BACKEND", "dynamodb")
    if args.db_path is None and clip_store_backend != "dynamodb":
        parser.error("--db-path or TALKINGBOATS_CLIP_DB_PATH is required")
    if not args.bucket:
        parser.error("--bucket or TALKINGBOATS_RAW_BUCKET is required")
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    if args.sample_rate_hz <= 0:
        parser.error("--sample-rate-hz must be positive")
    if args.beam_size <= 0:
        parser.error("--beam-size must be positive")
    if args.vad_min_silence_duration_ms < 0:
        parser.error("--vad-min-silence-duration-ms must be non-negative")
    if args.vad_speech_pad_ms < 0:
        parser.error("--vad-speech-pad-ms must be non-negative")

    event_store = durable_event_store_from_env(aws_region=args.aws_region)
    if clip_store_backend == "dynamodb":
        from talkingboats.dynamo_clip_store import dynamo_clip_store_from_env

        store = dynamo_clip_store_from_env(
            event_store=event_store,
            aws_region=args.aws_region,
        )
    else:
        store = UploadedClipStore(args.db_path, event_store=event_store)
    reader = S3ClipReader(bucket=args.bucket, aws_region=args.aws_region)
    model = _load_faster_whisper_model(
        model_size=args.model_size,
        device=args.device,
        compute_type=args.compute_type,
    )

    _log_event(
        "uploaded_clip_transcriber_start",
        **_transcriber_start_log_fields(
            bucket=args.bucket,
            db_path=args.db_path,
            clip_store_backend=clip_store_backend,
        ),
    )
    audio_filter = (
        None if args.no_audio_filter else (args.audio_filter or DEFAULT_SPEECH_AUDIO_FILTER)
    )
    while True:
        summary = process_pending_uploads_once(
            store=store,
            clip_reader=reader,
            model=model,
            limit=args.limit,
            retry_errors=args.retry_errors,
            vad_filter=args.vad_filter,
            vad_parameters={
                "min_silence_duration_ms": args.vad_min_silence_duration_ms,
                "speech_pad_ms": args.vad_speech_pad_ms,
            },
            min_segment_avg_logprob=args.min_segment_avg_logprob,
            audio_filter=audio_filter,
            sample_rate_hz=args.sample_rate_hz,
            beam_size=args.beam_size,
            hotwords=args.hotwords,
            trust_edge_preprocessed_audio=args.trust_edge_preprocessed_audio,
        )
        _log_event("uploaded_clip_transcriber_poll", **asdict(summary))
        if args.once:
            break
        time.sleep(args.poll_seconds)


def _row_to_record(row: tuple[Any, ...]) -> UploadedClipRecord:
    return UploadedClipRecord(
        key=row[0],
        channel=row[1],
        started_at=row[2],
        ended_at=row[3],
        duration_seconds=row[4],
        content_type=row[5],
        idempotency_key=row[6],
        status=row[7],
        transcript=row[8],
        error=row[9],
    )


def _default_db_path() -> Path | None:
    value = os.getenv("TALKINGBOATS_CLIP_DB_PATH")
    return Path(value) if value else None


def _transcriber_start_log_fields(
    *,
    bucket: str,
    db_path: Path | None,
    clip_store_backend: str,
) -> dict[str, str]:
    fields = {"bucket": bucket, "clip_store_backend": clip_store_backend}
    if clip_store_backend != "dynamodb":
        fields["db_path"] = str(db_path)
    return fields


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    declaration: str,
) -> None:
    columns = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}")


def _parse_training_flags(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return normalize_training_flags([value])
        if isinstance(parsed, list):
            return normalize_training_flags([str(item) for item in parsed])
        return []
    if isinstance(value, (list, tuple, set)):
        return normalize_training_flags([str(item) for item in value])
    return []


def _correction_from_sqlite_row(row: tuple[Any, ...]) -> dict[str, object]:
    (
        key,
        channel,
        started_at,
        ended_at,
        duration_seconds,
        content_type,
        original_transcript,
        corrected_transcript,
        reviewer,
        note,
        include_in_training,
        training_quality,
        training_split,
        training_flags,
        training_reason,
    ) = row
    return {
        "key": key,
        "channel": channel,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": duration_seconds,
        "content_type": content_type,
        "original_transcript": original_transcript,
        "corrected_transcript": corrected_transcript,
        "reviewer": reviewer,
        "note": note,
        "include_in_training": bool(include_in_training),
        "training_quality": normalize_training_quality(training_quality),
        "training_split": normalize_training_split(training_split),
        "training_flags": _parse_training_flags(training_flags),
        "training_reason": training_reason,
    }


def _default_vad_parameters() -> dict[str, int]:
    return {
        "min_silence_duration_ms": DEFAULT_TRANSCRIBE_VAD_MIN_SILENCE_DURATION_MS,
        "speech_pad_ms": DEFAULT_TRANSCRIBE_VAD_SPEECH_PAD_MS,
    }


def _audio_filter_for_record(
    record: UploadedClipRecord,
    *,
    audio_filter: str | None,
    trust_edge_preprocessed_audio: bool,
) -> str | None:
    if trust_edge_preprocessed_audio and record.content_type == "audio/mpeg":
        return None
    return audio_filter


def _segment_payload(segment: UploadedClipSegment) -> dict[str, object]:
    return {
        "text": segment.text,
        "started_at": segment.started_at,
        "ended_at": segment.ended_at,
        "relative_start_seconds": segment.relative_start_seconds,
        "relative_end_seconds": segment.relative_end_seconds,
    }


def _load_faster_whisper_model(*, model_size: str, device: str, compute_type: str) -> Any:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Install with: "
            'conda run -n dell python -m pip install -e ".[transcribe]"'
        ) from exc
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def _unique_channels(channels: Iterable[str] | None) -> list[str]:
    if channels is None:
        return []
    selected: list[str] = []
    seen: set[str] = set()
    for channel in channels:
        normalized = channel.strip()
        if normalized and normalized not in seen:
            selected.append(normalized)
            seen.add(normalized)
    return selected


def is_displayable_transcript(text: object) -> bool:
    rendered = " ".join(str(text or "").split())
    return _transcript_has_alnum(rendered) and not _is_likely_static_hallucination(rendered)


def _transcript_has_alnum(text: str) -> bool:
    return re.search(r"[a-z0-9]", text, flags=re.IGNORECASE) is not None


def _sqlite_transcript_displayable(text: object) -> int:
    return 1 if is_displayable_transcript(text) else 0


def _connect_upload_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.create_function(
        "talkingboats_transcript_displayable",
        1,
        _sqlite_transcript_displayable,
    )
    return connection


def _is_likely_static_hallucination(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    if normalized in {
        "i love you",
        "lets go",
        "subs by www zeoranger co uk",
        "thank you",
        "thanks for watching",
        "we ll be right back",
        "well be right back",
    }:
        return True
    return (
        normalized.startswith("subtitles by ")
        or normalized.startswith("subs by ")
        or _is_repeated_short_token_hallucination(normalized)
    )


def _is_repeated_short_token_hallucination(normalized_text: str) -> bool:
    tokens = re.findall(r"[a-z0-9]+", normalized_text)
    if len(tokens) < 6:
        return False
    if any(len(token) > 3 for token in tokens):
        return False
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    most_common_count = max(counts.values())
    return most_common_count / len(tokens) >= 0.75


def _suffix_for_content_type(content_type: str) -> str:
    return {
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/aac": ".aac",
        "audio/flac": ".flac",
        "audio/m4a": ".m4a",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
    }.get(content_type, ".audio")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _log_event(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
