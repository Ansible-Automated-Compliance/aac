> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: none specific — unreviewed for 293 days.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

> [!NOTE]
> **2026-10-17:** `ansible/compliance-automation-playbook.yml` and the framework roles it imported
> (`compliance_base`, `iso27001_compliance`, `pci_dss_compliance`, `soc2_compliance`) were removed
> from the tree; nothing called them. Assessments run from `ansible/playbooks/` (for example
> `cis_rhel9_assessment.yml`) through AAP job templates.

# Compliance Framework Documentation

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025


This document provides detailed information about each compliance framework implemented in the OPA Enterprise Compliance Automation Platform.

## 🏛️ FISMA (Federal Information Security Modernization Act)

### Overview
FISMA compliance implementation based on NIST Risk Management Framework (RMF) 2.0, providing comprehensive federal information system security validation.

### Framework Structure
- **Location**: `policies/fisma/`
- **Main Policy**: `fisma_main.rego`
- **Supporting Policies**: 
  - `system_security_plan.rego` - SSP validation per NIST SP 800-18
  - `continuous_monitoring.rego` - ISCM per NIST SP 800-137
  - `authority_to_operate.rego` - ATO assessment framework

### RMF Implementation (7 Steps)
1. **Prepare** - Organizational preparation and planning
2. **Categorize** - System impact categorization (Low/Moderate/High)
3. **Select** - Security control selection based on baseline
4. **Implement** - Security control implementation
5. **Assess** - Security control assessment
6. **Authorize** - Risk determination and ATO decision
7. **Monitor** - Continuous monitoring and assessment

### Key Features
- **System Categorization**: FIPS 199 impact levels (Low, Moderate, High)
- **Security Controls**: NIST SP 800-53 control validation
- **SSP Validation**: 7-section System Security Plan validation
- **ISCM Implementation**: 6-tier maturity assessment (Level 1-5)
- **ATO Framework**: Decision support (AUTHORIZE, CONDITIONAL, INTERIM, DENY)

### Example Usage
```bash
# Test FISMA compliance
opa eval -d policies/fisma/fisma_main.rego \
  -i examples/fisma/fisma_compliant_input.json \
  "data.fisma.fisma_compliant"

# Run via Ansible
ansible-playbook -i inventory/hosts.yml compliance-automation-playbook.yml \
  --limit federal_systems -e run_fisma=true
```

### Input Data Structure
```json
{
  "system_categorization": {
    "confidentiality_impact": "moderate",
    "integrity_impact": "high", 
    "availability_impact": "moderate",
    "overall_impact": "high"
  },
  "nist_controls": {
    "ac_2_account_management": true,
    "au_2_audit_events": true,
    "cm_2_baseline_configuration": true
  },
  "system_security_plan": {
    "sections_completed": 7,
    "system_description": true,
    "security_requirements": true
  }
}
```

---

## ⚡ NERC-CIP (Critical Infrastructure Protection)

### Overview
North American Electric Reliability Corporation Critical Infrastructure Protection standards for Bulk Electric System (BES) cybersecurity.

### Framework Structure
- **Location**: `policies/nerc_cip/`
- **Main Policy**: `nerc_cip_simplified.rego` (core 5 standards)
- **Comprehensive Policy**: `nerc_cip_comprehensive.rego` (all 13 standards)

### CIP Standards Coverage
- **CIP-002**: BES Cyber System Categorization
- **CIP-003**: Cyber Security Organization  
- **CIP-004**: Personnel & Training
- **CIP-005**: Electronic Security Perimeter
- **CIP-006**: Physical Security of BES Cyber Systems
- **CIP-007**: System Security Management
- **CIP-008**: Incident Reporting and Response Planning
- **CIP-009**: Recovery Plans for BES Cyber Systems

### Key Features
- **BES Categorization**: High, Medium, Low impact classification
- **Cyber Asset Protection**: Cyber assets and protected cyber assets
- **ESP Management**: Electronic Security Perimeter controls
- **Physical Security**: Multi-layer physical protection
- **Personnel Security**: Background verification and training

### Example Usage
```bash
# Test NERC-CIP compliance
opa eval -d policies/nerc_cip/nerc_cip_simplified.rego \
  -i examples/nerc_cip/nerc_cip_compliant_input.json \
  "data.nerc_cip.nerc_cip_compliant"

# Run via Ansible
ansible-playbook -i inventory/hosts.yml compliance-automation-playbook.yml \
  --limit utility_systems -e run_nerc_cip=true
```

### Input Data Structure
```json
{
  "bes_cyber_systems": [
    {
      "system_id": "BCS-001",
      "impact_categorization": "high",
      "functional_obligations": ["real_time_operations"]
    }
  ],
  "electronic_security_perimeter": {
    "defined": true,
    "documented": true,
    "access_points_controlled": true
  },
  "physical_security": {
    "physical_security_plan": true,
    "access_controls": true,
    "monitoring_systems": true
  }
}
```

---

## 🔒 SOC 2 (Service Organization Control 2)

### Overview
AICPA Trust Services Criteria for service organizations, focusing on security, availability, processing integrity, confidentiality, and privacy.

### Framework Structure
- **Location**: `policies/soc2/`
- **Trust Services Criteria**: 5 main categories with detailed controls
- **Assessment Types**: Type I (design) and Type II (operating effectiveness)

### Trust Services Categories
1. **Security**: Protection against unauthorized access
2. **Availability**: System operation and usability as committed
3. **Processing Integrity**: Complete, valid, accurate, timely processing
4. **Confidentiality**: Information designated as confidential is protected
5. **Privacy**: Personal information collection, use, retention, disclosure

### Key Features
- **Control Environment**: Organization-wide policies and procedures
- **Risk Assessment**: Identification and analysis of risks
- **Control Activities**: Policies and procedures to address risks
- **Information & Communication**: Quality information and communication
- **Monitoring**: Ongoing and periodic evaluations

---

## 💳 PCI-DSS (Payment Card Industry Data Security Standard)

### Overview
Security standards for organizations that handle credit card information, ensuring cardholder data protection.

### Framework Structure
- **Location**: `policies/pci_dss/`
- **Requirements**: 12 core requirements across 6 categories
- **Merchant Levels**: Level 1-4 based on transaction volume

### PCI-DSS Requirements
1. **Install and maintain firewall configuration**
2. **Do not use vendor-supplied defaults for passwords**
3. **Protect stored cardholder data**
4. **Encrypt transmission of cardholder data**
5. **Use and regularly update anti-virus software**
6. **Develop and maintain secure systems and applications**
7. **Restrict access to cardholder data by business need-to-know**
8. **Assign a unique ID to each person with computer access**
9. **Restrict physical access to cardholder data**
10. **Track and monitor all access to network resources**
11. **Regularly test security systems and processes**
12. **Maintain a policy that addresses information security**

### Key Features
- **Cardholder Data Environment**: Scope definition and protection
- **Vulnerability Management**: Regular scanning and patching
- **Access Control**: Strong access control measures
- **Network Security**: Secure network architecture
- **Regular Testing**: Penetration testing and vulnerability assessments

---

## 🌐 ISO 27001 (Information Security Management System)

### Overview
International standard for Information Security Management Systems (ISMS), providing systematic approach to managing sensitive company information.

### Framework Structure
- **Location**: `policies/iso27001/`
- **Clauses**: 10 main clauses (4-10)
- **Annex A**: 93 security controls across 4 categories

### ISMS Clauses
- **Clause 4**: Context of the Organization
- **Clause 5**: Leadership
- **Clause 6**: Planning
- **Clause 7**: Support
- **Clause 8**: Operation
- **Clause 9**: Performance Evaluation
- **Clause 10**: Improvement

### Annex A Control Categories
- **A.5**: Organizational controls (37 controls)
- **A.6**: People controls (8 controls) 
- **A.7**: Physical and environmental security (14 controls)
- **A.8**: Technological controls (34 controls)

### Key Features
- **Risk Management**: Systematic risk assessment and treatment
- **ISMS Scope**: Clear boundaries and applicability
- **Policy Framework**: Information security policy structure
- **Internal Audits**: Regular ISMS effectiveness review
- **Management Review**: Top management ISMS review
- **Continual Improvement**: PDCA cycle implementation

---

## 🛡️ CIS Benchmarks

### Overview
Technology-specific security configuration guidelines covering cloud providers, operating systems, applications, and network devices.

### Framework Structure
- **Location**: `policies/cis/`
- **Categories**: 8 major technology categories
- **Controls**: 200+ individual security controls

### Technology Categories
1. **Cloud Providers**: AWS, Azure, Google Cloud Platform
2. **Operating Systems**: Linux distributions, Windows Server
3. **DevSecOps Tools**: Docker, Kubernetes, Jenkins
4. **Mobile Devices**: iOS, Android
5. **Server Software**: Apache, NGINX, MySQL, PostgreSQL
6. **Network Devices**: Cisco, Juniper, Palo Alto Networks
7. **Desktop Software**: Microsoft Office, macOS
8. **DISA STIG**: Government security implementation guides

### Key Features
- **Baseline Security**: Consensus-based security configurations
- **Implementation Levels**: Level 1 (basic) and Level 2 (defense-in-depth)
- **Automated Assessment**: Machine-readable benchmarks
- **Vendor Neutral**: Technology-agnostic security guidance
- **Community Driven**: Industry expert consensus

---

## Multi-Framework Integration

### Consolidated Assessment
The platform supports simultaneous assessment across multiple frameworks:

```bash
# Run all frameworks simultaneously
ansible-playbook -i inventory/hosts.yml compliance-automation-playbook.yml \
  -e run_fisma=true \
  -e run_nerc_cip=true \
  -e run_soc2=true \
  -e run_pci_dss=true \
  -e run_iso27001=true \
  -e consolidated_report=true
```

### Consolidated Reporting
- **Single HTML Report**: Professional dashboard showing all framework results
- **Compliance Scoring**: Weighted scoring across frameworks
- **Executive Summary**: High-level compliance posture overview
- **Detailed Findings**: Framework-specific violations and recommendations
- **Trend Analysis**: Historical compliance tracking

### Framework Mapping
- **Common Controls**: Identification of overlapping requirements
- **Control Correlation**: Mapping between framework requirements
- **Unified Assessment**: Single assessment satisfying multiple frameworks
- **Gap Analysis**: Identification of framework-specific gaps

## Testing and Validation

Each framework includes comprehensive test examples:

### Test Structure
```
examples/
├── fisma/
│   ├── fisma_compliant_input.json
│   └── fisma_non_compliant_input.json
├── nerc_cip/
│   ├── nerc_cip_compliant_input.json
│   └── nerc_cip_non_compliant_input.json
└── multi_framework/
    └── consolidated_input.json
```

### Running Tests
```bash
# Test all frameworks
opa test policies/ tests/ -v

# Test specific framework
opa test policies/fisma/ tests/ -v

# Test with example data
opa eval -d policies/fisma/fisma_main.rego \
  -i examples/fisma/fisma_compliant_input.json \
  "data.fisma.fisma_assessment"
```

## Customization Guidelines

### Adding New Controls
1. **Identify Requirements**: Map regulatory requirements to technical controls
2. **Define Input Schema**: Structure expected configuration data
3. **Implement Logic**: Write Rego rules for compliance validation
4. **Create Tests**: Develop positive and negative test cases
5. **Update Documentation**: Document new controls and usage

### Framework Extension
1. **Create Directory Structure**: Follow established patterns
2. **Implement Base Rules**: Core compliance logic
3. **Add Assessment Logic**: Violation detection and scoring
4. **Create Ansible Role**: Automation integration
5. **Develop Examples**: Sample input and test data

### Integration Points
- **OPA Policies**: Core compliance logic in Rego
- **Ansible Roles**: Automation and orchestration
- **Fact Collection**: System configuration gathering
- **Reporting**: HTML dashboard generation
- **API Integration**: REST endpoints for external tools