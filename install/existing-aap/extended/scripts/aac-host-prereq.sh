#!/usr/bin/env bash
#
# aac-host-prereq.sh — AAC host: service account, packages, OPA dirs, podman volumes
#
# After --upgrade, the host reboots only when --reboot is also set (README default).
#
# Options:
#   --username NAME       Service account (default: compliance)
#   --password PASS       Set the service account password (optional; else run passwd)
#   --authorized-key-file Install an SSH public key for AAP (repeatable; from aac-host-ssh-key.sh)
#   --skip-ansible-deps   Skip pip psycopg2 and ansible-galaxy (collections requirements)
#   --skip-firewall       Skip firewalld AAC port configuration
#   --skip-pg-firewall    Do not open 5432/tcp (AAP reaches Postgres on a private path)
#   --upgrade             dnf upgrade -y after package install
#   --reboot              Reboot after --upgrade (no effect without --upgrade)
#   -h, --help            Show this help
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAYBOOKS_REQUIREMENTS="${SCRIPT_DIR}/../playbooks/requirements.yml"

readonly DEFAULT_USERNAME=compliance
USERNAME="$DEFAULT_USERNAME"
ACCOUNT_PASSWORD=""
AUTHORIZED_KEY_FILES=()
SKIP_ANSIBLE_DEPS=false
SKIP_FIREWALL=false
SKIP_PG_FIREWALL=false
DO_UPGRADE=false
DO_REBOOT=false

# README firewall section: Grafana, OPA, reports viewer; 5432 optional
readonly -a FIREWALL_PORTS_BASE=(3000 8181 8182 8183 8080 5000 5001 5002 5003 5004)

log() { printf '[aac-host-prereq] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

usage() {
  sed -n '3,25p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --username)   USERNAME=$2; shift 2 ;;
    --password)   ACCOUNT_PASSWORD=$2; shift 2 ;;
    --authorized-key-file) AUTHORIZED_KEY_FILES+=("$2"); shift 2 ;;
    --skip-ansible-deps) SKIP_ANSIBLE_DEPS=true; shift ;;
    --skip-firewall)     SKIP_FIREWALL=true; shift ;;
    --skip-pg-firewall)  SKIP_PG_FIREWALL=true; shift ;;
    --upgrade)    DO_UPGRADE=true; shift ;;
    --reboot)     DO_REBOOT=true; shift ;;
    -h|--help)    usage; exit 0 ;;
    *)            die "Unknown option: $1 (try --help)" ;;
  esac
done

[[ $EUID -eq 0 ]] || die "Run as root on the AAC host."

if command -v subscription-manager >/dev/null 2>&1; then
  if ! subscription-manager status &>/dev/null; then
    log "WARNING: subscription-manager reports the host is not subscribed. Register RHEL before pulling packages."
  fi
fi

# ── Service account ────────────────────────────────────────────────────────

if id "$USERNAME" &>/dev/null; then
  log "User $USERNAME already exists."
else
  log "Creating user $USERNAME."
  useradd -m -c "Compliance AAC service account" -G wheel -s /bin/bash "$USERNAME"
fi

if [[ -n "$ACCOUNT_PASSWORD" ]]; then
  echo "${USERNAME}:${ACCOUNT_PASSWORD}" | chpasswd
  log "Password set for $USERNAME."
else
  log "No --password given; set a password with: passwd $USERNAME"
fi

SUDOERS_FILE="/etc/sudoers.d/${USERNAME}"
SUDOERS_LINE="${USERNAME} ALL=(ALL) NOPASSWD: ALL"
if [[ -f "$SUDOERS_FILE" ]] && grep -qF "$SUDOERS_LINE" "$SUDOERS_FILE"; then
  log "sudoers entry for $USERNAME already present."
else
  printf '%s\n' "$SUDOERS_LINE" >"$SUDOERS_FILE"
  chmod 0440 "$SUDOERS_FILE"
  visudo -cf "$SUDOERS_FILE"
  log "Wrote $SUDOERS_FILE"
fi

USER_HOME=$(getent passwd "$USERNAME" | cut -d: -f6)
USER_UID=$(id -u "$USERNAME")

append_line_once() {
  local file=$1 line=$2
  if [[ -f "$file" ]] && grep -qF "$line" "$file"; then
    return 0
  fi
  printf '%s\n' "$line" >>"$file"
}

BASHRC="${USER_HOME}/.bashrc"
append_line_once "$BASHRC" 'export TERM=xterm-256color'
append_line_once "$BASHRC" "export XDG_RUNTIME_DIR=/run/user/${USER_UID}"
append_line_once "$BASHRC" 'export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"'

loginctl enable-linger "$USERNAME"

# ── SSH authorized_keys (AAP AAC Host credential) ─────────────────────────

install_authorized_key_file() {
  local pubkey_file=$1
  [[ -f "$pubkey_file" ]] || die "Public key file not found: $pubkey_file"
  local ssh_dir="${USER_HOME}/.ssh"
  local auth_keys="${ssh_dir}/authorized_keys"
  local key_line
  key_line=$(grep -E '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256) ' "$pubkey_file" | head -1)
  [[ -n "$key_line" ]] || die "No OpenSSH public key line in $pubkey_file"

  install -d -m 0700 -o "$USERNAME" -g "$USERNAME" "$ssh_dir"
  if [[ -f "$auth_keys" ]] && grep -qF "$key_line" "$auth_keys"; then
    log "SSH public key already in ${auth_keys}."
    return 0
  fi
  printf '%s\n' "$key_line" >>"$auth_keys"
  chown "${USERNAME}:${USERNAME}" "$auth_keys"
  chmod 0600 "$auth_keys"
  log "Appended SSH public key from $pubkey_file to ${auth_keys}."
}

for pubkey in "${AUTHORIZED_KEY_FILES[@]}"; do
  install_authorized_key_file "$pubkey"
done

# ── OPA installation prerequisites (README: OPA → Prerequisites) ─────────

log "Creating OPA policy directories."
mkdir -p /opt/opa/compliance /etc/opa
chown -R "${USERNAME}:${USERNAME}" /opt/opa/compliance /etc/opa

# ── Packages (root) ────────────────────────────────────────────────────────

log "Installing packages."
dnf install -y \
  podman ansible-core git vim tree jq curl python3-pip bash-completion ncurses-term firewalld

if $DO_UPGRADE; then
  log "Upgrading installed packages."
  dnf upgrade -y
fi

# ── User session systemd (as service account) ─────────────────────────────

run_as_user() {
  sudo -u "$USERNAME" \
    HOME="$USER_HOME" \
    USER="$USERNAME" \
    XDG_RUNTIME_DIR="/run/user/${USER_UID}" \
  "$@"
}

if run_as_user systemctl --user daemon-reload 2>/dev/null; then
  log "Reloaded user systemd for $USERNAME."
else
  log "Note: user systemd not active yet; daemon-reload will apply after first login or linger."
fi

# ── Podman volumes (PostgreSQL, Grafana — README / quadlets) ───────────────

ensure_volume() {
  local vol=$1
  if run_as_user podman volume inspect "$vol" &>/dev/null; then
    log "Podman volume $vol already exists."
  else
    run_as_user podman volume create "$vol"
    log "Created podman volume $vol."
  fi
}

ensure_volume compliance_pgdata
ensure_volume compliance_grafanadata

# ── Ansible deps (psycopg2, collections — playbooks/requirements.yml) ───────
# requirements.yml already lists amazon.aws and community.postgresql (no separate installs).

if ! $SKIP_ANSIBLE_DEPS; then
  log "Installing Python and Ansible collections for local playbooks."
  run_as_user pip3 install --user psycopg2-binary
  if [[ -f "$PLAYBOOKS_REQUIREMENTS" ]]; then
    run_as_user ansible-galaxy collection install -r "$PLAYBOOKS_REQUIREMENTS"
  else
    die "Missing $PLAYBOOKS_REQUIREMENTS — run from the repo (install/existing-aap/extended/scripts/)."
  fi
else
  log "Skipping pip and ansible-galaxy (--skip-ansible-deps)."
fi

# ── Firewall (README: Firewall configuration) ─────────────────────────────

configure_firewall() {
  local port
  local ports=("${FIREWALL_PORTS_BASE[@]}")
  if ! $SKIP_PG_FIREWALL; then
    ports+=(5432)
  fi
  if ! command -v firewall-cmd >/dev/null 2>&1; then
    die "firewall-cmd not found; install firewalld or use --skip-firewall"
  fi
  if ! systemctl is-active --quiet firewalld; then
    log "Enabling firewalld."
    systemctl enable --now firewalld
  fi
  for port in "${ports[@]}"; do
    firewall-cmd --permanent --add-port="${port}/tcp"
    log "Permanent rule: ${port}/tcp"
  done
  firewall-cmd --reload
  log "Open ports: $(firewall-cmd --list-ports)"
}

if $SKIP_FIREWALL; then
  log "Skipping firewall configuration (--skip-firewall)."
elif $SKIP_PG_FIREWALL; then
  log "Configuring firewall (5432/tcp omitted — --skip-pg-firewall)."
  configure_firewall
else
  log "Configuring firewall (includes 5432/tcp; use --skip-pg-firewall if AAP uses a private DB path)."
  configure_firewall
fi

# ── Upgrade and reboot ────────────────────────────────────────────────────

if $DO_UPGRADE && $DO_REBOOT; then
  log "Rebooting in 10 seconds (--upgrade --reboot); Ctrl+C to cancel."
  sleep 10
  systemctl reboot
elif $DO_UPGRADE; then
  log "Upgrade completed. Reboot before continuing: systemctl reboot"
  log "Or re-run with: $0 --upgrade --reboot"
fi
