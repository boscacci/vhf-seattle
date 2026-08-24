# Service Level Objectives

These SLOs guard the live public experience beyond unit tests. They are intended
to run against Dev after every deploy and before promoting to prod.

## Public clip freshness

- A newest-clip age above one hour remains a visible CloudWatch diagnostic,
  but it does not page. Publishable speech depends on real radio traffic, so
  content age alone is not a reliable service-health signal.
- `talkingboats-public-clip-refresh.timer` publishes a dev-validated export
  every 15 minutes.
- The independent AWS monitor samples the newest clip, manifest generation,
  and AIS generation timestamps every five minutes.
- Operator email is reserved for actionable pipeline health: the public
  manifest must remain less than one hour old for three consecutive samples,
  while the AIS heartbeat must remain less than 15 minutes old for three
  consecutive samples. Missing monitor data is handled by the AIS alarm.
- During diagnosis, inspect both the manifest `generated_at` heartbeat and the
  newest clip `ended_at`. A fresh manifest with an older newest clip means the
  publisher is healthy and the radio has been quiet.

## Public Listen Live

Run:

```bash
npm run slo:dev
```

Default target:

```bash
TALKINGBOATS_SLO_BASE_URL=https://dev.seattleboatradio.com npm run slo:dev
```

Objectives:

- Recent queue API p95: `<= 1500 ms` for five cache-busted samples.
- All-but-traffic queue API p95: `<= 1500 ms` for five cache-busted samples.
- Cursor load-more API p95: `<= 1500 ms` for five cache-busted second batches.
- Oldest queue API p95: `<= 1500 ms` for five cache-busted samples using
  `sort=oldest`.
- Mobile Clip Review first card, including a cold browser cache: `<= 2000 ms`.
- Clip Review 24-to-48 load-more interaction: `<= 3000 ms`.
- Clip Review oldest-batch click-to-rendered cards: `<= 2000 ms`.
- Clip Review all-but-traffic preset click-to-rendered non-traffic cards:
  `<= 2000 ms`.
- All-but-traffic selector visible after entering Listen live: `<= 2000 ms`.
- All-but-traffic click-to-queued-audio state: `<= 2000 ms`.
- No browser console or page errors during the mobile flow.

The all-but-traffic Clip Review and Listen live paths must use the global
recent clip index with
`exclude_channels=14`, not a fanout of `channels=` query parameters.
Infinite loading must use the opaque `next_cursor`, not page numbers or deep
offsets. The oldest path must begin a new cursor sequence with `sort=oldest`.
Datetime navigation uses `around=<ISO 8601 datetime>`. Values without an offset
are Pacific wall time (`America/Los_Angeles`); `sort=newest` starts at or before
that instant and `sort=oldest` starts at or after it. The datetime and channel
filters are part of the cursor binding, and DynamoDB reads must use sort-key
bounds rather than walking forward from the newest clip.

## Threshold Overrides

Use overrides only when intentionally changing the SLO target:

```bash
TALKINGBOATS_SLO_RECENT_API_P95_MS=1500 \
TALKINGBOATS_SLO_LOAD_MORE_API_P95_MS=1500 \
TALKINGBOATS_SLO_OLDEST_API_P95_MS=1500 \
TALKINGBOATS_SLO_MOBILE_CLIP_READY_MS=2000 \
TALKINGBOATS_SLO_LOAD_MORE_READY_MS=3000 \
TALKINGBOATS_SLO_OLDEST_BATCH_READY_MS=2000 \
TALKINGBOATS_SLO_CLIP_ALL_BUT_TRAFFIC_READY_MS=2000 \
TALKINGBOATS_SLO_ALL_BUT_TRAFFIC_SELECTOR_READY_MS=2000 \
TALKINGBOATS_SLO_ALL_BUT_TRAFFIC_QUEUE_READY_MS=2000 \
npm run slo:dev
```
