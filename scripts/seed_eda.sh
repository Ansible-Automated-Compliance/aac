#!/bin/bash
# Quick script to seed AAP with compliance configuration
# Run this after EDA is installed to create projects, job templates, and inventory

set -e

echo "=========================================="
echo "Seeding AAP with Compliance Configuration"
echo "=========================================="
echo ""

# Check if CONTROLLER_PASSWORD is set
if [ -z "$CONTROLLER_PASSWORD" ]; then
    echo "ERROR: CONTROLLER_PASSWORD environment variable not set"
    echo ""
    echo "Please set it first:"
    echo "  export CONTROLLER_PASSWORD=$AAP_ADMIN_PASSWORD"
    echo ""
    exit 1
fi

echo "Using AAP host: ${AAC_HOST:?set AAC_HOST}"
echo "Username: admin"
echo ""

# Check if awx.awx collection is installed
echo "Checking for awx.awx collection..."
if ! ansible-galaxy collection list | grep -q "awx.awx"; then
    echo "Installing awx.awx collection..."
    ansible-galaxy collection install awx.awx --force
else
    echo "✓ awx.awx collection already installed"
fi

echo ""
echo "Running seeding playbook..."
echo ""

# Run the playbook
ansible-playbook seed_eda_compliance.yml

echo ""
echo "=========================================="
echo "Seeding Complete!"
echo "=========================================="
echo ""
echo "The following resources were created in AAP:"
echo ""
echo "  ✓ Project: Compliance Automation"
echo "    - Synced with: https://github.com/ansible-automated-compliance/aac.git"
echo ""
echo "  ✓ Inventory: Compliance Infrastructure"
echo "    - Groups: linux_servers, oracle_servers, critical_infrastructure"
echo ""
echo "  ✓ Job Templates:"
echo "    - CIS RHEL 9 Compliance Validation"
echo "    - CIS Oracle 19c Compliance Validation"
echo "    - Multi-Framework Compliance Check"
echo "    - NERC-CIP Compliance Validation"
echo "    - FISMA Compliance Validation"
echo ""
echo "Next steps:"
echo "  1. Login to AAP: https://${AAC_HOST:?set AAC_HOST}"
echo "  2. Verify project: Resources → Projects → Compliance Automation"
echo "  3. Create rulebook activations: Automation Decisions → Rulebook Activations"
echo "  4. See guide: CREATE_RULEBOOK_ACTIVATIONS.md"
echo ""
