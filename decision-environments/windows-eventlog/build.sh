#!/usr/bin/env bash
# Build the windows-eventlog Decision Environment and push to local AAP hub registry.
# Run from the build host, or locally if you have podman + access to push to
# the registry.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
# Post-CRC the registry is the Private Automation Hub route, NOT the bare host.
# AAP_HOST/... was the pre-CRC layout and no longer resolves as a registry.
TAG="${TAG:-${REGISTRY:?set REGISTRY to the Private Automation Hub route}/de-windows-eventlog:latest}"

cd "$REPO_ROOT"

echo "Building $TAG (from $REPO_ROOT)..."
podman build -t "$TAG" -f decision-environments/windows-eventlog/Containerfile .

echo ""
echo "Verifying collection presence..."
podman run --rm "$TAG" \
  ls /usr/share/ansible/collections/ansible_collections/lab/eda/plugins/event_source/

echo ""
# Credentials are REQUIRED explicitly — no defaults. A default password here is a
# committed secret, and this file is in git.
#   export REG_USER=... REG_PASS=...     (or omit both and log in interactively first)
#
# TLS_VERIFY defaults to false ONLY because the lab hub route presents a
# self-signed certificate. Set TLS_VERIFY=true anywhere with a real certificate.
TLS_VERIFY="${TLS_VERIFY:-false}"

if [ -n "${REG_USER:-}" ] || [ -n "${REG_PASS:-}" ]; then
  echo "Logging in to the hub registry..."
  podman login --tls-verify="$TLS_VERIFY" \
    -u "${REG_USER:?REG_USER required when REG_PASS is set}" \
    -p "${REG_PASS:?REG_PASS required when REG_USER is set}" \
    "${TAG%%/*}"
else
  echo "No REG_USER/REG_PASS set — assuming an existing podman login for ${TAG%%/*}"
fi

echo "Pushing to registry..."
podman push --tls-verify="$TLS_VERIFY" "$TAG"

echo ""
echo ""
echo "Done. Now register it in EDA:"
echo "  1. Create an EDA credential of type 'Container Registry' for ${TAG%%/*}"
echo "  2. Create a Decision Environment with image_url=$TAG and that credential"
echo "  3. Point the windows_golden_enforcement activation at it"
echo ""
echo "NOTE: the activation POST field is 'eda_credentials' (list of ids), not"
echo "'eda_credential_ids'. The wrong name fails with a misleading error:"
echo "  'The rulebook requires a RH AAP credential.'"
