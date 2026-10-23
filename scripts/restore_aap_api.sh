#!/bin/bash
# Restore AAP Configuration using direct API calls
# Works with AAP 2.6 gateway API

set -e

AAP_HOST="https://${AAC_HOST:?set AAC_HOST}"
AAP_USER="admin"
AAP_PASS="${AAP_PASSWORD:?Error: AAP_PASSWORD environment variable must be set}"
API_BASE="$AAP_HOST/api/controller/v2"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}AAP Configuration Restoration${NC}"
echo -e "${GREEN}============================================${NC}"

# Test connection
echo -e "\n${YELLOW}Testing API connection...${NC}"
curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/ping/" > /dev/null 2>&1
echo -e "${GREEN}✓ API connection successful${NC}"

# =========================================
# CREDENTIALS
# =========================================
echo -e "\n${YELLOW}Creating credentials...${NC}"

# Machine Credential (SSH) - Type 1
echo -n "  Creating Compliance SSH Credential... "
RESULT=$(curl -sk -u "$AAP_USER:$AAP_PASS" -X POST "$API_BASE/credentials/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Compliance SSH Credential",
    "description": "SSH credential for compliance-managed Linux hosts",
    "organization": 1,
    "credential_type": 1,
    "inputs": {
      "username": "ec2-user"
    }
  }' 2>&1)
if echo "$RESULT" | grep -q '"id"'; then
  echo -e "${GREEN}✓${NC}"
elif echo "$RESULT" | grep -q "already exists"; then
  echo -e "${YELLOW}exists${NC}"
else
  echo -e "${RED}failed${NC}"
fi

# AWS Credential - Type 5
echo -n "  Creating AWS Compliance Lab... "
# Secrets come from two vault files with distinct schemas (ansible/vars/*.example):
#   vault_secrets.lab.yml — lab-only values (AWS lab keys, lab DB passwords); encrypted
#   vault_secrets.yml     — personal / cross-environment values (vault_github_pat)
# Each key is read from its designated file first, then the other as a fallback.
# A file is decrypted in memory through `ansible-vault view` when it carries the
# $ANSIBLE_VAULT header and read as-is otherwise; PLACEHOLDER values count as unset.
VAULT_PW="${ANSIBLE_VAULT_PASSWORD_FILE:-$HOME/.vault_pass}"
vault_read_file() {  # vault_read_file <file>
  [ -f "$1" ] || return 0
  if head -1 "$1" | grep -q '^\$ANSIBLE_VAULT'; then
    ansible-vault view "$1" --vault-password-file "$VAULT_PW" 2>/dev/null || true
  else
    cat "$1"
  fi
}
vault_get() {  # vault_get <key> <file> [<fallback file>]
  local key="$1" v f
  for f in "$2" "${3:-}"; do
    [ -n "$f" ] || continue
    v=""
    v=$(vault_read_file "$f" | python3 -c "
import sys
key = sys.argv[1] + ':'
for line in sys.stdin:
    if line.startswith(key):
        v = line.split(':', 1)[1]
        if ' #' in v: v = v.split(' #', 1)[0]
        v = v.strip().strip(chr(39)).strip(chr(34)).strip()
        if v.upper().startswith('PLACEHOLDER'): v = ''
        print(v)
        break" "$key" || true)
    [ -n "$v" ] && { echo "$v"; return 0; }
  done
  echo ""
}
LAB_VAULT=ansible/vars/vault_secrets.lab.yml
GEN_VAULT=ansible/vars/vault_secrets.yml
AWS_ACCESS=$(vault_get aws_lab_access_key "$LAB_VAULT" "$GEN_VAULT")
AWS_SECRET=$(vault_get aws_lab_secret_key "$LAB_VAULT" "$GEN_VAULT")

if [ -n "$AWS_ACCESS" ] && [ -n "$AWS_SECRET" ]; then
  RESULT=$(curl -sk -u "$AAP_USER:$AAP_PASS" -X POST "$API_BASE/credentials/" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"AWS Compliance Lab\",
      \"description\": \"AWS credentials for EC2 compliance lab\",
      \"organization\": 1,
      \"credential_type\": 5,
      \"inputs\": {
        \"username\": \"$AWS_ACCESS\",
        \"password\": \"$AWS_SECRET\"
      }
    }" 2>&1)
  if echo "$RESULT" | grep -q '"id"'; then
    echo -e "${GREEN}✓${NC}"
  elif echo "$RESULT" | grep -q "already exists"; then
    echo -e "${YELLOW}exists${NC}"
  else
    echo -e "${RED}failed${NC}"
  fi
else
  echo -e "${RED}skipped (no vault credentials)${NC}"
fi

# GitHub PAT - Type 11
echo -n "  Creating GitHub PAT... "
GITHUB_PAT=$(vault_get vault_github_pat "$GEN_VAULT" "$LAB_VAULT")
if [ -n "$GITHUB_PAT" ]; then
  RESULT=$(curl -sk -u "$AAP_USER:$AAP_PASS" -X POST "$API_BASE/credentials/" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"GitHub PAT\",
      \"description\": \"GitHub Personal Access Token for private repos\",
      \"organization\": 1,
      \"credential_type\": 11,
      \"inputs\": {
        \"token\": \"$GITHUB_PAT\"
      }
    }" 2>&1)
  if echo "$RESULT" | grep -q '"id"'; then
    echo -e "${GREEN}✓${NC}"
  elif echo "$RESULT" | grep -q "already exists"; then
    echo -e "${YELLOW}exists${NC}"
  else
    echo -e "${RED}failed${NC}"
  fi
else
  echo -e "${RED}skipped (no vault credentials)${NC}"
fi

# =========================================
# PROJECTS
# =========================================
echo -e "\n${YELLOW}Creating projects...${NC}"

# Get GitHub credential ID
GITHUB_CRED_ID=$(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/credentials/?name=GitHub+PAT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] > 0 else '')" 2>/dev/null || echo "")

echo -n "  Creating Compliance Automation project... "
PROJ_DATA='{
  "name": "Compliance Automation",
  "description": "AAC Compliance Automation - CIS, FISMA, PCI-DSS, SOC 2, NERC-CIP",
  "organization": 1,
  "scm_type": "git",
  "scm_url": "https://github.com/ansible-automated-compliance/aac.git",
  "scm_branch": "main",
  "scm_update_on_launch": true'

if [ -n "$GITHUB_CRED_ID" ]; then
  PROJ_DATA="$PROJ_DATA, \"credential\": $GITHUB_CRED_ID"
fi
PROJ_DATA="$PROJ_DATA}"

RESULT=$(curl -sk -u "$AAP_USER:$AAP_PASS" -X POST "$API_BASE/projects/" \
  -H "Content-Type: application/json" \
  -d "$PROJ_DATA" 2>&1)
if echo "$RESULT" | grep -q '"id"'; then
  echo -e "${GREEN}✓${NC}"
  PROJECT_ID=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
elif echo "$RESULT" | grep -q "already exists"; then
  echo -e "${YELLOW}exists${NC}"
  PROJECT_ID=$(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/projects/?name=Compliance+Automation" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] > 0 else '')")
else
  echo -e "${RED}failed${NC}"
  PROJECT_ID=""
fi

# =========================================
# INVENTORIES
# =========================================
echo -e "\n${YELLOW}Creating inventories...${NC}"

echo -n "  Creating Compliance Infrastructure... "
RESULT=$(curl -sk -u "$AAP_USER:$AAP_PASS" -X POST "$API_BASE/inventories/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Compliance Infrastructure",
    "description": "Infrastructure for compliance assessments",
    "organization": 1
  }' 2>&1)
if echo "$RESULT" | grep -q '"id"'; then
  echo -e "${GREEN}✓${NC}"
  COMPLIANCE_INV_ID=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
elif echo "$RESULT" | grep -q "already exists"; then
  echo -e "${YELLOW}exists${NC}"
  COMPLIANCE_INV_ID=$(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/inventories/?name=Compliance+Infrastructure" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] > 0 else '')")
else
  echo -e "${RED}failed${NC}"
fi

echo -n "  Creating AWS Test Environment... "
RESULT=$(curl -sk -u "$AAP_USER:$AAP_PASS" -X POST "$API_BASE/inventories/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AWS Test Environment",
    "description": "AWS EC2 compliance lab instances",
    "organization": 1,
    "variables": "aws_region: us-east-1\nansible_python_interpreter: /usr/bin/python3"
  }' 2>&1)
if echo "$RESULT" | grep -q '"id"'; then
  echo -e "${GREEN}✓${NC}"
  AWS_INV_ID=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
elif echo "$RESULT" | grep -q "already exists"; then
  echo -e "${YELLOW}exists${NC}"
  AWS_INV_ID=$(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/inventories/?name=AWS+Test+Environment" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] > 0 else '')")
else
  echo -e "${RED}failed${NC}"
fi

echo -n "  Creating localhost inventory... "
RESULT=$(curl -sk -u "$AAP_USER:$AAP_PASS" -X POST "$API_BASE/inventories/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "localhost",
    "description": "Local execution for AWS provisioning",
    "organization": 1
  }' 2>&1)
if echo "$RESULT" | grep -q '"id"'; then
  echo -e "${GREEN}✓${NC}"
  LOCALHOST_INV_ID=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
elif echo "$RESULT" | grep -q "already exists"; then
  echo -e "${YELLOW}exists${NC}"
  LOCALHOST_INV_ID=$(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/inventories/?name=localhost" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] > 0 else '')")
else
  echo -e "${RED}failed${NC}"
fi

# Add localhost host
if [ -n "$LOCALHOST_INV_ID" ]; then
  echo -n "    Adding localhost host... "
  RESULT=$(curl -sk -u "$AAP_USER:$AAP_PASS" -X POST "$API_BASE/hosts/" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"localhost\",
      \"inventory\": $LOCALHOST_INV_ID,
      \"variables\": \"ansible_connection: local\"
    }" 2>&1)
  if echo "$RESULT" | grep -q '"id"'; then
    echo -e "${GREEN}✓${NC}"
  elif echo "$RESULT" | grep -q "already exists"; then
    echo -e "${YELLOW}exists${NC}"
  else
    echo -e "${RED}failed${NC}"
  fi
fi

# =========================================
# JOB TEMPLATES
# =========================================
echo -e "\n${YELLOW}Creating job templates...${NC}"

# Get project ID if not set
if [ -z "$PROJECT_ID" ]; then
  PROJECT_ID=$(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/projects/?name=Compliance+Automation" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] > 0 else '')" 2>/dev/null || echo "")
fi

# Get inventory IDs if not set
if [ -z "$COMPLIANCE_INV_ID" ]; then
  COMPLIANCE_INV_ID=$(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/inventories/?name=Compliance+Infrastructure" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] > 0 else '')" 2>/dev/null || echo "")
fi
if [ -z "$LOCALHOST_INV_ID" ]; then
  LOCALHOST_INV_ID=$(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/inventories/?name=localhost" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] > 0 else '')" 2>/dev/null || echo "")
fi

# Get AWS credential ID
AWS_CRED_ID=$(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/credentials/?name=AWS+Compliance+Lab" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['id'] if d['count'] > 0 else '')" 2>/dev/null || echo "")

if [ -n "$PROJECT_ID" ] && [ -n "$COMPLIANCE_INV_ID" ]; then
  # Compliance templates
  TEMPLATES=(
    "CIS RHEL 9 Compliance Assessment|ansible/playbooks/cis_rhel9_assessment.yml|$COMPLIANCE_INV_ID"
    "CIS RHEL 9 Remediation|ansible/playbooks/cis_rhel9_remediation.yml|$COMPLIANCE_INV_ID"
    "FISMA Compliance Assessment|ansible/playbooks/fisma_assessment.yml|$COMPLIANCE_INV_ID"
    "PCI-DSS Compliance Assessment|ansible/playbooks/pci_dss_assessment.yml|$COMPLIANCE_INV_ID"
    "SOC 2 Compliance Assessment|ansible/playbooks/soc2_assessment.yml|$COMPLIANCE_INV_ID"
    "NERC-CIP Compliance Assessment|ansible/playbooks/nerc_cip_assessment.yml|$COMPLIANCE_INV_ID"
    "Multi-Framework Compliance Assessment|ansible/playbooks/multi_framework_assessment.yml|$COMPLIANCE_INV_ID"
  )

  for TMPL in "${TEMPLATES[@]}"; do
    NAME=$(echo "$TMPL" | cut -d'|' -f1)
    PLAYBOOK=$(echo "$TMPL" | cut -d'|' -f2)
    INV_ID=$(echo "$TMPL" | cut -d'|' -f3)

    echo -n "  Creating $NAME... "
    RESULT=$(curl -sk -u "$AAP_USER:$AAP_PASS" -X POST "$API_BASE/job_templates/" \
      -H "Content-Type: application/json" \
      -d "{
        \"name\": \"$NAME\",
        \"job_type\": \"run\",
        \"inventory\": $INV_ID,
        \"project\": $PROJECT_ID,
        \"playbook\": \"$PLAYBOOK\",
        \"ask_limit_on_launch\": true,
        \"ask_variables_on_launch\": true,
        \"extra_vars\": \"opa_server_url: http://${AAC_HOST:?set AAC_HOST}:8181\\ngenerate_report: true\"
      }" 2>&1)
    if echo "$RESULT" | grep -q '"id"'; then
      echo -e "${GREEN}✓${NC}"
    elif echo "$RESULT" | grep -q "already exists"; then
      echo -e "${YELLOW}exists${NC}"
    else
      echo -e "${RED}failed${NC}"
    fi
  done
fi

# AWS Lab templates
if [ -n "$PROJECT_ID" ] && [ -n "$LOCALHOST_INV_ID" ]; then
  AWS_TEMPLATES=(
    "AWS Lab - Provision|aws-lab/playbooks/provision_lab.yml"
    "AWS Lab - Manage Instances|aws-lab/playbooks/manage_instances.yml"
    "AWS Lab - Destroy|aws-lab/playbooks/destroy_lab.yml"
  )

  for TMPL in "${AWS_TEMPLATES[@]}"; do
    NAME=$(echo "$TMPL" | cut -d'|' -f1)
    PLAYBOOK=$(echo "$TMPL" | cut -d'|' -f2)

    echo -n "  Creating $NAME... "
    RESULT=$(curl -sk -u "$AAP_USER:$AAP_PASS" -X POST "$API_BASE/job_templates/" \
      -H "Content-Type: application/json" \
      -d "{
        \"name\": \"$NAME\",
        \"job_type\": \"run\",
        \"inventory\": $LOCALHOST_INV_ID,
        \"project\": $PROJECT_ID,
        \"playbook\": \"$PLAYBOOK\",
        \"ask_variables_on_launch\": true,
        \"extra_vars\": \"aws_region: us-east-1\\nlab_name: compliance-lab\\ninstance_type: t3.micro\"
      }" 2>&1)
    if echo "$RESULT" | grep -q '"id"'; then
      echo -e "${GREEN}✓${NC}"
      # Add AWS credential to template
      if [ -n "$AWS_CRED_ID" ]; then
        TMPL_ID=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
        curl -sk -u "$AAP_USER:$AAP_PASS" -X POST "$API_BASE/job_templates/$TMPL_ID/credentials/" \
          -H "Content-Type: application/json" \
          -d "{\"id\": $AWS_CRED_ID}" > /dev/null 2>&1
      fi
    elif echo "$RESULT" | grep -q "already exists"; then
      echo -e "${YELLOW}exists${NC}"
    else
      echo -e "${RED}failed${NC}"
    fi
  done
fi

# =========================================
# SUMMARY
# =========================================
echo -e "\n${GREEN}============================================${NC}"
echo -e "${GREEN}Configuration Restoration Complete!${NC}"
echo -e "${GREEN}============================================${NC}"

echo -e "\n${YELLOW}Current AAP Status:${NC}"
echo "  Projects: $(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/projects/" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])" 2>/dev/null)"
echo "  Inventories: $(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/inventories/" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])" 2>/dev/null)"
echo "  Credentials: $(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/credentials/" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])" 2>/dev/null)"
echo "  Job Templates: $(curl -sk -u "$AAP_USER:$AAP_PASS" "$API_BASE/job_templates/" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])" 2>/dev/null)"

echo -e "\n${YELLOW}Next Steps:${NC}"
echo "  1. Verify project sync at: $AAP_HOST"
echo "  2. Add hosts to Compliance Infrastructure inventory"
echo "  3. Run 'AWS Lab - Provision' to create test instances"
echo "  4. Run compliance assessments"
