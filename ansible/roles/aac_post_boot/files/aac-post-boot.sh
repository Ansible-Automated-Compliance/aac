#!/bin/bash
# =============================================================================
# AAC post-boot recovery
#
# Runs once at boot on the lab-aap host. Everything AAC serves lives inside the
# CRC VM, and CRC does not auto-start — so after a reboot the platform is down
# and the Grafana dashboards go stale until somebody notices.
#
# Order matters and is deliberate:
#   1. Clear podman's stale runtime dirs. After an unhandled reboot every
#      podman command fails with "current system boot ID differs from cached
#      boot ID", which is what makes aap-mcp.service fail with exit 125.
#      This is fast, so it runs first.
#   2. Restart aap-mcp. It does not need CRC, so recover it before the slow part.
#   3. crc start. Several minutes.
#   4. Wait for the AAP controller to answer.
#   5. Launch the refresh templates so the dashboards reflect reality rather
#      than the last nightly run.
#
# Config lives in ~/.config/aac/post-boot.env (not in git — it holds credentials).
# See post-boot.env.example.
# =============================================================================
set -uo pipefail

CONF="${AAC_POST_BOOT_CONF:-$HOME/.config/aac/post-boot.env}"
LOG_DIR="${AAC_POST_BOOT_LOG_DIR:-$HOME/.local/state}"
LOG="$LOG_DIR/aac-post-boot.log"
mkdir -p "$LOG_DIR"
# `crc start` echoes the kubeadmin password on stdout and this log captures it,
# so the file must not be world-readable.
touch "$LOG"; chmod 0600 "$LOG"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG"; }

log "═══ AAC post-boot recovery starting (uptime: $(uptime -p 2>/dev/null || echo '?')) ═══"

# shellcheck source=/dev/null
[ -f "$CONF" ] && . "$CONF" || log "WARN  no config at $CONF — using defaults"

AAP_URL="${AAP_URL:?set AAP_URL in $CONF (the AAP gateway route)}"
# Checked here, not first in sync_registry: a missing route must stop the hook
# before it starts CRC, not halfway through recovery.
OPA_COMPLIANCE_URL="${OPA_COMPLIANCE_URL:?set OPA_COMPLIANCE_URL in $CONF (the OPA compliance route)}"
AAP_USER="${AAP_USER:-admin}"
AAP_PASS="${AAP_PASS:?set AAP_PASS}"
START_CRC="${START_CRC:-true}"
REFRESH_TEMPLATES="${REFRESH_TEMPLATES:-212,214,10}"
AAP_WAIT_SECONDS="${AAP_WAIT_SECONDS:-1800}"

# ── 1. podman runtime dirs ───────────────────────────────────────────────────
# These are runtime scratch in /tmp; persistent images/volumes live in
# ~/.local/share/containers and are untouched. sudo is needed because the retired
# AAP 2.6 stack left root-owned files behind.
if podman ps >/dev/null 2>&1; then
  log "podman OK — no boot-ID cleanup needed"
else
  log "podman broken (stale boot ID) — clearing runtime dirs"
  sudo -n rm -rf "/tmp/storage-run-$(id -u)/containers" "/tmp/storage-run-$(id -u)/libpod/tmp" 2>>"$LOG" \
    && log "  cleared" || log "  WARN cleanup failed (passwordless sudo unavailable?)"
  podman ps >/dev/null 2>&1 && log "  podman recovered" || log "  WARN podman still failing"
fi

# ── 2. MCP (independent of CRC — recover it before the slow part) ────────────
if systemctl --user restart aap-mcp.service 2>>"$LOG"; then
  sleep 5
  log "aap-mcp: $(systemctl --user is-active aap-mcp.service 2>/dev/null)"
else
  log "WARN aap-mcp restart failed"
fi

# ── 3. CRC ───────────────────────────────────────────────────────────────────
if [ "$START_CRC" = "true" ]; then
  # Anchor to start-of-line: the "Disk Usage" line also contains the string
  # "(Inside the CRC VM)", and being later it would otherwise win the match —
  # making state look like a disk figure and forcing a needless crc start.
  state=$(crc status 2>/dev/null | awk -F: '/^CRC VM:/{gsub(/ /,"",$2); print $2}')
  if [ "$state" = "Running" ]; then
    log "CRC already Running — skipping start"
  else
    log "CRC is '${state:-unknown}' — starting (this takes several minutes)"
    # Scrub the credentials crc prints on success — this log is kept for triage.
    crc start 2>&1 | sed -E 's/(Password:[[:space:]]*).*/\1<redacted>/' >>"$LOG"
    rc=${PIPESTATUS[0]}
    [ "$rc" -eq 0 ] && log "crc start returned 0" || log "WARN crc start returned $rc"
  fi
else
  log "START_CRC=false — not starting CRC"
fi

# ── 4. wait for the controller ───────────────────────────────────────────────
log "waiting up to ${AAP_WAIT_SECONDS}s for AAP to answer"
deadline=$(( $(date +%s) + AAP_WAIT_SECONDS ))
aap_up=false
while [ "$(date +%s)" -lt "$deadline" ]; do
  code=$(curl -sk --max-time 8 -o /dev/null -w '%{http_code}' \
         -u "$AAP_USER:$AAP_PASS" "$AAP_URL/api/controller/v2/ping/" 2>/dev/null)
  if [ "$code" = "200" ]; then aap_up=true; break; fi
  sleep 20
done

if [ "$aap_up" != true ]; then
  log "ERROR AAP did not answer within ${AAP_WAIT_SECONDS}s — skipping refresh"
  log "═══ finished (degraded) ═══"
  exit 1
fi
log "AAP is up"

# ── 5. refresh the dashboards ────────────────────────────────────────────────
# Without this the panels keep showing the last nightly run: the Compliance
# Operator's CCRs live in etcd, and only the collate job moves them into
# compliance_results, which is what Grafana reads.
launch() {
  local tid=$1 jid=""
  for attempt in 1 2 3; do
    # The gateway route intermittently returns a 404 HTML page on POST /launch/.
    jid=$(curl -sk --max-time 25 -u "$AAP_USER:$AAP_PASS" -X POST \
          "$AAP_URL/api/controller/v2/job_templates/$tid/launch/" \
          -H 'Content-Type: application/json' -d '{}' 2>/dev/null \
          | python3 -c 'import sys,json;print(json.load(sys.stdin).get("id",""))' 2>/dev/null)
    [ -n "$jid" ] && break
    sleep 5
  done
  [ -z "$jid" ] && { log "  T$tid: LAUNCH FAILED after 3 attempts"; return 1; }
  for _ in $(seq 1 60); do
    st=$(curl -sk --max-time 15 -u "$AAP_USER:$AAP_PASS" \
         "$AAP_URL/api/controller/v2/jobs/$jid/" 2>/dev/null \
         | python3 -c 'import sys,json;print(json.load(sys.stdin).get("status","?"))' 2>/dev/null)
    case "$st" in successful|failed|error|canceled) break;; esac
    sleep 10
  done
  log "  T$tid -> job $jid: $st"
  [ "$st" = "successful" ]
}

# ── 5a. re-publish the MCP governance template registry ─────────────────────
# data.aac.templates is pushed to OPA over the REST API and is held IN MEMORY.
# OPA's init container restores /policies on restart but NOT API-pushed data, so
# after any OPA restart the registry is empty. With OPA_GOVERNANCE_ENABLED=true
# an empty registry means the policy default-denies EVERY job launch — a
# fail-closed outage. Re-publishing here makes a reboot self-healing.
sync_registry() {
  local opa="$OPA_COMPLIANCE_URL"
  local jt wf n
  jt=$(curl -sk --max-time 20 -u "$AAP_USER:$AAP_PASS" \
       "$AAP_URL/api/controller/v2/job_templates/?page_size=400" 2>/dev/null \
       | python3 -c 'import sys,json;print(json.dumps({str(r["id"]):r["name"] for r in json.load(sys.stdin)["results"]}))' 2>/dev/null)
  wf=$(curl -sk --max-time 20 -u "$AAP_USER:$AAP_PASS" \
       "$AAP_URL/api/controller/v2/workflow_job_templates/?page_size=400" 2>/dev/null \
       | python3 -c 'import sys,json;print(json.dumps({str(r["id"]):r["name"] for r in json.load(sys.stdin)["results"]}))' 2>/dev/null)
  if [ -z "$jt" ] || [ -z "$wf" ]; then log "  WARN could not read templates — registry NOT synced"; return 1; fi
  curl -s --max-time 15 -X PUT --data "$jt" "$opa/v1/data/aac/templates/controller" >/dev/null 2>&1
  curl -s --max-time 15 -X PUT --data "$wf" "$opa/v1/data/aac/templates/workflows"  >/dev/null 2>&1
  # A 204 is not proof; read it back.
  n=$(curl -s --max-time 10 "$opa/v1/data/aac/templates/controller" 2>/dev/null \
      | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("result",{}) or {}))' 2>/dev/null)
  if [ "${n:-0}" -gt 0 ]; then log "  registry synced — $n templates registered"; return 0; fi
  log "  ERROR registry reads back EMPTY — governance would deny every launch"; return 1
}

log "re-publishing MCP governance template registry"
sync_registry || rc_registry=1

log "refreshing dashboards (templates: $REFRESH_TEMPLATES)"
rc=${rc_registry:-0}
IFS=',' read -ra TIDS <<< "$REFRESH_TEMPLATES"
for t in "${TIDS[@]}"; do launch "$t" || rc=1; done

[ $rc -eq 0 ] && log "═══ finished OK ═══" || log "═══ finished with failures ═══"
exit $rc
