> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x4.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# NIST Standards Integration with OPA and Ansible

This document explains how NIST cybersecurity frameworks integrate with our OPA Rego policies and Ansible automation for comprehensive compliance validation.

## Overview

The NIST (National Institute of Standards and Technology) integration provides automated compliance validation for:

- **NIST Cybersecurity Framework 2.0** (6 functions, 100+ subcategories)
- **NIST SP 800-53 Rev 5** (18 control families, 300+ controls)
- **NIST SP 800-171 Rev 3** (14 families, 110 requirements)
- **NIST Risk Management Framework** (7-step process)
- **NIST Privacy Framework** (5 functions)

## NIST Framework Structure and OPA Integration

### 1. NIST Cybersecurity Framework 2.0

**Structure**: 6 Functions → Categories → Subcategories

```yaml
# Ansible Facts for CSF Assessment
csf_assessment:
  governance:
    cybersecurity_strategy:
      documented: true
      approved_by_leadership: true
      regularly_reviewed: true
    oversight_structure:
      exists: true
      defined_roles: true
      clear_accountability: true
    policies:
      cybersecurity_policy:
        exists: true
        current: true
        communicated: true
```

**Maps to Rego Policies:**
```rego
# policies/nist/cybersecurity_framework_2.0/govern/governance.rego
organizational_strategy_established {
    input.governance.cybersecurity_strategy.documented == true
    input.governance.cybersecurity_strategy.approved_by_leadership == true
    input.governance.cybersecurity_strategy.regularly_reviewed == true
}
```

### 2. NIST SP 800-53 Security Controls

**Structure**: 18 Control Families → Individual Controls → Control Enhancements

```yaml
# Ansible Facts for SP 800-53 Assessment
sp800_53_assessment:
  ac_controls:
    policy:
      documented: true
      disseminated: true
      reviewed_updated: true
    account_management:
      automated_tools: true
      approval_process: true
      regular_reviews: true
    session_lock:
      inactivity_timeout: 900  # 15 minutes
      pattern_hiding: true
      authentication_required: true
```

**Maps to Rego Policies:**
```rego
# policies/nist/sp_800_53/access_control/ac_controls.rego
session_lock {
    input.ac_controls.session_lock.inactivity_timeout <= 900
    input.ac_controls.session_lock.pattern_hiding == true
    input.ac_controls.session_lock.authentication_required == true
}
```

### 3. NIST SP 800-171 CUI Requirements

**Structure**: 14 Requirement Families → Specific Requirements

```yaml
# Ansible Facts for SP 800-171 Assessment
sp800_171_assessment:
  cui_access:
    user_authorization:
      all_users_authorized: true
      process_authorization: true
      device_authorization: true
    session_lock:
      inactivity_timeout: 900
      pattern_hiding: true
      authentication_required: true
    logon_limits:
      maximum_attempts: 3
      lockout_implemented: true
      lockout_duration: 15
```

**Maps to Rego Policies:**
```rego
# policies/nist/sp_800_171/access_control/cui_access_control.rego
session_lock_implementation {
    input.cui_access.session_lock.inactivity_timeout <= 900
    input.cui_access.session_lock.pattern_hiding == true
    input.cui_access.session_lock.authentication_required == true
}
```

### 4. NIST Risk Management Framework

**Structure**: 7 RMF Steps → Activities → Tasks

```yaml
# Ansible Facts for RMF Assessment
rmf_assessment:
  system_categorization:
    confidentiality:
      impact_level: "moderate"
      rationale: "PII data processing"
      loss_scenario_documented: true
    integrity:
      impact_level: "high"
      rationale: "Financial transactions"
      loss_scenario_documented: true
    availability:
      impact_level: "moderate"
      rationale: "Business operations"
      loss_scenario_documented: true
    overall_impact_level: "high"
    high_water_mark_applied: true
```

**Maps to Rego Policies:**
```rego
# policies/nist/risk_management_framework/categorize/system_categorization.rego
high_water_mark_properly_applied {
    input.system_categorization.integrity.impact_level == "high"
    input.system_categorization.overall_impact_level == "high"
}
```

## Comprehensive Ansible Integration

### Multi-Framework Assessment Playbook

```yaml
---
- name: Comprehensive NIST Compliance Assessment
  hosts: all
  gather_facts: yes
  vars:
    opa_endpoint: "http://localhost:8181/v1/data"
    
  tasks:
    # =============================================================================
    # NIST CSF 2.0 Assessment
    # =============================================================================
    - name: Gather CSF governance information
      set_fact:
        csf_governance_data:
          governance:
            cybersecurity_strategy:
              documented: "{{ governance_strategy_documented | default(false) }}"
              approved_by_leadership: "{{ strategy_leadership_approved | default(false) }}"
              regularly_reviewed: "{{ strategy_regularly_reviewed | default(false) }}"
            oversight_structure:
              exists: "{{ oversight_structure_exists | default(false) }}"
              defined_roles: "{{ oversight_roles_defined | default(false) }}"
              clear_accountability: "{{ oversight_accountability_clear | default(false) }}"

    - name: Assess NIST CSF Govern function compliance
      uri:
        url: "{{ opa_endpoint }}/nist/csf/govern/nist_csf_govern_compliant"
        method: POST
        body_format: json
        body:
          input: "{{ csf_governance_data }}"
      register: csf_govern_result
      failed_when: false

    # =============================================================================
    # NIST SP 800-53 Assessment  
    # =============================================================================
    - name: Gather SP 800-53 access control information
      set_fact:
        sp800_53_ac_data:
          ac_controls:
            policy:
              documented: "{{ ac_policy_documented | default(false) }}"
              disseminated: "{{ ac_policy_disseminated | default(false) }}"
              reviewed_updated: "{{ ac_policy_reviewed | default(false) }}"
            session_lock:
              inactivity_timeout: "{{ session_timeout | default(1800) }}"
              pattern_hiding: "{{ session_pattern_hiding | default(false) }}"
              authentication_required: "{{ session_auth_required | default(false) }}"
            unsuccessful_logon_attempts:
              lockout_configured: "{{ logon_lockout_configured | default(false) }}"
              maximum_attempts: "{{ max_logon_attempts | default(10) }}"
              lockout_duration: "{{ logon_lockout_duration | default(0) }}"

    - name: Assess NIST SP 800-53 Access Control compliance
      uri:
        url: "{{ opa_endpoint }}/nist/sp800_53/access_control/nist_sp800_53_ac_compliant"
        method: POST
        body_format: json
        body:
          input: "{{ sp800_53_ac_data }}"
      register: sp800_53_ac_result
      failed_when: false

    # =============================================================================
    # NIST SP 800-171 Assessment
    # =============================================================================
    - name: Gather SP 800-171 CUI access control information
      set_fact:
        sp800_171_cui_data:
          cui_access:
            user_authorization:
              all_users_authorized: "{{ cui_users_authorized | default(false) }}"
              process_authorization: "{{ cui_processes_authorized | default(false) }}"
              device_authorization: "{{ cui_devices_authorized | default(false) }}"
            session_lock:
              inactivity_timeout: "{{ cui_session_timeout | default(1800) }}"
              pattern_hiding: "{{ cui_pattern_hiding | default(false) }}"
              authentication_required: "{{ cui_auth_required | default(false) }}"
            logon_limits:
              maximum_attempts: "{{ cui_max_attempts | default(10) }}"
              lockout_implemented: "{{ cui_lockout_enabled | default(false) }}"
              lockout_duration: "{{ cui_lockout_duration | default(0) }}"

    - name: Assess NIST SP 800-171 Access Control compliance
      uri:
        url: "{{ opa_endpoint }}/nist/sp800_171/access_control/nist_sp800_171_ac_compliant"
        method: POST
        body_format: json
        body:
          input: "{{ sp800_171_cui_data }}"
      register: sp800_171_ac_result
      failed_when: false

    # =============================================================================
    # NIST RMF Assessment
    # =============================================================================
    - name: Gather RMF system categorization information
      set_fact:
        rmf_categorization_data:
          system_categorization:
            confidentiality:
              impact_level: "{{ confidentiality_impact | default('low') }}"
              rationale: "{{ confidentiality_rationale | default('') }}"
              loss_scenario_documented: "{{ confidentiality_scenario_documented | default(false) }}"
            integrity:
              impact_level: "{{ integrity_impact | default('low') }}"
              rationale: "{{ integrity_rationale | default('') }}"
              loss_scenario_documented: "{{ integrity_scenario_documented | default(false) }}"
            availability:
              impact_level: "{{ availability_impact | default('low') }}"
              rationale: "{{ availability_rationale | default('') }}"
              loss_scenario_documented: "{{ availability_scenario_documented | default(false) }}"
            overall_impact_level: "{{ overall_system_impact | default('low') }}"
            high_water_mark_applied: "{{ high_water_mark_applied | default(false) }}"

    - name: Assess NIST RMF Categorization compliance
      uri:
        url: "{{ opa_endpoint }}/nist/rmf/categorize/rmf_categorization_compliant"
        method: POST
        body_format: json
        body:
          input: "{{ rmf_categorization_data }}"
      register: rmf_categorization_result
      failed_when: false

    # =============================================================================
    # Compliance Reporting
    # =============================================================================
    - name: Generate comprehensive NIST compliance report
      template:
        src: nist_compliance_report.j2
        dest: "/tmp/nist_compliance_{{ inventory_hostname }}.html"
      vars:
        nist_compliance_results:
          csf_govern: "{{ csf_govern_result.json.result | default('N/A') }}"
          sp800_53_ac: "{{ sp800_53_ac_result.json.result | default('N/A') }}"
          sp800_171_ac: "{{ sp800_171_ac_result.json.result | default('N/A') }}"
          rmf_categorization: "{{ rmf_categorization_result.json.result | default('N/A') }}"
        assessment_data:
          csf: "{{ csf_governance_data }}"
          sp800_53: "{{ sp800_53_ac_data }}"
          sp800_171: "{{ sp800_171_cui_data }}"
          rmf: "{{ rmf_categorization_data }}"

    - name: Display NIST compliance summary
      debug:
        msg: |
          ===============================================
          NIST COMPLIANCE SUMMARY FOR {{ inventory_hostname }}
          ===============================================
          
          FRAMEWORK COMPLIANCE RESULTS:
          - NIST CSF 2.0 Govern: {{ csf_govern_result.json.result | default('UNKNOWN') }}
          - NIST SP 800-53 Access Control: {{ sp800_53_ac_result.json.result | default('UNKNOWN') }}
          - NIST SP 800-171 Access Control: {{ sp800_171_ac_result.json.result | default('UNKNOWN') }}
          - NIST RMF Categorization: {{ rmf_categorization_result.json.result | default('UNKNOWN') }}
          
          Report generated: /tmp/nist_compliance_{{ inventory_hostname }}.html
          ===============================================
```

## Framework-Specific Data Collection

### CSF 2.0 Data Collection

```yaml
- name: Collect CSF governance data
  block:
    - name: Check for documented cybersecurity strategy
      stat:
        path: "{{ cybersecurity_strategy_path | default('/etc/security/strategy.doc') }}"
      register: strategy_doc
      
    - name: Verify strategy approval
      shell: grep -i "approved.*leadership" "{{ cybersecurity_strategy_path }}" || echo "not_found"
      register: strategy_approval
      when: strategy_doc.stat.exists
      
    - name: Set CSF governance facts
      set_fact:
        governance_strategy_documented: "{{ strategy_doc.stat.exists }}"
        strategy_leadership_approved: "{{ 'not_found' not in strategy_approval.stdout }}"
```

### SP 800-53 Data Collection

```yaml
- name: Collect SP 800-53 control implementation data
  block:
    - name: Check session timeout configuration
      shell: |
        if command -v gsettings >/dev/null 2>&1; then
          gsettings get org.gnome.desktop.session idle-delay 2>/dev/null || echo "1800"
        else
          echo "1800"  # Default if not GNOME
        fi
      register: session_timeout_check
      
    - name: Check account lockout policy
      shell: |
        if [[ -f /etc/pam.d/common-auth ]]; then
          grep -E "pam_faillock|pam_tally" /etc/pam.d/common-auth | wc -l
        else
          echo "0"
        fi
      register: lockout_policy_check
      
    - name: Set SP 800-53 facts
      set_fact:
        session_timeout: "{{ session_timeout_check.stdout | int }}"
        logon_lockout_configured: "{{ lockout_policy_check.stdout | int > 0 }}"
```

### SP 800-171 Data Collection

```yaml
- name: Collect SP 800-171 CUI protection data
  block:
    - name: Check user authorization documentation
      find:
        paths: 
          - "/etc/security"
          - "/usr/share/doc"
        patterns: "*authorization*,*user*access*"
        file_type: file
      register: user_auth_docs
      
    - name: Check device authorization controls
      shell: |
        if [[ -f /etc/udev/rules.d/99-device-authorization.rules ]]; then
          echo "true"
        else
          echo "false"
        fi
      register: device_auth_check
      
    - name: Set SP 800-171 facts
      set_fact:
        cui_users_authorized: "{{ user_auth_docs.matched > 0 }}"
        cui_devices_authorized: "{{ device_auth_check.stdout == 'true' }}"
```

### RMF Data Collection

```yaml
- name: Collect RMF system categorization data
  block:
    - name: Check for system categorization documentation
      find:
        paths: "/etc/security"
        patterns: "*categorization*,*impact*assessment*"
        file_type: file
      register: categorization_docs
      
    - name: Read impact levels from configuration
      ini_file:
        path: "{{ system_categorization_file | default('/etc/security/system-categorization.conf') }}"
        section: "impact_levels"
        option: "{{ item }}"
        mode: '0600'
      register: impact_levels
      loop:
        - confidentiality
        - integrity
        - availability
      failed_when: false
      
    - name: Set RMF categorization facts
      set_fact:
        confidentiality_impact: "{{ impact_levels.results[0].value | default('low') }}"
        integrity_impact: "{{ impact_levels.results[1].value | default('low') }}"
        availability_impact: "{{ impact_levels.results[2].value | default('low') }}"
```

## Cross-Framework Analysis

### Combined CIS and NIST Assessment

```yaml
- name: Comprehensive CIS and NIST assessment
  block:
    # Run CIS assessment
    - include_tasks: cis_assessment.yml
    
    # Run NIST assessment  
    - include_tasks: nist_assessment.yml
    
    # Analyze coverage gaps
    - name: Identify coverage gaps
      set_fact:
        coverage_analysis:
          cis_covered: "{{ cis_compliance_results }}"
          nist_covered: "{{ nist_compliance_results }}"
          gaps_identified: "{{ coverage_gaps | default([]) }}"
          recommendations: "{{ compliance_recommendations | default([]) }}"
```

## Integration Benefits

### 1. **Comprehensive Coverage**
- **CIS**: Technology-specific hardening (what to configure)
- **NIST**: Process frameworks and controls (how to manage)
- **Combined**: Complete cybersecurity program

### 2. **Risk-Based Approach**
- **RMF**: Systematic risk management process
- **CSF**: Strategic cybersecurity framework
- **SP 800-53**: Detailed control implementation
- **SP 800-171**: CUI-specific requirements

### 3. **Automated Compliance**
- **Real-time assessment**: Continuous compliance monitoring
- **Standardized reporting**: Consistent compliance documentation
- **Gap analysis**: Automated identification of deficiencies
- **Remediation guidance**: Specific improvement recommendations

### 4. **Scalable Implementation**
- **Multi-framework support**: Single platform for multiple standards
- **Flexible assessment**: Framework-specific or comprehensive evaluation
- **Enterprise deployment**: Hundreds of systems assessed simultaneously

## Usage Examples

### Quick NIST Assessment
```bash
# Assess NIST CSF compliance
ansible-playbook nist-csf-assessment.yml -i inventory

# Assess SP 800-53 controls
ansible-playbook nist-sp800-53-assessment.yml -i inventory

# Comprehensive NIST assessment
ansible-playbook nist-comprehensive-assessment.yml -i inventory
```

### Framework-Specific Queries
```bash
# CSF Govern function
curl -X POST http://localhost:8181/v1/data/nist/csf/govern/nist_csf_govern_compliant \
  -d @csf-governance-input.json

# SP 800-53 Access Control
curl -X POST http://localhost:8181/v1/data/nist/sp800_53/access_control/nist_sp800_53_ac_compliant \
  -d @sp800-53-ac-input.json

# SP 800-171 CUI Requirements
curl -X POST http://localhost:8181/v1/data/nist/sp800_171/access_control/nist_sp800_171_ac_compliant \
  -d @sp800-171-cui-input.json
```

This integration provides a comprehensive, automated approach to NIST framework compliance validation, complementing the existing CIS benchmark capabilities for complete cybersecurity compliance coverage.