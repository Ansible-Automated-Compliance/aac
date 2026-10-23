#!/bin/bash
#
# install_postgres.sh — Deploy PostgreSQL for AAC Compliance Data Storage
#
# Two modes:
#   (default) Deploy a local PostgreSQL 15 container and (optionally) init schema.
#   (--pg-host) EXTERNAL mode — deploy NO container; init the schema against an
#               existing PostgreSQL 15+ instance (e.g. a customer's managed DB).
#
# PostgreSQL 15+ is required (JSONB + GIN). Stores historical assessment data.
#
# Usage: ./install_postgres.sh [OPTIONS]
#   --password PASSWORD   DB password for the admin/owner user (prompted if omitted)
#   --init-schema         Initialize the compliance schema (compliance_results +
#                         compliance_reader role)
#   --pg-host HOST        EXTERNAL DB host. When set, no container is deployed;
#                         the schema is initialized against HOST over the network.
#   --pg-port PORT        DB port (default: 5432)
#   --pg-user USER        Admin/owner login (default: postgres)
#   --pg-image IMAGE      PostgreSQL image for the local-container mode
#                         (default: registry.redhat.io/rhel9/postgresql-15)
#   --reader-password PW  Password for the read-only compliance_reader role
#   --help                Show this help message
#
# Local container details (default mode):
#   Name: postgresql | Port: 5432 | User: postgres | Database: compliance
#
# NOTE: the authoritative, full schema (11 tables) is created by the
# aac_compliance_db AAP role. This script initializes the primary
# compliance_results table + the compliance_reader role as a bootstrap;
# run the AAP role/template for the complete schema.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PG_CONTAINER_NAME="postgresql"
# registry.access.redhat.com/ubi9/postgresql-15 does NOT exist (wrong path/tag).
# Default to the Red Hat rhel9 image (needs `podman login registry.redhat.io`).
# For an unsubscribed host, override with: --pg-image docker.io/postgres:15
PG_IMAGE="registry.redhat.io/rhel9/postgresql-15"
PG_VOLUME="compliance_pgdata"
PG_PORT=5432
PG_USER="postgres"
PG_DATABASE="compliance"
PG_PASSWORD=""
PG_HOST=""            # empty = local container mode; set = external DB mode
READER_PASSWORD=""
INIT_SCHEMA=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --password) PG_PASSWORD=$2; shift 2 ;;
        --init-schema) INIT_SCHEMA=true; shift ;;
        --pg-host) PG_HOST=$2; shift 2 ;;
        --pg-port) PG_PORT=$2; shift 2 ;;
        --pg-user) PG_USER=$2; shift 2 ;;
        --pg-image) PG_IMAGE=$2; shift 2 ;;
        --reader-password) READER_PASSWORD=$2; shift 2 ;;
        --help) sed -n '3,29p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

# EXTERNAL DB mode implies schema init (there's nothing else to do).
[ -n "$PG_HOST" ] && INIT_SCHEMA=true

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

EXTERNAL_DB=false
[ -n "$PG_HOST" ] && EXTERNAL_DB=true

# Verify podman is available (needed for the container in local mode, and for a
# throwaway psql client in external mode).
if ! command -v podman &>/dev/null; then
    log_error "podman is required but not found. Install podman first."
    exit 1
fi

# Prompt for password if not provided
if [ -z "$PG_PASSWORD" ]; then
    echo -n "Enter database password for user '${PG_USER}': "
    read -s PG_PASSWORD
    echo ""
    if [ -z "$PG_PASSWORD" ]; then
        log_error "Password cannot be empty"
        exit 1
    fi
fi

# Run a SQL heredoc against either the local container (podman exec) or the
# external host (throwaway psql client container). Reads SQL from stdin.
run_psql() {
    local db="${1:-$PG_DATABASE}"
    if $EXTERNAL_DB; then
        # PGPASSWORD is exported (unquoted assignment) and passed through by name
        # so no secret literal appears inline.
        export PGPASSWORD=$PG_PASSWORD
        podman run --rm -i -e PGPASSWORD "$PG_IMAGE" \
            psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$db"
    else
        podman exec -i "$PG_CONTAINER_NAME" psql -U "$PG_USER" -d "$db"
    fi
}

# Initialize the bootstrap schema (primary table + read-only role). The full
# 11-table schema is created by the aac_compliance_db AAP role.
init_schema() {
    log_info "Initializing compliance schema on ${PG_HOST:-$PG_CONTAINER_NAME}/${PG_DATABASE}..."

    # No default reader password. A shipped default is a password every
    # deployment shares, and this role is what Grafana authenticates with.
    if [[ -z "${READER_PASSWORD:-}" ]]; then
        log_error "READER_PASSWORD is not set."
        echo "       Pass --reader-password <value>, or export READER_PASSWORD." >&2
        return 1
    fi
    # Double any single quote: the value lands inside a SQL string literal, and
    # a generated password containing ' would otherwise terminate the literal
    # early and break the statement (or worse). '' is the SQL standard escape.
    local reader_password_sql=${READER_PASSWORD//\'/\'\'}

    run_psql "$PG_DATABASE" << EOSQL
-- Ansible Automated Compliance (AAC) — bootstrap schema
CREATE TABLE IF NOT EXISTS compliance_results (
    id                    SERIAL PRIMARY KEY,
    hostname              VARCHAR(255),
    ip_address            VARCHAR(45),
    framework             VARCHAR(100) NOT NULL,
    policy_name           VARCHAR(255),
    policy_version        VARCHAR(100),
    total_controls        INTEGER,
    passed_controls       INTEGER,
    failed_controls       INTEGER,
    compliance_percentage DECIMAL(5,2),
    compliant             BOOLEAN,
    violations            JSONB,
    metadata              JSONB,
    evaluation_timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    facts_id              INTEGER
);
CREATE INDEX IF NOT EXISTS idx_results_hostname   ON compliance_results(hostname);
CREATE INDEX IF NOT EXISTS idx_results_framework  ON compliance_results(framework);
CREATE INDEX IF NOT EXISTS idx_results_timestamp  ON compliance_results(evaluation_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_results_compliant  ON compliance_results(compliant);

-- Read-only role used by Grafana / reporting
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'compliance_reader') THEN
    CREATE ROLE compliance_reader LOGIN PASSWORD '${reader_password_sql}';
  END IF;
END \$\$;
GRANT CONNECT ON DATABASE ${PG_DATABASE} TO compliance_reader;
GRANT USAGE ON SCHEMA public TO compliance_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO compliance_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO compliance_reader;

SELECT 'AAC bootstrap schema initialized' AS status;
EOSQL
    log_info "Schema initialized"
}

echo "=============================================="
echo "  AAC — PostgreSQL ($([ "$EXTERNAL_DB" = true ] && echo external || echo local container))"
echo "=============================================="
echo ""

if $EXTERNAL_DB; then
    # ── EXTERNAL DB mode: no container; verify reachability then init schema ──
    log_info "External PostgreSQL: ${PG_HOST}:${PG_PORT} (user ${PG_USER}, db ${PG_DATABASE})"
    if ! echo '\q' | run_psql postgres >/dev/null 2>&1; then
        log_error "Cannot reach ${PG_HOST}:${PG_PORT} as ${PG_USER}. Check host/port/creds/firewall (5432)."
        exit 1
    fi
    # Create the compliance database if the admin login can, and it's absent.
    echo "SELECT 1 FROM pg_database WHERE datname='${PG_DATABASE}';" | run_psql postgres 2>/dev/null | grep -q 1 \
        || echo "CREATE DATABASE ${PG_DATABASE};" | run_psql postgres 2>/dev/null \
        || log_warn "Could not auto-create '${PG_DATABASE}' — ensure it exists on the external DB."
    init_schema
else
    # ── LOCAL CONTAINER mode ──
    if podman ps -a --format '{{.Names}}' | grep -q "^${PG_CONTAINER_NAME}$"; then
        log_warn "Existing container found: ${PG_CONTAINER_NAME}"
        read -rp "  Remove and redeploy? [y/N] " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            log_info "Stopping and removing existing container..."
            podman stop "$PG_CONTAINER_NAME" 2>/dev/null || true
            podman rm "$PG_CONTAINER_NAME" 2>/dev/null || true
        else
            log_info "Skipping deployment — using existing container"
            $INIT_SCHEMA && init_schema
            exit 0
        fi
    fi

    log_info "Pulling PostgreSQL image: ${PG_IMAGE}"
    podman pull "$PG_IMAGE" -q

    log_info "Starting PostgreSQL container..."
    export POSTGRES_PASSWORD=$PG_PASSWORD
    podman run -d \
        --name "$PG_CONTAINER_NAME" \
        -p "${PG_PORT}:5432" \
        -e POSTGRES_PASSWORD \
        -e POSTGRES_DB="$PG_DATABASE" \
        -v "${PG_VOLUME}:/var/lib/postgresql/data" \
        --restart=always \
        "$PG_IMAGE"
    unset POSTGRES_PASSWORD

    log_info "Waiting for PostgreSQL to start..."
    for i in {1..60}; do
        if podman exec "$PG_CONTAINER_NAME" pg_isready -U "$PG_USER" >/dev/null 2>&1; then
            log_info "PostgreSQL is ready"; break
        fi
        sleep 1
        if [ $i -eq 60 ]; then
            log_error "PostgreSQL failed to start — check: podman logs ${PG_CONTAINER_NAME}"
            exit 1
        fi
    done

    $INIT_SCHEMA && init_schema
fi

echo ""
echo "=============================================="
echo "  PostgreSQL Ready"
echo "=============================================="
echo ""
if $EXTERNAL_DB; then
echo "Mode:       EXTERNAL (no container deployed)"
echo "Host:       ${PG_HOST}:${PG_PORT}"
else
echo "Mode:       local container (${PG_CONTAINER_NAME})"
echo "Host:       localhost:${PG_PORT}"
echo "Verify:     podman exec ${PG_CONTAINER_NAME} pg_isready -U ${PG_USER}"
fi
echo "User:       ${PG_USER}"
echo "Database:   ${PG_DATABASE}"
echo ""
echo "For the COMPLETE schema (11 tables), initialize via AAP:"
echo "  Run job template: 'AAC - Initialize PostgreSQL Database'"
echo "  (this script created the bootstrap compliance_results + compliance_reader)"
echo ""
