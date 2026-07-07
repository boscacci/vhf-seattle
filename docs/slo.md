# Service Level Objectives

These SLOs guard the live public experience beyond unit tests. They are intended
to run against Dev after every deploy and before promoting to prod.

## Public Live Monitor

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
- Page-five recent API p95: `<= 1500 ms` for five cache-busted samples using
  `page=5`.
- Oldest queue API p95: `<= 1500 ms` for five cache-busted samples using
  `sort=oldest`.
- Mobile Clip Review first card: `<= 5000 ms`.
- Clip Review page-five click-to-rendered cards: `<= 3000 ms`.
- Clip Review oldest-page click-to-rendered cards: `<= 3000 ms`.
- Clip Review all-but-traffic preset click-to-rendered non-traffic cards:
  `<= 3000 ms`.
- All-but-traffic selector visible after entering Live Monitor: `<= 2000 ms`.
- All-but-traffic click-to-queued-audio state: `<= 3000 ms`.
- No browser console or page errors during the mobile flow.

The all-but-traffic Clip Review and Live Monitor paths must use the global
recent clip index with
`exclude_channels=14`, not a fanout of `channels=` query parameters.
Numbered pagination must use `page=N`, not deep offsets. The oldest-page path
must use `sort=oldest&page=1`.

## Threshold Overrides

Use overrides only when intentionally changing the SLO target:

```bash
TALKINGBOATS_SLO_RECENT_API_P95_MS=1500 \
TALKINGBOATS_SLO_PAGE_FIVE_API_P95_MS=1500 \
TALKINGBOATS_SLO_OLDEST_API_P95_MS=1500 \
TALKINGBOATS_SLO_MOBILE_CLIP_READY_MS=5000 \
TALKINGBOATS_SLO_PAGE_FIVE_READY_MS=3000 \
TALKINGBOATS_SLO_OLDEST_PAGE_READY_MS=3000 \
TALKINGBOATS_SLO_CLIP_ALL_BUT_TRAFFIC_READY_MS=3000 \
TALKINGBOATS_SLO_ALL_BUT_TRAFFIC_SELECTOR_READY_MS=2000 \
TALKINGBOATS_SLO_ALL_BUT_TRAFFIC_QUEUE_READY_MS=3000 \
npm run slo:dev
```
