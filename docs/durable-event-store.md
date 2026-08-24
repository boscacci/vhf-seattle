# Durable Event Store

DynamoDB is the operational durable store for clip metadata, live transcripts,
and serving read models. SQLite is retained
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
transcripts, segment metadata, analysis pointers, and AIS
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
TALKINGBOATS_CLIP_COUNT_AGGREGATES_ENABLED=false
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

Legacy SQLite clip backfill:

```bash
talkingboats-backfill-durable-events \
  --db-path /home/rob/.local/share/talkingboats/live-transcripts.sqlite3 \
  --table "$(cd infra/opentofu && tofu output -raw dev_radio_events_table_name)" \
  --environment dev \
  --mode both
```

Run `--mode read-model` after the durable events already exist and you only need
to rebuild the DynamoDB serving indexes.

## Stream-maintained clip counts

The public clip API and exporter need a total by channel, quality, featured
state, and queue status. Those totals are materialized in the same table by a
small DynamoDB Streams Lambda rather than issuing a full query for every count
request. The aggregate stores counts and hashed index memberships only: it does
not duplicate transcript text, raw-object keys, or clip payloads.

The consumer follows the existing `clips#transcribed`, `clips#featured`, and
`clip_status#...` indexes. It rereads the current index row before a
conditional transaction, so duplicate, delayed, and overlapping stream records
converge safely. Queue status totals come from the aggregate; the operator
stats endpoint makes only one bounded `Limit=1` query to find the oldest
pending item.

Keep `TALKINGBOATS_CLIP_COUNT_AGGREGATES_ENABLED=false` until a table-specific
backfill is complete. Once enabled, a missing or invalid aggregate returns
`counts_deferred=true`; it intentionally does not fall back to an expensive
full index count.

### Safe rollout

1. Deliver the OpenTofu and application artifact to **dev** through the normal
   CI path. The stream mapping starts at `LATEST`, and its filter accepts only
   the six serving-index partitions used by these counters.
2. Backfill the same dev table using the deployed code. A dry run is safe for
   reviewing scope; the real command writes only aggregate and hashed
   membership items.

   ```bash
   talkingboats-backfill-clip-counts \
     --table "$(cd infra/opentofu && tofu output -raw dev_radio_events_table_name)" \
     --region us-west-2 \
     --dry-run

   talkingboats-backfill-clip-counts \
     --table "$(cd infra/opentofu && tofu output -raw dev_radio_events_table_name)" \
     --region us-west-2
   ```

3. Compare the dev API's visible, featured, quarantined, and queue totals
   before and after enabling the flag. Confirm the aggregate Lambda has no
   errors or iterator lag, then restart the dev API with
   `TALKINGBOATS_CLIP_COUNT_AGGREGATES_ENABLED=true` and run the browser smoke
   suite.
4. Promote the exact dev-tested artifact only through the auditable production
   approval gate. Repeat the table-specific backfill and validation there
   before enabling the production flag.

Rollback is a configuration change back to `false`; no table migration, data
deletion, billing-mode switch, or PITR change is part of this rollout.
