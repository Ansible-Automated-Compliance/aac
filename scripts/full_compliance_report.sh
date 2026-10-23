#!/bin/bash

# Generate Complete CIS RHEL 9 Compliance Report
# Usage: ./full_compliance_report.sh <input_json_file>

INPUT_FILE="${1:-test_data/mock_facts/webserver_noncompliant.json}"

HOSTNAME=$(cat "$INPUT_FILE" | jq -r '.hostname // "unknown"')
TIMESTAMP=$(cat "$INPUT_FILE" | jq -r '.collection_timestamp // "unknown"')

echo "==================================================================================================="
echo "                      CIS RED HAT ENTERPRISE LINUX 9 BENCHMARK v2.0.0"
echo "                               COMPLIANCE VALIDATION REPORT"
echo "==================================================================================================="
echo ""
echo "System:    $HOSTNAME"
echo "Timestamp: $TIMESTAMP"
echo "Input:     $INPUT_FILE"
echo ""

# Section 1: Filesystem
echo "---------------------------------------------------------------------------------------------------"
echo "SECTION 1.1: FILESYSTEM CONFIGURATION"
echo "---------------------------------------------------------------------------------------------------"
FS_VIOLATIONS=$(opa eval --data policies/cis_rhel9/modules/filesystem_validation.rego \
  --input "$INPUT_FILE" \
  --format raw \
  'data.cis_rhel9.filesystem.violations' | jq -r 'length')
FS_COMPLIANT=$(opa eval --data policies/cis_rhel9/modules/filesystem_validation.rego \
  --input "$INPUT_FILE" \
  --format raw \
  'data.cis_rhel9.filesystem.compliant')

echo "Status: $([ "$FS_COMPLIANT" = "true" ] && echo "✓ COMPLIANT" || echo "✗ NON-COMPLIANT")"
echo "Violations: $FS_VIOLATIONS"
echo ""
if [ "$FS_COMPLIANT" != "true" ]; then
  echo "Details:"
  opa eval --data policies/cis_rhel9/modules/filesystem_validation.rego \
    --input "$INPUT_FILE" \
    --format raw \
    'data.cis_rhel9.filesystem.violations' | jq -r '.[] | "  - " + .'
  echo ""
fi

# Section 4.2: Logging
echo "---------------------------------------------------------------------------------------------------"
echo "SECTION 4.2: LOGGING CONFIGURATION"
echo "---------------------------------------------------------------------------------------------------"
LOG_VIOLATIONS=$(opa eval --data policies/cis_rhel9/modules/logging_validation.rego \
  --input "$INPUT_FILE" \
  --format raw \
  'data.cis_rhel9.logging.violations' | jq -r 'length')
LOG_COMPLIANT=$(opa eval --data policies/cis_rhel9/modules/logging_validation.rego \
  --input "$INPUT_FILE" \
  --format raw \
  'data.cis_rhel9.logging.compliant')

echo "Status: $([ "$LOG_COMPLIANT" = "true" ] && echo "✓ COMPLIANT" || echo "✗ NON-COMPLIANT")"
echo "Violations: $LOG_VIOLATIONS"
echo ""
if [ "$LOG_COMPLIANT" != "true" ]; then
  echo "Details:"
  opa eval --data policies/cis_rhel9/modules/logging_validation.rego \
    --input "$INPUT_FILE" \
    --format raw \
    'data.cis_rhel9.logging.violations' | jq -r '.[] | "  - " + .'
  echo ""
fi

# Section 6.1: File Permissions
echo "---------------------------------------------------------------------------------------------------"
echo "SECTION 6.1: FILE PERMISSIONS"
echo "---------------------------------------------------------------------------------------------------"
PERM_VIOLATIONS=$(opa eval --data policies/cis_rhel9/modules/file_permissions_validation.rego \
  --input "$INPUT_FILE" \
  --format raw \
  'data.cis_rhel9.file_permissions.violations' | jq -r 'length')
PERM_COMPLIANT=$(opa eval --data policies/cis_rhel9/modules/file_permissions_validation.rego \
  --input "$INPUT_FILE" \
  --format raw \
  'data.cis_rhel9.file_permissions.compliant')

echo "Status: $([ "$PERM_COMPLIANT" = "true" ] && echo "✓ COMPLIANT" || echo "✗ NON-COMPLIANT")"
echo "Violations: $PERM_VIOLATIONS"
echo ""
if [ "$PERM_COMPLIANT" != "true" ]; then
  echo "Details:"
  opa eval --data policies/cis_rhel9/modules/file_permissions_validation.rego \
    --input "$INPUT_FILE" \
    --format raw \
    'data.cis_rhel9.file_permissions.violations' | jq -r '.[] | "  - " + .'
  echo ""
fi

# Section 2: Services
echo "---------------------------------------------------------------------------------------------------"
echo "SECTION 2: SERVICE CONFIGURATION"
echo "---------------------------------------------------------------------------------------------------"
SVC_VIOLATIONS=$(opa eval --data policies/cis_rhel9/modules/service_validation.rego \
  --input "$INPUT_FILE" \
  --format raw \
  'data.cis_rhel9.services.violations' | jq -r 'length')
SVC_COMPLIANT=$(opa eval --data policies/cis_rhel9/modules/service_validation.rego \
  --input "$INPUT_FILE" \
  --format raw \
  'data.cis_rhel9.services.compliant')

echo "Status: $([ "$SVC_COMPLIANT" = "true" ] && echo "✓ COMPLIANT" || echo "✗ NON-COMPLIANT")"
echo "Violations: $SVC_VIOLATIONS"
echo ""
if [ "$SVC_COMPLIANT" != "true" ]; then
  echo "Details:"
  opa eval --data policies/cis_rhel9/modules/service_validation.rego \
    --input "$INPUT_FILE" \
    --format raw \
    'data.cis_rhel9.services.violations' | jq -r '.[] | "  - " + .'
  echo ""
fi

# Section 3: Network
echo "---------------------------------------------------------------------------------------------------"
echo "SECTION 3: NETWORK CONFIGURATION"
echo "---------------------------------------------------------------------------------------------------"
NET_VIOLATIONS=$(opa eval --data policies/cis_rhel9/modules/network_validation.rego \
  --input "$INPUT_FILE" \
  --format raw \
  'data.cis_rhel9.network.violations' | jq -r 'length')
NET_COMPLIANT=$(opa eval --data policies/cis_rhel9/modules/network_validation.rego \
  --input "$INPUT_FILE" \
  --format raw \
  'data.cis_rhel9.network.compliant')

echo "Status: $([ "$NET_COMPLIANT" = "true" ] && echo "✓ COMPLIANT" || echo "✗ NON-COMPLIANT")"
echo "Violations: $NET_VIOLATIONS"
echo ""
if [ "$NET_COMPLIANT" != "true" ]; then
  echo "Details:"
  opa eval --data policies/cis_rhel9/modules/network_validation.rego \
    --input "$INPUT_FILE" \
    --format raw \
    'data.cis_rhel9.network.violations' | jq -r '.[] | "  - " + .'
  echo ""
fi

# Summary
echo "==================================================================================================="
echo "                                    COMPLIANCE SUMMARY"
echo "==================================================================================================="
TOTAL_VIOLATIONS=$((FS_VIOLATIONS + LOG_VIOLATIONS + PERM_VIOLATIONS + SVC_VIOLATIONS + NET_VIOLATIONS))
COMPLIANT_SECTIONS=0
[ "$FS_COMPLIANT" = "true" ] && COMPLIANT_SECTIONS=$((COMPLIANT_SECTIONS + 1))
[ "$LOG_COMPLIANT" = "true" ] && COMPLIANT_SECTIONS=$((COMPLIANT_SECTIONS + 1))
[ "$PERM_COMPLIANT" = "true" ] && COMPLIANT_SECTIONS=$((COMPLIANT_SECTIONS + 1))
[ "$SVC_COMPLIANT" = "true" ] && COMPLIANT_SECTIONS=$((COMPLIANT_SECTIONS + 1))
[ "$NET_COMPLIANT" = "true" ] && COMPLIANT_SECTIONS=$((COMPLIANT_SECTIONS + 1))

COMPLIANCE_PCT=$((COMPLIANT_SECTIONS * 100 / 5))

echo ""
echo "Overall Status:          $([ $COMPLIANT_SECTIONS -eq 5 ] && echo "✓ COMPLIANT" || echo "✗ NON-COMPLIANT")"
echo "Compliant Sections:      $COMPLIANT_SECTIONS / 5"
echo "Compliance Percentage:   $COMPLIANCE_PCT%"
echo "Total Violations:        $TOTAL_VIOLATIONS"
echo ""
echo "Section Breakdown:"
echo "  - Filesystem (1.1):        $([ "$FS_COMPLIANT" = "true" ] && echo "✓" || echo "✗")  ($FS_VIOLATIONS violations)"
echo "  - Logging (4.2):           $([ "$LOG_COMPLIANT" = "true" ] && echo "✓" || echo "✗")  ($LOG_VIOLATIONS violations)"
echo "  - File Permissions (6.1):  $([ "$PERM_COMPLIANT" = "true" ] && echo "✓" || echo "✗")  ($PERM_VIOLATIONS violations)"
echo "  - Services (2.x):          $([ "$SVC_COMPLIANT" = "true" ] && echo "✓" || echo "✗")  ($SVC_VIOLATIONS violations)"
echo "  - Network (3.x):           $([ "$NET_COMPLIANT" = "true" ] && echo "✓" || echo "✗")  ($NET_VIOLATIONS violations)"
echo ""
echo "==================================================================================================="
echo "                                  END OF COMPLIANCE REPORT"
echo "==================================================================================================="
