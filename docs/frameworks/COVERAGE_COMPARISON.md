> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: none specific — unreviewed for 320 days.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

> [!NOTE]
> **2026-10-17:** the legacy `ansible/roles/gather_*` roles this document describes were removed
> from the tree (no playbook called them). The same roles live in the `aac.cis_facts` collection
> at `collections/ansible_collections/aac/cis_facts/roles/`; the production CIS path uses
> `ansible/roles/aac_facts_collector` and `ansible/playbooks/cis_rhel9_assessment.yml`.

# CIS RHEL 9 Coverage Comparison: Our Implementation vs Ansible Lockdown

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025


## Executive Summary

**CIS RHEL 9 Benchmark v2.0.0 Total Controls:** 338

### Our Current Coverage
- **Controls Covered:** 90/338 (26.6%)
- **Approach:** Fact Collection + OPA Policy Validation
- **Focus:** Assessment and auditing
- **Maturity:** Early stage (6 roles built)

### Ansible Lockdown Coverage
- **Controls Covered:** 338/338 (100%)
- **Approach:** Direct Remediation with Ansible
- **Focus:** Automated hardening/remediation
- **Maturity:** Production-ready (v2.0.2, released July 2024)

## Key Differences

### 1. Fundamental Approach

**Our Implementation:**
- **Fact Collection First**: Ansible roles gather system configuration facts
- **OPA Policy Evaluation**: Facts fed to Open Policy Agent for compliance checking
- **Separation of Concerns**: Fact collection, policy evaluation, and reporting are separate
- **Non-Invasive**: Read-only operations, doesn't modify systems
- **Flexible Policy**: Easy to customize compliance logic in Rego

**Ansible Lockdown:**
- **Direct Remediation**: Ansible tasks directly modify system configurations
- **Built-in Assessment**: Uses Goss for lightweight pre/post-remediation auditing
- **Integrated Approach**: Remediation and verification in one playbook
- **System Modification**: Actively hardens systems to meet CIS requirements
- **Tag-Based Control**: Granular control via Ansible tags

### 2. Coverage Breakdown

#### Our Implementation (90/338 controls - 26.6%)

| Section | Controls | Role | Status |
|---------|----------|------|--------|
| 1.4.x | 3 | gather_grub_security | ✓ Complete |
| 3.5.1.x | 7 | gather_firewalld_detailed | ✓ Complete |
| 4.1.x | 25 | gather_auditd_facts | ✓ Complete |
| 5.2.x | 21 | gather_ssh_config | ✓ Complete |
| 5.3.x/5.4.x | 8 | gather_pam_config | ✓ Complete |
| 5.5.x/6.2.x | 26 | gather_user_security | ✓ Complete |
| **TOTAL** | **90** | **6 roles** | **26.6%** |

**Not Yet Covered (248/338 - 73.4%):**
- Section 1.1.x: Filesystem configuration (40+ controls)
- Section 1.2.x: Package management (8 controls)
- Section 1.3.x: SELinux configuration (8 controls)
- Section 1.5.x: Process hardening (4 controls)
- Section 1.6.x: Mandatory Access Control (7 controls)
- Section 1.7.x: Command line warnings (6 controls)
- Section 1.8.x: GNOME Display Manager (10 controls)
- Section 2.x: Services configuration (30+ controls)
- Section 3.1-3.4.x: Network configuration (20+ controls)
- Section 4.2.x: Logging configuration (17 controls)
- Section 6.1.x: File permissions (9 controls)
- Section 7.x: System Maintenance (remaining controls)

#### Ansible Lockdown (338/338 controls - 100%)

**Section Breakdown:**

| Section | Description | Est. Controls |
|---------|-------------|---------------|
| 1.1.x | Filesystem Configuration | ~50 |
| 1.2.x | Software Updates | ~8 |
| 1.3.x | Mandatory Access Control | ~8 |
| 1.4.x | Bootloader Security | 3 |
| 1.5.x | Process Hardening | ~4 |
| 1.6.x | Mandatory Access Control | ~7 |
| 1.7.x | Warning Banners | ~6 |
| 1.8.x | GNOME Display Manager | ~10 |
| 2.1.x | Server Services | ~22 |
| 2.2.x | Client Services | ~5 |
| 2.3.x | Time Synchronization | ~3 |
| 3.1.x | Disable Unused Network Protocols | ~3 |
| 3.2.x | Network Parameters (Host Only) | ~4 |
| 3.3.x | Network Parameters (Host and Router) | ~11 |
| 3.4.x | Uncommon Network Protocols | ~2 |
| 3.5.x | Firewall Configuration | ~7 |
| 4.1.x | Auditing | ~25 |
| 4.2.x | Logging | ~17 |
| 5.1.x | Cron and at | ~9 |
| 5.2.x | SSH Server | ~21 |
| 5.3.x | Privilege Escalation | ~8 |
| 5.4.x | PAM and Password Configuration | ~10 |
| 5.5.x | User Accounts and Environment | ~10 |
| 6.1.x | System File Permissions | ~15 |
| 6.2.x | User and Group Settings | ~16 |
| 7.x | System Maintenance | ~40+ |

**Total: 338 controls**

## Architectural Comparison

### Our Fact Collection + OPA Architecture

```
┌─────────────────────┐
│  Target RHEL 9 Host │
│                     │
│  Ansible Roles:     │
│  - gather_grub      │
│  - gather_firewalld │
│  - gather_auditd    │
│  - gather_ssh       │
│  - gather_pam       │
│  - gather_user      │
└──────────┬──────────┘
           │ Facts (JSON)
           ▼
┌─────────────────────┐
│   Facts Repository  │
│   /collected/rhel9/ │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  OPA Policy Engine  │
│  cis_rhel_9.rego    │
│  - Evaluates facts  │
│  - Returns results  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Compliance Reports  │
│ - Pass/Fail         │
│ - Recommendations   │
└─────────────────────┘
```

**Advantages:**
- ✓ Read-only, non-invasive assessment
- ✓ Flexible policy changes without re-running Ansible
- ✓ Easy to customize compliance rules
- ✓ Facts can be used for multiple frameworks (CIS, NIST, PCI-DSS)
- ✓ Historical compliance tracking via fact snapshots
- ✓ Separation of assessment from remediation

**Disadvantages:**
- ✗ Doesn't fix issues automatically
- ✗ Requires separate remediation step
- ✗ More complex architecture (Ansible + OPA)
- ✗ Limited coverage currently (26.6%)

### Ansible Lockdown Remediation Architecture

```
┌─────────────────────┐
│  Target RHEL 9 Host │
│                     │
│  Pre-Audit (Goss)   │◄─── Optional pre-check
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Ansible Lockdown    │
│ RHEL9-CIS Playbook  │
│                     │
│ Applies 338 tasks:  │
│ - Filesystem config │
│ - Package hardening │
│ - Network security  │
│ - Service disabling │
│ - File permissions  │
│ - User/group config │
│ - Audit config      │
│ - SSH hardening     │
│ - PAM configuration │
└──────────┬──────────┘
           │ Direct system modification
           ▼
┌─────────────────────┐
│  Hardened System    │
│                     │
│  Post-Audit (Goss)  │◄─── Verification
└─────────────────────┘
```

**Advantages:**
- ✓ Complete coverage (338/338 controls)
- ✓ Automated remediation
- ✓ Production-ready and battle-tested
- ✓ Simpler architecture (Ansible-only)
- ✓ Tag-based selective hardening
- ✓ Built-in pre/post audit with Goss
- ✓ Active community and commercial support

**Disadvantages:**
- ✗ Modifies systems directly (risk of breakage)
- ✗ Less flexible policy customization
- ✗ Harder to adapt for non-CIS frameworks
- ✗ Remediation and assessment tightly coupled

## Use Case Comparison

### When to Use Our Implementation

1. **Assessment-Only Environments**
   - You need to audit without making changes
   - Regulatory requirement for read-only scanning
   - Testing/development environments

2. **Multi-Framework Compliance**
   - Need to check CIS, NIST, PCI-DSS, SOC2, etc. from same facts
   - Want unified fact collection across frameworks
   - Complex policy requirements

3. **Policy Flexibility**
   - Frequent policy changes
   - Custom compliance requirements
   - Need to quickly test "what-if" scenarios

4. **Gradual Hardening**
   - Want to assess first, plan remediation later
   - Need executive buy-in before changes
   - Phased compliance approach

5. **Learning and Development**
   - Building custom compliance framework
   - Understanding system configurations
   - Research and analysis

### When to Use Ansible Lockdown

1. **Immediate Compliance Required**
   - Need to harden systems quickly
   - Regulatory audit deadline approaching
   - New system deployment requiring immediate hardening

2. **Production Hardening**
   - Enterprise-scale deployment
   - Need battle-tested, reliable remediation
   - Want commercial support option

3. **Complete CIS Coverage**
   - Must meet all 338 CIS v2.0.0 controls
   - CIS certification requirement
   - Comprehensive hardening needed

4. **DevOps/IaC Integration**
   - Automated hardening in CI/CD pipeline
   - Infrastructure as Code workflows
   - Immutable infrastructure patterns

5. **Limited Resources**
   - Don't want to build custom solution
   - Need immediate, comprehensive solution
   - Smaller team without OPA expertise

## Gap Analysis: What We're Missing

### Critical Gaps (High Security Impact)

1. **Filesystem Security (Section 1.1.x - ~50 controls)**
   - Separate partition requirements (/tmp, /var, /home, etc.)
   - Mount options (nodev, nosuid, noexec)
   - Sticky bit on world-writable directories
   - **Impact:** Prevents privilege escalation, limits attack surface

2. **Service Management (Section 2.x - ~30 controls)**
   - Disable unnecessary services (avahi, cups, dhcp, etc.)
   - Time synchronization configuration
   - Remove legacy services
   - **Impact:** Reduces attack surface significantly

3. **Network Configuration (Section 3.1-3.4 - ~20 controls)**
   - Kernel network parameters (IP forwarding, ICMP, etc.)
   - IPv6 configuration
   - TCP wrappers
   - **Impact:** Network-level security hardening

4. **Logging (Section 4.2.x - 17 controls)**
   - rsyslog/journald configuration
   - Remote log host configuration
   - Log file permissions
   - **Impact:** Critical for incident response and forensics

5. **File Permissions (Section 6.1.x - 9 controls)**
   - System file permissions (/etc/passwd, /etc/shadow, etc.)
   - SUID/SGID audit
   - Unowned files
   - **Impact:** Prevents unauthorized access to sensitive files

### Medium Priority Gaps

6. **SELinux (Section 1.3.x - 8 controls)**
   - SELinux state and policy
   - Confined services
   - MCS/MLS configuration

7. **Process Hardening (Section 1.5.x - 4 controls)**
   - Core dumps
   - Address space layout randomization (ASLR)
   - Prelink

8. **Cron Security (Section 5.1.x - 9 controls)**
   - Cron daemon configuration
   - crontab permissions
   - at daemon security

9. **GNOME Display Manager (Section 1.8.x - 10 controls)**
   - GDM login banner
   - Screen lock settings
   - Idle session timeout

### Already Covered (90 controls)

✓ **Bootloader (1.4.x)** - 3 controls
✓ **Firewall (3.5.x)** - 7 controls
✓ **Audit (4.1.x)** - 25 controls
✓ **SSH (5.2.x)** - 21 controls
✓ **PAM/Password (5.3/5.4.x)** - 8 controls
✓ **User Security (5.5.x, 6.2.x)** - 26 controls

## Roadmap to Close the Gap

### Phase 1: Critical Roles (Completed ✓)
- [x] gather_grub_security (3 controls) ✓
- [x] gather_firewalld_detailed (7 controls) ✓
- [x] gather_auditd_facts (25 controls) ✓
- [x] gather_ssh_config (21 controls) ✓
- [x] gather_pam_config (8 controls) ✓
- [x] gather_user_security (26 controls) ✓
**Total: 90/338 (26.6%)**

### Phase 2: High Priority (In Planning)
- [ ] gather_filesystem_config (~50 controls) - Section 1.1.x
- [ ] gather_service_config (~30 controls) - Section 2.x
- [ ] gather_network_config (~20 controls) - Section 3.1-3.4.x
- [ ] gather_logging_config (17 controls) - Section 4.2.x
- [ ] gather_file_permissions (9 controls) - Section 6.1.x
**Estimated: +126 controls → 216/338 (63.9%)**

### Phase 3: Medium Priority
- [ ] gather_selinux_advanced (8 controls) - Section 1.3.x
- [ ] gather_process_hardening (4 controls) - Section 1.5.x
- [ ] gather_mac_config (7 controls) - Section 1.6.x
- [ ] gather_warning_banners (6 controls) - Section 1.7.x
- [ ] gather_gdm_config (10 controls) - Section 1.8.x
- [ ] gather_cron_security (9 controls) - Section 5.1.x
**Estimated: +44 controls → 260/338 (76.9%)**

### Phase 4: Comprehensive Coverage
- [ ] gather_software_updates (8 controls) - Section 1.2.x
- [ ] gather_system_maintenance (remaining ~78 controls) - Section 7.x
**Estimated: +78 controls → 338/338 (100%)**

### Timeline Estimate
- **Phase 2:** 4-6 weeks (5 complex roles)
- **Phase 3:** 3-4 weeks (6 medium complexity roles)
- **Phase 4:** 2-3 weeks (remaining controls)
- **Total:** 9-13 weeks to 100% coverage

## Hybrid Approach Recommendation

Given the strengths of both approaches, consider a **hybrid strategy**:

### 1. Assessment Phase (Our Implementation)
```bash
# Use our fact collection roles
ansible-playbook collect-cis-facts-with-roles.yml

# Evaluate with OPA
opa eval --data policies/cis_benchmarks/rhel_9/cis_rhel_9.rego \
         --input facts-repo/collected/rhel9/server1_facts.json

# Generate compliance report
python3 scripts/compliance_reporter.py
```

**Benefits:**
- Non-invasive baseline assessment
- Understand current compliance posture
- Identify gaps without risk
- Get executive approval for changes

### 2. Remediation Phase (Ansible Lockdown)
```bash
# Use Ansible Lockdown for comprehensive remediation
ansible-playbook ansible-lockdown/RHEL9-CIS/site.yml \
  --tags="level1-server,cat1" \
  --extra-vars "rhel9cis_apply_remediation=true"
```

**Benefits:**
- Comprehensive coverage (338 controls)
- Battle-tested remediation
- Tag-based selective hardening
- Production-ready

### 3. Verification Phase (Our Implementation)
```bash
# Re-collect facts post-remediation
ansible-playbook collect-cis-facts-with-roles.yml

# Verify compliance with OPA
opa eval --data policies/cis_benchmarks/rhel_9/cis_rhel_9.rego \
         --input facts-repo/collected/rhel9/server1_facts_post.json

# Generate delta report
python3 scripts/compliance_reporter.py --compare before after
```

**Benefits:**
- Independent verification
- Historical compliance tracking
- Custom reporting for stakeholders
- Multi-framework validation

## Conclusion

### Summary Table

| Aspect | Our Implementation | Ansible Lockdown | Hybrid Approach |
|--------|-------------------|------------------|-----------------|
| **Coverage** | 90/338 (26.6%) | 338/338 (100%) | 338/338 (100%) |
| **Approach** | Fact Collection + OPA | Direct Remediation | Best of Both |
| **Risk** | Low (read-only) | Medium (system changes) | Managed |
| **Flexibility** | High | Medium | High |
| **Maturity** | Early (6 roles) | Production | Mixed |
| **Time to Deploy** | Immediate (limited) | Immediate (full) | Phased |
| **Best For** | Assessment, Analysis | Remediation, Hardening | Complete Lifecycle |

### Recommendations

1. **Short Term (Now):**
   - Use our implementation for initial assessment
   - Identify critical compliance gaps
   - Use Ansible Lockdown for immediate remediation needs

2. **Medium Term (3-6 months):**
   - Complete Phase 2 roles (filesystem, services, network, logging)
   - Reach 60%+ coverage for comprehensive assessments
   - Continue using Ansible Lockdown for production remediation

3. **Long Term (6-12 months):**
   - Achieve 100% fact collection coverage
   - Build comprehensive OPA policies
   - Maintain hybrid approach: assess → remediate → verify

4. **Strategic Value:**
   - Our implementation provides unique value for:
     - Multi-framework compliance (CIS + NIST + PCI-DSS + SOC2)
     - Custom policy requirements
     - Continuous compliance monitoring
     - Historical trend analysis
   - Ansible Lockdown provides:
     - Immediate, comprehensive remediation
     - Production-ready hardening
     - Community and commercial support

### Next Steps

1. **Complete Phase 2 roles** to reach 60%+ coverage
2. **Document integration** with Ansible Lockdown
3. **Build OPA policies** for collected facts
4. **Create comparison reports** showing pre/post remediation
5. **Develop remediation playbooks** for our assessed findings

**Bottom Line:** We don't need to replace Ansible Lockdown. We complement it by providing flexible, multi-framework assessment capabilities. Together, they form a complete compliance lifecycle solution.
