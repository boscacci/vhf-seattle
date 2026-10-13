from datetime import UTC, datetime

from talkingboats.transcription_backlog import backlog_history


def test_shared_backlog_sampler_is_cached_bounded_and_keeps_unknown_as_unknown(tmp_path):
    calls = []

    class Store:
        def active_queue_snapshot(self, channels, **kwargs):
            calls.append((channels, kwargs))
            return {
                "complete": True,
                "queued_clips": 8,
                "oldest_started_at": "2026-10-13T00:00:00Z",
            }

    now = datetime(2026, 10, 13, 1, tzinfo=UTC)
    first = backlog_history(Store(), ["14", "74"], tmp_path, now=now)
    again = backlog_history(Store(), ["14", "74"], tmp_path, now=now)
    assert len(calls) == 1
    assert calls[0][0] == ["14"]
    assert first == again
    assert first["queued_clips"] == 8
    assert first["oldest_age_seconds"] == 3600
    assert first["history"][-1]["queuedClips"] == 8


def test_incomplete_backlog_never_becomes_a_zero_sample(tmp_path):
    class Store:
        def active_queue_snapshot(self, channels, **kwargs):
            return {"complete": False, "queued_clips": 0, "oldest_started_at": None}

    result = backlog_history(Store(), ["14"], tmp_path)
    assert result["status"] == "unavailable"
    assert result["queued_clips"] is None
    assert result["history"] == []


def test_queue_measurement_excludes_pruned_channels_and_stops_at_page_budget():
    from talkingboats.dynamo_clip_store import DynamoUploadedClipStore

    class Table:
        def __init__(self):
            self.calls = []

        def query(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "Items": [
                    {"channel": "14", "started_at": "2026-10-13T00:00:00Z"},
                    {"channel": "74", "started_at": "2026-10-12T00:00:00Z"},
                    {"channel": "77", "started_at": "2026-10-12T00:00:00Z"},
                ],
                "LastEvaluatedKey": {"pk": "more", "sk": "more"},
            }

    # Exercise the bounded measurement independently of unrelated store setup.
    store = object.__new__(DynamoUploadedClipStore)
    store.table = Table()
    result = store.active_queue_snapshot(["14"], max_pages=2, indexed_channels=True)
    assert result["complete"] is False
    assert result["queued_clips"] == 2
    assert result["oldest_started_at"] == "2026-10-13T00:00:00Z"
    assert len(store.table.calls) == 2
    assert all(c["ConsistentRead"] for c in store.table.calls)


def test_backlog_history_expires_after_seven_days(tmp_path):
    from datetime import timedelta

    class Store:
        def active_queue_snapshot(self, channels, **kwargs):
            return {"complete": True, "queued_clips": 1, "oldest_started_at": None}

    now = datetime(2026, 10, 13, 1, tzinfo=UTC)
    backlog_history(Store(), ["14"], tmp_path, now=now)
    later = backlog_history(Store(), ["14"], tmp_path, now=now + timedelta(days=8))
    assert len(later["history"]) == 1
