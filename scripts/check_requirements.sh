#!/bin/bash
#
# check_requirements.sh — Pre-installation Requirements Check for AAC
#
# Validates that this server meets all requirements before installing
# AAP and AAC. Run this FIRST before any other installation steps.
#
# Usage: ./check_requirements.sh [OPTIONS]
#   --fqdn FQDN       Expected FQDN for this server (e.g. aap.example.com)
#   --mcp             Also check port 8004 (MCP server for Claude Code)
#   --skip-ports      Skip port availability checks
#   --skip-specs      Skip CPU/RAM/disk checks
#   --help            Show this help message
#
# Exit codes:
#   0 — All requirements met
#   1 — One or more requirements not met

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

EXPECTED_FQDN=""
SKIP_PORTS=false
SKIP_SPECS=false
CHECK_MCP=false

CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNED=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --fqdn)       EXPECTED_FQDN="$2"; shift 2 ;;
        --mcp)        CHECK_MCP=true; shift ;;
        --skip-ports) SKIP_PORTS=true; shift ;;
        --skip-specs) SKIP_SPECS=true; shift ;;
        --help)       head -18 "$0" | tail -16; exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

section() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }
pass()    { echo -e "  ${GREEN}✅${NC} $1"; ((CHECKS_PASSED++)); }
fail()    { echo -e "  ${RED}❌${NC} $1"; ((CHECKS_FAILED++)); }
warn()    { echo -e "  ${YELLOW}⚠️ ${NC} $1"; ((CHECKS_WARNED++)); }

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║       Ansible Automated Compliance — Pre-Install Check   ║"
echo "╚══════════════════════════════════════════════════════════╝"

# ─── FQDN ─────────────────────────────────────────────────────────────────────
section "Hostname / FQDN"

ACTUAL_FQDN=$(hostname -f 2>/dev/null || echo "")
SHORT_HOST=$(hostname -s 2>/dev/null || echo "")

if [[ -z "$ACTUAL_FQDN" || "$ACTUAL_FQDN" == "localhost" || "$ACTUAL_FQDN" == "localhost.localdomain" ]]; then
    fail "FQDN is not set (got: '${ACTUAL_FQDN}')"
    echo "       Fix: set a proper FQDN before installing AAP"
    echo "         hostnamectl set-hostname aap.example.com"
    echo "         echo '$(hostname -I | awk \"{print \$1}\") aap.example.com' >> /etc/hosts"
elif [[ "$ACTUAL_FQDN" == "$SHORT_HOST" ]]; then
    warn "Hostname appears to be short name only: '${ACTUAL_FQDN}'"
    echo "       AAP works best with a fully-qualified domain name"
    echo "       Fix: hostnamectl set-hostname aap.example.com"
else
    pass "FQDN: ${ACTUAL_FQDN}"
fi

if [[ -n "$EXPECTED_FQDN" ]]; then
    if [[ "$ACTUAL_FQDN" == "$EXPECTED_FQDN" ]]; then
        pass "FQDN matches expected: ${EXPECTED_FQDN}"
    else
        fail "FQDN mismatch — expected: ${EXPECTED_FQDN}, got: ${ACTUAL_FQDN}"
    fi
fi

# Check FQDN resolves
if [[ -n "$ACTUAL_FQDN" && "$ACTUAL_FQDN" != "localhost"* ]]; then
    if getent hosts "$ACTUAL_FQDN" >/dev/null 2>&1; then
        RESOLVED_IP=$(getent hosts "$ACTUAL_FQDN" | awk '{print $1}')
        pass "FQDN resolves to: ${RESOLVED_IP}"
    else
        fail "FQDN does not resolve: ${ACTUAL_FQDN}"
        echo "       Fix: add entry to /etc/hosts or configure DNS"
        echo "         echo '$(hostname -I | awk \"{print \$1}\") ${ACTUAL_FQDN}' >> /etc/hosts"
    fi
fi

# ─── Operating System ─────────────────────────────────────────────────────────
section "Operating System"

if [[ -f /etc/redhat-release ]]; then
    OS_RELEASE=$(cat /etc/redhat-release)
    if echo "$OS_RELEASE" | grep -qE "Red Hat Enterprise Linux.*9\.|Rocky Linux.*9\."; then
        pass "OS: ${OS_RELEASE}"
    elif echo "$OS_RELEASE" | grep -qE "Red Hat Enterprise Linux.*8\."; then
        warn "RHEL 8 detected — AAP 2.6 recommends RHEL 9: ${OS_RELEASE}"
    else
        fail "Unsupported OS: ${OS_RELEASE} (AAP 2.6 requires RHEL 9)"
    fi
else
    fail "Not a Red Hat-based OS — AAP 2.6 requires RHEL 9"
fi

# Red Hat subscription
if command -v subscription-manager &>/dev/null; then
    if subscription-manager status 2>/dev/null | grep -q "Overall Status: Current"; then
        pass "Red Hat subscription: active"
    elif subscription-manager status 2>/dev/null | grep -q "Overall Status:"; then
        STATUS=$(subscription-manager status 2>/dev/null | grep "Overall Status:" | awk -F': ' '{print $2}')
        fail "Red Hat subscription: ${STATUS}"
        echo "       Fix: subscription-manager register --username=<RHN user>"
    else
        warn "Could not determine subscription status (requires root)"
    fi
else
    warn "subscription-manager not found — cannot verify Red Hat subscription"
fi

# ─── Hardware Specifications ───────────────────────────────────────────────────
if ! $SKIP_SPECS; then
    section "Hardware Specifications"

    # CPU
    CPU_COUNT=$(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null || echo 0)
    if [[ "$CPU_COUNT" -ge 8 ]]; then
        pass "CPU: ${CPU_COUNT} vCPUs (minimum 8 recommended)"
    elif [[ "$CPU_COUNT" -ge 4 ]]; then
        warn "CPU: ${CPU_COUNT} vCPUs (8+ recommended for production)"
    else
        fail "CPU: ${CPU_COUNT} vCPUs (minimum 4 required)"
    fi

    # RAM
    RAM_GB=$(awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo 0)
    if [[ "$RAM_GB" -ge 16 ]]; then
        pass "RAM: ${RAM_GB} GB (minimum 16 GB)"
    elif [[ "$RAM_GB" -ge 8 ]]; then
        warn "RAM: ${RAM_GB} GB (16 GB recommended for production)"
    else
        fail "RAM: ${RAM_GB} GB (minimum 8 GB required)"
    fi

    # Disk
    DISK_GB=$(df -BG / 2>/dev/null | awk 'NR==2 {gsub("G",""); print $4}' || echo 0)
    if [[ "$DISK_GB" -ge 60 ]]; then
        pass "Disk: ${DISK_GB} GB free on / (minimum 60 GB)"
    elif [[ "$DISK_GB" -ge 40 ]]; then
        warn "Disk: ${DISK_GB} GB free on / (60 GB recommended)"
    else
        fail "Disk: ${DISK_GB} GB free on / (minimum 40 GB required)"
    fi
fi

# ─── Required Tools ───────────────────────────────────────────────────────────
section "Required Tools"

for tool in podman curl python3; do
    if command -v "$tool" &>/dev/null; then
        VERSION=$("$tool" --version 2>/dev/null | head -1)
        pass "${tool}: ${VERSION}"
    else
        fail "${tool}: not found"
        echo "       Fix: dnf install -y ${tool}"
    fi
done

# Podman version check (need 4.x+)
if command -v podman &>/dev/null; then
    PODMAN_VER=$(podman --version 2>/dev/null | awk '{print $3}')
    PODMAN_MAJOR=$(echo "$PODMAN_VER" | cut -d. -f1)
    if [[ "$PODMAN_MAJOR" -ge 4 ]]; then
        pass "Podman version: ${PODMAN_VER} (4.x+ required)"
    else
        fail "Podman version: ${PODMAN_VER} (4.x+ required)"
        echo "       Fix: dnf update -y podman"
    fi
fi

# ─── Port Availability ────────────────────────────────────────────────────────
if ! $SKIP_PORTS; then
    section "Port Availability"
    echo "  Checking that required ports are not already in use..."
    echo ""

    # Port table: port|service|notes
    PORTS=(
        "80|AAP Gateway (HTTP redirect)|Required by AAP"
        "443|AAP Gateway (HTTPS)|Required by AAP"
        "5432|PostgreSQL|AAC compliance database"
        "8181|OPA Security|CIS, NIST, STIGs"
        "8182|OPA Compliance|ISO 27001, SOC 2, PCI-DSS, FISMA"
        "8183|OPA OT|NERC-CIP, AI Governance"
    )

    for entry in "${PORTS[@]}"; do
        PORT=$(echo "$entry" | cut -d'|' -f1)
        SVC=$(echo "$entry" | cut -d'|' -f2)
        NOTE=$(echo "$entry" | cut -d'|' -f3)

        if ss -tlnp 2>/dev/null | grep -q ":${PORT} " || \
           netstat -tlnp 2>/dev/null | grep -q ":${PORT} "; then
            OWNER=$(ss -tlnp 2>/dev/null | grep ":${PORT} " | awk '{print $NF}' | head -1)
            fail "Port ${PORT} in use (${SVC}) — ${OWNER}"
            echo "       Fix: stop the conflicting process before installing"
        else
            pass "Port ${PORT} available — ${SVC} (${NOTE})"
        fi
    done

    # Optional MCP port check
    if $CHECK_MCP; then
        echo ""
        echo "  Optional: MCP Server (Claude Code integration)"
        if ss -tlnp 2>/dev/null | grep -q ":8004 " || \
           netstat -tlnp 2>/dev/null | grep -q ":8004 "; then
            OWNER=$(ss -tlnp 2>/dev/null | grep ":8004 " | awk '{print $NF}' | head -1)
            fail "Port 8004 in use (AAP MCP Server) — ${OWNER}"
            echo "       Fix: stop the conflicting process before installing MCP server"
        else
            pass "Port 8004 available — AAP MCP Server (Claude Code integration)"
        fi
        warn "Port 8004 must be restricted to your dev workstation IP — never open broadly"
        echo "       Fix: firewall-cmd --permanent --add-rich-rule='rule family=\"ipv4\" source address=\"YOUR.DEV.IP/32\" port port=\"8004\" protocol=\"tcp\" accept'"
    fi
fi

# ─── Network Connectivity ─────────────────────────────────────────────────────
section "Network Connectivity"

# Red Hat registry
if curl -s --max-time 10 https://registry.redhat.io/v2/ >/dev/null 2>&1; then
    pass "registry.redhat.io: reachable"
else
    warn "registry.redhat.io: not reachable (required for AAP container images)"
fi

# GitHub
if curl -s --max-time 10 https://github.com >/dev/null 2>&1; then
    pass "github.com: reachable (required for AAC repository)"
else
    fail "github.com: not reachable"
    echo "       Fix: check firewall rules allow outbound HTTPS"
fi

# quay.io
if curl -s --max-time 10 https://quay.io >/dev/null 2>&1; then
    pass "quay.io: reachable (required for OPA and PostgreSQL images)"
else
    warn "quay.io: not reachable (needed for container images)"
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Requirements Summary${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}Passed:${NC}   ${CHECKS_PASSED}"
echo -e "  ${RED}Failed:${NC}   ${CHECKS_FAILED}"
echo -e "  ${YELLOW}Warnings:${NC} ${CHECKS_WARNED}"
echo ""

if [[ "$CHECKS_FAILED" -eq 0 ]]; then
    echo -e "  ${GREEN}✅ Server meets AAC requirements — proceed with installation${NC}"
    echo ""
    echo "  Next step: Install AAP 2.6"
    echo "    See: scripts/INSTALL.md"
    exit 0
else
    echo -e "  ${RED}❌ ${CHECKS_FAILED} requirement(s) not met — resolve before installing${NC}"
    echo ""
    echo "  Re-run after fixing: ./scripts/check_requirements.sh"
    exit 1
fi
