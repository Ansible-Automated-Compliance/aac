# NERC CIP Compliance Coverage

**Version:** v1.0
**Date:** 2026-07-16
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic)

**Standard:** NERC Critical Infrastructure Protection (CIP)
**Policy Location:** `policies/frameworks/critical_infrastructure/nerc_cip/`
**OPA Container:** `opa-ot` (port 8183)
**Coverage:** CIP-002 through CIP-015 (14 standards + aggregator)

---

## Overview

NERC CIP standards protect the Bulk Electric System (BES) from cybersecurity threats. AAC implements all 14 active CIP standards as OPA Rego policies, continuously assessing BES Cyber Systems against each requirement.

**Penalties:** Up to $1,000,000 per violation per day (FERC enforcement)

**Applicable Entities:**
- Transmission Owners and Operators
- Generation Owners and Operators
- Distribution Providers (where applicable)
- Reliability Coordinators
- Balancing Authorities

---

## Coverage Summary

| Standard | Title | Requirements | OPA Package |
|----------|-------|-------------|-------------|
| CIP-002-5.1a | BES Cyber System Categorization | R1–R3 | `nerc_cip.cip_002` |
| CIP-003-8 | Security Management Controls | R1–R6 | `nerc_cip.cip_003` |
| CIP-004-6 | Personnel & Training | R1–R6 | `nerc_cip.cip_004` |
| CIP-005-7 | Electronic Security Perimeters | R1–R3 | `nerc_cip.cip_005` |
| CIP-006-6 | Physical Security of BES Cyber Systems | R1–R3 | `nerc_cip.cip_006` |
| CIP-007-6 | Systems Security Management | R1–R6 | `nerc_cip.cip_007` |
| CIP-008-6 | Incident Reporting and Response | R1–R4 | `nerc_cip.cip_008` |
| CIP-009-6 | Recovery Plans for BES Cyber Systems | R1–R3 | `nerc_cip.cip_009` |
| CIP-010-4 | Configuration Change Management & Vulnerability | R1–R4 | `nerc_cip.cip_010` |
| CIP-011-3 | Information Protection | R1–R2 | `nerc_cip.cip_011` |
| CIP-012-1 | Communications Between Control Centers | R1 | `nerc_cip.cip_012` |
| CIP-013-2 | Supply Chain Risk Management | R1–R6 | `nerc_cip.cip_013` |
| CIP-014-3 | Physical Security of Transmission Stations | R1–R6 | `nerc_cip.cip_014` |
| CIP-015-1 | Internal Network Security Monitoring | R1–R3 | `nerc_cip_cip015` |

---

## Standard Details

### CIP-002 — BES Cyber System Categorization

**Purpose:** Identify and categorize BES Cyber Systems by impact level (High, Medium, Low) to determine which CIP requirements apply.

**Key Controls:**
- BES Cyber Systems identified using NERC Attachment 1 criteria
- Systems categorized as High, Medium, or Low impact
- Categorization reviewed and approved by CIP Senior Manager annually
- Low-impact systems identified with documented process

**Input:** `bes_cyber_systems[]` with `impact_level`, `categorization_rationale`, `senior_manager_approved`

**Why It Matters:** All other CIP requirements depend on correct categorization. Miscategorized systems result in under-protection and automatic violations.

---

### CIP-003 — Security Management Controls

**Purpose:** Establish cybersecurity management accountability and governance at the senior leadership level.

**Key Controls:**
- Cybersecurity policy documented and approved by CIP Senior Manager
- One or more documented cybersecurity policies covering all 11 topic areas
- CIP Senior Manager identified by name and title
- Delegations documented if responsibilities are delegated
- Annual policy review and re-approval
- Low-impact BES Cyber System protections documented

**11 Required Policy Topic Areas:** Physical security, electronic security, configuration management, vulnerability management, incident response, recovery, personnel training, information protection, supply chain, communications, and access management.

**Input:** `cybersecurity_organization`, `policies[]`, `low_impact_protections`

---

### CIP-004 — Personnel & Training

**Purpose:** Ensure personnel with access to BES Cyber Systems are trained, risk-assessed, and managed appropriately.

**Key Controls:**
- Cybersecurity awareness training at least every 15 months
- Role-based training before access is granted (or within 90 days for existing personnel)
- Personnel risk assessments (background checks) every 7 years
- Access revoked within 24 hours of termination
- Quarterly access reviews for all authorized personnel
- Training records maintained for 3 years

**Input:** `personnel[]` with `training_records`, `risk_assessment_date`, `access_level`, `termination_date`

---

### CIP-005 — Electronic Security Perimeters

**Purpose:** Define and protect Electronic Security Perimeters (ESPs) around BES Cyber Systems with External Routable Connectivity (ERC).

**Key Controls:**
- All applicable BES Cyber Systems placed inside a defined ESP
- All External Routable Connectivity through an Electronic Access Point (EAP)
- Inbound/outbound access permissions documented with business justification
- Dial-up connectivity protected (if used)
- Interactive Remote Access via encrypted, multi-factor authenticated sessions only
- Intermediate systems for remote access (jump servers)
- Session timeout after 15 minutes of inactivity

**Input:** `esps[]`, `eaps[]`, `remote_access` configuration

---

### CIP-006 — Physical Security

**Purpose:** Implement physical security controls for High and Medium Impact BES Cyber Systems.

**Key Controls:**
- Physical Security Perimeters (PSPs) defined for all applicable systems
- Six-wall boundary implemented (floor, ceiling, all walls)
- Access restricted to authorized personnel only
- Two-factor authentication for physical access (where applicable)
- Visitor access controlled and logged
- Physical access logs retained for 90 days
- Monitoring/alerting for unauthorized access attempts
- Operational Technology (OT) equipment physically protected

**Input:** `physical_security_perimeters[]`, `visitor_control`, `access_monitoring`

---

### CIP-007 — Systems Security Management

**Purpose:** Manage the security of BES Cyber System components through port control, patching, malware prevention, and logging.

**Key Controls (16 requirements tracked):**
- Only necessary ports and services enabled (documented justification for all)
- Security patches applied within 35 days of availability (or compensating controls)
- Patch management process documented with 35-day SLA
- Anti-malware deployed on applicable systems
- Anti-malware signatures updated at least every 35 days
- Security event logging enabled (authentication, config changes, process activity)
- Log retention minimum 90 days (online), 3 years (archive)
- System access attempts logged
- Default and shared accounts eliminated or controlled
- Password complexity and change requirements enforced

**Input:** `enabled_ports[]`, `patch_management`, `anti_malware`, `logging_configuration`, `account_management`

---

### CIP-008 — Incident Reporting and Response

**Purpose:** Identify, classify, respond to, and report Cyber Security Incidents affecting BES Cyber Systems.

**Key Controls:**
- Incident response plan documented and approved
- Incident response team roles defined and staffed
- Process to identify and classify Cyber Security Incidents
- Reportable incidents reported to E-ISAC and NERC within 1 hour of determination
- Incident response plan exercised at least every 15 months (tabletop or full exercise)
- After-action review completed within 60 days of exercise or actual incident
- Plan updated based on lessons learned

**Input:** `incident_response_plan`, `incident_response_team[]`, `incident_history[]`

---

### CIP-009 — Recovery Plans

**Purpose:** Ensure BES Cyber Systems can be recovered following a Cyber Security Incident.

**Key Controls (12 requirements tracked):**
- Recovery plan documented for each applicable BES Cyber System
- Recovery time objectives defined
- Recovery plan exercised at least every 15 months
- Backup and restore procedures tested
- Backup media stored at alternate location
- Backup integrity verified
- Lessons learned incorporated within 60 days
- Preservation of forensic data during recovery
- Notification to appropriate parties during recovery

**Input:** `recovery_plans[]`, `backup_configurations[]`, `recovery_tests[]`

---

### CIP-010 — Configuration Change Management & Vulnerability Assessment

**Purpose:** Prevent unauthorized modifications and identify vulnerabilities in BES Cyber System configurations.

**Key Controls (12 requirements tracked):**
- Baseline configurations documented for all applicable systems (OS, firmware, ports, software, security patches)
- Unauthorized change detection within 35 days
- Configuration changes authorized before implementation
- Transient devices (laptops, USB) managed with documented security controls
- Vulnerability assessments every 15 months (High Impact) or 36 months (Medium Impact)
- Active vulnerability scanning where technically feasible
- Newly identified vulnerabilities remediated or mitigated within 35 days
- Paper-based vulnerability assessments where active scanning not feasible

**Input:** `system_baselines[]`, `configuration_changes[]`, `vulnerability_assessments[]`, `transient_devices`

---

### CIP-011 — Information Protection

**Purpose:** Protect BES Cyber System Information (BCSI) from unauthorized access and disclosure.

**Key Controls (12 requirements tracked):**
- BCSI identified and classified
- Access to BCSI restricted to authorized personnel only
- BCSI access list reviewed at least every 15 months
- BCSI stored securely (encrypted or physical controls)
- BCSI transmitted only over protected channels
- BCSI properly disposed of when no longer needed (sanitization standard)
- Third-party access to BCSI controlled by contract
- BCSI stored with cloud or third-party providers — additional controls required

**Input:** `bcsi_inventory[]`, `bcsi_access_controls`, `bcsi_storage`, `bcsi_transmission`

---

### CIP-012 — Communications Between Control Centers

**Purpose:** Protect real-time assessment and monitoring data transmitted between Control Centers.

**Key Controls:**
- Communication links between Control Centers identified
- Data transmitted over protected links (encryption or equivalent protection)
- Protection method documented with business justification
- Unencrypted links require documented compensating controls
- Communication link inventory maintained and reviewed
- Monitoring for communication link availability

**Input:** `control_center_communications[]` with `link_type`, `encryption_method`, `protection_documented`

---

### CIP-013 — Supply Chain Risk Management

**Purpose:** Manage cybersecurity risks in the supply chain for BES Cyber Systems and associated hardware/software.

**Key Controls:**
- Supply chain cybersecurity risk management plan documented
- Vendor vulnerability notification processes established
- Vendor incident notification processes established
- Software and firmware authenticity verification procedures
- Vendor remote access controls
- Vendor risk assessments for all critical suppliers
- Security requirements in vendor contracts
- Supply chain monitoring (threat intelligence, vulnerability tracking)
- Plan reviewed every 15 months and approved by CIP Senior Manager

**Vendor Contract Requirements:** Vulnerability disclosure capability, incident response capability, software development practices, right to audit.

**Input:** `supply_chain_plan`, `vendors[]`, `vendor_risk_assessments`, `vendor_contracts`, `supply_chain_monitoring`

---

### CIP-014 — Physical Security of Transmission Stations

**Purpose:** Identify and protect Transmission stations and substations that, if damaged, could cause widespread instability or uncontrolled cascading.

**Key Controls:**
- Risk assessment identifies applicable Transmission stations (power flow analysis, contingency analysis, cascading potential)
- Risk assessment performed every 30 calendar months
- Unaffiliated third-party verifies risk assessment within 90 days
- Reliability Coordinator notified of verification completion
- Physical security plans developed for all applicable stations
- Physical threat assessments by qualified experts
- Security plans implemented within 12 months of third-party verification
- Plans reviewed every 36 calendar months
- Unaffiliated third party with physical security expertise reviews each plan

**Input:** `transmission_risk_assessment`, `applicable_transmission_stations[]`, `station_security_plans`

---

### CIP-015 — Internal Network Security Monitoring (INSM)

**Status:** FERC-approved, **NOT yet enforceable.** CIP-015-1 was approved by FERC Order 907
(26 June 2025); CIP-015-2 was approved under Docket RD26-6-000 (10 August 2026).

**Effective dates:**

| Version | Effective | Applicability |
|---|---|---|
| CIP-015-1 | **1 Oct 2028** | High impact BCS, and Medium impact at Control Centers |
| CIP-015-1 | **1 Oct 2030** | Medium impact with External Routable Connectivity elsewhere |
| CIP-015-2 | **1 Oct 2029** | Extends INSM beyond the ESP to EACMS, PACS, SCI and PCAs. CIP-015-1 retires immediately before v2 takes effect |

> **Corrected 2026-08-24.** This section previously stated "in effect ... effective April 1, 2026"
> with a Medium-impact date of April 1, 2027. Both were wrong, and in the worst direction — they
> described a future obligation as already enforceable. **Nothing in CIP-015 is enforceable today.**
> Do not build urgency on a compliance date that has not arrived; the real argument is that an
> architecture chosen now is what gets audited in 2028–2029.

> ⚠️ **Requirement structure below needs verification against the NERC standards register before
> customer use.** Published summaries of CIP-015-1 describe **R1** as a documented INSM process
> (R1.1 risk-based network data feeds, R1.2 methods to detect anomalous activity, R1.3 methods to
> evaluate detected anomalies), **R2** as retention of data associated with anomalous activity, and
> **R3** as protection of collected data against unauthorized deletion or modification. That does
> not match the R1/R2.1–R2.4/R3 breakdown documented below, which also drives the input contract of
> the `nerc_cip_cip015` Rego module. Reconcile the standard text, this section, and the module
> together — changing only this page would leave the policy evaluating the wrong shape.

**Purpose:** Implement internal network monitoring within Electronic Security Perimeters to detect threats that have bypassed the perimeter.

**Key Controls:**
- **R1:** Identify BES Cyber Systems with High/Medium impact and External Routable Connectivity requiring INSM; review annually
- **R2.1:** Establish and document network baseline within each ESP
- **R2.2:** Implement anomaly detection covering the full ESP
- **R2.3:** Document capability to identify malicious communications; list detection tools
- **R2.4:** Document response process for anomalous/malicious communications including notification and investigation procedures
- **R3:** INSM documentation established with identified reviewer; reviewed every 15 calendar months

**Why It Matters:** CIP-015 addresses the gap where threats penetrate the ESP perimeter and move laterally undetected. It is the most recently approved CIP standard and reflects lessons learned from attacks on operational technology environments.

**Input:** `insm.systems[]` with ESP, baseline, anomaly detection, and response configs; `insm.documentation_review`

---

## OPA Endpoints

All endpoints are served by the `opa-ot` container on port 8183. The host is
environment-specific — substitute `<opa-ot-host>` with the deployed address. The OPA
data path mirrors each policy's Rego `package` declaration (underscores/dots become
slashes), so the paths below are exact.

| Assessment | Endpoint |
|-----------|---------|
| Full NERC-CIP (all standards) | `POST http://<opa-ot-host>:8183/v1/data/nerc_cip_main` |
| CIP-015 INSM only | `POST http://<opa-ot-host>:8183/v1/data/nerc_cip_cip015/cip_015_compliance_report` |
| Individual standard | `POST http://<opa-ot-host>:8183/v1/data/nerc_cip/cip_00X/compliance_report` (e.g. `nerc_cip/cip_007`) |

---

## Compliance Levels

| Level | Score | Description |
|-------|-------|-------------|
| `fully_compliant` | 90–100% | All or nearly all requirements met |
| `substantially_compliant` | 70–89% | Most requirements met; gaps documented |
| `partially_compliant` | 50–69% | Significant gaps; immediate action required |
| `non_compliant` | <50% | Critical deficiencies; regulatory exposure |

---

## AAP Integration

**Job Templates:**
| ID | Name | Description |
|----|------|-------------|
| 26 | AAC - NERC CIP Compliance Report | Full CIP-002 through CIP-015 assessment |
| 27 | AAC - Load OPA Policies | Reload policies into opa-ot container |

**Example playbook:**
```yaml
- name: NERC CIP Assessment
  hosts: localhost
  connection: local
  tasks:
    - name: Run full CIP assessment
      uri:
        url: "http://{{ opa_ot_host }}:8183/v1/data/nerc_cip_main"
        method: POST
        body_format: json
        body: "{{ lookup('file', 'examples/nerc_cip_assessment_data.yml') | from_yaml }}"
      register: cip_result

    - name: Show compliance level
      debug:
        msg: "CIP Level: {{ cip_result.json.result.compliance_level }} ({{ cip_result.json.result.compliance_score }}%)"
```

---

## Sample Assessment Data

`examples/nerc_cip_assessment_data.yml` includes three pre-built BES Cyber Systems:
- **EMS** (Energy Management System) — High Impact
- **SCADA** (Supervisory Control) — High Impact
- **Substation RTU** — Medium Impact

Use as a template for real utility assessments.
