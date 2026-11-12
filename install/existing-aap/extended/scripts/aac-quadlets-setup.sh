#!/usr/bin/env bash
#
# aac-quadlets-setup.sh — Install user-level Podman Quadlets for AAC (compliance user)
#
# Copies install/existing-aap/extended/quadlets/*.container into
# ~/.config/containers/systemd/, substitutes aac_host in Grafana config, removes
# hand-started containers, and starts user systemd units.
#
# Usage (as root):
#   scripts/aac-quadlets-setup.sh --aac-host <fqdn>
#
# As the compliance user:
#   ./aac-quadlets-setup.sh --aac-host <fqdn> --skip-root-cleanup
#
# Options:
#   --username NAME         Service account (default: compliance)
#   --aac-host HOST         FQDN or hostname for GF_SERVER_ROOT_URL (required)
#   --skip-root-cleanup     Skip disabling system-level container-* units (root only)
#   --skip-webserver        Do not install/start aac-webserver quadlet
#   --skip-start            Install unit files only; do not start services
#   --dry-run               Run quadlet generator dry-run only, then exit
#   -h, --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUADLETS_SRC="${SCRIPT_DIR}/../quadlets"
readonly DEFAULT_USERNAME=compliance

USERNAME="$DEFAULT_USERNAME"
AAC_HOST=""
SKIP_ROOT_CLEANUP=false
SKIP_WEBSERVER=false
SKIP_START=false
DRY_RUN=false

readonly -a QUADLET_UNITS=(
  opa-security
  opa-compliance
  opa-ot
  aac-postgresql
  aac-grafana
)
readonly -a CONTAINER_NAMES=(
  opa-security
  opa-compliance
  opa-ot
  aac-postgresql
  aac-grafana
  aac-webserver
)

log() { printf '[aac-quadlets-setup] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

usage() {
  sed -n '3,26p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --username)          USERNAME=$2; shift 2 ;;
    --aac-host)          AAC_HOST=$2; shift 2 ;;
    --skip-root-cleanup) SKIP_ROOT_CLEANUP=true; shift ;;
    --skip-webserver)    SKIP_WEBSERVER=true; shift ;;
    --skip-start)        SKIP_START=true; shift ;;
    --dry-run)           DRY_RUN=true; shift ;;
    -h|--help)           usage; exit 0 ;;
    *)                   die "Unknown option: $1 (try --help)" ;;
  esac
done

[[ -n "$AAC_HOST" ]] || die "--aac-host is required"
[[ -d "$QUADLETS_SRC" ]] || die "Quadlet source not found: $QUADLETS_SRC"

id "$USERNAME" &>/dev/null || die "User $USERNAME does not exist"
USER_HOME=$(getent passwd "$USERNAME" | cut -d: -f6)
USER_UID=$(id -u "$USERNAME")
SYSTEMD_USER_DIR="${USER_HOME}/.config/containers/systemd"

run_as_user() {
  local -a env=(HOME="$USER_HOME" USER="$USERNAME" XDG_RUNTIME_DIR="/run/user/${USER_UID}")
  if [[ "$(id -un)" == "$USERNAME" ]]; then
    env "${env[@]}" "$@"
  else
    sudo -u "$USERNAME" env "${env[@]}" "$@"
  fi
}

write_quadlet() {
  local src=$1 dest=$2
  sed "s/<your-aac-host>/${AAC_HOST}/g" "$src" >"$dest"
  chmod 0644 "$dest"
}

# ── Root: remove system-level quadlet units (README once-only) ─────────────

if [[ $EUID -eq 0 ]] && ! $SKIP_ROOT_CLEANUP; then
  log "Disabling system-level container units (root)."
  systemctl disable --now container-opa-security.service \
    container-opa-compliance.service container-opa-ot.service 2>/dev/null || true
  rm -f /etc/systemd/system/container-opa-*.service \
    /etc/systemd/system/container-aac-postgresql.service \
    /etc/systemd/system/container-aac-grafana.service
  systemctl daemon-reload

  log "Ensuring OPA policy paths are owned by $USERNAME."
  mkdir -p /etc/opa/security /etc/opa/compliance /etc/opa/ot /opt/opa/compliance
  chown -R "${USERNAME}:${USERNAME}" /etc/opa /opt/opa/compliance

  loginctl enable-linger "$USERNAME" 2>/dev/null || true
elif [[ $EUID -ne 0 ]] && ! $SKIP_ROOT_CLEANUP; then
  die "Run as root for first-time setup, or pass --skip-root-cleanup as $USERNAME"
fi

if [[ $EUID -ne 0 ]] && [[ "$(id -un)" != "$USERNAME" ]]; then
  die "Run as root or as $USERNAME"
fi

# ── Podman secrets (required for postgres + grafana quadlets) ─────────────

for secret in compliance_db_password grafana_admin_password; do
  if ! run_as_user podman secret inspect "$secret" &>/dev/null; then
    die "Missing podman secret $secret — run scripts/aac-podman-secrets.sh as $USERNAME"
  fi
done

# ── Install .container files ─────────────────────────────────────────────

log "Installing quadlets into $SYSTEMD_USER_DIR"
if [[ $EUID -eq 0 ]]; then
  install -d -m 0755 -o "$USERNAME" -g "$USERNAME" "$SYSTEMD_USER_DIR"
else
  mkdir -p "$SYSTEMD_USER_DIR"
fi

install_quadlet() {
  local base=$1
  local src="${QUADLETS_SRC}/${base}.container"
  local dest="${SYSTEMD_USER_DIR}/${base}.container"
  [[ -f "$src" ]] || die "Missing $src"
  if [[ $EUID -eq 0 ]]; then
    write_quadlet "$src" "${dest}.$$"
    install -m 0644 -o "$USERNAME" -g "$USERNAME" "${dest}.$$" "$dest"
    rm -f "${dest}.$$"
  else
    write_quadlet "$src" "$dest"
  fi
  log "Installed ${base}.container"
}

for unit in "${QUADLET_UNITS[@]}"; do
  install_quadlet "$unit"
done

if ! $SKIP_WEBSERVER; then
  if run_as_user podman image exists aac-reports-viewer:latest 2>/dev/null; then
    install_quadlet aac-webserver
    if [[ $EUID -eq 0 ]]; then
      install -d -m 0755 -o "$USERNAME" -g "$USERNAME" "${USER_HOME}/reports"
    else
      mkdir -p "${USER_HOME}/reports"
    fi
  else
    log "Skipping aac-webserver (image aac-reports-viewer:latest not found; use services/build.sh)"
  fi
else
  log "Skipping aac-webserver (--skip-webserver)."
fi

# ── Quadlet syntax check ───────────────────────────────────────────────────

QUADLET_BIN="/usr/libexec/podman/quadlet"
if [[ -x "$QUADLET_BIN" ]]; then
  log "Quadlet dry-run:"
  run_as_user "$QUADLET_BIN" -dryrun -user || die "Quadlet dry-run failed — fix .container files"
else
  log "WARNING: $QUADLET_BIN not found; skipping dry-run"
fi

$DRY_RUN && { log "Dry-run complete (--dry-run)."; exit 0; }

# ── Hand-started containers ───────────────────────────────────────────────

for name in "${CONTAINER_NAMES[@]}"; do
  if run_as_user podman container exists "$name" 2>/dev/null; then
    log "Removing existing container $name"
    run_as_user podman rm -f "$name"
  fi
done

# ── User systemd ──────────────────────────────────────────────────────────

run_as_user systemctl --user daemon-reload

if $SKIP_START; then
  log "Units installed; not starting (--skip-start)."
  exit 0
fi

start_unit() {
  local unit=$1.service
  log "Starting $unit"
  run_as_user systemctl --user start "$unit"
  if ! run_as_user systemctl --user is-active --quiet "$unit"; then
    die "$unit failed to become active (see: sudo -u $USERNAME XDG_RUNTIME_DIR=/run/user/$USER_UID systemctl --user status $unit)"
  fi
}

for unit in "${QUADLET_UNITS[@]}"; do
  start_unit "$unit"
done

if [[ -f "${SYSTEMD_USER_DIR}/aac-webserver.container" ]]; then
  start_unit aac-webserver
fi

log "Active user units:"
run_as_user systemctl --user list-units --type=service --state=active 'opa-*.service' 'aac-*.service' 2>/dev/null || true
log "Done. Do not systemctl --user enable generated units; linger + [Install] handles boot."
