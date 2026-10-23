#!/bin/bash
#
# backup.sh — AAC Backup and Validation
#
# Backs up AAC-specific components:
#   - Ansible Vault (encrypted secrets)
#   - PostgreSQL compliance database
#   - AAP installer inventory (if present)
#
# OPA policies do not need backup — git is their backup.
# AAP platform backup uses the Red Hat installer playbook (see INSTALL.md).
#
# Usage: ./backup.sh [OPTIONS]
#   --dest DIR            Backup destination directory (default: ~/aac-backups)
#   --vault-pass-file FILE Vault password file (default: ~/.vault_pass)
#   --skip-postgres       Skip PostgreSQL backup
#   --skip-vault          Skip Ansible Vault backup
#   --validate-only       Validate existing backups without creating new ones
#   --help                Show this help message
#
# Exit codes:
#   0 — Backup and validation successful
#   1 — One or more steps failed

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DEST="${HOME}/aac-backups"
VAULT_PASS_FILE="${HOME}/.vault_pass"
VAULT_FILE="${REPO_ROOT}/ansible/vars/vault_secrets.yml"
SKIP_POSTGRES=false
SKIP_VAULT=false
VALIDATE_ONLY=false

STEPS_PASSED=0
STEPS_FAILED=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --dest)             BACKUP_DEST="$2"; shift 2 ;;
        --vault-pass-file)  VAULT_PASS_FILE="$2"; shift 2 ;;
        --skip-postgres)    SKIP_POSTGRES=true; shift ;;
        --skip-vault)       SKIP_VAULT=true; shift ;;
        --validate-only)    VALIDATE_ONLY=true; shift ;;
        --help)             head -26 "$0" | tail -24; exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

section() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }
pass()    { echo -e "  ${GREEN}✅${NC} $1"; ((STEPS_PASSED++)); }
fail()    { echo -e "  ${RED}❌${NC} $1"; ((STEPS_FAILED++)); }
warn()    { echo -e "  ${YELLOW}⚠️ ${NC} $1"; }
info()    { echo -e "  ${BLUE}ℹ️ ${NC} $1"; }

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_DEST}/${TIMESTAMP}"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         Ansible Automated Compliance — Backup            ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Destination: ${BACKUP_DIR}"
echo "  Mode:        $([ "$VALIDATE_ONLY" = true ] && echo 'Validate existing backups' || echo 'Backup + validate')"

# ─── Create backup directory ──────────────────────────────────────────────────
if ! $VALIDATE_ONLY; then
    mkdir -p "$BACKUP_DIR"
    chmod 700 "$BACKUP_DIR"
fi

# ─── Ansible Vault ────────────────────────────────────────────────────────────
if ! $SKIP_VAULT; then
    section "Ansible Vault Backup"

    if $VALIDATE_ONLY; then
        # Validate most recent vault backup
        LATEST_VAULT=$(find "$BACKUP_DEST" -name "vault_secrets_*.yml" 2>/dev/null | sort | tail -1)
        if [[ -z "$LATEST_VAULT" ]]; then
            fail "No vault backup found in ${BACKUP_DEST}"
        else
            if head -1 "$LATEST_VAULT" | grep -q "\$ANSIBLE_VAULT"; then
                SIZE=$(wc -c < "$LATEST_VAULT")
                BACKUP_DATE=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$LATEST_VAULT" 2>/dev/null || \
                              stat -c "%y" "$LATEST_VAULT" 2>/dev/null | cut -d. -f1)
                pass "Vault backup valid: $(basename "$LATEST_VAULT") (${SIZE} bytes, ${BACKUP_DATE})"

                # Test decryption if vault-pass-file exists
                if [[ -f "$VAULT_PASS_FILE" ]] && command -v ansible-vault &>/dev/null; then
                    if ansible-vault view "$LATEST_VAULT" --vault-password-file "$VAULT_PASS_FILE" >/dev/null 2>&1; then
                        pass "Vault backup decryption: OK"
                    else
                        fail "Vault backup decryption failed — backup may be corrupt"
                    fi
                fi
            else
                fail "Vault backup is NOT encrypted: ${LATEST_VAULT}"
            fi
        fi
    else
        # Create vault backup
        if [[ ! -f "$VAULT_FILE" ]]; then
            fail "Vault file not found: ${VAULT_FILE}"
        else
            VAULT_BACKUP="${BACKUP_DIR}/vault_secrets_${TIMESTAMP}.yml"
            cp "$VAULT_FILE" "$VAULT_BACKUP"
            chmod 600 "$VAULT_BACKUP"

            # Verify it's encrypted
            if head -1 "$VAULT_BACKUP" | grep -q "\$ANSIBLE_VAULT"; then
                SIZE=$(wc -c < "$VAULT_BACKUP")
                pass "Vault backup created: ${VAULT_BACKUP} (${SIZE} bytes)"
            else
                fail "Vault backup is NOT encrypted — do not store this backup!"
                rm -f "$VAULT_BACKUP"
            fi

            # Validate decryption
            if [[ -f "$VAULT_PASS_FILE" ]] && command -v ansible-vault &>/dev/null; then
                if ansible-vault view "$VAULT_BACKUP" --vault-password-file "$VAULT_PASS_FILE" >/dev/null 2>&1; then
                    pass "Vault backup decryption: OK"
                else
                    fail "Vault backup decryption failed — check vault password file"
                fi
            else
                warn "Cannot validate decryption — ansible-vault or ${VAULT_PASS_FILE} not found"
            fi
        fi
    fi
fi

# ─── PostgreSQL ───────────────────────────────────────────────────────────────
if ! $SKIP_POSTGRES; then
    section "PostgreSQL Backup"

    if ! command -v podman &>/dev/null; then
        warn "podman not found — skipping PostgreSQL backup"
    elif ! podman ps --format '{{.Names}}' 2>/dev/null | grep -q "^postgresql$"; then
        warn "postgresql container not running — skipping PostgreSQL backup"
        echo "       Start it first: podman start postgresql"
    else
        if $VALIDATE_ONLY; then
            # Validate most recent PostgreSQL backup
            LATEST_PG=$(find "$BACKUP_DEST" -name "compliance_*.sql.gz" 2>/dev/null | sort | tail -1)
            if [[ -z "$LATEST_PG" ]]; then
                fail "No PostgreSQL backup found in ${BACKUP_DEST}"
            else
                SIZE=$(wc -c < "$LATEST_PG")
                BACKUP_DATE=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$LATEST_PG" 2>/dev/null || \
                              stat -c "%y" "$LATEST_PG" 2>/dev/null | cut -d. -f1)
                # Verify gzip integrity
                if gzip -t "$LATEST_PG" 2>/dev/null; then
                    pass "PostgreSQL backup valid: $(basename "$LATEST_PG") (${SIZE} bytes, ${BACKUP_DATE})"
                else
                    fail "PostgreSQL backup is corrupt: ${LATEST_PG}"
                fi

                # Check row count in backup
                ROW_HINT=$(zcat "$LATEST_PG" 2>/dev/null | grep -c "^INSERT INTO" || echo "0")
                if [[ "$ROW_HINT" -gt 0 ]]; then
                    pass "Backup contains data (${ROW_HINT} INSERT statements)"
                else
                    warn "Backup appears to have no data rows — database may be empty"
                fi
            fi
        else
            # Create PostgreSQL backup
            PG_BACKUP="${BACKUP_DIR}/compliance_${TIMESTAMP}.sql.gz"
            info "Dumping compliance database..."

            if podman exec postgresql pg_dump -U postgres compliance 2>/dev/null | gzip > "$PG_BACKUP"; then
                SIZE=$(wc -c < "$PG_BACKUP")
                if [[ "$SIZE" -gt 100 ]]; then
                    pass "PostgreSQL backup created: ${PG_BACKUP} (${SIZE} bytes)"
                else
                    fail "PostgreSQL backup is suspiciously small (${SIZE} bytes) — may be empty"
                fi

                # Validate gzip integrity
                if gzip -t "$PG_BACKUP" 2>/dev/null; then
                    pass "PostgreSQL backup integrity: OK (gzip valid)"
                else
                    fail "PostgreSQL backup failed integrity check"
                fi

                # Check row count
                ROW_HINT=$(zcat "$PG_BACKUP" 2>/dev/null | grep -c "^INSERT INTO" || echo "0")
                if [[ "$ROW_HINT" -gt 0 ]]; then
                    pass "Backup contains data (${ROW_HINT} INSERT statements)"
                else
                    warn "No data rows found — compliance_results table may be empty"
                fi
            else
                fail "pg_dump failed — check: podman logs postgresql"
            fi
        fi
    fi
fi

# ─── AAP Installer Inventory ──────────────────────────────────────────────────
section "AAP Installer Inventory"

AAP_BUNDLE_DIR=$(find /opt/ansible-automation-platform -maxdepth 2 -name "inventory" -not -path "*/collections/*" 2>/dev/null | head -1 | xargs dirname 2>/dev/null || echo "")

if [[ -z "$AAP_BUNDLE_DIR" ]]; then
    warn "AAP installer directory not found — skipping inventory backup"
    echo "       Expected: /opt/ansible-automation-platform/*/inventory"
else
    AAP_INVENTORY="${AAP_BUNDLE_DIR}/inventory"
    if [[ -f "$AAP_INVENTORY" ]]; then
        if $VALIDATE_ONLY; then
            LATEST_INV=$(find "$BACKUP_DEST" -name "aap_inventory_*.ini" 2>/dev/null | sort | tail -1)
            if [[ -n "$LATEST_INV" ]]; then
                SIZE=$(wc -c < "$LATEST_INV")
                pass "AAP inventory backup found: $(basename "$LATEST_INV") (${SIZE} bytes)"
            else
                warn "No AAP inventory backup found in ${BACKUP_DEST}"
            fi
        else
            INV_BACKUP="${BACKUP_DIR}/aap_inventory_${TIMESTAMP}.ini"
            cp "$AAP_INVENTORY" "$INV_BACKUP"
            chmod 600 "$INV_BACKUP"
            SIZE=$(wc -c < "$INV_BACKUP")
            pass "AAP inventory backed up: ${INV_BACKUP} (${SIZE} bytes)"
            warn "This file contains passwords — store it securely and do not commit to git"
        fi
    else
        warn "AAP installer inventory not found at: ${AAP_INVENTORY}"
    fi
fi

# ─── List all backups ─────────────────────────────────────────────────────────
section "Backup Inventory"

if [[ -d "$BACKUP_DEST" ]]; then
    BACKUP_COUNT=$(find "$BACKUP_DEST" -maxdepth 2 -type f | wc -l | tr -d ' ')
    BACKUP_SIZE=$(du -sh "$BACKUP_DEST" 2>/dev/null | awk '{print $1}')
    info "Total backups: ${BACKUP_COUNT} files, ${BACKUP_SIZE} on disk"
    info "Location: ${BACKUP_DEST}"
    echo ""
    # Show last 5 backup timestamps
    find "$BACKUP_DEST" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -5 | while read -r dir; do
        COUNT=$(find "$dir" -type f | wc -l | tr -d ' ')
        echo "    $(basename "$dir")  (${COUNT} files)"
    done
else
    warn "Backup destination does not exist: ${BACKUP_DEST}"
fi

# ─── Retention: remove backups older than 30 days ─────────────────────────────
if ! $VALIDATE_ONLY && [[ -d "$BACKUP_DEST" ]]; then
    OLD_COUNT=$(find "$BACKUP_DEST" -mindepth 1 -maxdepth 1 -type d -mtime +30 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$OLD_COUNT" -gt 0 ]]; then
        find "$BACKUP_DEST" -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true
        info "Removed ${OLD_COUNT} backup(s) older than 30 days"
    fi
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Backup Summary${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}Passed:${NC} ${STEPS_PASSED}"
echo -e "  ${RED}Failed:${NC} ${STEPS_FAILED}"
echo ""

if [[ "$STEPS_FAILED" -eq 0 ]]; then
    echo -e "  ${GREEN}✅ Backup complete and validated${NC}"
    echo ""
    echo "  To validate backups later:"
    echo "    ./scripts/backup.sh --validate-only"
    exit 0
else
    echo -e "  ${RED}❌ ${STEPS_FAILED} step(s) failed — review errors above${NC}"
    exit 1
fi
