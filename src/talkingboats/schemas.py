from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Channel = Literal[
    "05A",
    "06",
    "09",
    "10",
    "13",
    "14",
    "16",
    "22A",
    "66A",
    "67",
    "68",
    "69",
    "71",
    "72",
    "73",
    "74",
    "77",
    "78A",
]


class ClipPresignRequest(BaseModel):
    channel: Channel
    started_at: datetime
    ended_at: datetime | None = None
    content_type: str = Field(default="audio/mpeg", min_length=5, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=200)
    duration_seconds: float | None = Field(default=None, gt=0, le=3600)

    @field_validator("content_type")
    @classmethod
    def validate_audio_type(cls, value: str) -> str:
        allowed = {
            "audio/aac",
            "audio/flac",
            "audio/m4a",
            "audio/mpeg",
            "audio/mp4",
            "audio/ogg",
            "audio/wav",
            "audio/x-wav",
        }
        if value not in allowed:
            raise ValueError("content_type must be a supported audio MIME type")
        return value

    @model_validator(mode="after")
    def validate_times(self) -> ClipPresignRequest:
        if self.ended_at is not None and self.ended_at <= self.started_at:
            raise ValueError("ended_at must be after started_at")
        return self


class ClipPresignResponse(BaseModel):
    bucket: str
    key: str
    upload_url: str
    expires_in_seconds: int
    required_headers: dict[str, str] = Field(default_factory=dict)


class PlaybackUrlRequest(BaseModel):
    key: str = Field(min_length=1, max_length=1024)


class PlaybackUrlResponse(BaseModel):
    playback_url: str
    expires_in_seconds: int


class TranscriptCorrectionRequest(BaseModel):
    channel: str = Field(min_length=1, max_length=8)
    started_at: str = Field(min_length=1, max_length=64)
    transcript: str = Field(min_length=1, max_length=8000)
    reviewer: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class TranscriptCorrectionResponse(BaseModel):
    status: Literal["corrected"]
    channel: str
    started_at: str
    original_transcript: str
    corrected_transcript: str
    transcript_reviewed: bool


class ClipFeatureRequest(BaseModel):
    channel: str = Field(min_length=1, max_length=8)
    started_at: str = Field(min_length=1, max_length=64)
    featured: bool = True
    featured_by: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class ClipFeatureResponse(BaseModel):
    status: Literal["featured", "unfeatured"]
    channel: str
    started_at: str
    featured: bool


class LiveChannelResponse(BaseModel):
    channel: str
    label: str
    frequency_mhz: float
    enabled: bool


class LiveChannelsResponse(BaseModel):
    channels: list[LiveChannelResponse]
