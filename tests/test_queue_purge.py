from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime

from talkingboats.queue_purge import purge_clip_queue

CUTOFF = datetime(2026, 8, 5, 6, 36, tzinfo=UTC)


def test_queue_purge_dry_run_counts_without_deleting() -> None:
    table = FakeTable([_queue_item("pending", "2026-08-05T06:35:00Z", "old.mp3")])

    summary = purge_clip_queue(table=table, cutoff=CUTOFF)

    assert summary.matched == {
        "pending": 1,
        "processing": 0,
        "waiting_upload": 0,
        "error": 0,
    }
    assert summary.deleted_items == 0
    assert table.deleted == []


def test_queue_purge_execute_deletes_only_queue_index_and_canonical_state() -> None:
    item = _queue_item("processing", "2026-08-05T06:34:00Z", "clip.mp3")
    table = FakeTable([item])

    summary = purge_clip_queue(table=table, cutoff=CUTOFF, execute=True)

    assert summary.matched["processing"] == 1
    assert summary.deleted_items == 2
    assert table.deleted == [
        {"pk": "clip_status#processing", "sk": item["sk"]},
        {"pk": "clip#clip.mp3", "sk": "state"},
    ]


def test_queue_purge_defensively_skips_records_after_cutoff() -> None:
    table = FakeTable([_queue_item("pending", "2026-08-05T06:37:00Z", "new.mp3")])

    summary = purge_clip_queue(table=table, cutoff=CUTOFF, execute=True)

    assert summary.matched["pending"] == 0
    assert summary.skipped_after_cutoff == 1
    assert table.deleted == []


class FakeTable:
    def __init__(self, items: list[dict[str, str]]) -> None:
        self.items = items
        self.deleted: list[dict[str, str]] = []

    def query(self, **kwargs):
        status_pk = kwargs["ExpressionAttributeValues"][":pk"]
        return {"Items": [item for item in self.items if item["pk"] == status_pk]}

    def batch_writer(self, **_kwargs):
        return nullcontext(self)

    def delete_item(self, *, Key):
        self.deleted.append(Key)


def _queue_item(status: str, started_at: str, key: str) -> dict[str, str]:
    return {
        "pk": f"clip_status#{status}",
        "sk": f"{started_at}#{key}",
        "key": key,
        "status": status,
        "started_at": started_at,
    }
