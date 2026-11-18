#!/usr/bin/env bash
#
# aac-host-ssh-key.sh — SSH key pair for AAP → AAC host (compliance user)
#
# Writes ~/.ssh/aac_host_ed25519{,.pub} for the invoking user.
# The private key belongs in playbooks/vars/secrets.yml (vault) as
# aac_host_ssh_private_key. Install the public key on the AAC host with
# aac-host-prereq.sh --authorized-key-file or append to ~compliance/.ssh/authorized_keys.
#
# Usage:
#   install/existing-aap/extended/scripts/aac-host-ssh-key.sh
#   install/existing-aap/extended/scripts/aac-host-ssh-key.sh --force
#
# Options:
#   --ssh-dir PATH    Key directory (default: ~/.ssh)
#   --force           Regenerate even if the private key already exists
#   -h, --help        Show help

set -euo pipefail

KEYS_DIR="${HOME}/.ssh"
FORCE=false

KEY_BASENAME=aac_host_ed25519
PRIVATE_KEY_NAME="${KEY_BASENAME}"
PUBLIC_KEY_NAME="${KEY_BASENAME}.pub"

log() { printf '[aac-host-ssh-key] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

usage() {
  sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh-dir) KEYS_DIR=$2; shift 2 ;;
    --keys-dir) KEYS_DIR=$2; shift 2 ;; # backward compatible alias
    --force)    FORCE=true; shift ;;
    -h|--help)  usage; exit 0 ;;
    *)          die "Unknown option: $1 (try --help)" ;;
  esac
done

command -v ssh-keygen >/dev/null 2>&1 || die "ssh-keygen is required."

mkdir -p "$KEYS_DIR"
KEYS_DIR="$(cd "$KEYS_DIR" && pwd)"
chmod 700 "$KEYS_DIR"

PRIVATE_KEY="${KEYS_DIR}/${PRIVATE_KEY_NAME}"
PUBLIC_KEY="${KEYS_DIR}/${PUBLIC_KEY_NAME}"

if [[ -f "$PRIVATE_KEY" ]] && ! $FORCE; then
  log "Key pair already exists at $PRIVATE_KEY (use --force to regenerate)."
  log "Public key for the AAC host: $PUBLIC_KEY"
  exit 0
fi

if $FORCE; then
  rm -f "$PRIVATE_KEY" "$PUBLIC_KEY"
fi

log "Generating ed25519 key pair in $KEYS_DIR (no passphrase)."
ssh-keygen -t ed25519 -f "$PRIVATE_KEY" -N "" -C "aac-aap-ssh"

chmod 600 "$PRIVATE_KEY"
chmod 644 "$PUBLIC_KEY"

log "Done."
log "  Private key: $PRIVATE_KEY"
log "    → playbooks/vars/secrets.yml as aac_host_ssh_private_key (vault-encrypt after edit)"
log "  Public key:  $PUBLIC_KEY"
log "    → on the AAC host: sudo scripts/aac-host-prereq.sh --authorized-key-file $PUBLIC_KEY"
log "       (copy the .pub to the host first if keygen ran elsewhere)"
log "Never commit or push the private key."
