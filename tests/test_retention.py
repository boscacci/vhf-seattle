from __future__ import annotations

from talkingboats.clip_transcriber import RecentTranscribedClip
from talkingboats.retention import tag_raw_audio_retention


def test_tag_raw_audio_retention_marks_starred_true_and_other_raw_false() -> None:
    storage = FakeRetentionStorage(
        [
            "raw/channel=14/date=2026-05-20/featured.mp3",
            "raw/channel=14/date=2026-05-20/ordinary.mp3",
        ]
    )
    store = FakeFeaturedStore(["raw/channel=14/date=2026-05-20/featured.mp3"])

    result = tag_raw_audio_retention(storage=storage, clip_store=store, page_size=2)

    assert result == {
        "raw_object_count": 2,
        "featured_key_count": 1,
        "tagged_featured_count": 1,
        "tagged_unfeatured_count": 1,
        "dry_run": False,
    }
    assert storage.tagged == [
        ("raw/channel=14/date=2026-05-20/featured.mp3", True),
        ("raw/channel=14/date=2026-05-20/ordinary.mp3", False),
    ]


def test_tag_raw_audio_retention_dry_run_reports_without_writing() -> None:
    storage = FakeRetentionStorage(["raw/channel=14/date=2026-05-20/ordinary.mp3"])
    store = FakeFeaturedStore([])

    result = tag_raw_audio_retention(storage=storage, clip_store=store, dry_run=True)

    assert result["raw_object_count"] == 1
    assert result["tagged_unfeatured_count"] == 1
    assert result["dry_run"] is True
    assert storage.tagged == []


class FakeRetentionStorage:
    def __init__(self, keys: list[str]) -> None:
        self.keys = keys
        self.tagged: list[tuple[str, bool]] = []

    def iter_raw_audio_keys(self, *, prefix: str = "raw/"):
        return (key for key in self.keys if key.startswith(prefix))

    def tag_raw_clip_featured(self, key: str, *, featured: bool) -> None:
        self.tagged.append((key, featured))


class FakeFeaturedStore:
    def __init__(self, featured_keys: list[str]) -> None:
        self.featured_keys = featured_keys

    def recent_transcribed(
        self,
        *,
        limit: int,
        offset: int = 0,
        featured_only: bool = False,
        **_kwargs: object,
    ) -> list[RecentTranscribedClip]:
        assert featured_only is True
        return [
            RecentTranscribedClip(
                key=key,
                channel="14",
                started_at="2026-05-20T19:12:00Z",
                ended_at=None,
                duration_seconds=2.0,
                content_type="audio/mpeg",
                transcript="Featured transcript.",
                transcript_reviewed=False,
                featured=True,
                featured_at="2026-05-21T19:12:00Z",
                segments=[],
            )
            for key in self.featured_keys[offset : offset + limit]
        ]
