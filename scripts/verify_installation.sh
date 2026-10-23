#!/bin/bash
#
# verify_installation.sh — Verify AAC Installation
#
# Checks that all AAC components are running correctly:
#   - Three OPA containers (security :8181, compliance :8182, OT :8183)
#   - PostgreSQL compliance database
#   - AAP Gateway and Controller
#   - Ansible Vault configuration
#
# Usage: ./verify_installation.sh [OPTIONS]
#   --aap-url URL             AAP URL (default: https://localhost)
#   --aap-token TOKEN         AAP Bearer token for API checks
#   --vault-pass-file FILE    Vault password file (default: ~/.vault_pass)
#   --skip-vault              Skip Ansible Vault check
#   --verbose                 Show detailed output
#   --help                    Show this help message
#
# Exit codes:
#   0 — All checks passed
#   1 — One or more checks failed

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

AAP_URL="https://localhost"
AAP_TOKEN=""
VAULT_PASS_FILE="${HOME}/.vault_pass"
SKIP_VAULT=false
VERBOSE=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
VAULT_FILE="${REPO_ROOT}/ansible/vars/vault_secrets.yml"

CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNED=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --aap-url)         AAP_URL="$2"; shift 2 ;;
        --aap-token)       AAP_TOKEN=$2; shift 2 ;;
        --vault-pass-file) VAULT_PASS_FILE="$2"; shift 2 ;;
        --skip-vault)      SKIP_VAULT=true; shift ;;
        --verbose)         VERBOSE=true; shift ;;
        --help)            head -22 "$0" | tail -19; exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

section()     { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }
pass()        { echo -e "  ${GREEN}✅${NC} $1"; ((CHECKS_PASSED++)); }
fail()        { echo -e "  ${RED}❌${NC} $1"; ((CHECKS_FAILED++)); }
warn()        { echo -e "  ${YELLOW}⚠️ ${NC} $1"; ((CHECKS_WARNED++)); }
info()        { $VERBOSE && echo -e "  ${BLUE}ℹ️ ${NC} $1"; }

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║       Ansible Automated Compliance — Verifier            ║"
echo "╚══════════════════════════════════════════════════════════╝"

# ─── OPA Containers ───────────────────────────────────────────────────────────
section "OPA Containers"

check_opa() {
    local name=$1 port=$2 desc=$3
    if curl -s "http://localhost:${port}/health" >/dev/null 2>&1; then
        local policy_count
        policy_count=$(curl -s "http://localhost:${port}/v1/policies" | grep -o '"id"' | wc -l | tr -d ' ')
        pass "${name} (:${port}) — ${desc} — ${policy_count} policies loaded"
    else
        fail "${name} (:${port}) — not responding"
        echo "       Fix: podman start ${name}"
        echo "       Or:  Run 'AAC - Deploy OPA Containers' (ID 28) in AAP"
    fi
}

check_opa "opa-security"   8181 "CIS, NIST, STIGs"
check_opa "opa-compliance" 8182 "ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, Sentinel"
check_opa "opa-ot"         8183 "NERC-CIP, AI Governance"

# ─── PostgreSQL ───────────────────────────────────────────────────────────────
section "PostgreSQL"

if command -v podman &>/dev/null; then
    if podman ps --format '{{.Names}}' 2>/dev/null | grep -q "^postgresql$"; then
        pass "postgresql container is running"

        # Check compliance DB is accessible
        if podman exec postgresql pg_isready -U postgres >/dev/null 2>&1; then
            pass "Database connection: OK (postgres@compliance)"
        else
            fail "Database not ready — check: podman logs postgresql"
        fi

        # Check compliance_results table exists
        TABLE_COUNT=$(podman exec postgresql psql -U postgres -d compliance -t \
            -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" \
            2>/dev/null | tr -d ' \n' || echo "0")
        if [ "$TABLE_COUNT" -gt 0 ]; then
            pass "Schema initialized — ${TABLE_COUNT} tables"
        else
            warn "Schema not initialized — run 'Initialize PostgreSQL Database' (ID 23) in AAP"
        fi
    else
        fail "postgresql container is not running"
        echo "       Fix: Run scripts/install_postgres.sh"
        echo "       Or:  podman start postgresql"
    fi
else
    warn "podman not found — cannot check PostgreSQL container"
fi

# ─── AAP ─────────────────────────────────────────────────────────────────────
section "Ansible Automation Platform"

if curl -sk "${AAP_URL}/api/gateway/v1/ping/" >/dev/null 2>&1; then
    pass "AAP Gateway: ${AAP_URL}"
else
    fail "AAP Gateway not reachable at ${AAP_URL}"
fi

if curl -sk "${AAP_URL}/api/controller/v2/ping/" >/dev/null 2>&1; then
    VERSION=$(curl -sk "${AAP_URL}/api/controller/v2/ping/" 2>/dev/null \
        | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('version','unknown'))" 2>/dev/null || echo "unknown")
    pass "AAP Controller: version ${VERSION}"
else
    fail "AAP Controller not reachable at ${AAP_URL}/api/controller/v2/"
fi

if [ -n "$AAP_TOKEN" ]; then
    HTTP=$(curl -sk -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer ${AAP_TOKEN}" \
        "${AAP_URL}/api/controller/v2/me/")
    if [ "$HTTP" = "200" ]; then
        pass "AAP API token: valid"
    else
        fail "AAP API token: invalid (HTTP ${HTTP})"
        echo "       Fix: rotate token and update ~/.claude.json + vault_aap_local_mcp_token"
    fi
fi

# ─── Ansible Vault ────────────────────────────────────────────────────────────
section "Ansible Vault"

if $SKIP_VAULT; then
    warn "Vault check skipped (--skip-vault)"
else
    if [ -f "$VAULT_FILE" ]; then
        if head -1 "$VAULT_FILE" | grep -q "\$ANSIBLE_VAULT"; then
            pass "Vault file exists and is encrypted"
        else
            fail "Vault file is NOT encrypted — contains plaintext secrets!"
        fi
    else
        fail "Vault file not found: ${VAULT_FILE}"
    fi

    if [ -f "$VAULT_PASS_FILE" ]; then
        PERMS=$(stat -f "%OLp" "$VAULT_PASS_FILE" 2>/dev/null || stat -c "%a" "$VAULT_PASS_FILE" 2>/dev/null)
        if [ "$PERMS" = "600" ] || [ "$PERMS" = "400" ]; then
            pass "Vault password file: ${VAULT_PASS_FILE} (permissions OK)"
        else
            warn "Vault password file permissions: ${PERMS} (should be 600)"
            echo "       Fix: chmod 600 ${VAULT_PASS_FILE}"
        fi

        if command -v ansible-vault &>/dev/null; then
            if ansible-vault view "$VAULT_FILE" --vault-password-file "$VAULT_PASS_FILE" >/dev/null 2>&1; then
                pass "Vault decryption: OK"
            else
                fail "Vault decryption failed — check password in ${VAULT_PASS_FILE}"
            fi
        else
            warn "ansible-vault not installed — cannot verify vault contents"
        fi
    else
        fail "Vault password file not found: ${VAULT_PASS_FILE}"
        echo "       Fix: echo 'your-vault-password' > ~/.vault_pass && chmod 600 ~/.vault_pass"
    fi
fi

# ─── Repository ───────────────────────────────────────────────────────────────
section "Repository Structure"

POLICY_COUNT=$(find "${REPO_ROOT}/policies" -name "*.rego" 2>/dev/null | wc -l | tr -d ' ')
if [ "$POLICY_COUNT" -gt 100 ]; then
    pass "Rego policies: ${POLICY_COUNT} files found"
else
    warn "Rego policies: only ${POLICY_COUNT} found (expected 200+)"
fi

for dir in "ansible/playbooks" "ansible/vars" "scripts"; do
    if [ -d "${REPO_ROOT}/${dir}" ]; then
        info "Directory OK: ${dir}"
    else
        warn "Directory missing: ${dir}"
    fi
done

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Verification Summary${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}Passed:${NC}   ${CHECKS_PASSED}"
echo -e "  ${RED}Failed:${NC}   ${CHECKS_FAILED}"
echo -e "  ${YELLOW}Warnings:${NC} ${CHECKS_WARNED}"
echo ""

if [ "$CHECKS_FAILED" -eq 0 ]; then
    echo -e "  ${GREEN}✅ All critical checks passed — AAC is ready${NC}"
    echo ""
    echo "  Run the Sentinel demo:"
    echo "    demo runbooks: https://github.com/ynotbhatc/aac-demos"
    exit 0
else
    echo -e "  ${RED}❌ ${CHECKS_FAILED} check(s) failed — fix the issues above${NC}"
    echo ""
    echo "  Then re-run: ./scripts/verify_installation.sh"
    echo "  Or use AAP:  Run 'AAC Demo — Pre-flight Check' (ID 38)"
    exit 1
fi
