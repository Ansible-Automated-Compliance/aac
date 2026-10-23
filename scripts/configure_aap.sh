#!/bin/bash
#
# configure_aap.sh — Automatically configure AAP for Ansible Automated Compliance
#
# Run AFTER install.sh (OPA + PostgreSQL deployed) and AAP 2.6 is installed.
# Automates all AAP configuration steps via the Controller REST API:
#
#   1. Authenticate and create an API token
#   2. Create the AAC project (git sync)
#   3. Wait for project sync to complete
#   4. Create core bootstrap job templates
#   5. Run: Load OPA Policies → Demo Stability Setup → Seed Sentinel Templates
#   6. Run: AAC Verify Installation (final GO/NO-GO)
#
# Usage:
#   ./configure_aap.sh [OPTIONS]
#
#   --aap-host HOST      AAP server IP or hostname (default: localhost)
#   --aap-user USER      AAP admin username (default: admin)
#   --aap-password PASS  AAP admin password (prompted if omitted)
#   --git-repo URL       Git repo URL (default: https://github.com/ansible-automated-compliance/aac.git)
#   --git-branch BRANCH  Git branch (default: main)
#   --skip-run           Create templates but do not run them
#   --dry-run            Show what would be created without making changes
#   --help               Show this help message

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ─── Defaults ─────────────────────────────────────────────────────────────────
AAP_HOST="localhost"
AAP_USER="admin"
AAP_PASS=""
GIT_REPO="https://github.com/ansible-automated-compliance/aac.git"
GIT_BRANCH="main"
SKIP_RUN=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --aap-host)      AAP_HOST=$2;   shift 2 ;;
        --aap-user)      AAP_USER=$2;   shift 2 ;;
        --aap-password)  AAP_PASS=$2;   shift 2 ;;
        --git-repo)      GIT_REPO=$2;   shift 2 ;;
        --git-branch)    GIT_BRANCH=$2; shift 2 ;;
        --skip-run)      SKIP_RUN=true; shift ;;
        --dry-run)       DRY_RUN=true;  shift ;;
        --help)          head -26 "$0" | tail -24; exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

log_info()    { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_section() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }
log_step()    { echo -e "${CYAN}  ▶${NC} $1"; }
log_ok()      { echo -e "${GREEN}  ✓${NC} $1"; }

AAP_URL="https://${AAP_HOST}"
CTRL_API="${AAP_URL}/api/controller/v2"
GW_API="${AAP_URL}/api/gateway/v1"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          AAC — Configure Ansible Automation Platform     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  AAP Host:   ${AAP_HOST}"
echo "  Git Repo:   ${GIT_REPO}"
echo "  Git Branch: ${GIT_BRANCH}"
$DRY_RUN && echo -e "  ${YELLOW}DRY RUN mode — no changes will be made${NC}"
echo ""

# ─── Helper: AAP API call ─────────────────────────────────────────────────────
aap_get()  { curl -sk -H "Authorization: Bearer ${AAP_TOKEN}" "${CTRL_API}$1"; }
aap_post() { curl -sk -X POST -H "Authorization: Bearer ${AAP_TOKEN}" \
                  -H "Content-Type: application/json" -d "$2" "${CTRL_API}$1"; }

# ─── Helper: Wait for job ─────────────────────────────────────────────────────
wait_for_job() {
    local job_id=$1 label=$2
    local elapsed=0 max=300
    echo -ne "  ⏳ Waiting for ${label} (job ${job_id})"
    while [[ $elapsed -lt $max ]]; do
        sleep 5; elapsed=$((elapsed + 5))
        local status
        status=$(aap_get "/jobs/${job_id}/" | python3 -c \
            "import sys,json; print(json.load(sys.stdin).get('status','unknown'))")
        echo -ne "."
        case $status in
            successful) echo -e " ${GREEN}✓ done${NC}"; return 0 ;;
            failed|error|canceled)
                echo -e " ${RED}✗ ${status}${NC}"
                log_error "Job ${job_id} (${label}) ${status}"
                return 1 ;;
        esac
    done
    echo -e " ${YELLOW}⚠ timed out after ${max}s${NC}"
    return 1
}

# ─── Step 1: Prompt for password if needed ────────────────────────────────────
log_section "Authentication"

if [[ -z "$AAP_PASS" ]]; then
    read -r -s -p "  AAP admin password: " AAP_PASS
    echo ""
fi

if $DRY_RUN; then
    log_ok "Dry run — skipping token creation"
    AAP_TOKEN=DRYRUN_PLACEHOLDER  # placeholder only — never sent to AAP
else
    log_step "Creating API token for ${AAP_USER}..."
    token_resp=$(curl -sk -X POST \
        -u "${AAP_USER}:${AAP_PASS}" \
        -H "Content-Type: application/json" \
        -d '{"description":"AAC Installer Token","scope":"write"}' \
        "${GW_API}/tokens/")

    AAP_TOKEN=$(echo "$token_resp" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); print(d.get('token',''))" 2>/dev/null)
    TOKEN_ID=$(echo "$token_resp" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null)

    if [[ -z "$AAP_TOKEN" ]]; then
        log_error "Failed to create token. Check your AAP admin credentials."
        echo "  Response: ${token_resp}" | head -3
        exit 1
    fi
    log_ok "Token created (ID: ${TOKEN_ID})"
fi

# ─── Step 2: Resolve org and EE IDs ──────────────────────────────────────────
log_section "Resolving AAP Object IDs"

if ! $DRY_RUN; then
    ORG_ID=$(aap_get "/organizations/?name=Default" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] else 1)" 2>/dev/null)
    log_ok "Organization ID: ${ORG_ID}"

    EE_ID=$(aap_get "/execution_environments/?name=AAC+Compliance+EE" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] else '')" 2>/dev/null)
    if [[ -z "$EE_ID" ]]; then
        # Fall back to default EE
        EE_ID=$(aap_get "/execution_environments/?name=Default+execution+environment" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] else 4)" 2>/dev/null)
        log_warn "AAC Compliance EE not found — using default EE (ID: ${EE_ID})"
    else
        log_ok "Execution Environment: AAC Compliance EE (ID: ${EE_ID})"
    fi
else
    ORG_ID=1; EE_ID=6
    log_ok "Dry run — using placeholder IDs (org=1, ee=6)"
fi

# ─── Step 3: Create or find the AAC project ──────────────────────────────────
log_section "AAC Git Project"

if $DRY_RUN; then
    log_ok "Dry run — would create project: Compliance Automation → ${GIT_REPO}"
    PROJECT_ID=11
else
    existing_project=$(aap_get "/projects/?name=Compliance+Automation" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] else '')" 2>/dev/null)

    if [[ -n "$existing_project" ]]; then
        PROJECT_ID=$existing_project
        log_ok "Project already exists (ID: ${PROJECT_ID}) — triggering sync"
        aap_post "/projects/${PROJECT_ID}/update/" "{}" >/dev/null
    else
        log_step "Creating project: Compliance Automation"
        project_resp=$(aap_post "/projects/" "$(python3 -c "import json; print(json.dumps({
            'name': 'Compliance Automation',
            'description': 'Ansible Automated Compliance (AAC) — Policy-as-Code compliance at enterprise scale',
            'scm_type': 'git',
            'scm_url': '${GIT_REPO}',
            'scm_branch': '${GIT_BRANCH}',
            'scm_update_on_launch': False,
            'organization': ${ORG_ID}
        }))")")
        PROJECT_ID=$(echo "$project_resp" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null)
        if [[ -z "$PROJECT_ID" ]]; then
            log_error "Failed to create project. Response:"
            echo "$project_resp" | python3 -m json.tool 2>/dev/null | head -10
            exit 1
        fi
        log_ok "Project created (ID: ${PROJECT_ID})"
    fi

    # Wait for sync
    log_step "Waiting for project sync..."
    elapsed=0; max=180
    echo -ne "  ⏳ Syncing"
    while [[ $elapsed -lt $max ]]; do
        sleep 5; elapsed=$((elapsed + 5))
        sync_status=$(aap_get "/projects/${PROJECT_ID}/" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(d.get('status','pending'))" 2>/dev/null)
        echo -ne "."
        case $sync_status in
            successful) echo -e " ${GREEN}✓ synced${NC}"; break ;;
            failed)     echo -e " ${RED}✗ sync failed${NC}"; exit 1 ;;
        esac
        [[ $elapsed -ge $max ]] && { echo -e " ${YELLOW}⚠ timed out${NC}"; exit 1; }
    done
fi

# ─── Step 4: Find or create the localhost inventory ──────────────────────────
log_section "Inventory"

if $DRY_RUN; then
    log_ok "Dry run — using placeholder inventory ID 4"
    INV_ID=4
else
    INV_ID=$(aap_get "/inventories/?name=localhost" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] else '')" 2>/dev/null)

    if [[ -z "$INV_ID" ]]; then
        log_step "Creating 'localhost' inventory"
        inv_resp=$(aap_post "/inventories/" "$(python3 -c "import json; print(json.dumps({
            'name': 'localhost',
            'description': 'Local controller execution',
            'organization': ${ORG_ID}
        }))")")
        INV_ID=$(echo "$inv_resp" | python3 -c \
            "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

        # Add localhost host
        aap_post "/inventories/${INV_ID}/hosts/" "$(python3 -c "import json; print(json.dumps({
            'name': 'localhost',
            'variables': 'ansible_connection: local\nansible_python_interpreter: /usr/bin/python3'
        }))")" >/dev/null
        log_ok "Inventory created (ID: ${INV_ID}) with localhost host"
    else
        log_ok "Inventory 'localhost' exists (ID: ${INV_ID})"
    fi
fi

# ─── Step 5: Create bootstrap job templates ───────────────────────────────────
log_section "Bootstrap Job Templates"

# Template definitions: "name|playbook|description"
declare -a TEMPLATES=(
    "AAC - Load OPA Policies|ansible/playbooks/load_opa_policies.yml|Load all policies from git into OPA containers (security/compliance/ot)"
    "AAC - Deploy OPA Containers|ansible/playbooks/deploy_opa_containers.yml|Recreate all three OPA containers from scratch"
    "AAC - Seed Phase 2 Templates|ansible/playbooks/seed_phase2_templates.yml|Create AAC - Evaluate Stored Facts and related DB-evaluation templates"
    "AAC - Verify Installation|ansible/playbooks/verify_installation.yml|End-to-end GO/NO-GO validation of all AAC components"
)

declare -A TEMPLATE_IDS

for tpl_def in "${TEMPLATES[@]}"; do
    IFS='|' read -r tpl_name tpl_playbook tpl_desc <<< "$tpl_def"

    if $DRY_RUN; then
        log_ok "Would create: ${tpl_name}"
        continue
    fi

    existing=$(aap_get "/job_templates/?name=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${tpl_name}'))")" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] else '')" 2>/dev/null)

    if [[ -n "$existing" ]]; then
        log_ok "${tpl_name} already exists (ID: ${existing})"
        TEMPLATE_IDS["$tpl_name"]=$existing
    else
        log_step "Creating: ${tpl_name}"
        tpl_resp=$(aap_post "/job_templates/" "$(python3 -c "import json; print(json.dumps({
            'name': '${tpl_name}',
            'description': '${tpl_desc}',
            'job_type': 'run',
            'inventory': ${INV_ID},
            'project': ${PROJECT_ID},
            'playbook': '${tpl_playbook}',
            'execution_environment': ${EE_ID},
            'become_enabled': False,
            'host_config_key': ''
        }))")")
        new_id=$(echo "$tpl_resp" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null)
        if [[ -n "$new_id" ]]; then
            log_ok "${tpl_name} created (ID: ${new_id})"
            TEMPLATE_IDS["$tpl_name"]=$new_id
        else
            log_warn "Failed to create ${tpl_name} — may already exist or playbook not found after sync"
        fi
    fi
done

# ─── Step 6: Run bootstrap templates in order ────────────────────────────────
if $SKIP_RUN || $DRY_RUN; then
    log_section "Skipping Template Execution"
    log_warn "Templates created but not launched. Run them manually in AAP in this order:"
    echo "    1. AAC - Load OPA Policies"
    echo "    2. AAC - Demo Stability Setup"
    echo "    3. AAC - Seed Sentinel Job Templates"
    echo "    4. AAC - Seed Sentinel Templates"
    echo "    5. AAC - Seed Phase 2 Templates"
    echo "    6. AAC - Seed AMI Templates"
    echo "    7. AAC - Verify Installation"
else
    log_section "Running Bootstrap Templates"

    # Run order: OPA policies first, then stability, then seed (which needs templates to exist), then verify
    declare -a RUN_ORDER=(
        "AAC - Load OPA Policies"
        "AAC - Demo Stability Setup"
        "AAC - Seed Sentinel Job Templates"
        "AAC - Seed Sentinel Templates"
        "AAC - Seed Phase 2 Templates"
        "AAC - Seed AMI Templates"
        "AAC - Verify Installation"
    )

    for tpl_name in "${RUN_ORDER[@]}"; do
        tpl_id=${TEMPLATE_IDS["$tpl_name"]}
        if [[ -z "$tpl_id" ]]; then
            log_warn "Skipping ${tpl_name} — no template ID (template may not exist)"
            continue
        fi
        log_step "Launching: ${tpl_name} (ID: ${tpl_id})"
        launch_resp=$(aap_post "/job_templates/${tpl_id}/launch/" "{}")
        job_id=$(echo "$launch_resp" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null)
        if [[ -z "$job_id" ]]; then
            log_warn "Could not launch ${tpl_name} — skipping"
            continue
        fi
        wait_for_job "$job_id" "$tpl_name" || log_warn "${tpl_name} did not complete successfully — continuing"
    done
fi

# ─── Step 7: Cleanup installer token ─────────────────────────────────────────
if ! $DRY_RUN && [[ -n "$TOKEN_ID" ]]; then
    curl -sk -X DELETE \
        -u "${AAP_USER}:${AAP_PASS}" \
        "${GW_API}/tokens/${TOKEN_ID}/" >/dev/null 2>&1 || true
    log_info "Installer token cleaned up"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║               AAC Configuration Complete                 ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  AAP Project:  Compliance Automation (synced from git)"
echo "  Templates:    ${#TEMPLATES[@]} bootstrap templates created"
echo ""
echo "  Access AAP at: ${AAP_URL}"
echo ""
echo "  Next: open AAP and explore job templates starting with 'AAC'"
echo "  Verify: run 'AAC - Verify Installation' anytime to check health"
echo ""
