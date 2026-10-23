#!/bin/bash
# CIS RHEL 9 Compliance Assessment Runner
# This script runs the CIS compliance assessment on specified hosts

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CIS RHEL 9 Compliance Assessment${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANSIBLE_DIR="${SCRIPT_DIR}/ansible"
INVENTORY="${ANSIBLE_DIR}/inventory/rhel9_test.yml"
PLAYBOOK="${ANSIBLE_DIR}/playbooks/cis_rhel9_assessment.yml"
OPA_SERVER="${OPA_SERVER_URL:-http://localhost:8181}"
REPORTS_DIR="${SCRIPT_DIR}/reports"

# Create reports directory
mkdir -p "${REPORTS_DIR}"

echo -e "${YELLOW}Configuration:${NC}"
echo "  Inventory: ${INVENTORY}"
echo "  Playbook: ${PLAYBOOK}"
echo "  OPA Server: ${OPA_SERVER}"
echo "  Reports Directory: ${REPORTS_DIR}"
echo

# Check if OPA is running
echo -e "${YELLOW}Checking OPA server status...${NC}"
if curl -s -f "${OPA_SERVER}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ OPA server is running at ${OPA_SERVER}${NC}"
else
    echo -e "${RED}✗ OPA server is not accessible at ${OPA_SERVER}${NC}"
    echo -e "${YELLOW}Please ensure OPA is running with: docker ps | grep opa${NC}"
    exit 1
fi

# Load CIS RHEL 9 policy into OPA
echo
echo -e "${YELLOW}Loading CIS RHEL 9 policy into OPA...${NC}"
POLICY_FILE="${SCRIPT_DIR}/policies/cis_benchmarks/rhel_9/cis_rhel_9.rego"

if [ -f "${POLICY_FILE}" ]; then
    curl -X PUT "${OPA_SERVER}/v1/policies/cis_rhel_9" \
        --data-binary @"${POLICY_FILE}" \
        -H "Content-Type: text/plain" \
        > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ CIS RHEL 9 policy loaded successfully${NC}"
    else
        echo -e "${RED}✗ Failed to load policy into OPA${NC}"
        exit 1
    fi
else
    echo -e "${RED}✗ Policy file not found: ${POLICY_FILE}${NC}"
    exit 1
fi

# Verify policy is loaded
echo -e "${YELLOW}Verifying policy...${NC}"
POLICY_CHECK=$(curl -s "${OPA_SERVER}/v1/policies/cis_rhel_9")
if [ -n "${POLICY_CHECK}" ]; then
    echo -e "${GREEN}✓ Policy verified in OPA${NC}"
else
    echo -e "${RED}✗ Policy verification failed${NC}"
    exit 1
fi

# Run Ansible playbook
echo
echo -e "${YELLOW}Running compliance assessment playbook...${NC}"
echo -e "${BLUE}----------------------------------------${NC}"

export OPA_SERVER_URL="${OPA_SERVER}"

cd "${ANSIBLE_DIR}"

ansible-playbook \
    -i "${INVENTORY}" \
    "${PLAYBOOK}" \
    -v

PLAYBOOK_EXIT_CODE=$?

echo
echo -e "${BLUE}----------------------------------------${NC}"

if [ ${PLAYBOOK_EXIT_CODE} -eq 0 ]; then
    echo -e "${GREEN}✓ Assessment completed successfully${NC}"
    echo
    echo -e "${YELLOW}Reports generated in: ${REPORTS_DIR}${NC}"
    echo

    # List generated reports
    if [ -d "${REPORTS_DIR}" ]; then
        echo -e "${YELLOW}Generated reports:${NC}"
        ls -lh "${REPORTS_DIR}"/*.json 2>/dev/null | tail -5
        echo

        # Display latest report summary
        LATEST_REPORT=$(ls -t "${REPORTS_DIR}"/*_compliance_report_*.json 2>/dev/null | head -1)
        if [ -n "${LATEST_REPORT}" ]; then
            echo -e "${YELLOW}Latest report summary:${NC}"
            echo -e "${BLUE}File: $(basename ${LATEST_REPORT})${NC}"
            jq -r '.compliance_summary' "${LATEST_REPORT}" 2>/dev/null || cat "${LATEST_REPORT}"
        fi
    fi
else
    echo -e "${RED}✗ Assessment failed with exit code ${PLAYBOOK_EXIT_CODE}${NC}"
    exit ${PLAYBOOK_EXIT_CODE}
fi

echo
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Assessment Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
