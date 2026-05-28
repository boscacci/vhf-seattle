# Durable Event Store

The local SQLite databases are still the operational source of truth for live
transcripts and performance history. DynamoDB is now scaffolded in OpenTofu as
the durable event target for the next migration step.

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
  "sk": "event#2026-05-27T20:00:00Z#presigned",
  "event_type": "clip.presigned",
  "environment": "dev",
  "channel": "14",
  "observed_at": "2026-05-27T20:00:00Z"
}
```

Keep raw audio in S3. DynamoDB should store event metadata, analysis pointers,
AIS observations, and telemetry samples, not large transcript or audio blobs.

## Migration Path

1. Apply the dev table with OpenTofu.
2. Add dual-write event publishing from the API/proxy edge while SQLite remains
   authoritative.
3. Backfill existing clip, analysis, AIS, and telemetry records into dev with
   deterministic `pk`/`sk` keys.
4. Build read models from DynamoDB Streams for dashboard queries.
5. Promote the same path to prod only after dev replay and dashboard smoke tests
   are clean.
