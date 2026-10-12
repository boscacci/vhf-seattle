import json

from talkingboats.queue_channel_indexes import seed_indexes


class Table:
    name = "fixture"

    def __init__(self):
        self.writes = []

    def query(self, **kwargs):
        status = kwargs["ExpressionAttributeValues"][":pk"].split("#")[1]
        return {
            "Items": [
                {"pk": "clip_status#" + status, "sk": channel, "channel": channel}
                for channel in ["14", "74", "68"]
            ],
            "ConsumedCapacity": {"CapacityUnits": 256},
        }

    def batch_writer(self, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def put_item(self, *, Item):
        self.writes.append(Item)


def test_index_cutover_preserves_retained_pending_work_without_mutating_excluded_history(tmp_path):
    table = Table()
    checkpoint = tmp_path / "progress.json"
    first = seed_indexes(table, checkpoint, max_units=256)
    assert not first["complete"]
    assert table.writes == [{"pk": "clip_status#pending#channel#14", "sk": "14", "channel": "14"}]
    resumed = seed_indexes(table, checkpoint)
    assert resumed["complete"]
    assert len(table.writes) == 3
    assert all(row["channel"] == "14" and "#channel#14" in row["pk"] for row in table.writes)
    assert json.loads(checkpoint.read_text())["status_index"] == 3
    assert seed_indexes(table, checkpoint)["complete"] and len(table.writes) == 3
