#!/bin/bash
# Test script for CIS Oracle Database 19c policies

set -e

echo "=== Testing CIS Oracle Database 19c Policies ==="
echo ""

# Test compliant database
echo "--- Testing Compliant Database ---"
echo "Evaluating: test_data/oracle_mock_facts/oracle_compliant.json"
echo ""

opa eval --data policies/cis_oracle/modules/ \
  --input test_data/oracle_mock_facts/oracle_compliant.json \
  --format pretty \
  '{
    "installation": data.cis_oracle.installation_patches.compliant,
    "listener": data.cis_oracle.listener_configuration.compliant,
    "parameters": data.cis_oracle.database_parameters.compliant,
    "accounts": data.cis_oracle.user_account_management.compliant,
    "total_violations": (
      count(data.cis_oracle.installation_patches.violations) +
      count(data.cis_oracle.listener_configuration.violations) +
      count(data.cis_oracle.database_parameters.violations) +
      count(data.cis_oracle.user_account_management.violations)
    )
  }'

echo ""
echo ""

# Test non-compliant database
echo "--- Testing Non-Compliant Database ---"
echo "Evaluating: test_data/oracle_mock_facts/oracle_noncompliant.json"
echo ""

opa eval --data policies/cis_oracle/modules/ \
  --input test_data/oracle_mock_facts/oracle_noncompliant.json \
  --format pretty \
  '{
    "installation": data.cis_oracle.installation_patches.compliant,
    "listener": data.cis_oracle.listener_configuration.compliant,
    "parameters": data.cis_oracle.database_parameters.compliant,
    "accounts": data.cis_oracle.user_account_management.compliant,
    "total_violations": (
      count(data.cis_oracle.installation_patches.violations) +
      count(data.cis_oracle.listener_configuration.violations) +
      count(data.cis_oracle.database_parameters.violations) +
      count(data.cis_oracle.user_account_management.violations)
    )
  }'

echo ""
echo ""

# Show detailed violations from non-compliant database
echo "--- Detailed Violations (Non-Compliant Database) ---"
echo ""

echo "Installation & Patches:"
opa eval --data policies/cis_oracle/modules/ \
  --input test_data/oracle_mock_facts/oracle_noncompliant.json \
  --format pretty \
  'data.cis_oracle.installation_patches.violations'

echo ""
echo "Listener Configuration:"
opa eval --data policies/cis_oracle/modules/ \
  --input test_data/oracle_mock_facts/oracle_noncompliant.json \
  --format pretty \
  'data.cis_oracle.listener_configuration.violations'

echo ""
echo "Database Parameters:"
opa eval --data policies/cis_oracle/modules/ \
  --input test_data/oracle_mock_facts/oracle_noncompliant.json \
  --format pretty \
  'data.cis_oracle.database_parameters.violations'

echo ""
echo "User Account Management:"
opa eval --data policies/cis_oracle/modules/ \
  --input test_data/oracle_mock_facts/oracle_noncompliant.json \
  --format pretty \
  'data.cis_oracle.user_account_management.violations'

echo ""
echo "=== Testing Complete ==="
