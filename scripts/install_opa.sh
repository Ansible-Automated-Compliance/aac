#!/bin/bash
#
# install_opa.sh — Deploy OPA Containers for Ansible Automated Compliance
#
# Deploys three purpose-specific OPA containers:
#   opa-security   (:8181) — CIS Benchmarks, NIST, STIGs
#   opa-compliance (:8182) — ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, Sentinel
#   opa-ot         (:8183) — NERC-CIP, AI Governance
#
# Usage: ./install_opa.sh [OPTIONS]
#   --restart-only    Restart existing containers via systemd (don't recreate)
#   --help            Show this help message
#
# Environment:
#   OPA_IMAGE   OPA container image (default: openpolicyagent/opa:1.10.0 —
#               the version the AAC platform is validated against; do NOT use
#               :latest, which can pull a breaking OPA release)
#
# Each container is registered as a systemd service (container-opa-*.service)
# so it automatically starts on host reboot.
#
# After running this script, load policies via AAP:
#   AAP Job Template: "AAC - Load OPA Policies"

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Pinned to the validated OPA version (CLAUDE.md / the running AAC deployment).
# Overridable via the OPA_IMAGE env var. Never :latest — Rego v1 + policy
# behavior are version-sensitive.
OPA_IMAGE="${OPA_IMAGE:-openpolicyagent/opa:1.10.0}"
RESTART_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --restart-only) RESTART_ONLY=true; shift ;;
        --help) sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Verify podman is available
if ! command -v podman &>/dev/null; then
    log_error "podman is required but not found. Install podman first."
    exit 1
fi

echo "=============================================="
echo "  AAC — OPA Container Deployment"
echo "=============================================="
echo ""

# Define the three OPA containers
declare -A OPA_NAMES=( [security]="opa-security" [compliance]="opa-compliance" [ot]="opa-ot" )
declare -A OPA_PORTS=( [security]="8181" [compliance]="8182" [ot]="8183" )
declare -A OPA_DESC=(
    [security]="CIS Benchmarks, NIST, STIGs"
    [compliance]="ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, Sentinel"
    [ot]="NERC-CIP, AI Governance"
)

deploy_opa_container() {
    local type=$1
    local name=${OPA_NAMES[$type]}
    local port=${OPA_PORTS[$type]}
    local desc=${OPA_DESC[$type]}
    local policy_dir="/etc/opa/${type}"

    log_info "Deploying ${name} (port ${port}) — ${desc}"

    # Create policy directory on host
    sudo mkdir -p "$policy_dir"
    sudo chmod 755 "$policy_dir"

    if $RESTART_ONLY; then
        # Check unit existence (not just active state) — unit may exist but be stopped
        if systemctl list-unit-files "container-${name}.service" 2>/dev/null | grep -q "container-${name}.service"; then
            sudo systemctl restart "container-${name}.service"
            log_info "  Restarted via systemd: container-${name}.service"
        elif podman ps -a --format '{{.Names}}' | grep -q "^${name}$"; then
            podman restart "$name"
            log_info "  Restarted: ${name}"
        else
            log_warn "  Container ${name} not found — run without --restart-only first"
        fi
        return
    fi

    # Stop and remove existing container if present
    if podman ps -a --format '{{.Names}}' | grep -q "^${name}$"; then
        log_info "  Removing existing container: ${name}"
        podman stop "$name" 2>/dev/null || true
        podman rm "$name" 2>/dev/null || true
    fi

    # Pull latest image
    log_info "  Pulling OPA image..."
    podman pull "$OPA_IMAGE" -q

    # Deploy container
    podman run -d \
        --name "$name" \
        -p "${port}:8181" \
        -v "${policy_dir}:/policies:ro,z" \
        --restart=always \
        "$OPA_IMAGE" \
        run --server --addr :8181

    # Wait for health
    log_info "  Waiting for ${name} to start..."
    for i in {1..30}; do
        if curl -s "http://localhost:${port}/health" >/dev/null 2>&1; then
            log_info "  ${name} is healthy on port ${port}"
            break
        fi
        sleep 1
        if [[ $i -eq 30 ]]; then
            log_error "  ${name} failed to start — check: podman logs ${name}"
            exit 1
        fi
    done

    # Register as a systemd service so OPA survives host reboots
    log_info "  Registering ${name} as a systemd service..."
    local systemd_dir="/etc/systemd/system"
    local service_file="${systemd_dir}/container-${name}.service"

    # Generate service unit to a temp file first — avoids a truncated unit on failure.
    # Capture stderr separately so we can surface the error message on failure.
    local tmp_service_file tmp_stderr
    tmp_service_file="$(mktemp)"
    tmp_stderr="$(mktemp)"
    if podman generate systemd --new --name "$name" \
        --restart-policy always \
        --container-prefix container \
        --separator '-' \
        > "$tmp_service_file" 2>"$tmp_stderr"; then
        # Use 'install' to set correct ownership/mode atomically (sudo mv leaves non-root owner)
        sudo install -o root -g root -m 0644 "$tmp_service_file" "$service_file"
        rm -f "$tmp_service_file" "$tmp_stderr"
    else
        local err_msg
        err_msg="$(cat "$tmp_stderr")"
        rm -f "$tmp_service_file" "$tmp_stderr"
        log_error "  Failed to generate systemd service for ${name}: ${err_msg}"
        exit 1
    fi

    # Enable via systemd (sudo required — writing to /etc/systemd/system)
    sudo systemctl daemon-reload
    sudo systemctl enable "container-${name}.service"
    log_info "  Systemd service enabled: container-${name}.service"
}

# Pull image once
log_info "Pulling OPA image: ${OPA_IMAGE}"
podman pull "$OPA_IMAGE" -q
echo ""

# Deploy all three containers
for type in security compliance ot; do
    deploy_opa_container "$type"
    echo ""
done

echo "=============================================="
echo "  OPA Deployment Complete"
echo "=============================================="
echo ""
echo "Containers:"
echo "  opa-security   → http://localhost:8181  (${OPA_DESC[security]})"
echo "  opa-compliance → http://localhost:8182  (${OPA_DESC[compliance]})"
echo "  opa-ot         → http://localhost:8183  (${OPA_DESC[ot]})"
echo ""
echo "Verify:"
echo "  curl http://localhost:8181/health"
echo "  curl http://localhost:8182/health"
echo "  curl http://localhost:8183/health"
echo ""
echo "Next step — load policies via AAP:"
echo "  Run job template: 'AAC - Load OPA Policies'"
echo ""
