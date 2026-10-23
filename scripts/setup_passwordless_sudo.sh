#!/bin/bash
#
# setup_passwordless_sudo.sh - Configure Passwordless Sudo for Ansible
#
# This script configures passwordless sudo access for the Ansible service account
# on target systems. Required for compliance fact collection that needs root access.
#
# Approach: creates a dedicated 'aac-sudo' group (not wheel — avoids granting
# NOPASSWD to all existing admins), adds the automation user to it, and writes
# a group-level NOPASSWD drop-in (/etc/sudoers.d/aac-sudo_nopasswd) only if
# the group does not already have NOPASSWD. Easier to audit and revoke.
#
# Usage: ./setup_passwordless_sudo.sh [OPTIONS]
#   -u, --user USER       Ansible user (default: ansible)
#   -t, --target HOST     Target host(s), comma-separated
#   -i, --inventory FILE  Ansible inventory file
#   -k, --ssh-key FILE    SSH private key file
#   --dry-run             Show what would be done without making changes
#   --help                Show this help message
#
# Examples:
#   ./setup_passwordless_sudo.sh -u ansible -t server1,server2
#   ./setup_passwordless_sudo.sh -i inventory/hosts.yml
#   ./setup_passwordless_sudo.sh -t server1 --dry-run

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Defaults
ANSIBLE_USER="ansible"
TARGET_HOSTS=""
INVENTORY_FILE=""
SSH_KEY=""
DRY_RUN=false
# Dedicated sudo group — only automation users are added here.
# Using wheel directly would grant NOPASSWD to all admins already in wheel.
AAC_SUDO_GROUP="aac-sudo"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--user)
            ANSIBLE_USER="$2"
            shift 2
            ;;
        -t|--target)
            TARGET_HOSTS="$2"
            shift 2
            ;;
        -i|--inventory)
            INVENTORY_FILE="$2"
            shift 2
            ;;
        -k|--ssh-key)
            SSH_KEY="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            head -24 "$0" | tail -21
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Validate inputs
if [ -z "$TARGET_HOSTS" ] && [ -z "$INVENTORY_FILE" ]; then
    log_error "Either --target or --inventory must be specified"
    exit 1
fi

# Build SSH options
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"
if [ -n "$SSH_KEY" ]; then
    SSH_OPTS="$SSH_OPTS -i $SSH_KEY"
fi

# Setup sudo on a single host via a dedicated automation group (aac-sudo).
# Using a dedicated group — not wheel — means existing admins in wheel are
# not affected. Only the Ansible service account gets NOPASSWD sudo.
setup_sudo_on_host() {
    local host="$1"
    local drop_in="/etc/sudoers.d/${AAC_SUDO_GROUP}_nopasswd"

    log_info "Configuring sudo on: $host"

    if $DRY_RUN; then
        log_info "  [DRY-RUN] Would create group '${AAC_SUDO_GROUP}' if absent"
        log_info "  [DRY-RUN] Would add $ANSIBLE_USER to group '${AAC_SUDO_GROUP}'"
        log_info "  [DRY-RUN] Would configure ${AAC_SUDO_GROUP} NOPASSWD drop-in if not already set"
        return 0
    fi

    # Check connectivity
    if ! ssh $SSH_OPTS "$host" "echo connected" > /dev/null 2>&1; then
        log_error "  Cannot connect to $host"
        return 1
    fi

    # Check if user exists; create if not
    if ! ssh $SSH_OPTS "$host" "id $ANSIBLE_USER" > /dev/null 2>&1; then
        log_warn "  User $ANSIBLE_USER does not exist on $host"
        log_info "  Creating user $ANSIBLE_USER..."
        ssh $SSH_OPTS "$host" "sudo useradd -m -s /bin/bash $ANSIBLE_USER" || {
            log_error "  Failed to create user"
            return 1
        }
    fi

    # Create dedicated automation group if it doesn't already exist
    log_info "  Ensuring group '${AAC_SUDO_GROUP}' exists..."
    ssh $SSH_OPTS "$host" \
        "sudo getent group ${AAC_SUDO_GROUP} > /dev/null 2>&1 || sudo groupadd ${AAC_SUDO_GROUP}" || {
        log_error "  Failed to create group '${AAC_SUDO_GROUP}'"
        return 1
    }

    # Add user to dedicated group (not wheel — avoids blanket escalation)
    log_info "  Adding $ANSIBLE_USER to group '${AAC_SUDO_GROUP}'..."
    ssh $SSH_OPTS "$host" "sudo usermod -aG ${AAC_SUDO_GROUP} $ANSIBLE_USER" || {
        log_error "  Failed to add $ANSIBLE_USER to group '${AAC_SUDO_GROUP}'"
        return 1
    }
    log_info "  $ANSIBLE_USER added to '${AAC_SUDO_GROUP}'"

    # Check if aac-sudo already has NOPASSWD in sudoers.
    # Use recursive grep over /etc/sudoers.d (avoids glob expansion failure)
    # and explicit grep on /etc/sudoers to cover both locations robustly.
    if ssh $SSH_OPTS "$host" "sudo sh -c \"\
        grep -qE '^[[:space:]]*%${AAC_SUDO_GROUP}[[:space:]]+ALL=.ALL.[[:space:]]+NOPASSWD' \
            /etc/sudoers 2>/dev/null || \
        grep -R -qE '^[[:space:]]*%${AAC_SUDO_GROUP}[[:space:]]+ALL=.ALL.[[:space:]]+NOPASSWD' \
            /etc/sudoers.d 2>/dev/null\""; then
        log_info "  ${AAC_SUDO_GROUP} already has NOPASSWD — no drop-in needed"
    else
        log_info "  Creating NOPASSWD drop-in for group '${AAC_SUDO_GROUP}'..."
        ssh $SSH_OPTS "$host" \
            "echo '%${AAC_SUDO_GROUP} ALL=(ALL) NOPASSWD: ALL' | sudo tee ${drop_in} > /dev/null"
        ssh $SSH_OPTS "$host" "sudo chmod 0440 ${drop_in}"
        # Validate syntax before leaving it in place
        if ssh $SSH_OPTS "$host" "sudo visudo -c -f ${drop_in}" > /dev/null 2>&1; then
            log_info "  Drop-in validated: ${drop_in}"
        else
            log_error "  Invalid sudoers syntax — removing drop-in"
            ssh $SSH_OPTS "$host" "sudo rm -f ${drop_in}"
            return 1
        fi
    fi

    # Test sudo access
    if ssh $SSH_OPTS "${ANSIBLE_USER}@${host}" "sudo whoami" 2>/dev/null | grep -q "root"; then
        log_info "  Passwordless sudo: OK"
    else
        log_warn "  Could not verify sudo access — group membership may require re-login to take effect"
    fi

    return 0
}

# Get hosts from inventory
get_hosts_from_inventory() {
    local inventory="$1"

    if [ ! -f "$inventory" ]; then
        log_error "Inventory file not found: $inventory"
        exit 1
    fi

    # Extract hosts (simple parsing for INI and YAML formats)
    if [[ "$inventory" == *.yml ]] || [[ "$inventory" == *.yaml ]]; then
        # YAML inventory - extract hosts
        grep -E "^\s+\S+:" "$inventory" | grep -v "vars:" | grep -v "children:" | sed 's/://g' | tr -d ' '
    else
        # INI inventory - extract hosts
        grep -v "^\[" "$inventory" | grep -v "^#" | grep -v "^$" | awk '{print $1}'
    fi
}

# Main
echo "=============================================="
echo "  Passwordless Sudo Setup for Ansible"
echo "=============================================="
echo ""
echo "Ansible User: $ANSIBLE_USER"
$DRY_RUN && echo "Mode: DRY-RUN (no changes will be made)"
echo ""

# Build host list
HOSTS=()
if [ -n "$TARGET_HOSTS" ]; then
    IFS=',' read -ra HOSTS <<< "$TARGET_HOSTS"
fi
if [ -n "$INVENTORY_FILE" ]; then
    while IFS= read -r host; do
        [ -n "$host" ] && HOSTS+=("$host")
    done < <(get_hosts_from_inventory "$INVENTORY_FILE")
fi

if [ ${#HOSTS[@]} -eq 0 ]; then
    log_error "No hosts found to configure"
    exit 1
fi

log_info "Hosts to configure: ${#HOSTS[@]}"
echo ""

# Process each host
SUCCESS=0
FAILED=0

for host in "${HOSTS[@]}"; do
    if setup_sudo_on_host "$host"; then
        ((SUCCESS++))
    else
        ((FAILED++))
    fi
    echo ""
done

# Summary
echo "=============================================="
echo "  Setup Complete"
echo "=============================================="
echo ""
echo "Results:"
echo "  Successful: $SUCCESS"
echo "  Failed:     $FAILED"
echo ""
if [ $FAILED -gt 0 ]; then
    log_warn "Some hosts failed. Check the output above for details."
    exit 1
fi

echo "Next steps:"
echo "  1. Copy SSH keys: ssh-copy-id $ANSIBLE_USER@<host>"
echo "  2. Test connection: ansible -i inventory all -m ping"
echo ""
