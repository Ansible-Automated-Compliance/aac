---
title: "AMI 2.0 Compliance Assessment — Audit Scope"
subtitle: "Ansible Automated Compliance (AAC) | Utility / Energy Sector"
date: "March 2026"
author: "Ansible Automated Compliance Platform"
---

> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx5, SPLIT-PORTSx4.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.


# AMI 2.0 Compliance Assessment — Audit Scope

**Platform:** Ansible Automated Compliance (AAC)
**Sector:** Utility / Energy — Advanced Metering Infrastructure
**Assessment Date:** March 2026
**Utilities Assessed:** Electric, Gas, Water

---

## Overview

The AMI 2.0 compliance assessment evaluates Advanced Metering Infrastructure against three complementary frameworks, providing end-to-end coverage from smart meter devices through communications networks to the MDMS head-end system. Results are stored to PostgreSQL and visualised in Grafana.

Each utility (electric, gas, water) is assessed independently across all three frameworks.

---

## Framework 1 — NIST IR 7628 Rev 1: Smart Grid Cybersecurity

**OPA Endpoint:** `POST http://AAP_HOST:8183/v1/data/ami/nist_ir7628/complete`
**AAP Job Template:** AMI - NIST IR 7628 Assessment (ID 41)

NIST IR 7628 is the primary smart grid cybersecurity framework, covering the entire AMI ecosystem: head-end systems, communication networks, and end devices. Six control families are assessed.

### SG.AC — Access Control

| Control | Description |
|---------|-------------|
| SG.AC-1 | Access control policy documented, approved, and reviewed annually |
| SG.AC-2 | User accounts managed with formal provisioning/de-provisioning processes |
| SG.AC-3 | Default-deny access enforcement on all AMI systems |
| SG.AC-6 | Least privilege — users and processes have minimum required access |
| SG.AC-11 | Session management with secure tokens and inactivity timeout |
| SG.AC-17 | Remote access controls enforced |

### SG.AU — Audit and Accountability

| Control | Description |
|---------|-------------|
| SG.AU-2 | All required event types captured (login, logout, data access, commands, config changes, privilege escalation) |
| SG.AU-4 | Audit log storage capacity monitored with alerting before saturation |
| SG.AU-5 | Automated alerting on audit subsystem failures; minimum 365-day retention |
| SG.AU-9 | Log encryption and HMAC integrity protection (write-once storage) |
| SG.AU-11 | SIEM integration with real-time alerting on critical events |

### SG.IA — Identification and Authentication

| Control | Description |
|---------|-------------|
| SG.IA-3 | Every AMI device authenticates with a unique credential (no shared device accounts) |
| SG.IA-5 (Certs) | Device PKI certificates use strong algorithms; none expired; none expiring within 30 days |
| SG.IA-5 (Keys) | Device credentials rotated at least every 90 days |
| SG.IA-7 | Head-end uses FIPS 140-2/3 validated cryptographic modules |
| SG.IA-8 | MFA enforced for all privileged user access to head-end systems |

### SG.SC — System and Communications Protection

| Control | Description |
|---------|-------------|
| SG.SC-1 | Communications security policy documented |
| SG.SC-4 | AMI network segmented from corporate IT and public internet |
| SG.SC-8 | TLS 1.2 minimum on all AMI data-in-transit links; no prohibited cipher suites |
| SG.SC-8 (RF) | RF mesh network encrypted end-to-end |
| SG.SC-12 | Cryptographic keys managed via HSM or equivalent key management system |

### SG.CM — Configuration Management

| Control | Description |
|---------|-------------|
| SG.CM-2 | Documented baseline configuration for all AMI components, reviewed annually |
| SG.CM-3 | Formal change control process for all AMI system modifications |
| SG.CM-6 | Device hardening applied — unnecessary services, ports, and protocols disabled |
| SG.CM-7 | Least functionality — AMI devices run minimum required software |
| SG.CM-8 | Current inventory of all AMI devices and components maintained |

### SG.IR — Incident Response

| Control | Description |
|---------|-------------|
| SG.IR-1 | AMI-specific incident response plan documented and approved |
| SG.IR-2 | Staff trained on IR procedures including AMI/smart grid scenarios |
| SG.IR-3 | IR procedures tested at least annually (tabletop or simulation) |
| SG.IR-4 | Automated detection capability for AMI security events |
| SG.IR-6 | Incidents reported within defined timeframes; escalation to E-ISAC/ICS-CERT configured |

---

## Framework 2 — AMI Device Compliance

**OPA Endpoint:** `POST http://AAP_HOST:8183/v1/data/ami/device/compliance`
**AAP Job Template:** AMI - Device Compliance Check (ID 42)
**Data Source:** Smart Meter Simulator API (`http://AAP_HOST:8085/api/meters`)

Each physical meter is assessed individually. Results are aggregated per utility with critical violations flagged for immediate action.

### Firmware

| Check | Violation Raised When |
|-------|-----------------------|
| Version currency | Firmware version below minimum required version |
| Signature validity | Firmware signature invalid or uses weak algorithm |
| OTA update signing | OTA updates not enforced to require a valid signature |
| Rollback protection | Firmware rollback protection not enabled |
| Secure boot | Secure boot not enabled on device |

### Certificate Management

| Check | Severity | Violation Raised When |
|-------|----------|-----------------------|
| Certificate expiry | **CRITICAL** | Device certificate has expired |
| Expiry warning | WARNING | Certificate expires within 30 days |
| Algorithm strength | HIGH | Certificate uses weak/deprecated algorithm |

### Key Management

| Check | Violation Raised When |
|-------|-----------------------|
| Rotation cadence | Key rotation overdue — last rotation >90 days ago |
| Secure storage | Keys not stored in hardware (TPM / secure element / HSM) |

### Communications Security

| Check | Violation Raised When |
|-------|-----------------------|
| Encryption algorithm | Prohibited encryption algorithms in use (DES, RC4, etc.) |
| Communications encryption | Communications not encrypted with approved AES mode |
| Mutual authentication | Mutual authentication with head-end not enabled |

### Physical Security

| Check | Severity | Violation Raised When |
|-------|----------|-----------------------|
| Tamper detection hardware | HIGH | Tamper detection hardware not enabled or not operational |
| Tamper event | **CRITICAL** | Physical tamper detected — immediate investigation required |

---

## Framework 3 — AMI Head-End Security

**OPA Endpoint:** `POST http://AAP_HOST:8183/v1/data/ami/headend/security`
**AAP Job Template:** AMI - Head-End Security Assessment (ID 43)
**Standards:** NIST IR 7628, NIST SP 800-82, IEC 62443

The head-end assessment evaluates the MDMS server hardening posture across 19 controls in 5 categories.

### API Gateway Security (5 controls)

| Code | Control |
|------|---------|
| HEADEND-API-1 | MFA enabled and required for all admin API access |
| HEADEND-API-2 | OAuth2/JWT session management with JWT expiry ≤60 minutes and token rotation |
| HEADEND-API-3 | RBAC with default-deny enforced on API gateway |
| HEADEND-API-4 | TLS 1.2 minimum — SSLv3, TLS 1.0, TLS 1.1 disabled |
| HEADEND-API-5 | Input validation and rate limiting enabled |

### Database Security (6 controls)

| Code | Control |
|------|---------|
| HEADEND-DB-1 | Database encrypted at rest with AES-256 |
| HEADEND-DB-2 | Transparent Data Encryption (TDE) enabled |
| HEADEND-DB-3 | Encryption keys managed by HSM, AWS KMS, Azure Key Vault, or HashiCorp Vault |
| HEADEND-DB-4 | Database not reachable from public network; default port changed |
| HEADEND-DB-5 | Per-application service accounts — no shared admin/root accounts |
| HEADEND-DB-6 | All database connections require SSL/TLS 1.2+ |

### Audit Logging (4 controls)

| Code | Control |
|------|---------|
| HEADEND-AUD-1 | All required event types logged: user login/logout, failed auth, data access, data modification, config change, privilege escalation, API calls, meter commands, firmware updates |
| HEADEND-AUD-2 | Log retention minimum 365 days |
| HEADEND-AUD-3 | Logs encrypted, HMAC-integrity protected, stored on write-once media |
| HEADEND-AUD-4 | SIEM integration with real-time alerting on critical events |

### Network Segmentation (3 controls)

| Code | Control |
|------|---------|
| HEADEND-NET-1 | OT and IT networks physically or logically separated with firewall between zones |
| HEADEND-NET-2 | AMI head-end not internet-facing; DMZ required |
| HEADEND-NET-3 | Direct SSH blocked — all admin access via bastion host |

### Patch Management (1 control)

| Code | Control |
|------|---------|
| HEADEND-PATCH-1 | Critical patches applied within 30 days; high-severity patches within 60 days; vulnerability scanning enabled |

---

## Current Assessment Results (March 2026)

| Utility | NIST IR 7628 | Device Compliance | Head-End Security |
|---------|-------------|-------------------|-------------------|
| Electric | ~83% (Mostly Compliant) | 40% (4/10 meters) | 90% |
| Gas | ~83% (Mostly Compliant) | 40% (4/10 meters) | 90% |
| Water | ~83% (Mostly Compliant) | 40% (4/10 meters) | 90% |

**Active critical violation:** Physical tamper detected on 1 meter per utility — immediate investigation required.

---

## Assessment Architecture

```
Smart Meter Simulator ──► AAP (fact collection) ──► OPA opa-ot :8183 ──► PostgreSQL
(port 8085)                                          (policy evaluation)    (compliance DB)
                                                           │
                                                     Grafana :3000
                                               (AMI Compliance Dashboard)
```

**Grafana Dashboard:** `http://AAP_HOST:3000/d/ami-compliance-001`
**Run Full Audit:** AAP Job Template ID 29 — *AMI - Full Compliance Audit and Store*

---

*Generated by Ansible Automated Compliance (AAC) — Policy-as-Code Compliance at Enterprise Scale*
