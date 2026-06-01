# Durable Event Store

The local SQLite databases are still the operational read model for live
transcripts and performance history. DynamoDB is the durable append-only event
store and is the migration path away from the OptiPlex SQLite database as a
single point of failure.

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
transcripts, segment metadata, correction text, analysis pointers, AIS
observations, and telemetry samples. Do not store audio bytes or large derived
artifacts in DynamoDB.

## Runtime Configuration

Enable the dual-write path with:

```bash
TALKINGBOATS_DURABLE_EVENTS_TABLE="$(cd infra/opentofu && tofu output -raw dev_radio_events_table_name)"
TALKINGBOATS_DURABLE_EVENTS_ENVIRONMENT=dev
TALKINGBOATS_DURABLE_EVENTS_REQUIRED=false
```

`false` is intentional for the first rollout: SQLite remains the serving read
model while DynamoDB events are verified. Once the backfill and dashboard read
model are clean, set `TALKINGBOATS_DURABLE_EVENTS_REQUIRED=true` so new clip
writes fail fast if they cannot be durably recorded.

## Migration Path

1. Apply the dev table with OpenTofu.
2. Enable dual-write event publishing from the private API and uploaded-clip
   transcriber while SQLite remains the read model.
3. Backfill existing clip, correction, analysis, AIS, and telemetry records into
   dev with deterministic `pk`/`sk` keys.
4. Build read models from DynamoDB Streams for dashboard queries.
5. Flip durable writes to required mode after dev replay and dashboard smoke
   tests are clean.
6. Promote the same path to prod only after the dev path survives restart and
   recovery testing.
