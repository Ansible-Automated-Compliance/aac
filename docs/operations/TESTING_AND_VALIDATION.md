> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x6.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

> [!NOTE]
> **2026-10-17:** `ansible/compliance-automation-playbook.yml` and the framework roles it imported
> (`compliance_base`, `iso27001_compliance`, `pci_dss_compliance`, `soc2_compliance`) were removed
> from the tree; nothing called them. Assessments run from `ansible/playbooks/` (for example
> `cis_rhel9_assessment.yml`) through AAP job templates.

# Testing and Validation Documentation

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025


This document provides comprehensive testing and validation procedures for the OPA Enterprise Compliance Automation Platform.

## 🎯 Overview

The platform includes extensive testing capabilities to ensure compliance policies work correctly across all supported frameworks. Testing covers individual policy validation, multi-framework assessment, Ansible Automation Platform automation, and end-to-end scenarios.

## 🧪 Testing Strategy

### Testing Levels
1. **Unit Testing**: Individual Rego policy validation
2. **Integration Testing**: Framework-level compliance assessment
3. **System Testing**: Multi-framework consolidated assessment
4. **Automation Testing**: Ansible Automation Platform role and playbook validation
5. **End-to-End Testing**: Complete workflow validation

### Testing Frameworks
- **OPA Testing**: Built-in `opa test` command
- **AAP Testing**: Molecule for role testing
- **Shell Testing**: BATS for script validation
- **API Testing**: cURL and REST API validation

## 📁 Test Structure

```
tests/
├── unit/                               # Individual policy tests
│   ├── fisma_tests.rego               # FISMA policy unit tests
│   ├── nerc_cip_tests.rego            # NERC-CIP policy unit tests
│   ├── soc2_tests.rego                # SOC 2 policy unit tests
│   ├── pci_dss_tests.rego             # PCI-DSS policy unit tests
│   └── iso27001_tests.rego            # ISO 27001 policy unit tests
├── integration/                       # Framework integration tests
│   ├── multi_framework_tests.rego     # Multi-framework assessment tests
│   └── consolidated_assessment_tests.rego
├── ansible/                           # Ansible Automation Platform tests
│   ├── molecule/                      # Molecule test scenarios
│   ├── inventory_tests.yml            # Inventory validation tests
│   └── playbook_tests.yml             # Playbook execution tests
├── api/                               # API endpoint tests
│   ├── opa_api_tests.sh               # OPA REST API tests
│   └── compliance_endpoint_tests.sh   # Framework endpoint tests
├── examples/                          # Test input data
│   ├── fisma/                         # FISMA test examples
│   ├── nerc_cip/                      # NERC-CIP test examples
│   ├── soc2/                          # SOC 2 test examples
│   ├── pci_dss/                       # PCI-DSS test examples
│   ├── iso27001/                      # ISO 27001 test examples
│   └── multi_framework/               # Multi-framework test examples
└── scripts/                           # Test automation scripts
    ├── run_all_tests.sh               # Comprehensive test runner
    ├── validate_policies.sh           # Policy validation script
    └── test_aap_roles.sh              # AAP role testing script
```

## 🔬 Unit Testing

### FISMA Policy Testing

#### Test File: `tests/unit/fisma_tests.rego`

```rego
package fisma_tests

import rego.v1

# Test RMF Step 1 - Prepare
test_rmf_step_1_prepare_passes {
    fisma.rmf_step_1_prepare_compliant with input as {
        "organizational_preparation": true,
        "system_stakeholders_identified": true,
        "risk_executive_designated": true,
        "authorizing_official_designated": true
    }
}

test_rmf_step_1_prepare_fails_missing_stakeholders {
    not fisma.rmf_step_1_prepare_compliant with input as {
        "organizational_preparation": true,
        "system_stakeholders_identified": false,
        "risk_executive_designated": true,
        "authorizing_official_designated": true
    }
}

# Test RMF Step 2 - Categorize
test_rmf_step_2_categorize_passes_high_impact {
    fisma.rmf_step_2_categorize_compliant with input as {
        "system_categorization": {
            "confidentiality_impact": "high",
            "integrity_impact": "high",
            "availability_impact": "high",
            "overall_impact": "high"
        }
    }
}

test_rmf_step_2_categorize_fails_invalid_impact {
    not fisma.rmf_step_2_categorize_compliant with input as {
        "system_categorization": {
            "confidentiality_impact": "invalid",
            "integrity_impact": "high",
            "availability_impact": "high",
            "overall_impact": "high"
        }
    }
}

# Test System Security Plan validation
test_ssp_validation_passes {
    fisma.system_security_plan.ssp_compliant with input as {
        "system_security_plan": {
            "sections_completed": 7,
            "system_description": true,
            "security_requirements": true,
            "system_boundaries": true,
            "security_controls": true,
            "contingency_planning": true,
            "risk_assessment": true,
            "assessment_procedures": true
        }
    }
}

# Test Continuous Monitoring
test_continuous_monitoring_level_4 {
    fisma.continuous_monitoring.iscm_maturity_level == 4 with input as {
        "continuous_monitoring": {
            "define_strategy": true,
            "establish_metrics": true,
            "implement_tools": true,
            "analyze_data": true,
            "respond_findings": true,
            "review_update": true,
            "reporting_frequency": "monthly",
            "automation_level": "high"
        }
    }
}
```

#### Running FISMA Tests
```bash
# Run all FISMA tests
opa test policies/fisma/ tests/unit/fisma_tests.rego -v

# Run specific test
opa test policies/fisma/ tests/unit/fisma_tests.rego -v -r test_rmf_step_1_prepare_passes

# Test with example data
opa eval -d policies/fisma/fisma_main.rego \
  -i examples/fisma/fisma_compliant_input.json \
  "data.fisma.fisma_compliant"
```

### NERC-CIP Policy Testing

#### Test File: `tests/unit/nerc_cip_tests.rego`

```rego
package nerc_cip_tests

import rego.v1

# Test BES Cyber System Categorization
test_bes_categorization_passes {
    nerc_cip.bes_cyber_system_categorization_compliant with input as {
        "bes_cyber_systems": [
            {
                "system_id": "BCS-001",
                "system_name": "Energy Management System",
                "impact_categorization": "high",
                "functional_obligations": ["real_time_operations"]
            }
        ]
    }
}

test_bes_categorization_fails_invalid_impact {
    not nerc_cip.bes_cyber_system_categorization_compliant with input as {
        "bes_cyber_systems": [
            {
                "system_id": "BCS-001",
                "impact_categorization": "invalid",
                "functional_obligations": ["real_time_operations"]
            }
        ]
    }
}

# Test Electronic Security Perimeter
test_esp_passes {
    nerc_cip.electronic_security_perimeter_compliant with input as {
        "electronic_security_perimeter": {
            "defined": true,
            "documented": true,
            "access_points_controlled": true,
            "external_connectivity_restricted": true
        }
    }
}

# Test Physical Security
test_physical_security_passes {
    nerc_cip.physical_security_compliant with input as {
        "physical_security": {
            "physical_security_plan": true,
            "access_controls": true,
            "monitoring_systems": true,
            "visitor_control": true
        }
    }
}
```

#### Running NERC-CIP Tests
```bash
# Run all NERC-CIP tests
opa test policies/nerc_cip/ tests/unit/nerc_cip_tests.rego -v

# Test with simplified policy
opa test policies/nerc_cip/nerc_cip_simplified.rego tests/unit/nerc_cip_tests.rego -v

# Test with example data
opa eval -d policies/nerc_cip/nerc_cip_simplified.rego \
  -i examples/nerc_cip/nerc_cip_compliant_input.json \
  "data.nerc_cip.nerc_cip_compliant"
```

### Multi-Framework Testing

#### Test File: `tests/integration/multi_framework_tests.rego`

```rego
package multi_framework_tests

import rego.v1

# Test consolidated compliance assessment
test_multi_framework_assessment_passes {
    result := data.compliance.multi_framework_assessment with input as {
        "fisma": {
            "system_categorization": {
                "overall_impact": "high"
            },
            "nist_controls": {
                "ac_2_account_management": true,
                "au_2_audit_events": true
            }
        },
        "nerc_cip": {
            "bes_cyber_systems": [
                {
                    "impact_categorization": "high"
                }
            ]
        },
        "soc2": {
            "security_controls": true,
            "availability_controls": true
        }
    }
    
    result.overall_compliant
    count(result.frameworks_assessed) == 3
}

# Test framework prioritization
test_framework_priority_federal_system {
    result := data.compliance.determine_framework_priority with input as {
        "system_type": "federal",
        "organization": {
            "entity_type": "federal_agency"
        }
    }
    
    result.primary_framework == "fisma"
    "fisma" in result.required_frameworks
}

test_framework_priority_utility_system {
    result := data.compliance.determine_framework_priority with input as {
        "system_type": "utility",
        "organization": {
            "entity_type": "transmission_operator"
        }
    }
    
    result.primary_framework == "nerc_cip"
    "nerc_cip" in result.required_frameworks
}
```

## 🔗 Integration Testing

### API Endpoint Testing

#### Script: `tests/api/opa_api_tests.sh`

```bash
#!/bin/bash
set -e

OPA_URL="http://localhost:8181"
TEST_DATA_DIR="examples"

echo "🧪 Testing OPA API Endpoints"

# Test OPA health
echo "Testing OPA health endpoint..."
curl -f -s "${OPA_URL}/health" > /dev/null
echo "✅ OPA health check passed"

# Test policy loading
echo "Testing policy loading..."
curl -f -s "${OPA_URL}/v1/policies" | jq '.result | keys' > /dev/null
echo "✅ Policy loading check passed"

# Test FISMA compliance endpoint
echo "Testing FISMA compliance assessment..."
FISMA_RESULT=$(curl -s -X POST "${OPA_URL}/v1/data/fisma/fisma_assessment" \
  -H 'Content-Type: application/json' \
  -d @"${TEST_DATA_DIR}/fisma/fisma_compliant_input.json")

echo "$FISMA_RESULT" | jq '.result.compliant' | grep -q "true"
echo "✅ FISMA assessment passed"

# Test NERC-CIP compliance endpoint
echo "Testing NERC-CIP compliance assessment..."
NERC_RESULT=$(curl -s -X POST "${OPA_URL}/v1/data/nerc_cip/nerc_cip_assessment" \
  -H 'Content-Type: application/json' \
  -d @"${TEST_DATA_DIR}/nerc_cip/nerc_cip_compliant_input.json")

echo "$NERC_RESULT" | jq '.result.compliant' | grep -q "true"
echo "✅ NERC-CIP assessment passed"

# Test multi-framework assessment
echo "Testing multi-framework assessment..."
MULTI_RESULT=$(curl -s -X POST "${OPA_URL}/v1/data/compliance/multi_framework_assessment" \
  -H 'Content-Type: application/json' \
  -d @"${TEST_DATA_DIR}/multi_framework/consolidated_input.json")

echo "$MULTI_RESULT" | jq '.result.overall_compliant' | grep -q "true"
echo "✅ Multi-framework assessment passed"

echo "🎉 All API tests passed!"
```

### Ansible Automation Platform Role Testing

#### Molecule Configuration: `tests/ansible/molecule/default/molecule.yml`

```yaml
---
dependency:
  name: galaxy
driver:
  name: docker
platforms:
  - name: fisma-test
    image: quay.io/ansible/ubuntu2004:latest
    pre_build_image: true
    groups:
      - federal_systems
  - name: nerc-test
    image: quay.io/ansible/ubuntu2004:latest
    pre_build_image: true
    groups:
      - utility_systems
  - name: commercial-test
    image: quay.io/ansible/ubuntu2004:latest
    pre_build_image: true
    groups:
      - commercial_systems

provisioner:
  name: ansible
  inventory:
    group_vars:
      federal_systems:
        run_fisma: true
      utility_systems:
        run_nerc_cip: true
      commercial_systems:
        run_soc2: true
        run_pci_dss: true

verifier:
  name: ansible
```

#### Molecule Test Playbook: `tests/ansible/molecule/default/converge.yml`

```yaml
---
- name: Converge
  hosts: all
  tasks:
    - name: Include compliance automation playbook
      import_playbook: ../../../../ansible/compliance-automation-playbook.yml
```

#### Molecule Verification: `tests/ansible/molecule/default/verify.yml`

```yaml
---
- name: Verify
  hosts: all
  tasks:
    - name: Verify compliance reports exist
      stat:
        path: "/tmp/compliance_assessments/consolidated_compliance_report_{{ inventory_hostname }}.html"
      register: report_file

    - name: Assert report was generated
      assert:
        that:
          - report_file.stat.exists
        fail_msg: "Compliance report was not generated"

    - name: Verify JSON summary exists
      stat:
        path: "/tmp/compliance_assessments/compliance_summary_{{ inventory_hostname }}.json"
      register: json_file

    - name: Assert JSON summary was generated
      assert:
        that:
          - json_file.stat.exists
        fail_msg: "JSON summary was not generated"
```

#### Running Molecule Tests
```bash
# Install molecule
pip install molecule docker

# Run molecule tests
cd ansible/roles/fisma_compliance
molecule test

# Run specific scenarios
molecule test --scenario-name fisma-only
molecule test --scenario-name multi-framework
```

## 🎬 End-to-End Testing

### Complete Workflow Test Script: `tests/scripts/run_all_tests.sh`

```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEST_OUTPUT_DIR="/tmp/compliance_test_results"

echo "🚀 Starting Comprehensive Compliance Platform Tests"
echo "=================================================="

# Setup test environment
mkdir -p "${TEST_OUTPUT_DIR}"
cd "${PROJECT_ROOT}"

# 1. Start OPA Server
echo "1️⃣ Starting OPA server..."
./start_opa.sh &
OPA_PID=$!
sleep 5

# Wait for OPA to be ready
echo "Waiting for OPA server to be ready..."
for i in {1..30}; do
    if curl -f -s http://localhost:8181/health > /dev/null; then
        echo "✅ OPA server is ready"
        break
    fi
    sleep 1
done

# 2. Run Unit Tests
echo "2️⃣ Running unit tests..."
echo "Testing FISMA policies..."
opa test policies/fisma/ tests/unit/fisma_tests.rego -v

echo "Testing NERC-CIP policies..."
opa test policies/nerc_cip/ tests/unit/nerc_cip_tests.rego -v

echo "Testing integration policies..."
opa test policies/ tests/integration/ -v

# 3. Run API Tests
echo "3️⃣ Running API tests..."
bash tests/api/opa_api_tests.sh

# 4. Test Individual Framework Examples
echo "4️⃣ Testing framework examples..."

echo "Testing FISMA compliant example..."
opa eval -d policies/fisma/fisma_main.rego \
  -i examples/fisma/fisma_compliant_input.json \
  "data.fisma.fisma_compliant"

echo "Testing FISMA non-compliant example..."
opa eval -d policies/fisma/fisma_main.rego \
  -i examples/fisma/fisma_non_compliant_input.json \
  "data.fisma.fisma_compliant"

echo "Testing NERC-CIP compliant example..."
opa eval -d policies/nerc_cip/nerc_cip_simplified.rego \
  -i examples/nerc_cip/nerc_cip_compliant_input.json \
  "data.nerc_cip.nerc_cip_compliant"

# 5. Test Ansible Automation
echo "5️⃣ Testing Ansible automation..."
cd ansible

echo "Testing Ansible syntax..."
ansible-playbook compliance-automation-playbook.yml --syntax-check

echo "Testing inventory..."
ansible-inventory -i inventory/hosts.yml --list > /dev/null

echo "Running dry-run assessment..."
ansible-playbook -i inventory/hosts.yml compliance-automation-playbook.yml \
  -e run_fisma=true \
  -e assessment_output_dir="${TEST_OUTPUT_DIR}" \
  --check

# 6. Test Report Generation
echo "6️⃣ Testing report generation..."
ansible-playbook -i inventory/hosts.yml compliance-automation-playbook.yml \
  --limit federal_systems \
  -e run_fisma=true \
  -e consolidated_report=true \
  -e assessment_output_dir="${TEST_OUTPUT_DIR}"

# Verify reports were generated
if [ -f "${TEST_OUTPUT_DIR}/consolidated_compliance_report_federal-web-01.html" ]; then
    echo "✅ Consolidated report generated successfully"
else
    echo "❌ Consolidated report generation failed"
    exit 1
fi

if [ -f "${TEST_OUTPUT_DIR}/compliance_summary_federal-web-01.json" ]; then
    echo "✅ JSON summary generated successfully"
else
    echo "❌ JSON summary generation failed"
    exit 1
fi

# 7. Test Multi-Framework Assessment
echo "7️⃣ Testing multi-framework assessment..."
ansible-playbook -i inventory/hosts.yml compliance-automation-playbook.yml \
  --limit commercial_systems \
  -e run_soc2=true \
  -e run_pci_dss=true \
  -e run_iso27001=true \
  -e consolidated_report=true \
  -e assessment_output_dir="${TEST_OUTPUT_DIR}"

# 8. Cleanup
echo "8️⃣ Cleaning up..."
kill $OPA_PID 2>/dev/null || true
cd "${PROJECT_ROOT}"

echo "🎉 All tests completed successfully!"
echo "Test results available in: ${TEST_OUTPUT_DIR}"
echo "Reports generated:"
ls -la "${TEST_OUTPUT_DIR}"/*.html 2>/dev/null || echo "No HTML reports found"
ls -la "${TEST_OUTPUT_DIR}"/*.json 2>/dev/null || echo "No JSON reports found"
```

### Running the Complete Test Suite
```bash
# Run all tests
chmod +x tests/scripts/run_all_tests.sh
./tests/scripts/run_all_tests.sh

# Run specific test categories
./tests/scripts/run_unit_tests.sh
./tests/scripts/run_integration_tests.sh
./tests/scripts/run_ansible_tests.sh
```

## 📊 Test Data Management

### Example Input Data Structure

#### FISMA Compliant Input: `examples/fisma/fisma_compliant_input.json`
```json
{
  "system_categorization": {
    "confidentiality_impact": "high",
    "integrity_impact": "high",
    "availability_impact": "moderate",
    "overall_impact": "high"
  },
  "organizational_preparation": true,
  "system_stakeholders_identified": true,
  "risk_executive_designated": true,
  "authorizing_official_designated": true,
  "nist_controls": {
    "ac_2_account_management": true,
    "au_2_audit_events": true,
    "cm_2_baseline_configuration": true,
    "ia_2_identification_authentication": true,
    "ra_5_vulnerability_scanning": true,
    "sc_7_boundary_protection": true,
    "si_2_flaw_remediation": true
  },
  "system_security_plan": {
    "sections_completed": 7,
    "system_description": true,
    "security_requirements": true,
    "system_boundaries": true,
    "security_controls": true,
    "contingency_planning": true,
    "risk_assessment": true,
    "assessment_procedures": true
  },
  "continuous_monitoring": {
    "define_strategy": true,
    "establish_metrics": true,
    "implement_tools": true,
    "analyze_data": true,
    "respond_findings": true,
    "review_update": true,
    "reporting_frequency": "monthly",
    "automation_level": "high"
  },
  "authorization_status": "authorized"
}
```

#### NERC-CIP Compliant Input: `examples/nerc_cip/nerc_cip_compliant_input.json`
```json
{
  "bes_cyber_systems": [
    {
      "system_id": "BCS-001",
      "system_name": "Energy Management System",
      "impact_categorization": "high",
      "functional_obligations": ["real_time_operations"]
    }
  ],
  "cyber_security_organization": {
    "cso_designated": true,
    "roles_responsibilities_defined": true,
    "senior_manager_identified": true
  },
  "personnel_risk_assessment": {
    "background_verification": true,
    "training_program": true,
    "access_management": true
  },
  "electronic_security_perimeter": {
    "defined": true,
    "documented": true,
    "access_points_controlled": true,
    "external_connectivity_restricted": true
  },
  "physical_security": {
    "physical_security_plan": true,
    "access_controls": true,
    "monitoring_systems": true,
    "visitor_control": true
  }
}
```

### Test Data Generation

#### Script: `tests/scripts/generate_test_data.sh`
```bash
#!/bin/bash

# Generate test variations
echo "Generating test data variations..."

# FISMA variations
python3 << EOF
import json

base_fisma = {
    "system_categorization": {"overall_impact": "high"},
    "nist_controls": {"ac_2_account_management": True}
}

# Generate compliant variation
compliant = base_fisma.copy()
compliant["nist_controls"]["au_2_audit_events"] = True

# Generate non-compliant variation  
non_compliant = base_fisma.copy()
non_compliant["nist_controls"]["au_2_audit_events"] = False

with open('examples/fisma/fisma_test_compliant.json', 'w') as f:
    json.dump(compliant, f, indent=2)

with open('examples/fisma/fisma_test_non_compliant.json', 'w') as f:
    json.dump(non_compliant, f, indent=2)
EOF

echo "Test data generated successfully"
```

## 🔍 Performance Testing

### Load Testing Script: `tests/scripts/load_test.sh`

```bash
#!/bin/bash

echo "🚀 Running OPA Performance Tests"

# Test concurrent assessments
for i in {1..10}; do
    {
        echo "Running assessment $i..."
        curl -s -X POST http://localhost:8181/v1/data/fisma/fisma_assessment \
          -H 'Content-Type: application/json' \
          -d @examples/fisma/fisma_compliant_input.json > /tmp/result_$i.json
        echo "Assessment $i completed"
    } &
done

wait
echo "All concurrent assessments completed"

# Analyze results
echo "Performance analysis:"
for i in {1..10}; do
    if [ -f "/tmp/result_$i.json" ]; then
        echo "Assessment $i: $(jq '.result.compliant' /tmp/result_$i.json)"
    fi
done
```

## 🚨 Continuous Integration Testing

### GitHub Actions Workflow: `.github/workflows/compliance-tests.yml`

```yaml
name: Compliance Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Setup OPA
      run: |
        curl -L -o opa https://openpolicyagent.org/downloads/v1.10.0/opa_linux_amd64_static
        chmod +x opa
        sudo mv opa /usr/local/bin/
    
    - name: Start OPA Server
      run: |
        ./start_opa.sh &
        sleep 5
    
    - name: Run Unit Tests
      run: |
        opa test policies/ tests/unit/ -v
    
    - name: Run Integration Tests
      run: |
        opa test policies/ tests/integration/ -v
    
    - name: Run API Tests
      run: |
        bash tests/api/opa_api_tests.sh
    
    - name: Setup Ansible
      run: |
        pip install ansible
    
    - name: Test Ansible Syntax
      run: |
        cd ansible
        ansible-playbook compliance-automation-playbook.yml --syntax-check
    
    - name: Run Ansible Tests
      run: |
        cd ansible
        ansible-playbook -i inventory/hosts.yml compliance-automation-playbook.yml \
          -e run_fisma=true --check
```

## 📋 Test Documentation

### Test Coverage Report

#### Coverage Script: `tests/scripts/coverage_report.sh`
```bash
#!/bin/bash

echo "📊 Generating Test Coverage Report"

# Count total policies
TOTAL_POLICIES=$(find policies/ -name "*.rego" | wc -l)

# Count tested policies
TESTED_POLICIES=$(find tests/unit/ -name "*_tests.rego" | wc -l)

# Calculate coverage
COVERAGE=$((TESTED_POLICIES * 100 / TOTAL_POLICIES))

echo "Policy Coverage: ${TESTED_POLICIES}/${TOTAL_POLICIES} (${COVERAGE}%)"

# Framework-specific coverage
echo "Framework Coverage:"
for framework in fisma nerc_cip soc2 pci_dss iso27001; do
    policies=$(find "policies/${framework}/" -name "*.rego" 2>/dev/null | wc -l)
    tests=$(find "tests/unit/" -name "${framework}_tests.rego" 2>/dev/null | wc -l)
    if [ $policies -gt 0 ]; then
        framework_coverage=$((tests * 100 / policies))
        echo "  $framework: ${tests}/${policies} (${framework_coverage}%)"
    fi
done
```

### Test Report Generation

The platform automatically generates test reports in multiple formats:

1. **HTML Reports**: Visual test result dashboards
2. **JSON Reports**: Machine-readable test results
3. **JUnit XML**: CI/CD integration format
4. **Coverage Reports**: Policy test coverage analysis

## 🔧 Troubleshooting Tests

### Common Test Issues

#### OPA Server Connection
```bash
# Check OPA health
curl -f http://localhost:8181/health

# Check OPA logs
docker logs opa-server 2>&1 | tail -50
```

#### Policy Loading Issues
```bash
# List loaded policies
curl http://localhost:8181/v1/policies

# Load specific policy
curl -X PUT http://localhost:8181/v1/policies/fisma \
  -H 'Content-Type: text/plain' \
  -d @policies/fisma/fisma_main.rego
```

#### Ansible Test Failures
```bash
# Debug Ansible execution
ansible-playbook compliance-automation-playbook.yml \
  -e run_fisma=true \
  -vvv \
  --check

# Test inventory
ansible-inventory -i inventory/hosts.yml --list
```

### Debug Mode Testing

Enable comprehensive debugging:
```bash
# OPA debug mode
opa run --server --log-level debug --log-format json

# Ansible debug mode
ANSIBLE_DEBUG=1 ansible-playbook compliance-automation-playbook.yml

# Test debug mode
export DEBUG=1
./tests/scripts/run_all_tests.sh
```

This comprehensive testing documentation ensures the platform maintains high quality and reliability across all compliance frameworks and automation components.