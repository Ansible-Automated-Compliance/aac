#!/bin/bash
# GitHub Actions runner job hook (ACTIONS_RUNNER_HOOK_JOB_STARTED / _COMPLETED).
#
# Kills processes an EARLIER job of THIS runner left behind. A cancelled or
# lost job can leave a step's child running with no parent: on 2026-10-16 an
# orphaned `opa test` held 8 GiB for 5.5 hours and pushed this host into swap,
# which starved every later job. Three runners share the ghrunner account, so
# only processes that are orphaned (parent is PID 1), owned by the runner user,
# and whose working directory is inside THIS runner's _work tree are touched.
# A runner runs one job at a time, so at job start and job end nothing in its
# own _work tree is legitimately running without a parent.
set -u
WORK="${RUNNER_TEMP:+${RUNNER_TEMP%/_temp}}"
if [ -z "$WORK" ]; then   # fall back to the runner install this hook runs under
  exe=$(readlink -f /proc/$PPID/exe 2>/dev/null || true)
  WORK="${exe%/bin/*}/_work"
fi
case "$WORK" in /opt/actions-runners/*/_work) ;; *) echo "orphan cleanup: unexpected work dir '$WORK', skipping"; exit 0 ;; esac
me=$(id -un); found=0
# Several passes: killing an orphan re-parents ITS children to PID 1, and they
# are only orphans on the next scan.
for pass in 1 2 3 4 5; do
  victims=()
  for p in $(pgrep -u "$me"); do
    [ "$p" = "$$" ] && continue
    [ "$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')" = "1" ] || continue
    cwd=$(readlink "/proc/$p/cwd" 2>/dev/null) || continue
    case "$cwd/" in "$WORK"/*) victims+=("$p") ;; esac
  done
  [ ${#victims[@]} -eq 0 ] && break
  found=1
  for p in "${victims[@]}"; do echo "orphan cleanup: TERM $p $(ps -o etime=,rss=,args= -p "$p" | cut -c1-120)"; done
  kill -TERM "${victims[@]}" 2>/dev/null; sleep 5
  for p in "${victims[@]}"; do kill -0 "$p" 2>/dev/null && { echo "orphan cleanup: KILL $p"; kill -KILL "$p" 2>/dev/null; }; done
done
[ $found -eq 0 ] && echo "orphan cleanup: none under $WORK"
exit 0
