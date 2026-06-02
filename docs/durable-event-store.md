# Durable Event Store

DynamoDB is the operational durable store for clip metadata, live transcripts,
reviewed transcript corrections, and serving read models. SQLite is retained
only for explicit legacy backfills, local fixture tests, and the separate
realtime performance telemetry ring buffer.

## Tables

OpenTofu defines separate prod and dev event tables:

- `radio_events_table_name`
- `dev_radio_events_table_name`

Both tables use:

- `pk` string hash key
- `sk` string range key
- on-demand billing
- point-in-time recovery
- server-side encryption
- DynamoDB Streams with `NEW_AND_OLD_IMAGES`

## Event Shape

Use append-oriented event records so retries are idempotent:

```json
{
  "pk": "clip#raw/channel=14/date=2026-05-27/example.mp3",
  "sk": "event#clip.presigned#edge-upload-uuid",
  "event_type": "clip.presigned",
  "environment": "dev",
  "channel": "14",
  "observed_at": "2026-05-27T20:00:00Z"
}
```

Keep raw audio in S3. DynamoDB stores clip metadata, status transitions,
transcripts, segment metadata, correction text, analysis pointers, and AIS
observations. Do not store audio bytes, large derived artifacts, or high-rate
performance telemetry samples in DynamoDB.

## Runtime Configuration

Runtime services should use:

```bash
TALKINGBOATS_DURABLE_EVENTS_TABLE="$(cd infra/opentofu && tofu output -raw dev_radio_events_table_name)"
TALKINGBOATS_DURABLE_EVENTS_ENVIRONMENT=dev
TALKINGBOATS_DURABLE_EVENTS_REQUIRED=true
TALKINGBOATS_CLIP_STORE_BACKEND=dynamodb
TALKINGBOATS_TRANSCRIPT_STORE_BACKEND=dynamodb
```

Use `TALKINGBOATS_DURABLE_EVENTS_REQUIRED=false` only during controlled recovery
or backfill work. Normal runtime writes should fail fast if they cannot be
durably recorded.

## Migration Path

1. Keep DynamoDB read models enabled with `TALKINGBOATS_CLIP_STORE_BACKEND` and
   `TALKINGBOATS_TRANSCRIPT_STORE_BACKEND` set to `dynamodb`.
2. Keep durable event writes required in normal runtime service env files.
3. Use SQLite only as an explicit source for one-time backfills or local
   regression fixtures.
4. Promote schema/config changes to prod only after the dev path survives
   restart and dashboard smoke tests.

Legacy SQLite clip and correction backfill:

```bash
talkingboats-backfill-durable-events \
  --db-path /home/rob/.local/share/talkingboats/live-transcripts.sqlite3 \
  --table "$(cd infra/opentofu && tofu output -raw dev_radio_events_table_name)" \
  --environment dev \
  --mode both
```

Run `--mode read-model` after the durable events already exist and you only need
to rebuild the DynamoDB serving indexes.
