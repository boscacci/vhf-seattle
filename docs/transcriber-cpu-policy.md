# OptiPlex transcription CPU policy

The i7-9700 has eight physical cores without SMT. The reviewed policy allows
six inference threads and 600% CPU quota: n-2 on this host. Nice=10 and
CPUWeight=25 retain priority for interactive services. This is a ceiling on
aggregate CPU time, not an exclusive reservation or a promise of six-core use.
The installer rejects a different CPU count rather than silently overallocating.

An explicit `--cpu-threads 6` overrides any older value in the shared environment
file. One worker, the hourly schedule, and `--once --limit 1000` remain intact.
Installation reloads systemd without restarting a running batch. The new thread
count takes effect at the next launch. Existing processes cannot resize their
Whisper thread pools through a systemd configuration reload.

CI tests the configuration installer, archives the reviewed main commit, deploys
dev automatically and runs browser smoke. Select an annotated `transcriber/vX.Y.Z`
tag and dispatch the CPU-policy workflow from main; the protected production
job uses the same digest. Dev does not run an extra worker against production
clips. After rollout, verify `cpu_threads: 6` in the next batch startup event,
observe CPU usage and temperatures under load, and confirm fresh AIS/API output.
The pre-change CPU temperature was already 88 C during simultaneous Plex and
transcription. More threads may finish work faster but can raise sustained heat;
if temperatures approach the sensor's 100 C critical value, restore the previous
quota immediately and investigate cooling before retaining the higher budget.

The installer retains the previous override or an absence marker under
`~/.local/share/talkingboats/releases/transcriber-cpu/COMMIT/`. To revert, restore
that saved override (or remove only `zzz-cpu-budget.conf` if previously absent)
and reload the user systemd manager. The existing 200% base quota then applies;
use `systemctl --user set-property --runtime talkingboats-uploaded-clip-transcriber.service CPUQuota=200%`
for immediate thermal mitigation of an already-running process. Six-thread
processes return to two threads on their next launch after rollback.
