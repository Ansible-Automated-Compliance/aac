#!/usr/bin/env bash
#
# aac-podman-secrets.sh — Create podman secrets for AAC quadlets
#
# Reads compliance_db_password and grafana_admin_password from
# playbooks/vars/secrets.yml (plain or ansible-vault encrypted). Values never
# appear on the command line; they are piped to podman on stdin.
#
# Required for quadlets
#
# Run as the same user that owns the quadlets (typically compliance after linger).
#
# Usage:
#   install/existing-aap/extended/scripts/aac-podman-secrets-from-vault.sh
#   install/existing-aap/extended/scripts/aac-podman-secrets-from-vault.sh --force
#
# Options:
#   --secrets-file PATH        Default: ../playbooks/vars/secrets.yml
#   --vault-password-file PATH Same as ansible-vault / ANSIBLE_VAULT_PASSWORD_FILE
#   --force                    Replace existing podman secrets
#   -h, --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_FILE="${SCRIPT_DIR}/../playbooks/vars/secrets.yml"
VAULT_PASSWORD_FILE="${ANSIBLE_VAULT_PASSWORD_FILE:-}"
FORCE=false

# name in podman : key in secrets.yml
readonly -a PAIRS=(
  "compliance_db_password:compliance_db_password"
  "grafana_admin_password:grafana_admin_password"
)

log() { printf '[aac-podman-secrets] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

usage() {
  sed -n '3,21p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --secrets-file)          SECRETS_FILE=$2; shift 2 ;;
    --vault-password-file)   VAULT_PASSWORD_FILE=$2; shift 2 ;;
    --force)                 FORCE=true; shift ;;
    -h|--help)               usage; exit 0 ;;
    *)                       die "Unknown option: $1 (try --help)" ;;
  esac
done

[[ -f "$SECRETS_FILE" ]] || die "Secrets file not found: $SECRETS_FILE"

command -v podman >/dev/null 2>&1 || die "podman is required."
command -v python3 >/dev/null 2>&1 || die "python3 is required."
python3 -c 'import yaml' 2>/dev/null || die "python3 PyYAML is required (python3-pyyaml / ansible install)."

read_secrets_yaml() {
  if head -1 "$SECRETS_FILE" | grep -q '^\$ANSIBLE_VAULT;'; then
    command -v ansible-vault >/dev/null 2>&1 || die "ansible-vault required for encrypted $SECRETS_FILE"
    local vault_args=()
    if [[ -n "$VAULT_PASSWORD_FILE" ]]; then
      vault_args+=(--vault-password-file "$VAULT_PASSWORD_FILE")
    fi
    ansible-vault view "${vault_args[@]}" "$SECRETS_FILE"
  else
    cat "$SECRETS_FILE"
  fi
}

get_secret_value() {
  local yaml_key=$1
  local value
  value="$(read_secrets_yaml | python3 -c "
import sys
import yaml

key = sys.argv[1]
data = yaml.safe_load(sys.stdin) or {}
val = data.get(key)
if val is None or val == '' or val == 'PLACEHOLDER':
    sys.stderr.write(f'missing or PLACEHOLDER: {key}\n')
    sys.exit(2)
if not isinstance(val, str):
    val = str(val)
sys.stdout.write(val)
" "$yaml_key")" || die "Set $yaml_key in $SECRETS_FILE before running."
  printf '%s' "$value"
}

create_or_replace_secret() {
  local podman_name=$1
  local yaml_key=$2
  local value

  value="$(get_secret_value "$yaml_key")"

  if podman secret inspect "$podman_name" &>/dev/null; then
    if ! $FORCE; then
      log "Secret $podman_name already exists (use --force to replace)."
      return 0
    fi
    podman secret rm "$podman_name"
    log "Removed existing secret $podman_name."
  fi

  printf '%s' "$value" | podman secret create "$podman_name" -
  unset value
  log "Created podman secret $podman_name."
}

for pair in "${PAIRS[@]}"; do
  podman_name="${pair%%:*}"
  yaml_key="${pair#*:}"
  create_or_replace_secret "$podman_name" "$yaml_key"
done

log "Done. podman secret list:"
podman secret list
