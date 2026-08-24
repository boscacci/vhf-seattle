import asyncio
import base64
import inspect
import json
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from talkingboats.api import (
    app,
    get_clip_store,
    get_durable_event_store,
    get_settings,
    get_storage,
    recent_clips,
)
from talkingboats.clip_transcriber import ClipQualityMetadata, UploadedClipStore
from talkingboats.config import LiveChannel, Settings
from talkingboats.durable_events import NullDurableEventStore
from talkingboats.lexical_analysis import write_cached_lexical_analysis


class FakeStorage:
    def __init__(
        self,
        *,
        missing_playback_keys: set[str] | None = None,
        playback_content: bytes = b"mp3-data",
        tag_error: RuntimeError | None = None,
    ) -> None:
        self.missing_playback_keys = missing_playback_keys or set()
        self.playback_content = playback_content
        self.tag_error = tag_error
        self.opened_playback_keys: list[str] = []
        self.presigned_playback_keys: list[str] = []
        self.featured_tags: list[tuple[str, bool]] = []

    def presign_raw_upload(self, request):
        return (
            f"raw/channel={request.channel}/date=2026-05-20/fake.mp3",
            "https://s3.example.test/upload",
        )

    def presign_playback(self, key):
        if not key.startswith(("raw/", "hall-of-fame/")):
            raise ValueError("playback key must be in raw/ or hall-of-fame/")
        self.presigned_playback_keys.append(key)
        return "https://s3.example.test/playback"

    def playback_exists(self, key):
        if not key.startswith(("raw/", "hall-of-fame/")):
            raise ValueError("playback key must be in raw/ or hall-of-fame/")
        return key not in self.missing_playback_keys

    def open_playback(self, key):
        if not key.startswith(("raw/", "hall-of-fame/")):
            raise ValueError("playback key must be in raw/ or hall-of-fame/")
        if key in self.missing_playback_keys:
            raise FileNotFoundError(key)
        self.opened_playback_keys.append(key)
        return FakePlaybackBody(self.playback_content)

    def tag_raw_clip_featured(self, key: str, *, featured: bool) -> None:
        if self.tag_error:
            raise self.tag_error
        self.featured_tags.append((key, featured))


def test_recent_clips_runs_blocking_storage_work_in_fastapi_threadpool() -> None:
    assert inspect.iscoroutinefunction(recent_clips) is False


class FakePlaybackBody:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False

    def iter_chunks(self, chunk_size: int):
        assert chunk_size > 0
        yield self.content

    def close(self) -> None:
        self.closed = True


class NoPlaybackHeadStorage(FakeStorage):
    def playback_exists(self, key):
        raise AssertionError(f"playback_exists should not be called for {key}")


class CapturingEventStore:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def record_clip_event(
        self,
        event_type: str,
        *,
        key: str,
        payload,
        idempotency_key: str,
        observed_at=None,
    ) -> None:
        self.events.append(
            {
                "event_type": event_type,
                "key": key,
                "observed_at": observed_at,
                "idempotency_key": idempotency_key,
                "payload": payload,
            }
        )


def test_ingest_presign_requires_ingest_token() -> None:
    client = _client()

    response = client.post("/api/ingest/clips/presign", json=_clip_request())

    assert response.status_code == 401


def test_ingest_presign_returns_short_lived_upload_url() -> None:
    client = _client()

    response = client.post(
        "/api/ingest/clips/presign",
        headers={"X-TalkingBoats-Ingest-Token": "ingest-token"},
        json=_clip_request(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["bucket"] == "raw-bucket"
    assert body["key"].startswith("raw/channel=68/")
    assert body["upload_url"] == "https://s3.example.test/upload"
    assert body["expires_in_seconds"] == 900
    assert body["required_headers"] == {
        "Content-Type": "audio/mpeg",
        "x-amz-tagging": "talkingboats-featured=false",
    }


def test_ingest_presign_records_upload_for_background_transcription(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)

    response = client.post(
        "/api/ingest/clips/presign",
        headers={"X-TalkingBoats-Ingest-Token": "ingest-token"},
        json=_clip_request(),
    )

    assert response.status_code == 200
    store = UploadedClipStore(db_path)
    pending = store.pending_uploads(limit=10)
    assert len(pending) == 1
    assert pending[0].key == "raw/channel=68/date=2026-05-20/fake.mp3"
    assert pending[0].channel == "68"
    assert pending[0].status == "pending"


def test_ingest_presign_records_durable_event_without_sqlite() -> None:
    event_store = CapturingEventStore()
    client = _client(clip_db_path=None, event_store=event_store)

    response = client.post(
        "/api/ingest/clips/presign",
        headers={"X-TalkingBoats-Ingest-Token": "ingest-token"},
        json=_clip_request(),
    )

    assert response.status_code == 200
    assert event_store.events == [
        {
            "event_type": "clip.presigned",
            "key": "raw/channel=68/date=2026-05-20/fake.mp3",
            "observed_at": datetime(2026, 5, 20, 19, 12, tzinfo=UTC),
            "idempotency_key": "unique-radio-event",
            "payload": {
                "bucket": "raw-bucket",
                "channel": "68",
                "started_at": "2026-05-20T19:12:00Z",
                "ended_at": None,
                "duration_seconds": 12.5,
                "content_type": "audio/mpeg",
                "audio_profile": None,
                "idempotency_key": "unique-radio-event",
            },
        }
    ]


def test_operator_can_read_ingest_clip_stats_when_db_configured(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    client.post(
        "/api/ingest/clips/presign",
        headers={"X-TalkingBoats-Ingest-Token": "ingest-token"},
        json=_clip_request(),
    )

    response = client.get("/api/ingest/clips/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is True
    assert body["counts"] == {"pending": 1}
    assert body["recent"][0]["key"] == "raw/channel=68/date=2026-05-20/fake.mp3"


def test_recent_clips_are_public_read_only_with_playback_urls(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    key = "raw/channel=14/date=2026-05-20/fake.mp3"
    store.record_presigned_upload(key=key, request=_clip_presign(channel="14"))
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Seattle Traffic inbound for Elliott Bay",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )

    response = client.get("/api/clips/recent?limit=5")

    assert response.status_code == 200
    body = response.json()
    assert "key" not in body["clips"][0]
    assert key not in response.text
    assert body["clips"][0]["channel"] == "14"
    assert body["clips"][0]["channel_label"] == "VTS / Seattle Traffic"
    assert body["clips"][0]["transcript"] == "Seattle Traffic inbound for Elliott Bay"
    assert body["clips"][0]["segments"][0]["text"] == "Seattle Traffic inbound for Elliott Bay"
    assert body["clips"][0]["playback_url"] == "https://s3.example.test/playback"
    assert body["clips"][0]["playback_expires_in_seconds"] == 300
    assert body["channel_counts"] == {"14": 1}
    assert body["clip_count"] == 1
    assert body["filtered_clip_count"] == 1
    assert body["channel_labels"]["13"] == "Bridge-to-bridge"
    assert body["channel_labels"]["14"] == "VTS / Seattle Traffic"


def test_recent_clips_quarantine_filter_is_explicit(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    good_key = "raw/channel=14/date=2026-05-20/good.mp3"
    noisy_key = "raw/channel=66A/date=2026-05-20/noisy.mp3"
    store.record_presigned_upload(key=good_key, request=_clip_presign(channel="14"))
    store.record_presigned_upload(
        key=noisy_key,
        request=_clip_presign(channel="66A").model_copy(
            update={"started_at": datetime(2026, 5, 20, 19, 15, tzinfo=UTC)}
        ),
    )
    store.mark_transcribed(
        good_key,
        [
            _segment(
                text="Seattle Traffic inbound for Elliott Bay",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
        quality=ClipQualityMetadata(quality_status="ok", quality_score=91.0),
    )
    store.mark_transcribed(
        noisy_key,
        [
            _segment(
                text="No address is moving",
                started_at="2026-05-20T19:15:00Z",
                ended_at="2026-05-20T19:15:04Z",
            )
        ],
        quality=ClipQualityMetadata(
            quality_status="quarantined",
            quality_score=21.0,
            quality_reason="low_snr",
            quality_flags=("low_snr",),
            audio_metrics={"speech_contrast_db": 1.2},
        ),
    )

    default_body = client.get("/api/clips/recent?limit=5").json()
    quarantine_body = client.get("/api/clips/recent?limit=5&quality=quarantined").json()

    assert [clip["channel"] for clip in default_body["clips"]] == ["14"]
    assert default_body["channel_counts"] == {"14": 1}
    assert default_body["quality"] == "visible"
    assert [clip["channel"] for clip in quarantine_body["clips"]] == ["66A"]
    assert quarantine_body["clips"][0]["quality_status"] == "quarantined"
    assert quarantine_body["clips"][0]["quality_reason"] == "low_snr"
    assert quarantine_body["clips"][0]["quality_flags"] == ["low_snr"]
    assert quarantine_body["clips"][0]["audio_metrics"]["speech_contrast_db"] == 1.2
    assert quarantine_body["channel_counts"] == {"66A": 1}
    assert quarantine_body["quality"] == "quarantined"


def test_recent_clips_hide_legacy_scores_below_current_intelligibility_limit(
    tmp_path,
) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    garbage_key = "raw/channel=06/date=2026-07-28/garbage.mp3"
    clear_key = "raw/channel=06/date=2026-07-28/clear.mp3"
    garbage_started_at = datetime(2026, 7, 28, 21, 9, 22, tzinfo=UTC)
    clear_started_at = garbage_started_at + timedelta(seconds=10)
    for key, started_at, score, text in (
        (garbage_key, garbage_started_at, 88.4, "All right."),
        (clear_key, clear_started_at, 91.0, "Seattle Traffic, roger."),
    ):
        store.record_presigned_upload(
            key=key,
            request=_clip_presign(channel="06").model_copy(
                update={
                    "started_at": started_at,
                    "ended_at": started_at + timedelta(seconds=2),
                    "idempotency_key": f"radio-event-{key.rsplit('/', 1)[-1]}",
                }
            ),
        )
        store.mark_transcribed(
            key,
            [
                _segment(
                    text=text,
                    started_at=started_at.isoformat().replace("+00:00", "Z"),
                    ended_at=(started_at + timedelta(seconds=2))
                    .isoformat()
                    .replace("+00:00", "Z"),
                )
            ],
            quality=ClipQualityMetadata(quality_status="ok", quality_score=score),
        )

    visible_body = client.get(
        "/api/clips/recent?limit=5&include_playback_url=false&verify_playback_exists=false"
    ).json()
    all_body = client.get(
        "/api/clips/recent?limit=5&quality=all&include_playback_url=false&"
        "verify_playback_exists=false"
    ).json()

    assert [clip["transcript"] for clip in visible_body["clips"]] == [
        "Seattle Traffic, roger."
    ]
    assert [clip["transcript"] for clip in all_body["clips"]] == [
        "Seattle Traffic, roger.",
        "All right.",
    ]


def test_recent_clips_can_defer_presigned_playback_urls(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    storage = FakeStorage()
    client = _client(clip_db_path=db_path, storage=storage)
    store = UploadedClipStore(db_path)
    key = "raw/channel=14/date=2026-05-20/fake.mp3"
    store.record_presigned_upload(key=key, request=_clip_presign(channel="14"))
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Seattle Traffic inbound for Elliott Bay",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )

    response = client.get("/api/clips/recent?limit=5&include_playback_url=false")

    assert response.status_code == 200
    clip = response.json()["clips"][0]
    assert "playback_url" not in clip
    assert clip["audio_url"] == "/api/clips/audio?channel=14&started_at=2026-05-20T19%3A12%3A00Z"
    assert storage.presigned_playback_keys == []


def test_recent_clips_can_skip_playback_head_checks(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    storage = NoPlaybackHeadStorage()
    client = _client(clip_db_path=db_path, storage=storage)
    store = UploadedClipStore(db_path)
    key = "raw/channel=14/date=2026-05-20/fake.mp3"
    store.record_presigned_upload(key=key, request=_clip_presign(channel="14"))
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Seattle Traffic inbound for Elliott Bay",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )

    response = client.get(
        "/api/clips/recent?limit=5&include_playback_url=true&verify_playback_exists=false"
    )

    assert response.status_code == 200
    assert response.json()["clips"][0]["playback_url"] == "https://s3.example.test/playback"
    assert storage.presigned_playback_keys == [key]


def test_recent_clips_can_skip_count_queries_for_live_queue(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "radio.sqlite3"
    storage = NoPlaybackHeadStorage()
    client = _client(clip_db_path=db_path, storage=storage)
    store = UploadedClipStore(db_path)
    key = "raw/channel=14/date=2026-05-20/fake.mp3"
    store.record_presigned_upload(key=key, request=_clip_presign(channel="14"))
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Seattle Traffic inbound for Elliott Bay",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )

    def fail_count_query(self, **kwargs):
        raise AssertionError("count queries should be skipped")

    monkeypatch.setattr(UploadedClipStore, "transcribed_channel_counts", fail_count_query)

    response = client.get(
        "/api/clips/recent?limit=5&include_counts=false&"
        "include_playback_url=false&verify_playback_exists=false"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["clips"][0]["audio_url"] == (
        "/api/clips/audio?channel=14&started_at=2026-05-20T19%3A12%3A00Z"
    )
    assert body["clip_count"] == 0
    assert body["received_clip_count"] == 0
    assert body["channel_counts"] == {}
    assert body["counts_deferred"] is True


def test_recent_clips_does_not_fall_back_to_a_scan_when_aggregate_is_missing(tmp_path) -> None:
    client = _client(clip_db_path=tmp_path / "radio.sqlite3", storage=NoPlaybackHeadStorage())

    class AggregateOnlyStore:
        aggregate_counts_enabled = True

        def clip_count_snapshot(self):
            return None

        def transcribed_channel_counts(self, **kwargs):
            raise AssertionError("aggregate rollout must not fall back to a count scan")

        def recent_transcribed(self, **kwargs):
            return []

    async def override_clip_store():
        return AggregateOnlyStore()

    app.dependency_overrides[get_clip_store] = override_clip_store

    response = client.get(
        "/api/clips/recent?limit=5&include_playback_url=false&verify_playback_exists=false"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["clips"] == []
    assert body["clip_count"] == 0
    assert body["channel_counts"] == {}
    assert body["counts_deferred"] is True


def test_recent_clips_can_exclude_traffic_channel_for_live_queue(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "radio.sqlite3"
    storage = NoPlaybackHeadStorage()
    client = _client(clip_db_path=db_path, storage=storage)
    store = UploadedClipStore(db_path)
    traffic_key = "raw/channel=14/date=2026-05-20/traffic.mp3"
    non_traffic_key = "raw/channel=78A/date=2026-05-20/non-traffic.mp3"
    store.record_presigned_upload(key=traffic_key, request=_clip_presign(channel="14"))
    store.mark_transcribed(
        traffic_key,
        [
            _segment(
                text="Seattle Traffic inbound for Elliott Bay",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )
    store.record_presigned_upload(
        key=non_traffic_key,
        request=_clip_presign(channel="78A"),
    )
    store.mark_transcribed(
        non_traffic_key,
        [
            _segment(
                text="Non traffic working channel",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )

    def fail_count_query(self, **kwargs):
        raise AssertionError("count queries should be skipped")

    monkeypatch.setattr(UploadedClipStore, "transcribed_channel_counts", fail_count_query)

    response = client.get(
        "/api/clips/recent?limit=5&include_counts=false&exclude_channels=14&"
        "include_playback_url=false&verify_playback_exists=false"
    )

    assert response.status_code == 200
    body = response.json()
    assert [clip["channel"] for clip in body["clips"]] == ["78A"]
    assert body["clips"][0]["audio_url"] == (
        "/api/clips/audio?channel=78A&started_at=2026-05-20T19%3A12%3A00Z"
    )
    assert body["clip_count"] == 0


def test_recent_clips_exclude_traffic_counts_without_channel_fanout(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    storage = NoPlaybackHeadStorage()
    client = _client(clip_db_path=db_path, storage=storage)
    store = UploadedClipStore(db_path)
    traffic_key = "raw/channel=14/date=2026-05-20/traffic.mp3"
    non_traffic_key = "raw/channel=78A/date=2026-05-20/non-traffic.mp3"
    store.record_presigned_upload(key=traffic_key, request=_clip_presign(channel="14"))
    store.mark_transcribed(
        traffic_key,
        [
            _segment(
                text="Seattle Traffic inbound for Elliott Bay",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )
    store.record_presigned_upload(
        key=non_traffic_key,
        request=_clip_presign(channel="78A"),
    )
    store.mark_transcribed(
        non_traffic_key,
        [
            _segment(
                text="Non traffic working channel",
                started_at="2026-05-20T19:13:00Z",
                ended_at="2026-05-20T19:13:04Z",
            )
        ],
    )

    response = client.get(
        "/api/clips/recent?limit=5&exclude_channels=14&"
        "include_playback_url=false&verify_playback_exists=false"
    )

    assert response.status_code == 200
    body = response.json()
    assert [clip["channel"] for clip in body["clips"]] == ["78A"]
    assert body["channel_counts"] == {"78A": 1}
    assert body["clip_count"] == 1
    assert body["filtered_clip_count"] == 1
    assert body["playable_clip_count"] == 1
    assert body["filtered_playable_clip_count"] == 1


def test_operator_can_star_clip_for_hall_of_fame_filter(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    event_store = CapturingEventStore()
    storage = FakeStorage()
    client = _client(clip_db_path=db_path, event_store=event_store, storage=storage)
    store = UploadedClipStore(db_path)
    starred_key = "raw/channel=14/date=2026-05-20/featured.mp3"
    plain_key = "raw/channel=68/date=2026-05-20/plain.mp3"
    store.record_presigned_upload(key=starred_key, request=_clip_presign(channel="14"))
    store.record_presigned_upload(
        key=plain_key,
        request=_clip_presign(channel="68").model_copy(
            update={
                "started_at": datetime(2026, 5, 20, 19, 13, tzinfo=UTC),
                "ended_at": datetime(2026, 5, 20, 19, 13, 5, tzinfo=UTC),
                "idempotency_key": "radio-event-68-plain",
            }
        ),
    )
    store.mark_transcribed(
        starred_key,
        [
            _segment(
                text="PAN-PAN all stations",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )
    store.mark_transcribed(
        plain_key,
        [
            _segment(
                text="Routine recreational call",
                started_at="2026-05-20T19:13:00Z",
                ended_at="2026-05-20T19:13:04Z",
            )
        ],
    )

    response = client.post(
        "/api/clips/features",
        json={
            "channel": "14",
            "started_at": "2026-05-20T19:12:00Z",
            "featured": True,
            "featured_by": "operator-ui",
        },
    )
    recent = client.get("/api/clips/recent?limit=5&featured=true")

    assert response.status_code == 200
    assert response.json() == {
        "status": "featured",
        "channel": "14",
        "started_at": "2026-05-20T19:12:00Z",
        "featured": True,
    }
    body = recent.json()
    assert [clip["transcript"] for clip in body["clips"]] == ["PAN-PAN all stations"]
    assert body["clips"][0]["featured"] is True
    assert body["clip_count"] == 2
    assert body["filtered_clip_count"] == 1
    assert starred_key not in recent.text
    assert plain_key not in recent.text
    assert event_store.events[-1]["event_type"] == "clip.featured"
    assert storage.featured_tags == [(starred_key, True)]


def test_featured_recent_clips_report_live_featured_playable_counts(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    public_site_dir = tmp_path / "public-site"
    public_site_dir.mkdir()
    (public_site_dir / "public_manifest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-06-04T15:19:15Z",
                "stats": {"clip_count": 2, "channel_counts": {"14": 2}},
                "clips": [
                    {
                        "id": f"published-featured-{index}",
                        "channel": "14",
                        "started_at": f"2026-06-04T15:0{index}:00Z",
                        "audio_public_filename": f"published-featured-{index}.mp3",
                        "transcript_public": f"Published featured {index}",
                        "featured": True,
                    }
                    for index in range(2)
                ],
            }
        ),
        encoding="utf-8",
    )
    client = _client(clip_db_path=db_path, public_site_dir=public_site_dir)
    store = UploadedClipStore(db_path)
    for index in range(6):
        channel = "14" if index % 2 == 0 else "68"
        started_at = datetime(2026, 6, 4, 16, index, tzinfo=UTC)
        key = f"raw/channel={channel}/date=2026-06-04/featured-{index}.mp3"
        store.record_presigned_upload(
            key=key,
            request=_clip_presign(channel=channel).model_copy(
                update={
                    "started_at": started_at,
                    "ended_at": started_at + timedelta(seconds=4),
                    "idempotency_key": f"radio-event-featured-count-{index}",
                }
            ),
        )
        store.mark_transcribed(
            key,
            [
                _segment(
                    text=f"Live featured {index}",
                    started_at=started_at.isoformat().replace("+00:00", "Z"),
                    ended_at=(started_at + timedelta(seconds=4)).isoformat().replace("+00:00", "Z"),
                )
            ],
        )
        store.set_clip_featured(
            channel=channel,
            started_at=started_at.isoformat().replace("+00:00", "Z"),
            featured=True,
            featured_by="operator-ui",
        )

    response = client.get("/api/clips/recent?limit=6&featured=true")

    assert response.status_code == 200
    body = response.json()
    assert len(body["clips"]) == 6
    assert body["clip_count"] == 6
    assert body["filtered_clip_count"] == 6
    assert body["playable_clip_count"] == 6
    assert body["filtered_playable_clip_count"] == 6
    assert body["playable_channel_counts"] == {"14": 3, "68": 3}


def test_operator_can_remove_clip_from_hall_of_fame(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    storage = FakeStorage()
    client = _client(clip_db_path=db_path, storage=storage)
    store = UploadedClipStore(db_path)
    key = "raw/channel=14/date=2026-05-20/featured.mp3"
    store.record_presigned_upload(key=key, request=_clip_presign(channel="14"))
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Featured once",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )
    store.set_clip_featured(
        channel="14",
        started_at="2026-05-20T19:12:00Z",
        featured=True,
        featured_by="operator-ui",
    )

    response = client.post(
        "/api/clips/features",
        json={
            "channel": "14",
            "started_at": "2026-05-20T19:12:00Z",
            "featured": False,
            "featured_by": "operator-ui",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "unfeatured",
        "channel": "14",
        "started_at": "2026-05-20T19:12:00Z",
        "featured": False,
    }
    assert client.get("/api/clips/recent?limit=5&featured=true").json()["clips"] == []
    assert storage.featured_tags == [(key, False)]


def test_operator_star_returns_503_when_retention_tag_update_fails(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    storage = FakeStorage(tag_error=RuntimeError("S3 tagging failed"))
    client = _client(clip_db_path=db_path, storage=storage)
    store = UploadedClipStore(db_path)
    key = "raw/channel=14/date=2026-05-20/featured.mp3"
    store.record_presigned_upload(key=key, request=_clip_presign(channel="14"))
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Potential feature",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )

    response = client.post(
        "/api/clips/features",
        json={
            "channel": "14",
            "started_at": "2026-05-20T19:12:00Z",
            "featured": True,
            "featured_by": "operator-ui",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "S3 tagging failed"


def test_recent_clips_skip_missing_playback_objects(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    missing_key = "raw/channel=68/date=2026-05-20/missing.mp3"
    playable_key = "raw/channel=68/date=2026-05-20/playable.mp3"
    client = _client(
        clip_db_path=db_path,
        storage=FakeStorage(missing_playback_keys={missing_key}),
    )
    store = UploadedClipStore(db_path)
    for key, minute, text in [
        (missing_key, 13, "This audio object is gone"),
        (playable_key, 12, "This audio object is present"),
    ]:
        started_at = datetime(2026, 5, 20, 19, minute, tzinfo=UTC)
        store.record_presigned_upload(
            key=key,
            request=_clip_presign(channel="68").model_copy(
                update={
                    "started_at": started_at,
                    "idempotency_key": f"radio-event-{minute}",
                }
            ),
        )
        store.mark_transcribed(
            key,
            [
                _segment(
                    text=text,
                    started_at=f"2026-05-20T19:{minute}:00Z",
                    ended_at=f"2026-05-20T19:{minute}:04Z",
                )
            ],
        )

    response = client.get("/api/clips/recent?limit=5&channel=68")

    assert response.status_code == 200
    body = response.json()
    assert [clip["transcript"] for clip in body["clips"]] == ["This audio object is present"]
    assert missing_key not in response.text
    assert playable_key not in response.text


def test_recent_clips_reports_published_playable_counts_separately(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    public_site_dir = tmp_path / "public-site"
    public_site_dir.mkdir()
    (public_site_dir / "public_manifest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-06-04T15:19:15Z",
                "stats": {
                    "clip_count": 2,
                    "channel_counts": {"14": 1, "68": 1},
                },
                "clips": [
                    {
                        "id": "clip-one",
                        "channel": "14",
                        "started_at": "2026-06-04T15:00:00Z",
                        "audio_public_filename": "one.mp3",
                        "transcript_public": "Seattle traffic one",
                    },
                    {
                        "id": "clip-two",
                        "channel": "68",
                        "started_at": "2026-06-04T15:03:00Z",
                        "audio_public_filename": "two.mp3",
                        "transcript_public": "Recreational two",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    client = _client(clip_db_path=db_path, public_site_dir=public_site_dir)
    store = UploadedClipStore(db_path)
    for index in range(3):
        channel = "14" if index != 1 else "68"
        key = f"raw/channel={channel}/date=2026-06-04/fake-{index}.mp3"
        started_at = datetime(2026, 6, 4, 15, index, tzinfo=UTC)
        store.record_presigned_upload(
            key=key,
            request=_clip_presign(channel=channel).model_copy(
                update={
                    "started_at": started_at,
                    "ended_at": started_at + timedelta(seconds=4),
                    "idempotency_key": f"radio-event-playable-count-{index}",
                }
            ),
        )
        store.mark_transcribed(
            key,
            [
                _segment(
                    text=f"Transcript {index}",
                    started_at=started_at.isoformat().replace("+00:00", "Z"),
                    ended_at=(started_at + timedelta(seconds=4)).isoformat().replace("+00:00", "Z"),
                )
            ],
        )

    response = client.get("/api/clips/recent?limit=5")

    assert response.status_code == 200
    body = response.json()
    assert body["clip_count"] == 3
    assert body["received_clip_count"] == 3
    assert body["analyzed_clip_count"] == 3
    assert body["playable_clip_count"] == 2
    assert body["filtered_playable_clip_count"] == 2
    assert body["playable_channel_counts"] == {"14": 1, "68": 1}
    assert body["latest_playable_started_at"] == "2026-06-04T15:02:00Z"


def test_recent_clips_pages_over_playable_clips(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    missing_key = "raw/channel=68/date=2026-05-20/fake-1.mp3"
    client = _client(
        clip_db_path=db_path,
        storage=FakeStorage(missing_playback_keys={missing_key}),
    )
    store = UploadedClipStore(db_path)
    for index in range(7):
        started_at = datetime(2026, 5, 20, 19, index, tzinfo=UTC)
        key = f"raw/channel=68/date=2026-05-20/fake-{index}.mp3"
        request = _clip_presign(channel="68").model_copy(
            update={
                "started_at": started_at,
                "ended_at": started_at + timedelta(seconds=5),
                "idempotency_key": f"radio-event-page-{index}",
            }
        )
        store.record_presigned_upload(key=key, request=request)
        store.mark_transcribed(
            key,
            [
                _segment(
                    text=f"Playable page clip {index}",
                    started_at=f"2026-05-20T19:{index:02d}:00Z",
                    ended_at=f"2026-05-20T19:{index:02d}:04Z",
                )
            ],
        )

    page_1 = client.get("/api/clips/recent?limit=3&offset=0&channel=68")
    page_2 = client.get("/api/clips/recent?limit=3&offset=3&channel=68")
    oldest_page = client.get("/api/clips/recent?limit=3&offset=0&channel=68&sort=oldest")

    assert page_1.status_code == 200
    assert page_2.status_code == 200
    assert oldest_page.status_code == 200
    assert [clip["transcript"] for clip in page_1.json()["clips"]] == [
        "Playable page clip 6",
        "Playable page clip 5",
        "Playable page clip 4",
    ]
    assert [clip["transcript"] for clip in page_2.json()["clips"]] == [
        "Playable page clip 3",
        "Playable page clip 2",
        "Playable page clip 0",
    ]
    assert [clip["transcript"] for clip in oldest_page.json()["clips"]] == [
        "Playable page clip 0",
        "Playable page clip 2",
        "Playable page clip 3",
    ]


def test_recent_clips_cursor_is_stable_when_new_clip_arrives(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    for index in range(7):
        started_at = datetime(2026, 7, 28, 12, index, tzinfo=UTC)
        key = f"raw/channel=14/date=2026-07-28/cursor-{index}.mp3"
        store.record_presigned_upload(
            key=key,
            request=_clip_presign(channel="14").model_copy(
                update={
                    "started_at": started_at,
                    "ended_at": started_at + timedelta(seconds=5),
                    "idempotency_key": f"cursor-{index}",
                }
            ),
        )
        store.mark_transcribed(
            key,
            [
                _segment(
                    text=f"Cursor clip {index}",
                    started_at=started_at.isoformat().replace("+00:00", "Z"),
                    ended_at=(started_at + timedelta(seconds=4)).isoformat().replace("+00:00", "Z"),
                )
            ],
        )

    first = client.get("/api/clips/recent?limit=3&channel=14")
    assert first.status_code == 200
    first_body = first.json()
    assert [clip["transcript"] for clip in first_body["clips"]] == [
        "Cursor clip 6",
        "Cursor clip 5",
        "Cursor clip 4",
    ]
    assert first_body["next_cursor"]
    padded_cursor = first_body["next_cursor"] + ("=" * (-len(first_body["next_cursor"]) % 4))
    decoded_cursor = json.loads(base64.urlsafe_b64decode(padded_cursor))
    assert "anchor" in decoded_cursor
    assert "key" not in decoded_cursor
    assert "raw/channel=" not in json.dumps(decoded_cursor)

    newest_at = datetime(2026, 7, 28, 12, 10, tzinfo=UTC)
    newest_key = "raw/channel=14/date=2026-07-28/cursor-new.mp3"
    store.record_presigned_upload(
        key=newest_key,
        request=_clip_presign(channel="14").model_copy(
            update={
                "started_at": newest_at,
                "ended_at": newest_at + timedelta(seconds=5),
                "idempotency_key": "cursor-new",
            }
        ),
    )
    store.mark_transcribed(
        newest_key,
        [
            _segment(
                text="Cursor clip new",
                started_at=newest_at.isoformat().replace("+00:00", "Z"),
                ended_at=(newest_at + timedelta(seconds=4)).isoformat().replace("+00:00", "Z"),
            )
        ],
    )

    second = client.get(
        "/api/clips/recent",
        params={"limit": 3, "channel": "14", "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    assert [clip["transcript"] for clip in second.json()["clips"]] == [
        "Cursor clip 3",
        "Cursor clip 2",
        "Cursor clip 1",
    ]
    assert not {clip["transcript"] for clip in first_body["clips"]} & {
        clip["transcript"] for clip in second.json()["clips"]
    }


def test_recent_clips_cursor_is_bound_to_filters(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    for index in range(2):
        started_at = datetime(2026, 7, 28, 13, index, tzinfo=UTC)
        key = f"raw/channel=14/date=2026-07-28/bound-{index}.mp3"
        store.record_presigned_upload(
            key=key,
            request=_clip_presign(channel="14").model_copy(
                update={
                    "started_at": started_at,
                    "idempotency_key": f"bound-{index}",
                }
            ),
        )
        store.mark_transcribed(
            key,
            [
                _segment(
                    text=f"Bound cursor {index}",
                    started_at=started_at.isoformat().replace("+00:00", "Z"),
                    ended_at=(started_at + timedelta(seconds=4)).isoformat().replace("+00:00", "Z"),
                )
            ],
        )
    cursor = client.get("/api/clips/recent?limit=1&channel=14").json()["next_cursor"]

    response = client.get(
        "/api/clips/recent",
        params={"limit": 1, "channel": "68", "cursor": cursor},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "cursor does not match the requested clip filters"


def test_recent_clips_cursor_is_bound_to_datetime_anchor(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    for index in range(3):
        started_at = datetime(2026, 7, 28, 13, index, tzinfo=UTC)
        key = f"raw/channel=14/date=2026-07-28/around-bound-{index}.mp3"
        store.record_presigned_upload(
            key=key,
            request=_clip_presign(channel="14").model_copy(
                update={
                    "started_at": started_at,
                    "idempotency_key": f"around-bound-{index}",
                }
            ),
        )
        store.mark_transcribed(
            key,
            [
                _segment(
                    text=f"Around bound cursor {index}",
                    started_at=started_at.isoformat().replace("+00:00", "Z"),
                    ended_at=(started_at + timedelta(seconds=4))
                    .isoformat()
                    .replace("+00:00", "Z"),
                )
            ],
        )
    cursor = client.get(
        "/api/clips/recent",
        params={"limit": 1, "channel": "14", "around": "2026-07-28T13:02:00Z"},
    ).json()["next_cursor"]

    response = client.get(
        "/api/clips/recent",
        params={
            "limit": 1,
            "channel": "14",
            "around": "2026-07-28T13:01:00Z",
            "cursor": cursor,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "cursor does not match the requested clip filters"


def test_public_clip_playback_url_can_be_refreshed_without_exposing_key(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    started_at = datetime(2026, 5, 20, 19, 12, tzinfo=UTC)
    key = "raw/channel=14/date=2026-05-20/fake.mp3"
    store.record_presigned_upload(
        key=key,
        request=_clip_presign(channel="14").model_copy(update={"started_at": started_at}),
    )
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Seattle Traffic inbound for Elliott Bay",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )

    response = client.get(
        "/api/clips/playback?channel=14&started_at=2026-05-20T19%3A12%3A00%2B00%3A00"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["channel"] == "14"
    assert body["started_at"] == "2026-05-20T19:12:00Z"
    assert body["playback_url"] == "https://s3.example.test/playback"
    assert body["playback_expires_in_seconds"] == 300
    assert "key" not in body
    assert key not in response.text


def test_public_clip_audio_redirects_to_presigned_playback_without_proxying_body(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    storage = FakeStorage(playback_content=b"same-origin-mp3")
    client = _client(clip_db_path=db_path, storage=storage)
    store = UploadedClipStore(db_path)
    started_at = datetime(2026, 5, 20, 19, 12, tzinfo=UTC)
    key = "raw/channel=14/date=2026-05-20/fake.mp3"
    store.record_presigned_upload(
        key=key,
        request=_clip_presign(channel="14").model_copy(update={"started_at": started_at}),
    )
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Seattle Traffic inbound for Elliott Bay",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )

    response = client.get(
        "/api/clips/audio?channel=14&started_at=2026-05-20T19%3A12%3A00%2B00%3A00"
    )

    assert response.status_code == 307
    assert response.headers["location"] == "https://s3.example.test/playback"
    assert response.headers["cache-control"] == "no-store"
    assert storage.opened_playback_keys == []
    assert storage.presigned_playback_keys == [key]


def test_public_clip_playback_url_rejects_missing_playback_object(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    started_at = datetime(2026, 5, 20, 19, 12, tzinfo=UTC)
    key = "raw/channel=14/date=2026-05-20/missing.mp3"
    client = _client(
        clip_db_path=db_path,
        storage=FakeStorage(missing_playback_keys={key}),
    )
    store = UploadedClipStore(db_path)
    store.record_presigned_upload(
        key=key,
        request=_clip_presign(channel="14").model_copy(update={"started_at": started_at}),
    )
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Seattle Traffic inbound for Elliott Bay",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )

    response = client.get(
        "/api/clips/playback?channel=14&started_at=2026-05-20T19%3A12%3A00%2B00%3A00"
    )

    assert response.status_code == 404
    assert key not in response.text


def test_public_clip_playback_url_rejects_excluded_channels(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    key = "raw/channel=WX/date=2026-05-20/noaa.mp3"
    request = _clip_presign(channel="14").model_copy(
        update={"channel": "WX", "idempotency_key": "radio-event-wx"}
    )
    store.record_presigned_upload(key=key, request=request)
    store.mark_transcribed(
        key,
        [
            _segment(
                text="NOAA weather radio",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )

    response = client.get(
        "/api/clips/playback?channel=WX&started_at=2026-05-20T19%3A12%3A00%2B00%3A00"
    )

    assert response.status_code == 404
    assert key not in response.text


def test_recent_clips_reports_total_counts_and_supports_offsets_and_pages(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    for index in range(8):
        channel = "14" if index % 2 else "68"
        started_at = datetime(2026, 5, 20, 19, index, tzinfo=UTC)
        key = f"raw/channel={channel}/date=2026-05-20/fake-{index}.mp3"
        request = _clip_presign(channel=channel).model_copy(
            update={
                "started_at": started_at,
                "ended_at": started_at + timedelta(seconds=5),
                "idempotency_key": f"radio-event-{index}",
            }
        )
        store.record_presigned_upload(key=key, request=request)
        store.mark_transcribed(
            key,
            [
                _segment(
                    text=f"Clip {index}",
                    started_at=f"2026-05-20T19:{index:02d}:00Z",
                    ended_at=f"2026-05-20T19:{index:02d}:04Z",
                )
            ],
        )

    response = client.get("/api/clips/recent?limit=6&offset=6")
    page_response = client.get("/api/clips/recent?limit=6&page=2")

    assert response.status_code == 200
    assert page_response.status_code == 200
    body = response.json()
    page_body = page_response.json()
    assert len(body["clips"]) == 2
    assert [clip["transcript"] for clip in body["clips"]] == ["Clip 1", "Clip 0"]
    assert [clip["transcript"] for clip in page_body["clips"]] == ["Clip 1", "Clip 0"]
    assert body["clip_count"] == 8
    assert body["filtered_clip_count"] == 8
    assert body["limit"] == 6
    assert body["offset"] == 6
    assert page_body["offset"] == 6
    assert page_body["page"] == 2
    assert body["channel_counts"] == {"14": 4, "68": 4}


def test_recent_clips_can_filter_by_multiple_channels(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    channels = ["13", "14", "68", "72"]
    for index, channel in enumerate(channels):
        started_at = datetime(2026, 5, 20, 19, index, tzinfo=UTC)
        key = f"raw/channel={channel}/date=2026-05-20/fake-{index}.mp3"
        request = _clip_presign(channel=channel).model_copy(
            update={
                "started_at": started_at,
                "ended_at": started_at + timedelta(seconds=5),
                "idempotency_key": f"radio-event-multi-{index}",
            }
        )
        store.record_presigned_upload(key=key, request=request)
        store.mark_transcribed(
            key,
            [
                _segment(
                    text=f"Clip {channel}",
                    started_at=f"2026-05-20T19:{index:02d}:00Z",
                    ended_at=f"2026-05-20T19:{index:02d}:04Z",
                )
            ],
        )

    response = client.get("/api/clips/recent?limit=10&channels=13&channels=68")

    assert response.status_code == 200
    body = response.json()
    assert [clip["channel"] for clip in body["clips"]] == ["68", "13"]
    assert [clip["transcript"] for clip in body["clips"]] == ["Clip 68", "Clip 13"]
    assert body["clip_count"] == 4
    assert body["filtered_clip_count"] == 2
    assert body["channel_counts"] == {"13": 1, "14": 1, "68": 1, "72": 1}


def test_recent_clips_can_start_around_pacific_datetime_and_filter_channel(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    clips = [
        ("68", datetime(2026, 5, 20, 18, 58, tzinfo=UTC), "Before target"),
        ("14", datetime(2026, 5, 20, 18, 59, tzinfo=UTC), "Other channel"),
        ("68", datetime(2026, 5, 20, 19, 1, tzinfo=UTC), "After target one"),
        ("68", datetime(2026, 5, 20, 19, 2, tzinfo=UTC), "After target two"),
    ]
    for index, (channel, started_at, transcript) in enumerate(clips):
        key = f"raw/channel={channel}/date=2026-05-20/around-{index}.mp3"
        store.record_presigned_upload(
            key=key,
            request=_clip_presign(channel=channel).model_copy(
                update={
                    "started_at": started_at,
                    "ended_at": started_at + timedelta(seconds=5),
                    "idempotency_key": f"radio-event-around-{index}",
                }
            ),
        )
        store.mark_transcribed(
            key,
            [
                _segment(
                    text=transcript,
                    started_at=started_at.isoformat().replace("+00:00", "Z"),
                    ended_at=(started_at + timedelta(seconds=4))
                    .isoformat()
                    .replace("+00:00", "Z"),
                )
            ],
        )

    earlier = client.get(
        "/api/clips/recent",
        params={"limit": 5, "around": "2026-05-20T12:00", "channels": "68"},
    )
    later = client.get(
        "/api/clips/recent",
        params={
            "limit": 5,
            "around": "2026-05-20T12:00",
            "channels": "68",
            "sort": "oldest",
        },
    )
    unfiltered = client.get(
        "/api/clips/recent",
        params={"limit": 5, "around": "2026-05-20T12:00"},
    )

    assert earlier.status_code == 200
    assert later.status_code == 200
    assert unfiltered.status_code == 200
    assert [clip["transcript"] for clip in earlier.json()["clips"]] == ["Before target"]
    assert [clip["transcript"] for clip in later.json()["clips"]] == [
        "After target one",
        "After target two",
    ]
    assert earlier.json()["around"] == "2026-05-20T19:00:00Z"
    assert earlier.json()["around_timezone"] == "America/Los_Angeles"
    assert [clip["transcript"] for clip in unfiltered.json()["clips"]] == [
        "Other channel",
        "Before target",
    ]


def test_recent_clips_reject_invalid_around_datetime(tmp_path) -> None:
    client = _client(clip_db_path=tmp_path / "radio.sqlite3")

    response = client.get("/api/clips/recent", params={"around": "not-a-datetime"})

    assert response.status_code == 400
    assert response.json()["detail"] == "around must be an ISO 8601 date and time"


def test_recent_clips_reject_nonexistent_pacific_daylight_time(tmp_path) -> None:
    client = _client(clip_db_path=tmp_path / "radio.sqlite3")

    response = client.get(
        "/api/clips/recent",
        params={"around": "2026-03-08T02:30"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "around is not a valid Pacific date and time"


def test_recent_clips_can_filter_by_sparse_channel(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    client = _client(clip_db_path=db_path)
    store = UploadedClipStore(db_path)
    wx_key = "raw/channel=WX/date=2026-05-20/noaa.mp3"
    channel_14_key = "raw/channel=14/date=2026-05-20/traffic.mp3"
    legacy_wx_request = _clip_presign(channel="14").model_copy(
        update={"channel": "WX", "idempotency_key": "radio-event-wx"}
    )
    store.record_presigned_upload(key=wx_key, request=legacy_wx_request)
    store.record_presigned_upload(key=channel_14_key, request=_clip_presign(channel="14"))
    store.mark_transcribed(
        wx_key,
        [
            _segment(
                text="Weather radio forecast",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )
    store.mark_transcribed(
        channel_14_key,
        [
            _segment(
                text="Wait for your call",
                started_at="2026-05-20T19:12:00Z",
                ended_at="2026-05-20T19:12:04Z",
            )
        ],
    )

    response = client.get("/api/clips/recent?limit=5&channel=14")

    assert response.status_code == 200
    body = response.json()
    assert [clip["channel"] for clip in body["clips"]] == ["14"]
    assert [clip["channel_label"] for clip in body["clips"]] == ["VTS / Seattle Traffic"]
    assert [clip["transcript"] for clip in body["clips"]] == ["Wait for your call"]
    assert channel_14_key not in response.text
    assert all("key" not in clip for clip in body["clips"])
    assert body["channel_counts"] == {"14": 1}
    assert body["channel_labels"]["13"] == "Bridge-to-bridge"
    assert body["channel_labels"]["14"] == "VTS / Seattle Traffic"

    wx_response = client.get("/api/clips/recent?limit=5&channel=WX")

    assert wx_response.status_code == 200
    assert wx_response.json() == {
        "clips": [],
        "clip_count": 1,
        "received_clip_count": 2,
        "analyzed_clip_count": 1,
        "filtered_clip_count": 0,
        "playable_clip_count": 0,
        "filtered_playable_clip_count": 0,
        "playable_channel_counts": {},
        "latest_playable_started_at": None,
        "next_cursor": None,
        "limit": 5,
        "offset": 0,
        "page": 1,
        "featured": False,
        "quality": "visible",
        "channel_counts": {"14": 1},
        "counts_deferred": False,
        "channel_labels": {
            "05A": "VTS / Port Ops",
            "06": "Intership Safety",
            "09": "Calling / Commercial",
            "10": "Commercial",
            "13": "Bridge-to-bridge",
            "14": "VTS / Seattle Traffic",
            "68": "Recreational",
            "16": "Distress / Calling",
            "22A": "USCG Liaison",
            "65A": "Port Operations",
            "66A": "Port Operations",
            "67": "Commercial / Bridge",
            "69": "Non-commercial",
            "71": "Non-commercial",
            "72": "Ship-to-ship",
            "73": "Port Operations",
            "74": "Port Operations",
            "77": "Ship-to-ship",
            "78A": "Non-commercial",
        },
    }


def test_public_lexical_analysis_returns_missing_payload_without_cache(tmp_path) -> None:
    client = _client(clip_db_path=tmp_path / "radio.sqlite3")

    response = client.get("/api/analysis/lexical")

    assert response.status_code == 200
    assert response.json()["status"] == "missing"
    assert response.json()["source_clip_count"] == 0


def test_public_lexical_analysis_returns_cached_payload_without_private_fields(tmp_path) -> None:
    db_path = tmp_path / "radio.sqlite3"
    UploadedClipStore(db_path)
    cached = {
        "status": "ok",
        "generated_at": "2026-05-26T01:02:03Z",
        "source_clip_count": 1,
        "source_min_started_at": "2026-05-25T22:10:00Z",
        "source_max_started_at": "2026-05-25T22:10:00Z",
        "channels": {"14": 1},
        "frequency": {"by_channel": {"14": 1}},
        "terms": {"unigrams": []},
        "entities": [
            {
                "name": "Seattle Traffic",
                "kind": "shore_station",
                "count": 1,
                "confidence": 0.95,
                "channels": {"14": 1},
                "examples": [
                    {
                        "channel": "14",
                        "started_at": "2026-05-25T22:10:00Z",
                        "text": "Seattle Traffic roger.",
                    }
                ],
            }
        ],
        "topics": {"status": "skipped", "plot_url": "/analysis/topic_clusters.html"},
        "education": [],
    }
    write_cached_lexical_analysis(db_path, payload=cached, source_fingerprint="clip:1")
    client = _client(clip_db_path=db_path)

    response = client.get("/api/analysis/lexical")

    assert response.status_code == 200
    assert response.json() == cached
    assert "raw/channel" not in response.text
    assert "X-Amz-" not in response.text
    assert "127.0.0.1" not in response.text


def test_public_lexical_analysis_uses_published_json_in_dynamo_mode(
    tmp_path,
    monkeypatch,
) -> None:
    published = {
        "status": "ok",
        "generated_at": "2026-05-26T01:02:03Z",
        "source_clip_count": 1,
        "source_min_started_at": "2026-05-25T22:10:00Z",
        "source_max_started_at": "2026-05-25T22:10:00Z",
        "channels": {"14": 1},
        "frequency": {"by_channel": {"14": 1}},
        "terms": {"unigrams": []},
        "entities": [],
        "topics": {"status": "skipped", "plot_url": "/analysis/topic_clusters.html"},
        "education": [],
    }
    lexical_path = tmp_path / "lexical.json"
    lexical_path.write_text(json.dumps(published), encoding="utf-8")
    monkeypatch.setattr("talkingboats.api.PUBLISHED_LEXICAL_PATH", lexical_path)
    missing_db_path = tmp_path / "missing.sqlite3"
    client = _client(clip_db_path=missing_db_path, clip_store_backend="dynamodb")

    response = client.get("/api/analysis/lexical")

    assert response.status_code == 200
    assert response.json() == published


def test_public_clip_search_returns_vector_ranked_audio_results(
    tmp_path,
    monkeypatch,
) -> None:
    search_index = {
        "status": "ok",
        "generated_at": "2026-06-01T18:00:00Z",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "vector_dimension": 2,
        "source_clip_count": 3,
        "clips": [
            {
                "channel": "14",
                "started_at": "2026-06-01T17:58:00Z",
                "ended_at": "2026-06-01T17:58:12Z",
                "duration_seconds": 12,
                "content_type": "audio/mpeg",
                "transcript": "Seattle Traffic, tug and barge northbound.",
                "embedding": [0.99, 0.01],
            },
            {
                "channel": "13",
                "started_at": "2026-05-30T17:58:00Z",
                "ended_at": "2026-05-30T17:58:10Z",
                "duration_seconds": 10,
                "content_type": "audio/mpeg",
                "transcript": "Bridge to bridge passing arrangement.",
                "embedding": [0.8, 0.2],
            },
            {
                "channel": "14",
                "started_at": "2026-04-01T17:58:00Z",
                "ended_at": "2026-04-01T17:58:08Z",
                "duration_seconds": 8,
                "content_type": "audio/mpeg",
                "transcript": "Old tug and barge archive.",
                "embedding": [1.0, 0.0],
            },
        ],
    }
    index_path = tmp_path / "search_index.json"
    index_path.write_text(json.dumps(search_index), encoding="utf-8")
    monkeypatch.setattr("talkingboats.api.PUBLISHED_SEARCH_INDEX_PATH", index_path)

    class FakeSentenceTransformer:
        def __init__(self, model_name: str) -> None:
            assert model_name == "sentence-transformers/all-MiniLM-L6-v2"

        def encode(self, documents: list[str], *, show_progress_bar: bool) -> list[list[float]]:
            assert documents == ["tug barge"]
            assert show_progress_bar is False
            return [[1.0, 0.0]]

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    client = _client(clip_store_backend="dynamodb")

    response = client.get("/api/clips/search?q=tug%20barge&limit=2&recency=30d")

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "tug barge"
    assert payload["recency"] == "30d"
    assert payload["count"] == 2
    assert payload["index"]["source_clip_count"] == 3
    assert payload["results"][0]["transcript"] == "Seattle Traffic, tug and barge northbound."
    assert payload["results"][0]["audio_url"].startswith("/api/clips/audio?")
    assert payload["results"][0]["score"] > payload["results"][1]["score"]
    assert "Old tug and barge archive" not in response.text
    assert "raw/channel" not in response.text


def test_public_clip_search_reports_missing_index(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("talkingboats.api.PUBLISHED_SEARCH_INDEX_PATH", tmp_path / "missing.json")
    client = _client(clip_store_backend="dynamodb")

    response = client.get("/api/clips/search?q=barge")

    assert response.status_code == 503
    assert response.json()["detail"] == "clip search index is not ready"


def test_operator_live_channels_do_not_expose_upstream_urls() -> None:
    client = _client()

    response = client.get("/api/live/channels")

    assert response.status_code == 200
    rendered = response.text
    assert "127.0.0.1" not in rendered
    assert "vhf-68.mp3" not in rendered
    assert response.json()["channels"][0]["enabled"] is True


def test_operator_session_endpoint_is_not_exposed() -> None:
    client = _client()

    session_response = client.post("/api/operator/session")
    channels_response = client.get("/api/live/channels")

    assert session_response.status_code == 404
    assert channels_response.status_code == 200


def test_playback_presign_rejects_public_prefix() -> None:
    client = _client()

    response = client.post("/api/clips/playback-url", json={"key": "public/file.mp3"})

    assert response.status_code == 400


class AsgiTestClient:
    def __init__(self, app) -> None:
        self.app = app
        self.cookies = httpx.Cookies()

    def get(self, path: str, **kwargs) -> httpx.Response:
        return _run(self._request("GET", path, **kwargs))

    def post(self, path: str, **kwargs) -> httpx.Response:
        return _run(self._request("POST", path, **kwargs))

    def delete(self, path: str, **kwargs) -> httpx.Response:
        return _run(self._request("DELETE", path, **kwargs))

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies=self.cookies,
        ) as client:
            response = await client.request(method, path, **kwargs)
        self.cookies.update(response.cookies)
        return response


def _client(
    *,
    clip_db_path: Path | None = None,
    clip_store_backend: str = "sqlite",
    storage: FakeStorage | None = None,
    event_store: CapturingEventStore | None = None,
    public_site_dir: Path | None = None,
) -> AsgiTestClient:
    app.dependency_overrides.clear()

    async def override_settings() -> Settings:
        return Settings(
            aws_region="us-west-2",
            raw_bucket="raw-bucket",
            public_bucket="public-bucket",
            ingest_token="ingest-token",
            raw_presign_seconds=900,
            playback_presign_seconds=300,
            public_site_dir=public_site_dir or Path("/tmp/talkingboats-missing-public-site"),
            public_base_url="https://seattleboatradio.com",
            live_channels={
                "68": LiveChannel(
                    channel="68",
                    label="Recreational",
                    frequency_mhz=156.425,
                    stream_url="http://127.0.0.1:8040/vhf-68.mp3",
                ),
                "14": LiveChannel(
                    channel="14",
                    label="VTS / Seattle Traffic",
                    frequency_mhz=156.700,
                    stream_url=None,
                ),
            },
            clip_db_path=clip_db_path,
            clip_store_backend=clip_store_backend,
        )

    async def override_storage() -> FakeStorage:
        return storage or FakeStorage()

    async def override_durable_event_store():
        return event_store or NullDurableEventStore()

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_storage] = override_storage
    app.dependency_overrides[get_durable_event_store] = override_durable_event_store
    return AsgiTestClient(app)


def _run(awaitable):
    return asyncio.run(awaitable)


def _clip_request() -> dict[str, object]:
    return {
        "channel": "68",
        "started_at": "2026-05-20T19:12:00Z",
        "content_type": "audio/mpeg",
        "idempotency_key": "unique-radio-event",
        "duration_seconds": 12.5,
    }


def _clip_presign(*, channel: str) -> object:
    from talkingboats.schemas import ClipPresignRequest

    return ClipPresignRequest(
        channel=channel,
        started_at="2026-05-20T19:12:00Z",
        ended_at="2026-05-20T19:12:05Z",
        content_type="audio/mpeg",
        idempotency_key=f"radio-event-{channel}",
        duration_seconds=5.0,
    )


def _segment(*, text: str, started_at: str, ended_at: str) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(
        text=text,
        started_at=started_at,
        ended_at=ended_at,
        relative_start_seconds=0.0,
        relative_end_seconds=4.0,
    )
