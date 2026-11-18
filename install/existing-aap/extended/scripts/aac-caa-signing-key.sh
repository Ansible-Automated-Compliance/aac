#!/usr/bin/env bash
#
# aac-caa-signing-key.sh — Generate cosign key pair for CAA (CIS templates)
#
# Usage:
#   install/existing-aap/extended/scripts/aac-caa-signing-key.sh
#   install/existing-aap/extended/scripts/aac-caa-signing-key.sh --force
#
# Requires: podman, outbound pull to registry.access.redhat.com
#
# Options:
#   --keys-dir PATH   Output directory (default: ../ee/aac-caa-keys next to this script)
#   --cosign-image IMG  Container image with /usr/bin/cosign
#   --force           Regenerate even if cosign.key already exists
#   -h, --help        Show help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_KEYS_DIR="${SCRIPT_DIR}/../ee/aac-caa-keys"
DEFAULT_COSIGN_IMAGE='registry.access.redhat.com/rhtas/cosign-rhel9:latest'

KEYS_DIR="$DEFAULT_KEYS_DIR"
COSIGN_IMAGE="$DEFAULT_COSIGN_IMAGE"
FORCE=false

log() { printf '[aac-caa-signing-key] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

usage() {
  sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keys-dir)      KEYS_DIR=$2; shift 2 ;;
    --cosign-image)  COSIGN_IMAGE=$2; shift 2 ;;
    --force)         FORCE=true; shift ;;
    -h|--help)       usage; exit 0 ;;
    *)               die "Unknown option: $1 (try --help)" ;;
  esac
done

command -v podman >/dev/null 2>&1 || die "podman is required."

mkdir -p "$KEYS_DIR"
KEYS_DIR="$(cd "$KEYS_DIR" && pwd)"
chmod 700 "$KEYS_DIR"

PRIVATE_KEY="${KEYS_DIR}/cosign.key"
PUBLIC_KEY="${KEYS_DIR}/cosign.pub"
COSIGN_BIN="${KEYS_DIR}/cosign"

if [[ -f "$PRIVATE_KEY" ]] && ! $FORCE; then
  log "Key pair already exists at $PRIVATE_KEY (use --force to regenerate)."
  log "Public key for auditors: $PUBLIC_KEY"
  exit 0
fi

if $FORCE; then
  rm -f "$PRIVATE_KEY" "$PUBLIC_KEY"
fi

extract_cosign() {
  if [[ -x "$COSIGN_BIN" ]]; then
    return 0
  fi
  log "Pulling cosign binary from $COSIGN_IMAGE"
  local cid
  cid="$(podman create "$COSIGN_IMAGE")"
  trap 'podman rm -f "$cid" >/dev/null 2>&1 || true' RETURN
  podman cp "${cid}:/usr/bin/cosign" "$COSIGN_BIN"
  podman rm -f "$cid" >/dev/null
  trap - RETURN
  chmod 755 "$COSIGN_BIN"
}

extract_cosign

log "Generating key pair in $KEYS_DIR (empty passphrase)."
(
  cd "$KEYS_DIR"
  COSIGN_PASSWORD="" "$COSIGN_BIN" generate-key-pair
)

chmod 600 "$PRIVATE_KEY"
[[ -f "$PUBLIC_KEY" ]] && chmod 644 "$PUBLIC_KEY"

log "Done."
log "  Private key: $PRIVATE_KEY  (paste into playbooks/vars/secrets.yml as caa_signing_private_key)"
log "  Public key:  $PUBLIC_KEY  (auditors — do not attach to job templates)"
log "Next: ansible-vault edit install/existing-aap/extended/playbooks/vars/secrets.yml"
