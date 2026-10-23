> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: none specific — unreviewed for 293 days.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# NIST Standards Complete Directory Structure

This document outlines the comprehensive directory structure for all NIST (National Institute of Standards and Technology) cybersecurity frameworks and standards.

## Root Structure

```
policies/nist/
├── cybersecurity_framework_2.0/        # NIST CSF 2.0 functions
├── sp_800_53/                          # Security and Privacy Controls
├── sp_800_171/                         # Controlled Unclassified Information (CUI)
├── risk_management_framework/           # RMF lifecycle steps
└── privacy_framework/                  # Privacy Framework functions
```

## Detailed Structure by Framework

### 1. NIST Cybersecurity Framework 2.0 (`cybersecurity_framework_2.0/`)

The NIST CSF 2.0 is organized around **six core functions**:

```
cybersecurity_framework_2.0/
├── govern/                             # GV - Governance and risk management
├── identify/                           # ID - Asset and risk identification
├── protect/                            # PR - Protective safeguards
├── detect/                             # DE - Detection activities
├── respond/                            # RS - Response planning and activities
└── recover/                            # RC - Recovery planning and activities
```

#### Core Functions Detail:

**GOVERN (GV)**
- GV.OC: Organizational Context
- GV.RM: Risk Management Strategy
- GV.SC: Supply Chain Risk Management
- GV.PO: Policy, Procedures, and Processes

**IDENTIFY (ID)**
- ID.AM: Asset Management
- ID.RA: Risk Assessment
- ID.IM: Improvement

**PROTECT (PR)**
- PR.AC: Identity Management and Access Control
- PR.AT: Awareness and Training
- PR.DS: Data Security
- PR.IP: Information Protection Processes and Procedures
- PR.MA: Maintenance
- PR.PT: Protective Technology

**DETECT (DE)**
- DE.AE: Anomalies and Events
- DE.CM: Security Continuous Monitoring
- DE.DP: Detection Processes

**RESPOND (RS)**
- RS.RP: Response Planning
- RS.CO: Communications
- RS.AN: Analysis
- RS.MI: Mitigation
- RS.IM: Improvements

**RECOVER (RC)**
- RC.RP: Recovery Planning
- RC.IM: Improvements
- RC.CO: Communications

### 2. NIST SP 800-53 (`sp_800_53/`)

Security and Privacy Controls for Information Systems and Organizations:

```
sp_800_53/
├── access_control/                     # AC - Access Control
├── awareness_training/                 # AT - Awareness and Training
├── audit_accountability/               # AU - Audit and Accountability
├── assessment_authorization/           # CA - Assessment, Authorization, and Monitoring
├── configuration_management/           # CM - Configuration Management
├── contingency_planning/               # CP - Contingency Planning
├── identification_authentication/      # IA - Identification and Authentication
├── incident_response/                  # IR - Incident Response
├── maintenance/                        # MA - Maintenance
├── media_protection/                   # MP - Media Protection
├── physical_environmental/             # PE - Physical and Environmental Protection
├── planning/                          # PL - Planning
├── personnel_security/                # PS - Personnel Security
├── risk_assessment/                   # RA - Risk Assessment
├── system_acquisition/                # SA - System and Services Acquisition
├── system_communications/             # SC - System and Communications Protection
└── system_information_integrity/      # SI - System and Information Integrity
```

#### Control Families (18 families total):

1. **AC - Access Control**: 25 controls (AC-1 through AC-25)
2. **AT - Awareness and Training**: 6 controls (AT-1 through AT-6)
3. **AU - Audit and Accountability**: 16 controls (AU-1 through AU-16)
4. **CA - Assessment, Authorization, and Monitoring**: 9 controls (CA-1 through CA-9)
5. **CM - Configuration Management**: 14 controls (CM-1 through CM-14)
6. **CP - Contingency Planning**: 13 controls (CP-1 through CP-13)
7. **IA - Identification and Authentication**: 12 controls (IA-1 through IA-12)
8. **IR - Incident Response**: 10 controls (IR-1 through IR-10)
9. **MA - Maintenance**: 7 controls (MA-1 through MA-7)
10. **MP - Media Protection**: 8 controls (MP-1 through MP-8)
11. **PE - Physical and Environmental Protection**: 23 controls (PE-1 through PE-23)
12. **PL - Planning**: 11 controls (PL-1 through PL-11)
13. **PS - Personnel Security**: 9 controls (PS-1 through PS-9)
14. **RA - Risk Assessment**: 10 controls (RA-1 through RA-10)
15. **SA - System and Services Acquisition**: 23 controls (SA-1 through SA-23)
16. **SC - System and Communications Protection**: 51 controls (SC-1 through SC-51)
17. **SI - System and Information Integrity**: 23 controls (SI-1 through SI-23)
18. **PM - Program Management**: 32 controls (PM-1 through PM-32)

### 3. NIST SP 800-171 (`sp_800_171/`)

Protecting Controlled Unclassified Information (CUI) in Nonfederal Systems:

```
sp_800_171/
├── access_control/                     # 3.1 - Access Control (22 requirements)
├── audit_accountability/               # 3.3 - Audit and Accountability (9 requirements)
├── awareness_training/                 # 3.2 - Awareness and Training (3 requirements)
├── configuration_management/           # 3.4 - Configuration Management (9 requirements)
├── identification_authentication/      # 3.5 - Identification and Authentication (11 requirements)
├── incident_response/                  # 3.6 - Incident Response (3 requirements)
├── maintenance/                        # 3.7 - Maintenance (6 requirements)
├── media_protection/                   # 3.8 - Media Protection (9 requirements)
├── personnel_security/                 # 3.9 - Personnel Security (4 requirements)
├── physical_protection/                # 3.10 - Physical Protection (6 requirements)
├── risk_assessment/                    # 3.11 - Risk Assessment (5 requirements)
├── security_assessment/                # 3.12 - Security Assessment (4 requirements)
├── system_communications/              # 3.13 - System and Communications Protection (19 requirements)
└── system_information_integrity/       # 3.14 - System and Information Integrity (7 requirements)
```

#### CUI Requirement Categories (14 families total):

**Total: 110 security requirements** across 14 families, derived from NIST SP 800-53.

### 4. Risk Management Framework (`risk_management_framework/`)

The 7-step RMF process for managing cybersecurity and privacy risk:

```
risk_management_framework/
├── categorize/                         # Step 1: Categorize the system
├── select/                            # Step 2: Select controls
├── implement/                         # Step 3: Implement controls
├── assess/                            # Step 4: Assess controls
├── authorize/                         # Step 5: Authorize the system
└── monitor/                           # Step 6: Monitor controls
                                      # Step 7: Prepare (ongoing)
```

#### RMF Steps Detail:

1. **CATEGORIZE**: Information system categorization based on FIPS 199
2. **SELECT**: Control selection based on security categorization
3. **IMPLEMENT**: Control implementation with configuration management
4. **ASSESS**: Control assessment for effectiveness
5. **AUTHORIZE**: Risk-based authorization decision
6. **MONITOR**: Continuous monitoring of controls and risks
7. **PREPARE**: Essential activities across all steps

### 5. Privacy Framework (`privacy_framework/`)

NIST Privacy Framework functions for privacy risk management:

```
privacy_framework/
├── identify_p/                         # Identify-P: Privacy risk identification
├── govern_p/                          # Govern-P: Privacy governance
├── control_p/                         # Control-P: Privacy controls
├── communicate_p/                     # Communicate-P: Privacy communications
└── protect_p/                         # Protect-P: Privacy protection
```

## NIST Framework Integration and Mappings

### CSF 2.0 to SP 800-53 Mapping
The Cybersecurity Framework provides informative references to SP 800-53 controls, enabling organizations to use both frameworks together.

### SP 800-171 to SP 800-53 Derivation
SP 800-171 requirements are derived from SP 800-53 controls, specifically tailored for protecting CUI in nonfederal systems.

### RMF Integration
The Risk Management Framework provides the process for implementing SP 800-53 controls and can incorporate CSF guidance.

## Impact Levels and Control Baselines

### FIPS 199 Security Categories
- **Low Impact**: Limited adverse effect
- **Moderate Impact**: Serious adverse effect  
- **High Impact**: Severe or catastrophic adverse effect

### SP 800-53 Control Baselines
- **Low Baseline**: 125 controls
- **Moderate Baseline**: 204 controls
- **High Baseline**: 253 controls

### SP 800-171 Requirements
- **110 requirements** applicable to all CUI systems regardless of impact level

## Usage Patterns

### File Naming Convention
- Use descriptive names matching NIST control/requirement identifiers
- Include framework abbreviations where applicable
- Use snake_case for file names
- Example: `ac_access_control.rego`, `csf_govern.rego`

### Package Naming Convention
- Follow hierarchical structure: `nist.{framework}.{category}.{subcategory}`
- Examples:
  - `nist.csf.govern`
  - `nist.sp800_53.access_control`
  - `nist.sp800_171.access_control`
  - `nist.rmf.categorize`

### Control Implementation Levels
- **Basic**: Minimum implementation requirements
- **Enhanced**: Additional implementation guidance
- **Tailored**: Organization-specific adaptations

## Implementation Status

### ✅ Implemented
- NIST CSF 2.0 Govern Function (20 subcategories)
- NIST CSF 2.0 Protect Function (24 subcategories)
- NIST SP 800-53 Access Control Family (25 controls)
- NIST SP 800-171 Access Control Requirements (22 requirements)
- NIST RMF Categorization Step (12 activities)

### 🚧 In Progress
- Complete NIST CSF 2.0 functions (Identify, Detect, Respond, Recover)
- Additional SP 800-53 control families
- Complete SP 800-171 requirement families
- Remaining RMF steps

### 📋 Planned
- NIST Privacy Framework functions
- Advanced control implementations
- Cross-framework mappings
- Automated compliance reporting

## Integration with Existing CIS Library

The NIST library complements the existing CIS benchmark library:

```
policies/
├── cis/                               # CIS Benchmarks (technology-specific)
│   ├── cloud_providers/
│   ├── operating_systems/
│   └── ...
└── nist/                              # NIST Standards (process and control-oriented)
    ├── cybersecurity_framework_2.0/
    ├── sp_800_53/
    └── ...
```

### Complementary Coverage:
- **CIS**: Technology-specific hardening benchmarks
- **NIST**: Process frameworks and security controls
- **Combined**: Comprehensive cybersecurity compliance program

## Contributing

When adding new NIST controls or requirements:

1. Follow the established directory structure
2. Use consistent package naming conventions
3. Include comprehensive test coverage
4. Document input data requirements
5. Provide example configurations
6. Map to related frameworks where applicable

## References

- [NIST Cybersecurity Framework 2.0](https://www.nist.gov/cyberframework)
- [NIST SP 800-53 Rev 5](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
- [NIST SP 800-171 Rev 3](https://csrc.nist.gov/pubs/sp/800/171/r3/ipd)
- [NIST Risk Management Framework](https://csrc.nist.gov/projects/risk-management)
- [NIST Privacy Framework](https://www.nist.gov/privacy-framework)
- [FIPS 199](https://csrc.nist.gov/pubs/fips/199/final)