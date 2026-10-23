#!/bin/bash
# Setup compliance repository on ${AAC_HOST:?set AAC_HOST}
# Run from your workstation

set -e

AAP_HOST="${AAC_HOST:?set AAC_HOST}"
AAP_USER="aapuser1"
REPO_URL="https://github.com/ansible-automated-compliance/aac.git"
REPO_PATH="/home/${AAP_USER}/compliance"

echo "=========================================="
echo "Setting up compliance repository"
echo "Server: ${AAP_HOST}"
echo "User: ${AAP_USER}"
echo "Path: ${REPO_PATH}"
echo "=========================================="
echo ""

# Check if we can connect
echo "Testing SSH connection..."
if ! ssh -o ConnectTimeout=5 ${AAP_USER}@${AAP_HOST} "echo 'Connected'" 2>/dev/null; then
    echo "ERROR: Cannot connect to ${AAP_HOST} as ${AAP_USER}"
    echo "Please ensure you can SSH: ssh ${AAP_USER}@${AAP_HOST}"
    exit 1
fi
echo "✓ SSH connection successful"
echo ""

# Check if repo exists
echo "Checking for existing repository..."
if ssh ${AAP_USER}@${AAP_HOST} "test -d ${REPO_PATH}/.git"; then
    echo "✓ Repository already exists at ${REPO_PATH}"
    echo ""
    echo "Updating repository..."
    ssh ${AAP_USER}@${AAP_HOST} "cd ${REPO_PATH} && git pull"
    echo "✓ Repository updated"
else
    echo "Repository not found. Cloning..."
    ssh ${AAP_USER}@${AAP_HOST} "git clone ${REPO_URL} ${REPO_PATH}"
    echo "✓ Repository cloned to ${REPO_PATH}"
fi
echo ""

# Verify
echo "Verifying installation..."
ssh ${AAP_USER}@${AAP_HOST} "ls -la ${REPO_PATH}/" | head -15
echo ""

echo "=========================================="
echo "✓ Compliance repository ready at:"
echo "  ${REPO_PATH}"
echo ""
echo "Key paths:"
echo "  OPA policies: ${REPO_PATH}/policies/"
echo "  EDA rulebooks: ${REPO_PATH}/eda/rulebooks/"
echo "  Start OPA: ${REPO_PATH}/start_opa.sh"
echo ""
echo "Start OPA server:"
echo "  ssh ${AAP_USER}@${AAP_HOST} 'cd ${REPO_PATH} && ./start_opa.sh &'"
echo "=========================================="
