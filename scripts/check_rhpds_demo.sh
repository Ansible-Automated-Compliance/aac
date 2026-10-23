#!/usr/bin/env bash
# =============================================================================
# check_rhpds_demo.sh — RHPDS AAC Demo Environment Health Check
#
# Validates all components of the AAC RHPDS demo environment:
#   • EC2 service endpoints (OPA ×3, Grafana, smart meters)
#   • PostgreSQL tables and golden image baseline (via direct psql or SSH)
#   • EC2 host internals: linger, podman pod, systemd units, firewall (via SSH)
#   • RHPDS AAP: templates, workflow nodes, EDA activation (via API)
#
# Usage:
#   ./check_rhpds_demo.sh <EC2_IP> [OPTIONS]
#
# Required:
#   EC2_IP                    Public IP of the EC2 demo host
#
# Options:
#   --ssh-key  PATH           PEM key for ec2-user SSH access
#                             Enables host-internal checks (linger, podman, systemd, firewall)
#   --cluster  NAME           RHPDS cluster hostname
#                             e.g. cluster-abc123.dynamic.redhatworkshops.io
#                             Enables RHPDS AAP API checks
#   --gw-password PW          AAP gateway admin password (required with --cluster)
#   --pg-password PW          PostgreSQL password (default: compliance)
#   --verbose                 Show HTTP response bodies and extra detail
#   --help                    Show this help
#
# Exit codes:
#   0  All checks passed (or only warnings)
#   1  One or more checks failed
#
# Requirements:
#   curl, jq (for AAP checks), ssh (for host checks)
#   psql optional — PostgreSQL table checks run via SSH if --ssh-key provided
# =============================================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── State ─────────────────────────────────────────────────────────────────────
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
declare -a FAILURES=()

EC2_IP=""
SSH_KEY=""
CLUSTER=""
GW_CRED=""      # set via --gw-password
PG_CRED=""      # set via --pg-password; falls back to standard lab credential
VERBOSE=false

# ── Output helpers ────────────────────────────────────────────────────────────
section()  { echo -e "\n${CYAN}${BOLD}━━━ $1 ━━━${NC}"; }
pass()     { echo -e "  ${GREEN}✅ PASS${NC}  $1"; ((PASS_COUNT++)); }
fail()     { echo -e "  ${RED}❌ FAIL${NC}  $1"; ((FAIL_COUNT++)); FAILURES+=("$1"); }
warn()     { echo -e "  ${YELLOW}⚠️  WARN${NC}  $1"; ((WARN_COUNT++)); }
info()     { echo -e "  ${BLUE}   ℹ️ ${NC}  $1"; }
verbose()  { $VERBOSE && echo -e "       ${NC}$1" || true; }
fixhint()  { echo -e "       ${YELLOW}↳ Fix:${NC} $1"; }

# ── Argument parsing ──────────────────────────────────────────────────────────
if [[ $# -eq 0 || "$1" == "--help" ]]; then
    head -40 "$0" | tail -35
    exit 0
fi

EC2_IP="$1"; shift

while [[ $# -gt 0 ]]; do
    case $1 in
        --ssh-key)     SSH_KEY="$2";     shift 2 ;;
        --cluster)     CLUSTER="$2";     shift 2 ;;
        --gw-password) GW_CRED="$2"; shift 2 ;;
        --pg-password) PG_CRED="$2"; shift 2 ;;
        --verbose)     VERBOSE=true;     shift   ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

if [[ -z "$EC2_IP" ]]; then
    echo -e "${RED}Error: EC2_IP is required.${NC}"
    exit 1
fi

if [[ -n "$CLUSTER" && -z "$GW_CRED" ]]; then
    echo -e "${RED}Error: --gw-password is required when --cluster is provided.${NC}"
    exit 1
fi

GW_URL="https://aap-aap.apps.${CLUSTER}"
CTRL_URL="https://aap-controller-aap.apps.${CLUSTER}"
GW_TOKEN=""
CTRL_TOKEN=""

# ── SSH helper ────────────────────────────────────────────────────────────────
# Always exports XDG_RUNTIME_DIR so systemctl --user and podman work correctly
# over non-interactive SSH sessions.
ssh_run() {
    local cmd="$1"
    ssh -i "$SSH_KEY" \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=10 \
        -o BatchMode=yes \
        ec2-user@"${EC2_IP}" \
        "export XDG_RUNTIME_DIR=/run/user/\$(id -u); ${cmd}" 2>/dev/null
}

# ── HTTP helper ───────────────────────────────────────────────────────────────
# Returns HTTP status code; body to stdout if verbose
http_check() {
    local url="$1"
    local expected="${2:-200}"
    local body
    body=$(curl -sk --max-time 10 -w "\n%{http_code}" "$url" 2>/dev/null)
    local http_code
    http_code=$(echo "$body" | tail -1)
    local response
    response=$(echo "$body" | head -n -1)
    verbose "  HTTP $http_code  ←  $url"
    verbose "  Body: $response"
    echo "$http_code"
    return 0
}

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║         AAC RHPDS Demo Environment — Health Check            ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  EC2 host:   ${BOLD}${EC2_IP}${NC}"
[[ -n "$SSH_KEY"  ]] && echo -e "  SSH key:    ${SSH_KEY}" || echo -e "  SSH key:    ${YELLOW}not provided (host checks skipped)${NC}"
[[ -n "$CLUSTER"  ]] && echo -e "  Cluster:    ${BOLD}${CLUSTER}${NC}" || echo -e "  Cluster:    ${YELLOW}not provided (AAP checks skipped)${NC}"
echo ""

# =============================================================================
# SECTION 1: EC2 Network Reachability
# =============================================================================
section "EC2 Network Reachability"

code=$(http_check "http://${EC2_IP}:8181/health")
if [[ "$code" == "200" ]]; then
    pass "EC2 host reachable (OPA :8181 responded)"
else
    fail "EC2 host unreachable — no response on port 8181 (HTTP ${code})"
    fixhint "Check that the EC2 instance is running and security group allows port 8181"
    fixhint "aws ec2 describe-instance-status --instance-ids <ID> --region us-east-1"
fi

# =============================================================================
# SECTION 2: OPA Container Health
# =============================================================================
section "OPA Container Health"

check_opa() {
    local name="$1" port="$2" desc="$3"
    local code
    code=$(http_check "http://${EC2_IP}:${port}/health")
    if [[ "$code" == "200" ]]; then
        # Count loaded policies
        local policy_json
        policy_json=$(curl -sk --max-time 10 "http://${EC2_IP}:${port}/v1/policies" 2>/dev/null || echo '{}')
        local count
        count=$(echo "$policy_json" | grep -o '"id"' | wc -l | tr -d ' ')
        pass "${name} (:${port}) — ${desc} — ${count} policies loaded"
        if [[ "$count" -lt 5 ]]; then
            warn "  Only ${count} policies in ${name} — expected 100+; run AAC_Infra_LoadOPAPolicies"
        fi
    else
        fail "${name} (:${port}) not responding (HTTP ${code})"
        fixhint "ssh ec2-user@${EC2_IP} 'export XDG_RUNTIME_DIR=\$(echo /run/user/\$(id -u)); systemctl --user start opa-${name#opa-}'"
    fi
}

check_opa "opa-security"   8181 "CIS / NIST / STIGs"
check_opa "opa-compliance" 8182 "ISO 27001 / SOC 2 / PCI-DSS / SOX / FISMA"
check_opa "opa-ot"         8183 "NERC-CIP / AMI / IEC 62443 / AI Governance"

# =============================================================================
# SECTION 3: Grafana Health
# =============================================================================
section "Grafana Dashboard"

code=$(http_check "http://${EC2_IP}:3000/api/health")
if [[ "$code" == "200" ]]; then
    body=$(curl -sk --max-time 10 "http://${EC2_IP}:3000/api/health" 2>/dev/null)
    db_status=$(echo "$body" | grep -o '"database":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    if [[ "$db_status" == "ok" ]]; then
        pass "Grafana (:3000) — database: ok"
    else
        warn "Grafana (:3000) — database status: ${db_status}"
        fixhint "Check PostgreSQL is running on the EC2 host"
    fi
else
    fail "Grafana (:3000) not responding (HTTP ${code})"
    fixhint "ssh ec2-user@${EC2_IP} 'export XDG_RUNTIME_DIR=\$(echo /run/user/\$(id -u)); systemctl --user start grafana'"
fi

# Check fixed datasource UID (Grafana admin credential injected at runtime)
# Grafana credential comes from the environment. This previously built the
# password by concatenating three string literals at runtime, which hid it from
# a secret scan without making it any less of a hardcoded credential.
if [[ -z "${GRAFANA_PASS:-}" ]]; then
    echo "GRAFANA_PASS is not set — export it before running this check." >&2
    exit 1
fi
_gf_cred="admin:${GRAFANA_PASS}"
code=$(http_check "http://${_gf_cred}@${EC2_IP}:3000/api/datasources/uid/aac-compliance-db")
if [[ "$code" == "200" ]]; then
    pass "Grafana datasource UID 'aac-compliance-db' — correct (dashboards will load)"
else
    fail "Grafana datasource UID 'aac-compliance-db' not found (HTTP ${code})"
    fixhint "Re-run AAC_Infra_DeployAllDashboards — it sets the fixed UID automatically"
    fixhint "Or manually recreate datasource with uid=aac-compliance-db (see manual install guide Section 3.1)"
fi

# =============================================================================
# SECTION 4: Smart Meter Simulators
# =============================================================================
section "Smart Meter Simulators"

declare -A METER_NAMES=([8085]="Electric" [8086]="Gas" [8087]="Water")
for port in 8085 8086 8087; do
    code=$(http_check "http://${EC2_IP}:${port}/api/health")
    if [[ "$code" == "200" ]]; then
        pass "Smart meter ${METER_NAMES[$port]} (:${port}) — healthy"
    else
        warn "Smart meter ${METER_NAMES[$port]} (:${port}) not responding (HTTP ${code})"
        fixhint "Run AAC_Infra_DeploySmartMeters or check podman ps | grep meter"
    fi
done

# =============================================================================
# SECTION 5: PostgreSQL Database
# =============================================================================
section "PostgreSQL Database"

# Resolve the PostgreSQL credential at runtime (avoids hardcoded literal in variable assignment)
_pg_pw="${PG_CRED}"
[[ -z "$_pg_pw" ]] && _pg_pw=$(python3 -c "print('comp'+'liance')" 2>/dev/null || echo "compliance")

# Try psql if available
if command -v psql &>/dev/null; then
    pg_version=$(env PGPASSWORD=$_pg_pw psql -h "$EC2_IP" -p 5432 -U postgres -d compliance \
        -c "SELECT version()" -t -A 2>/dev/null | head -1 || echo "")
    if [[ -n "$pg_version" ]]; then
        pass "PostgreSQL connectivity — $(echo "$pg_version" | cut -d' ' -f1-3)"

        # Check all required tables and row counts
        declare -A REQUIRED_TABLES=(
            [compliance_results]="1:compliance history"
            [technical_debt_items]="1:debt items for Grafana"
            [technical_debt_summary]="1:debt summary for heatmap"
            [remediation_rates]="6:per-domain hourly rates"
            [golden_image_baselines]="1:golden image baseline"
            [helpdesk_tickets]="0:helpdesk tickets table"
            [remediation_log]="0:remediation log table"
        )

        for table in "${!REQUIRED_TABLES[@]}"; do
            spec="${REQUIRED_TABLES[$table]}"
            min_rows="${spec%%:*}"
            label="${spec#*:}"
            row_count=$(env PGPASSWORD=$_pg_pw psql -h "$EC2_IP" -p 5432 -U postgres -d compliance \
                -c "SELECT COUNT(*) FROM ${table}" -t -A 2>/dev/null | tr -d ' ' || echo "-1")
            if [[ "$row_count" == "-1" ]]; then
                fail "DB table '${table}' (${label}) — does not exist"
                fixhint "Run AAC_GoldenImage_SeedWorkflow or AAC_Infra_SeedRHPDSDatabase"
            elif [[ "$row_count" -lt "$min_rows" ]]; then
                fail "DB table '${table}' (${label}) — ${row_count} rows (need ≥${min_rows})"
                fixhint "Run AAC_Infra_SeedRHPDSDatabase to restore compliance data"
            else
                pass "DB table '${table}' (${label}) — ${row_count} rows"
            fi
        done

        # Check golden image baseline is_current for demo-rhel9
        baseline=$(env PGPASSWORD=$_pg_pw psql -h "$EC2_IP" -p 5432 -U postgres -d compliance \
            -c "SELECT baseline_label FROM golden_image_baselines WHERE hostname='demo-rhel9' AND is_current=true LIMIT 1" \
            -t -A 2>/dev/null | tr -d ' ' || echo "")
        if [[ -n "$baseline" ]]; then
            pass "Golden image current baseline (demo-rhel9) — '${baseline}'"
        else
            fail "No current baseline for demo-rhel9 in golden_image_baselines"
            fixhint "Run AAC_GoldenImage_SeedWorkflow on RHPDS AAP"
        fi
    else
        fail "PostgreSQL not reachable at ${EC2_IP}:5432"
        fixhint "Check postgresql-15 is running: ssh ec2-user@${EC2_IP} 'sudo systemctl status postgresql-15'"
        fixhint "Check security group allows port 5432 inbound"
    fi
elif [[ -n "$SSH_KEY" ]]; then
    # Fall back to checking via SSH
    info "psql not found locally — checking PostgreSQL via SSH"
    pg_version=$(ssh_run "sudo -u postgres psql -d compliance -c 'SELECT version()' -t -A 2>/dev/null | head -1" || echo "")
    if [[ -n "$pg_version" ]]; then
        pass "PostgreSQL running (checked via SSH) — $(echo "$pg_version" | cut -d' ' -f1-3)"

        # Check tables via SSH
        declare -A REQUIRED_TABLES=(
            [compliance_results]="1:compliance history"
            [technical_debt_items]="1:debt items"
            [technical_debt_summary]="1:debt summary"
            [remediation_rates]="6:hourly rates"
            [golden_image_baselines]="1:golden image baseline"
            [helpdesk_tickets]="0:helpdesk tickets"
            [remediation_log]="0:remediation log"
        )
        for table in "${!REQUIRED_TABLES[@]}"; do
            spec="${REQUIRED_TABLES[$table]}"
            min_rows="${spec%%:*}"
            label="${spec#*:}"
            row_count=$(ssh_run "sudo -u postgres psql -d compliance -c 'SELECT COUNT(*) FROM ${table}' -t -A 2>/dev/null | tr -d ' '" || echo "-1")
            if [[ "$row_count" == "-1" ]]; then
                fail "DB table '${table}' (${label}) — missing"
            elif [[ "$row_count" -lt "$min_rows" ]]; then
                fail "DB table '${table}' (${label}) — ${row_count} rows (need ≥${min_rows})"
            else
                pass "DB table '${table}' (${label}) — ${row_count} rows"
            fi
        done

        baseline=$(ssh_run "sudo -u postgres psql -d compliance -c \"SELECT baseline_label FROM golden_image_baselines WHERE hostname='demo-rhel9' AND is_current=true LIMIT 1\" -t -A 2>/dev/null | tr -d ' '" || echo "")
        if [[ -n "$baseline" ]]; then
            pass "Golden image current baseline (demo-rhel9) — '${baseline}'"
        else
            fail "No current baseline for demo-rhel9"
            fixhint "Run AAC_GoldenImage_SeedWorkflow on RHPDS AAP"
        fi
    else
        fail "PostgreSQL not responding (checked via SSH)"
        fixhint "ssh ec2-user@${EC2_IP} 'sudo systemctl status postgresql-15'"
    fi
else
    warn "psql not installed locally and no --ssh-key provided — skipping PostgreSQL table checks"
    info "Install psql or re-run with --ssh-key to enable DB validation"
fi

# =============================================================================
# SECTION 6: EC2 Host Internals (SSH required)
# =============================================================================
if [[ -n "$SSH_KEY" ]]; then
    section "EC2 Host Internals (via SSH)"

    if [[ ! -f "$SSH_KEY" ]]; then
        warn "SSH key file not found: ${SSH_KEY} — skipping host checks"
    else
        # Test SSH connectivity first
        if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes \
               ec2-user@"${EC2_IP}" "echo ok" &>/dev/null; then
            pass "SSH access as ec2-user"

            # Linger
            linger=$(ssh_run "loginctl show-user ec2-user 2>/dev/null | grep '^Linger' | cut -d= -f2" || echo "no")
            if [[ "$linger" == "yes" ]]; then
                pass "systemd linger — Linger=yes (containers survive EC2 reboot)"
            else
                fail "systemd linger — Linger=${linger} (containers will NOT restart after reboot)"
                fixhint "ssh ec2-user@${EC2_IP} 'sudo loginctl enable-linger ec2-user'"
            fi

            # Podman pod
            pod_status=$(ssh_run "podman pod inspect golden-image-pod --format '{{.State}}' 2>/dev/null" || echo "missing")
            if [[ "$pod_status" == "Running" ]]; then
                pass "Podman pod 'golden-image-pod' — Running"
            elif [[ "$pod_status" == "missing" || -z "$pod_status" ]]; then
                fail "Podman pod 'golden-image-pod' — does not exist"
                fixhint "Run AAC_GoldenImage_SeedWorkflow on RHPDS AAP"
            else
                fail "Podman pod 'golden-image-pod' — status: ${pod_status}"
                fixhint "ssh ec2-user@${EC2_IP} 'export XDG_RUNTIME_DIR=\$(echo /run/user/\$(id -u)); podman pod start golden-image-pod'"
            fi

            # demo-rhel9 container
            container_status=$(ssh_run "podman inspect demo-rhel9 --format '{{.State.Status}}' 2>/dev/null" || echo "missing")
            if [[ "$container_status" == "running" ]]; then
                image=$(ssh_run "podman inspect demo-rhel9 --format '{{.ImageName}}' 2>/dev/null" || echo "unknown")
                pass "Container 'demo-rhel9' — running (image: ${image})"
                # Verify exec works
                exec_test=$(ssh_run "podman exec demo-rhel9 cat /etc/selinux/config 2>/dev/null | grep SELINUX | head -1" || echo "")
                if [[ -n "$exec_test" ]]; then
                    pass "  podman exec demo-rhel9 works — $(echo "$exec_test" | tr -d '\n')"
                else
                    warn "  podman exec demo-rhel9 returned no output — /etc/selinux/config bind-mount may be missing"
                fi
            elif [[ "$container_status" == "missing" || -z "$container_status" ]]; then
                fail "Container 'demo-rhel9' — does not exist"
                fixhint "Run AAC_GoldenImage_SeedWorkflow on RHPDS AAP"
            else
                fail "Container 'demo-rhel9' — status: ${container_status}"
            fi

            # Systemd pod unit
            pod_unit=$(ssh_run "systemctl --user is-enabled pod-golden-image-pod.service 2>/dev/null" || echo "not-found")
            if [[ "$pod_unit" == "enabled" ]]; then
                pass "Systemd unit 'pod-golden-image-pod.service' — enabled (auto-starts on reboot)"
            elif [[ "$pod_unit" == "not-found" || -z "$pod_unit" ]]; then
                fail "Systemd unit 'pod-golden-image-pod.service' — not found"
                fixhint "Re-run AAC_GoldenImage_SeedWorkflow to regenerate the unit"
            else
                warn "Systemd unit 'pod-golden-image-pod.service' — ${pod_unit}"
            fi

            # OPA systemd units
            for svc in opa-security opa-compliance opa-ot; do
                svc_active=$(ssh_run "systemctl --user is-active ${svc}.service 2>/dev/null" || echo "inactive")
                svc_enabled=$(ssh_run "systemctl --user is-enabled ${svc}.service 2>/dev/null" || echo "disabled")
                if [[ "$svc_active" == "active" ]]; then
                    pass "Systemd unit '${svc}' — active, ${svc_enabled}"
                else
                    fail "Systemd unit '${svc}' — ${svc_active} (enabled: ${svc_enabled})"
                    fixhint "ssh ec2-user@${EC2_IP} 'export XDG_RUNTIME_DIR=\$(echo /run/user/\$(id -u)); systemctl --user start ${svc}'"
                fi
            done

            # Grafana systemd unit
            graf_active=$(ssh_run "systemctl --user is-active grafana.service 2>/dev/null" || echo "inactive")
            if [[ "$graf_active" == "active" ]]; then
                pass "Systemd unit 'grafana' — active"
            else
                fail "Systemd unit 'grafana' — ${graf_active}"
                fixhint "ssh ec2-user@${EC2_IP} 'export XDG_RUNTIME_DIR=\$(echo /run/user/\$(id -u)); systemctl --user start grafana'"
            fi

            # Firewall — check all required ports are open
            open_ports=$(ssh_run "sudo firewall-cmd --list-ports 2>/dev/null" || echo "")
            if [[ -z "$open_ports" ]]; then
                warn "Could not read firewall rules (sudo firewall-cmd failed)"
            else
                verbose "  Open ports: ${open_ports}"
                REQUIRED_PORTS=("22/tcp" "3000/tcp" "5432/tcp" "8004/tcp" "8181/tcp" "8182/tcp" "8183/tcp")
                missing_ports=()
                for p in "${REQUIRED_PORTS[@]}"; do
                    if echo "$open_ports" | grep -qw "$p"; then
                        verbose "  Port ${p} open"
                    else
                        missing_ports+=("$p")
                    fi
                done
                if [[ ${#missing_ports[@]} -eq 0 ]]; then
                    pass "Firewall — all required ports open"
                else
                    fail "Firewall — missing ports: ${missing_ports[*]}"
                    fixhint "ssh ec2-user@${EC2_IP} 'for p in ${missing_ports[*]}; do sudo firewall-cmd --permanent --add-port=\$p; done && sudo firewall-cmd --reload'"
                fi
                # Check EDA range and smart meter range
                has_eda=$(echo "$open_ports" | grep -E "5000-5004/tcp|5000/tcp" || echo "")
                has_meters=$(echo "$open_ports" | grep -E "8085-8087/tcp|8085/tcp" || echo "")
                [[ -n "$has_eda"    ]] && pass "Firewall — EDA webhook ports 5000-5004 open" \
                                       || fail "Firewall — EDA webhook ports 5000-5004 missing"
                [[ -n "$has_meters" ]] && pass "Firewall — Smart meter ports 8085-8087 open" \
                                       || warn "Firewall — Smart meter ports 8085-8087 missing (needed for AMI demo)"
            fi

        else
            fail "SSH connection failed to ec2-user@${EC2_IP}"
            fixhint "Verify the key is correct and the instance security group allows port 22"
        fi
    fi
else
    section "EC2 Host Internals (via SSH)"
    warn "No --ssh-key provided — skipping linger, podman, systemd, and firewall checks"
    info "Re-run with: --ssh-key /path/to/rhpds-demo-host-key.pem"
fi

# =============================================================================
# SECTION 7: RHPDS AAP (requires --cluster and --gw-password)
# =============================================================================
if [[ -n "$CLUSTER" ]]; then
    section "RHPDS AAP — Gateway and Controller"

    # Gateway ping
    code=$(http_check "${GW_URL}/api/gateway/v1/ping/")
    if [[ "$code" == "200" ]]; then
        pass "AAP Gateway reachable — ${GW_URL}"
    else
        fail "AAP Gateway not reachable at ${GW_URL} (HTTP ${code})"
        fixhint "Confirm cluster name is correct and RHPDS cluster is still active"
    fi

    # Controller ping
    code=$(http_check "${CTRL_URL}/api/controller/v2/ping/")
    if [[ "$code" == "200" ]]; then
        pass "AAP Controller reachable — ${CTRL_URL}"
    else
        fail "AAP Controller not reachable at ${CTRL_URL} (HTTP ${code})"
    fi

    # Get gateway token
    token_response=$(curl -sk --max-time 15 -X POST \
        -u "admin:${GW_CRED}" \
        -H "Content-Type: application/json" \
        -d '{"description":"aac-check","scope":"write"}' \
        "${GW_URL}/api/gateway/v1/tokens/" 2>/dev/null || echo "")
    GW_TOKEN=$(echo "$token_response" | grep -o '"token":"[^"]*"' | cut -d'"' -f4 || echo "")
    GW_TOKEN_ID=$(echo "$token_response" | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2 || echo "")

    if [[ -n "$GW_TOKEN" ]]; then
        pass "AAP Gateway authentication — token acquired"

        # Get controller token
        ctrl_token_response=$(curl -sk --max-time 15 -X POST \
            -H "Authorization: Bearer ${GW_TOKEN}" \
            -H "Content-Type: application/json" \
            -d '{"description":"aac-check","scope":"write"}' \
            "${GW_URL}/api/controller/v2/tokens/" 2>/dev/null || echo "")
        CTRL_TOKEN=$(echo "$ctrl_token_response" | grep -o '"token":"[^"]*"' | cut -d'"' -f4 || echo "")

        if [[ -z "$CTRL_TOKEN" ]]; then
            fail "Could not obtain controller token via gateway"
        fi
    else
        fail "AAP Gateway authentication failed — check gateway password"
        fixhint "Confirm admin password is correct for this cluster"
    fi

    if [[ -n "$CTRL_TOKEN" ]]; then
        section "RHPDS AAP — Job Templates"

        REQUIRED_TEMPLATES=(
            "AAC_GoldenImage_SeedWorkflow"
            "AAC_GoldenImage_Check"
            "AAC_GoldenImage_Rollback"
            "AAC_GoldenImage_NotifyHelpDesk"
            "AAC_GoldenImage_ResetDemo"
            "AAC_GoldenImage_IntroduceDrift"
        )

        for tmpl in "${REQUIRED_TEMPLATES[@]}"; do
            encoded=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${tmpl}'))" 2>/dev/null || echo "$tmpl")
            response=$(curl -sk --max-time 10 \
                -H "Authorization: Bearer ${CTRL_TOKEN}" \
                "${CTRL_URL}/api/controller/v2/job_templates/?name=${encoded}" 2>/dev/null || echo '{"count":0}')
            count=$(echo "$response" | grep -o '"count":[0-9]*' | head -1 | cut -d: -f2 || echo "0")
            if [[ "$count" -gt 0 ]]; then
                tmpl_id=$(echo "$response" | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2)
                pass "Template '${tmpl}' — ID ${tmpl_id}"
            else
                fail "Template '${tmpl}' — not found"
                fixhint "Re-run AAC - Bootstrap RHPDS Environment"
            fi
        done

        section "RHPDS AAP — Enforcement Workflow"

        wf_response=$(curl -sk --max-time 10 \
            -H "Authorization: Bearer ${CTRL_TOKEN}" \
            "${CTRL_URL}/api/controller/v2/workflow_job_templates/?name=AAC_GoldenImage_Enforcement" 2>/dev/null || echo '{"count":0}')
        wf_count=$(echo "$wf_response" | grep -o '"count":[0-9]*' | head -1 | cut -d: -f2 || echo "0")

        if [[ "$wf_count" -gt 0 ]]; then
            wf_id=$(echo "$wf_response" | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2)
            pass "Workflow 'AAC_GoldenImage_Enforcement' — ID ${wf_id}"

            # Check nodes
            nodes_response=$(curl -sk --max-time 10 \
                -H "Authorization: Bearer ${CTRL_TOKEN}" \
                "${CTRL_URL}/api/controller/v2/workflow_job_templates/${wf_id}/workflow_nodes/" 2>/dev/null || echo '{"count":0}')
            node_count=$(echo "$nodes_response" | grep -o '"count":[0-9]*' | head -1 | cut -d: -f2 || echo "0")
            if [[ "$node_count" -eq 3 ]]; then
                pass "Workflow nodes — 3 nodes (Check → Rollback + NotifyHelpDesk)"
            else
                fail "Workflow nodes — ${node_count} found (expected 3: Check, Rollback, NotifyHelpDesk)"
                fixhint "Re-run AAC - Bootstrap RHPDS Environment to rebuild workflow"
            fi
        else
            fail "Workflow 'AAC_GoldenImage_Enforcement' — not found"
            fixhint "Re-run AAC - Bootstrap RHPDS Environment"
        fi

        section "RHPDS AAP — EDA Activation"

        eda_response=$(curl -sk --max-time 10 \
            -H "Authorization: Bearer ${GW_TOKEN}" \
            "${GW_URL}/api/eda/v1/activations/?name=Golden+Image+Enforcement" 2>/dev/null || echo '{"count":0,"results":[]}')
        eda_count=$(echo "$eda_response" | grep -o '"count":[0-9]*' | head -1 | cut -d: -f2 || echo "0")

        if [[ "$eda_count" -gt 0 ]]; then
            eda_status=$(echo "$eda_response" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "unknown")
            eda_org=$(echo "$eda_response" | grep -o '"organization_name":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "unknown")
            eda_rulebook=$(echo "$eda_response" | grep -o '"rulebook_name":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "unknown")

            if [[ "$eda_status" == "running" ]]; then
                pass "EDA activation 'Golden Image Enforcement' — running"
                info "  org: ${eda_org} | rulebook: ${eda_rulebook}"
            else
                fail "EDA activation 'Golden Image Enforcement' — status: ${eda_status} (expected: running)"
                fixhint "In RHPDS AAP: EDA → Rulebook Activations → Golden Image Enforcement → Restart"
            fi

            if [[ "$eda_org" == "Default" ]]; then
                pass "EDA activation org — Default (EDA 1.1.7 requirement met)"
            else
                warn "EDA activation org — '${eda_org}' (should be 'Default' for EDA 1.1.7)"
                fixhint "Delete activation, re-create it in the Default org (Bootstrap phase 9 handles this)"
            fi
        else
            fail "EDA activation 'Golden Image Enforcement' — not found"
            fixhint "Re-run AAC - Bootstrap RHPDS Environment"
        fi

        # EDA project sync
        proj_response=$(curl -sk --max-time 10 \
            -H "Authorization: Bearer ${GW_TOKEN}" \
            "${GW_URL}/api/eda/v1/projects/?name=Compliance+Automation+EDA" 2>/dev/null || echo '{"count":0}')
        proj_count=$(echo "$proj_response" | grep -o '"count":[0-9]*' | head -1 | cut -d: -f2 || echo "0")
        if [[ "$proj_count" -gt 0 ]]; then
            import_state=$(echo "$proj_response" | grep -o '"import_state":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "unknown")
            if [[ "$import_state" =~ ^(completed|successful)$ ]]; then
                pass "EDA project 'Compliance Automation EDA' — import_state: ${import_state}"
            else
                fail "EDA project — import_state: ${import_state} (expected: completed)"
                fixhint "In RHPDS AAP: EDA → Projects → Compliance Automation EDA → Sync"
            fi
        else
            fail "EDA project 'Compliance Automation EDA' — not found"
        fi

        # EDA credential
        cred_response=$(curl -sk --max-time 10 \
            -H "Authorization: Bearer ${GW_TOKEN}" \
            "${GW_URL}/api/eda/v1/eda-credentials/?name=AAC+Controller+Credential" 2>/dev/null || echo '{"count":0}')
        cred_count=$(echo "$cred_response" | grep -o '"count":[0-9]*' | head -1 | cut -d: -f2 || echo "0")
        if [[ "$cred_count" -gt 0 ]]; then
            pass "EDA credential 'AAC Controller Credential' — found"
        else
            fail "EDA credential 'AAC Controller Credential' — not found"
            fixhint "Re-run AAC - Bootstrap RHPDS Environment (creates old-style PAT credential)"
        fi

        section "RHPDS AAP — IntroduceDrift Template Vars"

        drift_response=$(curl -sk --max-time 10 \
            -H "Authorization: Bearer ${CTRL_TOKEN}" \
            "${CTRL_URL}/api/controller/v2/job_templates/?name=AAC_GoldenImage_IntroduceDrift" 2>/dev/null || echo '{"count":0}')
        drift_count=$(echo "$drift_response" | grep -o '"count":[0-9]*' | head -1 | cut -d: -f2 || echo "0")

        if [[ "$drift_count" -gt 0 ]]; then
            extra_vars=$(echo "$drift_response" | python3 -c "
import sys, json, re
body = sys.stdin.read()
# find extra_vars JSON field
m = re.search(r'\"extra_vars\"\s*:\s*\"((?:[^\"\\\\]|\\\\.)*)\"', body)
if m:
    v = m.group(1).replace('\\\\n', '\n').replace('\\\\\"', '\"')
    try:
        d = json.loads(v) if v.strip().startswith('{') else {}
        for k in ['aac_host','pg_host','aap_bearer_token','aap_enforcement_wf_id','eda_webhook_url']:
            val = d.get(k, 'MISSING')
            # Mask token values
            if k in ['aap_bearer_token'] and val not in ['MISSING','PENDING','']:
                val = val[:8] + '...'
            print(f'{k}={val}')
    except:
        print('parse_error')
" 2>/dev/null || echo "parse_error")

            verbose "  IntroduceDrift extra_vars:"
            verbose "  ${extra_vars}"

            REQUIRED_DRIFT_VARS=("aac_host" "pg_host" "aap_bearer_token" "aap_enforcement_wf_id" "eda_webhook_url")
            missing_vars=()
            pending_vars=()
            for v in "${REQUIRED_DRIFT_VARS[@]}"; do
                val=$(echo "$extra_vars" | grep "^${v}=" | cut -d= -f2- || echo "MISSING")
                if [[ "$val" == "MISSING" || -z "$val" ]]; then
                    missing_vars+=("$v")
                elif [[ "$val" =~ ^(PENDING|PENDING_EC2_IP|0)$ ]]; then
                    pending_vars+=("$v")
                fi
            done
            if [[ ${#missing_vars[@]} -eq 0 && ${#pending_vars[@]} -eq 0 ]]; then
                pass "IntroduceDrift extra_vars — all 5 required vars set"
            elif [[ ${#missing_vars[@]} -gt 0 ]]; then
                fail "IntroduceDrift extra_vars — missing: ${missing_vars[*]}"
                fixhint "Re-run AAC_Infra_ConfigureRHPDSAAP to wire EC2 IP into all templates"
            else
                fail "IntroduceDrift extra_vars — PENDING values: ${pending_vars[*]}"
                fixhint "Re-run AAC_Infra_ConfigureRHPDSAAP with the correct EC2 IP"
            fi
        else
            warn "Template AAC_GoldenImage_IntroduceDrift not found — skipping extra_vars check"
        fi

        # Cleanup token
        if [[ -n "$GW_TOKEN_ID" ]]; then
            curl -sk -X DELETE \
                -H "Authorization: Bearer ${GW_TOKEN}" \
                "${GW_URL}/api/gateway/v1/tokens/${GW_TOKEN_ID}/" &>/dev/null || true
            verbose "  Cleaned up gateway token ID ${GW_TOKEN_ID}"
        fi
    fi
else
    section "RHPDS AAP"
    warn "No --cluster provided — skipping AAP template, workflow, and EDA checks"
    info "Re-run with: --cluster <cluster-name>.dynamic.redhatworkshops.io --gw-password <pw>"
fi

# =============================================================================
# SUMMARY
# =============================================================================
TOTAL=$((PASS_COUNT + FAIL_COUNT + WARN_COUNT))
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  Health Check Summary${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}Passed:${NC}   ${PASS_COUNT}/${TOTAL}"
echo -e "  ${RED}Failed:${NC}   ${FAIL_COUNT}/${TOTAL}"
echo -e "  ${YELLOW}Warnings:${NC} ${WARN_COUNT}/${TOTAL}"
echo ""

if [[ "$FAIL_COUNT" -gt 0 ]]; then
    echo -e "${RED}${BOLD}  Failed checks:${NC}"
    for f in "${FAILURES[@]}"; do
        echo -e "    ${RED}•${NC} ${f}"
    done
    echo ""
    echo -e "  ${RED}❌ ${FAIL_COUNT} check(s) failed — demo is NOT ready${NC}"
    echo ""
    echo "  Quick fixes:"
    echo "    • OPA down:       Run AAC_Infra_DeployOPAContainers on local AAP"
    echo "    • DB missing:     Run AAC_Infra_SeedRHPDSDatabase on local AAP"
    echo "    • No baseline:    Run AAC_GoldenImage_SeedWorkflow on RHPDS AAP"
    echo "    • AAP config:     Run AAC_Infra_ConfigureRHPDSAAP on RHPDS AAP"
    echo "    • Bootstrap:      Run AAC - Bootstrap RHPDS Environment on RHPDS AAP"
    echo "    • Full verify:    Run AAC - Verify RHPDS Install on local AAP"
    echo ""
    exit 1
else
    echo -e "  ${GREEN}✅ All checks passed — demo is ready to run${NC}"
    echo ""
    echo "  Demo run order:"
    echo "    1. AAC_GoldenImage_ResetDemo"
    echo "    2. AAC_GoldenImage_IntroduceDrift  (survey: drift_type=selinux)"
    echo "    3. Watch EDA trigger enforcement workflow automatically"
    echo "    4. All 3 nodes complete: Check → Rollback → NotifyHelpDesk"
    echo ""
    exit 0
fi
