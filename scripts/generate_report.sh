#!/bin/bash

# Generate CIS RHEL 9 Compliance Report
# Usage: ./generate_report.sh <input_json_file>

INPUT_FILE="${1:-test_data/mock_facts/server1_simplified.json}"

echo "==================================================================================================="
echo "CIS RHEL 9 Benchmark Compliance Report"
echo "==================================================================================================="
echo ""
echo "Input File: $INPUT_FILE"
echo ""

echo "---------------------------------------------------------------------------------------------------"
echo "FILESYSTEM VALIDATION (Section 1.1)"
echo "---------------------------------------------------------------------------------------------------"
opa eval --data policies/cis_rhel9/modules/filesystem_validation.rego \
  --input "$INPUT_FILE" \
  --format pretty \
  'data.cis_rhel9.filesystem.violations'
echo ""

echo "---------------------------------------------------------------------------------------------------"
echo "FILESYSTEM COMPLIANCE STATUS"
echo "---------------------------------------------------------------------------------------------------"
opa eval --data policies/cis_rhel9/modules/filesystem_validation.rego \
  --input "$INPUT_FILE" \
  --format pretty \
  'data.cis_rhel9.filesystem.compliant'
echo ""

echo "==================================================================================================="
echo "END OF REPORT"
echo "==================================================================================================="
