# Transcription Queue Capacity Incident — 2026-08-05

Status: remediation validated; bounded production purge and release verification
in progress.

## Summary

The clip transcriber was healthy as a process but unhealthy as a queue consumer.
It processed about 195 clips/hour while the edge produced about 435 clips/hour.
The newest-first policy kept current public clips fresh, masking a historical
backlog that had grown to 521,816 unprocessed records.

Two capacity constraints compounded each other: the CPU worker used the
`large-v3-turbo` Whisper model, and the loop slept for 30 seconds after every
five-record batch even when more work was immediately available.

## Impact

- Historical transcription work accumulated from May 20 through August 5.
- The queue held 521,615 pending, 14 processing, 41 waiting-upload, and 146
  error records at the remediation cutoff.
- Public serving stayed current because the queue intentionally selected newest
  work first; there was no corresponding public clip outage.
- The unbounded historical backlog added DynamoDB storage and query cost and
  left no recovery margin after a host restart or ingest burst.

## Purge boundary

The operator authorized a queue purge. The transcriber and its automatic
restart healthcheck were stopped before the inventory was taken. The fixed
cutoff was `2026-08-05T06:36:00Z`, so clips arriving during remediation remain
eligible for the new worker.

The purge deletes exactly two records for each matching unprocessed clip:

1. its `clip_status#<status>` queue index; and
2. its canonical `clip#<raw-key>` / `state` record.

It does not delete transcribed or empty records, durable event history, public
artifacts, or raw S3 audio. Raw audio continues to use the existing lifecycle
retention policy. The utility is dry-run by default and requires both
`--execute` and an exact `--confirm-table` match for destructive use.

## Model decision

All candidates used faster-whisper CPU `int8`, two CPU threads, one worker,
beam size 5, English, the production hotwords, and the same representative raw
clips. The measured arrival rate was 435 clips/hour; the selection target was
at least 653 clips/hour, providing 1.5 times headroom.

| Model | Clips/hour | Real-time factor | Mean character similarity to turbo |
| --- | ---: | ---: | ---: |
| turbo | 266 | 1.868 | reference |
| small.en | 750 | 0.662 | 0.589 |
| base.en | 1,628 | 0.305 | 0.629 |
| tiny.en | 4,159 | 0.119 | 0.434 |

This initial benchmark used 12 clips / 87 seconds of audio. A deterministic
60-clip validation across channel, duration, and existing-quality strata
confirmed `base.en` at 1,558 clips/hour over 395 seconds of audio, with p50
latency 1.05 seconds and p95 7.97 seconds. It agreed with the persisted turbo
reference on empty versus non-empty output for 57 of 60 clips.

`base.en` was selected because it exceeded observed ingress by 3.58 times in
the larger run and had better transcript agreement than `small.en` in the
direct comparison. `tiny.en` was rejected because its additional speed came
with materially lower reference agreement. Similarity to an earlier model is
not human ground truth; post-release empty and quarantine rates remain canary
signals, and reviewed maritime vocabulary is the appropriate future accuracy
set.

## Remediation and hardening

- Pin clip and live transcription defaults to `base.en`.
- Keep the two-core CPU cap and single worker, avoiding duplicate processing
  under the current read-then-mark claim behavior.
- Poll immediately after any non-empty batch; retain the 30-second delay only
  when the queue is idle.
- Include `next_poll_delay_seconds` in structured poll logs so operators can
  distinguish continuous draining from idle backoff.
- Preserve newest-first selection and the fixed-cutoff purge tool as explicit,
  tested recovery controls.

## Validation, rollback, and follow-up

Regression coverage proves dry-run safety, exact queue/state deletion,
post-cutoff preservation, the `base.en` runtime pin, and busy-versus-idle poll
behavior. Production verification must show the worker model and CPU limits in
its start event, fresh poll events, new clips reaching terminal states, no
failed units, working public audio, and a queue slope below zero during a
backlog drain or near zero when idle.

Rollback is to the prior versioned runtime configuration. Returning to `turbo`
under the same host budget is not a capacity-safe steady state: it may be used
only as a short diagnostic comparison while ingest is bounded or paused.

Add an actionable queue-age/capacity monitor after the current bounded purge.
It should alarm only on sustained growth or stale oldest eligible work and must
remain separate from public-content freshness, which depends on unpredictable
radio traffic.
