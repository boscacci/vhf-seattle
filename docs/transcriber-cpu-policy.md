# OptiPlex transcription CPU policy

The i7-9700 has eight physical cores without SMT. The reviewed policy allows
six inference threads with a **300% CPU quota**: at most three cores’ worth of
aggregate CPU time on this host. Nice=10 and CPUWeight=10 favor competing
interactive services. The thread count stays six to avoid changing model
execution during the runtime adjustment; the aggregate quota bounds their total
CPU use. This is a ceiling, not an exclusive reservation or CPU affinity rule.
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
accuracy equivalence or sustained peak capacity. Those historic six-thread timings used the higher CPU budget and do not
establish performance under the new 300% quota. Keep API responsiveness and thermal telemetry in
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

## Gentle operating budget

The October 16 adjustment halves the CPU ceiling from 600% to 300% and lowers
CPUWeight from 25 to 10. A runtime systemd property change can apply these limits
without restarting the shared worker or interrupting a clip. Such an adjustment
uses a late runtime drop-in so daemon reloads retain the limit. It lasts until
reboot or an explicit operator change; the checked-in release drop-ins carry
the same defaults for subsequent approved releases. The existing model, six
threads, one worker, five-second idle polling, SSD, and recording policy remain
unchanged. CPU quota may lengthen individual transcriptions and allow a small
queue, which is acceptable while its age remains bounded and it drains again.

Observe queue age and volume alongside CPU use after tuning; near-zero queue
samples alone do not prove peak-hour capacity. Record old and new limits and
observations privately under the existing operator state directory. To undo a
runtime adjustment, restore that record’s prior CPUQuota and CPUWeight through
the checked-in `scripts/set_transcriber_cpu_runtime.sh release-default` command;
no receiver restart is needed. Use its `gentle` action to apply the lower budget.
A bare `systemctl set-property --runtime` creates early `50-*` drop-ins, which
can be overridden by later installed release files during daemon reload.
