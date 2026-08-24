# Public Clip Freshness False Positive — 2026-08-04

Status: remediation implemented and validated; production promotion requires
the normal approval control or an explicitly authorized break-glass apply.

## Summary

At 09:47:07 UTC (02:47:07 PDT), CloudWatch emailed that
`talkingboats-talkingboats-prod-public-clips-stale` had entered `ALARM`. The
newest publishable clip was 3,840 seconds old, just beyond the one-hour
threshold. The alarm returned to `OK` at 10:22:07 UTC after a new publishable
clip appeared.

The station was not offline. The alert measured the age of content produced by
unpredictable marine-radio speech and treated a single breaching sample as a
service failure. This was the third short false positive since August 2.

## Impact

- One overnight `ALARM` email and one recovery email interrupted the operator.
- No public availability, ingest, transcription, publishing, live audio, or AIS
  outage occurred.
- Repeated false positives reduced the usefulness of a monitor that had
  correctly detected the July 31 Pi outage.

## Evidence

During 08:30–10:30 UTC, spanning the entire alarm:

- the Pi made 1,360 successful clip-presign requests; the first observed request
  was at 08:31:43 and the last at 10:29:51;
- the transcriber completed 75 polls and continued processing clips;
- every scheduled 15-minute public publisher run completed and promoted its
  dev-validated output;
- `LatestAisMessageAgeSeconds` remained between 0 and 2.1 seconds;
- `LatestPublicClipAgeSeconds` rose naturally to 5,640 seconds and reset when a
  new publishable transmission appeared; and
- CloudWatch reported the alarm as `OK` after recovery, with no missing monitor
  datapoints.

Current validation on August 5 also proved fresh clips, fresh AIS, reachable Pi
ports 22/8000/8050/8100, active edge and OptiPlex units, successful API health,
working clip audio, and a passing production browser SLO.

## Root cause

The alarm conflated two different questions:

1. Has a publishable transmission occurred recently?
2. Is the station and publishing pipeline healthy?

Only the second question is actionable. A one-hour gap in valid speech is
normal overnight, but the metric alarm was configured as one out of one
datapoints with both `ALARM` and `OK` email actions. The metric and threshold
worked as configured; the paging policy was semantically wrong.

## Remediation

The hardening separates content telemetry from health paging:

- `LatestPublicClipAgeSeconds` and its one-hour alarm remain visible, but that
  diagnostic alarm has actions disabled.
- The monitor now emits `PublicManifestAgeSeconds` from
  `public_manifest.json.generated_at`. A new action-enabled alarm requires a
  one-hour publisher stall for three consecutive five-minute samples.
- The action-enabled AIS heartbeat alarm requires three consecutive samples at
  least 15 minutes old. Missing monitor data is breaching there because the
  same Lambda emits all three metrics in one call.
- The publisher alarm treats missing data as non-breaching to avoid duplicate
  emails when the shared monitor fails; the AIS alarm owns that failure mode.
- Both paging alarms retain recovery notifications and the same confirmed SNS
  operator subscription.

This design continues to expose radio-content gaps, detects a stalled public
publisher without relying on speech, and detects a Pi/AIS or monitor outage
more quickly than the former one-hour single-sample alarm.

## Additional boot-health finding

The Pi's radio services were healthy, but `systemd` had remained in `starting`
since the August 1 reboot. An obsolete Raspberry Pi first-run `userconfig`
dialog was blocked on an unattended TTY while the already-configured `rob`
account was active. The service was stopped and disabled, its failed state was
cleared, and the queued cloud-init and apt jobs completed. The Pi then reported
`running`, no jobs, no failed units, and all TalkingBoats services active.

## Validation and rollback

Regression tests cover manifest-heartbeat parsing, missing or invalid
timestamps, metric publication, non-paging content telemetry, sustained
publisher paging, and sustained AIS paging. OpenTofu formatting and validation
pass, and the scoped plan is one alarm create plus four in-place updates with
no destroys.

Rollback is to restore actions on the clip-content alarm, remove the manifest
alarm and metric, and restore the AIS threshold to one hour. That rollback is
not recommended because it recreates the verified false-positive condition.

## Residual capacity risks

The current-serving path is fresh because the transcriber processes newest
items first, but the historical transcription queue is not healthy. A bounded
status-index query found 520,851 pending records, with the oldest from May 20.
Over a representative hour the edge added 435 records while the transcriber
processed 195, so the historical queue is growing even though current clips
continue to appear. There were 15 processing, 41 waiting-upload, and 145 error
records; sampled errors were invalid MP3 inputs.

No queued records were deleted or reclassified during this incident. Safe
remediation needs a separate retention decision and either a benchmarked
single-worker throughput change or an atomic lease/claim mechanism before
adding concurrent workers. Running duplicate workers against the current
read-then-mark queue would risk duplicate transcription.

The OptiPlex root filesystem is 89% used with 26 GiB free and only 17% of
inodes used. TalkingBoats generated outputs account for about 141 MiB, so this
incident did not delete unrelated repositories, caches, or media to manufacture
free space. Capacity is adequate now but should be cleaned up through the
host's broader storage-retention workflow.
