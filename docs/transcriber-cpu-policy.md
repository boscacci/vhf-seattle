# OptiPlex transcription CPU policy

The i7-9700 has eight physical cores without SMT. The reviewed policy allows
six inference threads and 600% CPU quota: n-2 on this host. Nice=10 and
CPUWeight=25 retain priority for interactive services. This is a ceiling on
aggregate CPU time, not an exclusive reservation or a promise of six-core use.
The installer rejects a different CPU count rather than silently overallocating.

The shared ASR release now installs a continuous-worker override, after legacy
hourly and CPU overrides. It explicitly selects six threads and one model worker,
keeps Turbo loaded, processes up to five clips per poll, and immediately polls
again after progress. When no clips are ready, it sleeps for five seconds. This
bounds idle database polling without delaying uploads until the next hour.
Transcription CPU is idle during that sleep; the loaded model remains in RAM.
The queue drains oldest first across retained channels, preventing newer clips
from starving older recordings. Processing latency still includes any backlog
and model inference time; five seconds is an idle pickup interval, not a promise
that every transcript completes in five seconds.

The release disables the hourly timer and enables the one existing shared service
at login/boot under the user manager. No dev-specific transcriber is created.
Failure restarts wait five seconds; an interrupted clip remains eligible for
processing on restart. Startup telemetry records model, threads, workers, mode,
poll interval and batch limit; each poll records processing and failure counts.
Full audio, beam size five, CPU int8 and quality rules remain unchanged.

Local tuning on October 13, 2026 used six saved recordings totaling 59.35 seconds:
two threads took 72.93 and 76.47 seconds; four took 46.85; six took 41.95.
Three concurrent clips with two threads each took 36.60 seconds, but require
additional safe scheduling and are not enabled. These are small warmed-model
speed probes, exclude database/download/preparation overhead, and do not prove
accuracy equivalence or sustained peak capacity. Six threads are a CPU ceiling,
not an exclusive reservation. Keep API responsiveness and thermal telemetry in
view during rollout.

Use `scripts/release_asr_feedback.sh` to build and deploy the immutable candidate
to dev. After manual dev smoke and the single production approval, promote that
same artifact. The prior worker override and timer/service enablement are
preserved for deployment rollback. The previous hourly CPU-only installer remains
available for historical releases; it is not the continuous-worker release path.

For immediate thermal mitigation of a running process, apply a runtime 200% CPU
quota through systemd. Restoring two inference threads requires a process restart.
The critical temperature is 100 C; monitor sustained temperature and application
responsiveness rather than treating a short benchmark as a thermal soak test.

Missing-upload retries share bounded batches with ready clips: reserve one retry
slot when both exist, so absent objects cannot block the ready queue and retries
still progress. Confirmed vocabulary is refreshed each batch rather than only at
process startup. Production rollback records timer and worker enablement alongside
the previous override. No historical bulk transcription is introduced.
