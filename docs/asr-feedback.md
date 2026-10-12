# Radio selection and reviewed transcription

The audited profile retains VHF **14, 13, 16, 66A, 78A, and 71**. VHF 74 is
excluded from public clips, playback, search, exports, and analysis. Other pruned
channels retain searchable historical clips. Receiver pruning preserves the
retained channels' exact frequency, squelch, gain, serial, and output settings.
Excluded DynamoDB queue entries and local spool files are retained; fresh
uploads use channel-specific processing indexes without scanning that backlog.
Production cutover adds indexes for existing retained-channel pending work,
without changing legacy queue entries or transcribing anything during migration.
This index-only migration has a resumable private checkpoint, a 90-second
window, and a 20,000-read-capacity-unit ceiling per invocation. A bounded pause
blocks cutover; retrying the same approved artifact resumes it.

## Measured capacity

`config/channel-selection.json` records the October 5–11, 2026 Pacific-time raw
upload inventory, clip-state durations, quality coverage, hourly audio load,
and Turbo timings. The audit counted 43,193 uploads. Quality is a persisted
proxy rather than human intelligibility or true RF SNR; silence-floor contrast
measurements are excluded. Counts include untranscribed uploads.

Eight channels needed 5,400 processing seconds during the busiest measured
hour; six needed 4,449. Neither meets the 2,400-second limit for 1.5 times
headroom. The operator explicitly requested Turbo despite this peak constraint.
The six-channel release therefore selects `large-v3-turbo`, with temporary
backlog allowed. The busiest sampled Pacific day requires 40,342 processing
seconds (11.2 hours); an empty-queue hourly replay clears its modeled peak
backlog of 849 processing seconds in the following hour. These forecasts exclude
existing backlog, startup costs, hourly invocation limits, and other host load.
`recovery_forecast` records the reproducible estimate; inspect actual queue age
after activation to confirm recovery. The stricter 1.5-times capacity criterion
still applies to fine-tuned candidate eligibility. The benchmark used ten
seeded recordings per channel, CPU int8, two threads, one worker, beam size 5,
and full audio without VAD. These sample-based estimates should be repeated
when hardware or capture conditions change. Seventy rounded timing events were
recovered after a task-created training clone exhausted system disk space;
the recorded times include a conservative rounding allowance. Training now
uses an isolated, pinned CPU-only environment on the data
volume instead of duplicating the CUDA serving environment. The installed data
SSD is the configured home for model caches, reviewed datasets, checkpoints,
and temporary experiment files. A missing data mount prevents job startup;
later deployments preserve this storage choice.

## Corrections and experiments

On dev, open a clip's **Correct transcript** editor. Saving or restoring text
updates the shared correction overlay immediately; there is no per-edit
approval gate. Original predictions and revision history remain intact.
Only the tailnet operator proxy can write, using a private server-to-server
credential. Public browsers receive corrected text without label notes,
embeddings, original predictions, object keys, or training metadata.

Incomplete edits help the displayed transcript. For training, mark every word
reviewed against intelligible audio. Clips longer than 30 seconds need a
selected range and a separate exact range transcript; the full corrected
transcript remains the public text. Enter confirmed names/places/call signs
from that range as comma-separated terms. Reviewed audio is copied into the
private `asr-feedback/audio/` prefix before it can count toward readiness.
Archival failures remain pending and appear in the operator journal; retry the
same saved revision to retry archival. Audio retention is bounded to 5 GiB and
25 MiB per file; labels are bounded to 2,000 active records.

In **Performance → Transcription experiments**, use the diverse review queue
and inspect minutes, vocabulary, and effort. Stable Pacific recording-day
splits keep related channels together. Reviewed ranges in the 30 minutes before
or after Pacific midnight, or crossing their original recording day, remain
display-only and never enter training or vocabulary hints. This conservative
buffer keeps short exchanges around midnight from straddling dataset splits. Training hints come only from reviewed
training labels; validation/test text and terms never become training hints.
Experiments require 30 training minutes, five validation minutes, five test
minutes, and 50 annotated test mentions. New dataset/configuration fingerprints
start new runs; unchanged requests reuse completed runs. Failed/interrupted
runs resume retained checkpoints through the same request.

Prepare the immutable representative capacity samples from the completed audit
before the first experiment:

```bash
PYTHONPATH=src conda run -n dell python -m talkingboats.capacity_benchmark \
  --selection config/channel-selection.json --audit-work outputs/channel-audit \
  --storage /path/to/owned/data-volume/asr
```

Every candidate repeats the full-audio benchmark on the same ten audited
recordings per retained channel; reviewed test ranges alone cannot establish
capacity. The dataset/audio hashes and hourly workload identity are pinned to
each run. Missing capacity proof keeps a candidate ineligible. Benchmark timing
checkpoints are reused after interruption. The one-core experiment limit makes
this capacity check conservative for the two-thread serving path.

The local worker freezes encoder/base weights and trains decoder LoRA attention
adapters. It evaluates plain Turbo, Turbo with hints, and merged/converted int8
candidates. Promotion eligibility requires at least 10% fewer entity omissions,
no more known-name insertions, at most one percentage point worse overall word
error, and 1.5 times workload headroom. Insertion metrics cover the annotated
vocabulary, not every possible hallucinated name. Estimated word edits show
correction effort per model; timed manual correction effort is reported
separately. Validation/test annotations can define scoring vocabulary but
never enter inference hints. Eligibility never promotes
weights automatically. Review example playback before requesting adoption. Experiment playback uses
the immutable dataset’s private reviewed audio, including after normal raw
audio expiry, and labels/plays the exact range that was evaluated.

Each job has one CPU core, 12 GiB RAM, and a two-hour limit. It checkpoints every
20 optimizer updates, keeps two training checkpoints, and preserves failed
runs. Twenty runs and 20 GiB of local artifacts are the initial storage bounds;
new runs are refused above 16 GiB to leave room for the next candidate.
No automatic nightly training or historical bulk retranscription occurs.

## Release and rollback

Run the checked-in setup script to install the pinned CPU-only training environment:

```bash
scripts/setup_asr_training.sh
```

From a clean reviewed commit, build once and deliver to dev:

```bash
scripts/release_asr_feedback.sh build
TALKINGBOATS_ASR_STORAGE_ROOT=/path/to/owned/data-volume/asr scripts/release_asr_feedback.sh dev
```

The script preserves an existing storage choice on later releases, configures a
mode-0600 operator credential, deploys only dev API/proxy services, installs the
on-demand worker, and runs Playwright. Smoke writes use isolated fixtures;
real dev channel/status/readiness reads and first audio bytes from every retained feed and a separate real DynamoDB fixture
probe validate the deployed boundaries without changing corpus labels.

Merge to the protected default branch after required checks, then deliver and
smoke that exact default-branch candidate. Cut an annotated immutable semver tag
on it. After a human manually smoke-tests dev, record exactly one approval:

```json
{
  "approval_kind": "human",
  "approved_by": "operator identity",
  "approved_at": "ISO-8601 timestamp with offset",
  "dev_manually_smoke_tested": true,
  "release_tag": "vMAJOR.MINOR.PATCH",
  "commit": "full dev-tested commit",
  "artifact_sha256": "dev-tested artifact digest",
  "environment": "prod"
}
```

Then `scripts/release_asr_feedback.sh prod TAG APPROVAL.json` verifies that record
and promotes the existing artifact, including shared Pi capture and worker
changes. It does not rebuild. Generated exports and the correction overlay
subsequently update through normal application paths.

Dev failures restore prior service drop-ins and the release symlink. Production
records previous runtime source and receiver files for rollback. Roll back to a
previous dev-tested release through the same one-approval production gate.
Never delete raw audio, queue history, or reviewed examples as a rollback step.
