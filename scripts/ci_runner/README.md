# Self-hosted CI runner: orphan cleanup hook

The compliance and portal repositories run CI on self-hosted GitHub Actions
runners that share one host (and one `ghrunner` account) with the lab's
OpenShift VM. A cancelled or lost job can leave a step's child process running
with no parent; the runner's systemd units use `KillMode=process`, so nothing
reaps it. On 2026-10-16 an orphaned `opa test` held 8 GiB for 5.5 hours, the
host ran out of swap, and later jobs took hours or failed with "the
self-hosted runner lost communication with the server".

`cleanup-orphans.sh` runs at the start and end of every job and kills
processes that an earlier job of the **same** runner left behind: owned by the
runner user, re-parented to PID 1, with a working directory inside that
runner's `_work` tree. Processes of the other runners on the host, and
anything outside `_work` (container `conmon`s, user services), are left alone.
It makes several passes, because killing an orphan re-parents its children.

## Install (per host)

```bash
sudo install -d -o root -g root -m 755 /opt/actions-runners/hooks
sudo install -o root -g root -m 755 cleanup-orphans.sh /opt/actions-runners/hooks/cleanup-orphans.sh
for r in /opt/actions-runners/*/; do
  [ -f "$r/.env" ] || continue
  sudo grep -q '^ACTIONS_RUNNER_HOOK_JOB_STARTED=' "$r/.env" || echo 'ACTIONS_RUNNER_HOOK_JOB_STARTED=/opt/actions-runners/hooks/cleanup-orphans.sh' | sudo tee -a "$r/.env"
  sudo grep -q '^ACTIONS_RUNNER_HOOK_JOB_COMPLETED=' "$r/.env" || echo 'ACTIONS_RUNNER_HOOK_JOB_COMPLETED=/opt/actions-runners/hooks/cleanup-orphans.sh' | sudo tee -a "$r/.env"
done
```

Restart each runner service **while it is idle** (the runner reads `.env` at
start; a restart mid-job kills the job). Each job log then shows an
"orphan cleanup:" line in its set-up and complete steps.

Every self-hosted job in `.github/workflows/` also carries `timeout-minutes`,
so a stuck job is ended by GitHub rather than holding the runner.
