#!/bin/bash
#
# install.sh — Ansible Automated Compliance (AAC) Setup
#
# Deploys AAC components on a server that already has AAP 2.6 installed.
# This script handles the infrastructure that runs alongside AAP:
#   - Three OPA containers (security, compliance, OT)
#   - PostgreSQL compliance database
#
# AAP itself must be installed first via the Red Hat containerized installer:
#   https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/containerized_installation
#
# Usage: ./install.sh [OPTIONS]
#   --opa-only           Deploy OPA containers only
#   --postgres-only      Deploy PostgreSQL only
#   --skip-postgres      Skip PostgreSQL deployment
#   --pg-password PW     DB password for the admin/owner user (prompted if omitted)
#   --init-schema        Initialize the compliance schema after deploy
#   --pg-host HOST       EXTERNAL PostgreSQL host — deploy no container; init the
#                        schema against an existing DB (e.g. a customer's managed DB)
#   --pg-port PORT       DB port (default: 5432)
#   --pg-user USER       DB admin/owner login (default: postgres)
#   --reader-password PW Password for the read-only compliance_reader role
#   --configure-aap      Also configure AAP (project, templates, run bootstrap)
#   --aap-host HOST      AAP hostname/IP for --configure-aap (default: localhost)
#   --aap-user USER      AAP admin user for --configure-aap (default: admin)
#   --aap-password PASS  AAP admin password for --configure-aap
#   --help               Show this help message
#
# One-command full install (local DB):
#   ./install.sh --pg-password MyPGPass --init-schema \
#                --configure-aap --aap-password MyAAPPass
#
# External-DB install (no PostgreSQL container — schema only):
#   ./install.sh --pg-host db.example.com --pg-user aac_admin \
#                --pg-password MyPGPass --reader-password MyReadPass

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_OPA=true
DEPLOY_POSTGRES=true
INIT_SCHEMA=false
PG_PASSWORD=""
PG_HOST=""
PG_PORT=""
PG_USER=""
READER_PASSWORD=""
CONFIGURE_AAP=false
AAP_HOST="localhost"
AAP_USER="admin"
AAP_PASS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --opa-only)        DEPLOY_POSTGRES=false; shift ;;
        --postgres-only)   DEPLOY_OPA=false; shift ;;
        --skip-postgres)   DEPLOY_POSTGRES=false; shift ;;
        --pg-password)     PG_PASSWORD=$2; shift 2 ;;
        --init-schema)     INIT_SCHEMA=true; shift ;;
        --pg-host)         PG_HOST=$2; shift 2 ;;
        --pg-port)         PG_PORT=$2; shift 2 ;;
        --pg-user)         PG_USER=$2; shift 2 ;;
        --reader-password) READER_PASSWORD=$2; shift 2 ;;
        --configure-aap)   CONFIGURE_AAP=true; shift ;;
        --aap-host)        AAP_HOST=$2; shift 2 ;;
        --aap-user)        AAP_USER=$2; shift 2 ;;
        --aap-password)    AAP_PASS=$2; shift 2 ;;
        --help)            sed -n '3,35p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

log_info()    { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_section() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║        Ansible Automated Compliance (AAC) Setup          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  This script deploys AAC infrastructure alongside AAP."
echo "  AAP 2.6 must already be installed and running."
echo ""

# ─── Prerequisites ────────────────────────────────────────────────────────────
log_section "Prerequisites"

# Podman is required
if ! command -v podman &>/dev/null; then
    log_error "podman is required but not found."
    echo "  Install podman: dnf install -y podman"
    exit 1
fi
log_info "podman: $(podman --version)"

# curl is required
if ! command -v curl &>/dev/null; then
    log_error "curl is required but not found."
    echo "  Install curl: dnf install -y curl"
    exit 1
fi
log_info "curl: OK"

# Check AAP is reachable
if curl -sk https://localhost/api/gateway/v1/ping/ >/dev/null 2>&1; then
    log_info "AAP Gateway: reachable"
else
    log_warn "AAP Gateway not responding at https://localhost — continuing anyway"
    log_warn "Ensure AAP is installed before running AAP job templates"
fi

# ─── OPA Containers ───────────────────────────────────────────────────────────
if $DEPLOY_OPA; then
    log_section "OPA Containers"
    "$SCRIPT_DIR/install_opa.sh"
fi

# ─── PostgreSQL ───────────────────────────────────────────────────────────────
if $DEPLOY_POSTGRES; then
    log_section "PostgreSQL"
    PG_ARGS=""
    [ -n "$PG_PASSWORD" ]     && PG_ARGS="$PG_ARGS --password $PG_PASSWORD"
    [ -n "$PG_HOST" ]         && PG_ARGS="$PG_ARGS --pg-host $PG_HOST"
    [ -n "$PG_PORT" ]         && PG_ARGS="$PG_ARGS --pg-port $PG_PORT"
    [ -n "$PG_USER" ]         && PG_ARGS="$PG_ARGS --pg-user $PG_USER"
    [ -n "$READER_PASSWORD" ] && PG_ARGS="$PG_ARGS --reader-password $READER_PASSWORD"
    $INIT_SCHEMA              && PG_ARGS="$PG_ARGS --init-schema"
    "$SCRIPT_DIR/install_postgres.sh" $PG_ARGS
fi

# ─── Configure AAP (optional) ─────────────────────────────────────────────────
if $CONFIGURE_AAP; then
    echo ""
    echo -e "${BLUE}━━━ AAP Configuration ━━━${NC}"
    AAP_ARGS="--aap-host ${AAP_HOST} --aap-user ${AAP_USER}"
    [ -n "$AAP_PASS" ] && AAP_ARGS="$AAP_ARGS --aap-password ${AAP_PASS}"
    "$SCRIPT_DIR/configure_aap.sh" $AAP_ARGS
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║               AAC Infrastructure Ready                   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Services deployed:"
if $DEPLOY_OPA; then
echo "    OPA Security   → http://localhost:8181"
echo "    OPA Compliance → http://localhost:8182"
echo "    OPA OT         → http://localhost:8183"
fi
if $DEPLOY_POSTGRES; then
if [ -n "$PG_HOST" ]; then
echo "    PostgreSQL     → ${PG_HOST}:${PG_PORT:-5432} (external, db: compliance)"
else
echo "    PostgreSQL     → localhost:5432 (db: compliance)"
fi
fi
echo ""
if ! $CONFIGURE_AAP; then
echo "  Next steps in AAP — OR run in one shot with --configure-aap:"
echo ""
echo "    1. Add this git repo as an AAP Project"
echo "       URL: https://github.com/ansible-automated-compliance/aac.git"
echo ""
echo "    2. Run: 'AAC - Initialize PostgreSQL Database' (full 11-table schema)"
echo "    3. Run: 'AAC - Load OPA Policies'              (loads all policies)"
echo "    4. Verify: scripts/verify_installation.sh      (GO/NO-GO check)"
echo ""
fi
echo "  Verify now:"
echo "    curl http://localhost:8181/health   # OPA Security"
echo "    curl http://localhost:8182/health   # OPA Compliance"
echo "    curl http://localhost:8183/health   # OPA OT"
echo ""
