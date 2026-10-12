"""Resumable index-only cutover; preserve active pending work and excluded backlog."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import boto3

from talkingboats.asr_experiments import atomic_json
from talkingboats.channel_metadata import ACTIVE_CAPTURE_CHANNELS

STATUSES = ("pending", "waiting_upload", "processing")


def seed_indexes(table, checkpoint: Path, *, max_units=20000, max_seconds=90):
    progress = (
        json.loads(checkpoint.read_text())
        if checkpoint.exists()
        else {
            "status_index": 0,
            "cursor": None,
            "indexed": 0,
            "channels": list(ACTIVE_CAPTURE_CHANNELS),
            "table_name": getattr(table, "name", None),
        }
    )
    if progress["channels"] != list(ACTIVE_CAPTURE_CHANNELS) or progress.get(
        "table_name"
    ) != getattr(table, "name", None):
        raise ValueError("queue migration belongs to a different selected profile")
    units = 0
    began = time.monotonic()
    while progress["status_index"] < len(STATUSES):
        if units + 256 > max_units:
            break  # One DynamoDB query page is at most 1 MiB (256 consistent RCUs).
        status = STATUSES[progress["status_index"]]
        query = dict(
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": "clip_status#" + status},
            ConsistentRead=True,
            Limit=250,
            ReturnConsumedCapacity="TOTAL",
        )
        if progress["cursor"]:
            query["ExclusiveStartKey"] = progress["cursor"]
        response = table.query(**query)
        units += float(response.get("ConsumedCapacity", {}).get("CapacityUnits", 0))
        with table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
            for item in response.get("Items", []):
                if item.get("channel") in ACTIVE_CAPTURE_CHANNELS:
                    # Only a derived index is added. The legacy index and source state stay intact.
                    batch.put_item(
                        Item={**item, "pk": f"clip_status#{status}#channel#{item['channel']}"}
                    )
                    progress["indexed"] += 1
        progress["cursor"] = response.get("LastEvaluatedKey")
        if not progress["cursor"]:
            progress["status_index"] += 1
        atomic_json(checkpoint, progress)
        if units >= max_units or time.monotonic() - began >= max_seconds:
            break
    return {
        **progress,
        "complete": progress["status_index"] == len(STATUSES),
        "read_capacity_units": units,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()
    table = boto3.resource("dynamodb", region_name="us-west-2").Table(args.table)
    result = seed_indexes(table, args.checkpoint)
    print(
        json.dumps(
            {
                "event": "asr_queue_indexes_seeded",
                "complete": result["complete"],
                "indexed": result["indexed"],
                "read_capacity_units": result["read_capacity_units"],
            }
        )
    )
    if not result["complete"]:
        raise SystemExit(
            "bounded migration stopped safely; retry this release to resume its checkpoint"
        )


if __name__ == "__main__":
    main()
