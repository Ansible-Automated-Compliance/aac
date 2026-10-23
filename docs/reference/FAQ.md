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

# Frequently Asked Questions - CIS Compliance Validation System

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025

## Storage and Retention

### Q: Do we have the ability to store the results from gather_facts for up to 1 month?

**A: Yes, and much more!**

The enterprise architecture uses **PostgreSQL with TimescaleDB** (time-series database extension) to store all collected facts with the following capabilities:

#### Storage Features:
- **Default Retention:** 13 months (configurable)
- **Compression:** Automatic compression for data older than 7 days
- **Partitioning:** Monthly partitions for performance
- **Indexing:** Fast queries by node_id, timestamp, or framework

#### What You Can Do:

1. **Query Historical Facts:**
   ```sql
   -- Get all facts for a node from last 30 days
   SELECT *
   FROM compliance_facts
   WHERE node_id = 'server-123'
     AND collection_timestamp > NOW() - INTERVAL '30 days'
   ORDER BY collection_timestamp DESC;
   ```

2. **Compare Over Time:**
   ```sql
   -- See how compliance changed for a node
   SELECT
       DATE(collection_timestamp) as date,
       (facts->'compliance_checks'->>'bootloader_password_set')::boolean as had_grub_password
   FROM compliance_facts
   WHERE node_id = 'server-123'
     AND framework = 'CIS_RHEL9'
     AND collection_timestamp > NOW() - INTERVAL '30 days'
   ORDER BY date;
   ```

3. **Detect Drift:**
   ```python
   # Identify when configuration changed
   async def detect_config_drift(node_id):
       baseline = await get_facts(node_id, days_ago=30)
       current = await get_facts(node_id, days_ago=0)

       if baseline['host_grub_facts'] != current['host_grub_facts']:
           print(f"GRUB configuration changed on {node_id}")
           print(f"Changed fields: {find_differences(baseline, current)}")
   ```

4. **Trend Analysis:**
   ```sql
   -- Show compliance trend for last month
   SELECT
       DATE(timestamp) as date,
       AVG(passing_controls * 100.0 / total_controls) as compliance_pct
   FROM compliance_results
   WHERE node_id = 'server-123'
     AND timestamp > NOW() - INTERVAL '30 days'
   GROUP BY DATE(timestamp)
   ORDER BY date;
   ```

#### Storage Capacity:

| Duration | Storage Size (100K nodes) | Compressed |
|----------|---------------------------|------------|
| 1 day | 5-50 GB | 1-10 GB |
| 1 week | 35-350 GB | 9-88 GB |
| 1 month | 150-1500 GB | 38-375 GB |
| 13 months | 2-20 TB | 0.5-5 TB |

#### Retention Policy Configuration:

```sql
-- Default: 13 months
SELECT add_retention_policy('compliance_facts', INTERVAL '13 months');

-- Can be adjusted:
SELECT add_retention_policy('compliance_facts', INTERVAL '6 months');  -- Less storage
SELECT add_retention_policy('compliance_facts', INTERVAL '24 months'); -- More history
```

## Scale and Performance

### Q: Can this really handle 100,000 nodes?

**A: Yes**, with the distributed architecture:

| Component | Scale | Performance |
|-----------|-------|-------------|
| AAP Towers | 10-20 instances | 5K-10K nodes each |
| Fact Collection | Parallel execution | 30-60 minutes total |
| Database | TimescaleDB cluster | Handles 100K+ writes/sec |
| OPA Validation | 5-10 instance cluster | 500-2000 validations/sec |
| Report Generation | Async workers | Scales horizontally |

**Total Time for Complete Cycle:**
- Fact Collection: 30-60 minutes (parallel)
- Storage: <5 minutes (high-speed writes)
- Validation: 1-3 minutes (distributed OPA)
- Report Generation: 2-5 minutes
- **Total: ~40-70 minutes for 100,000 nodes**

### Q: How do we collect facts from 100,000 nodes efficiently?

**A:** Using distributed collection:

1. **Multiple AAP Instances:**
   - 10-20 Ansible Automation Platform instances
   - Each handles 5,000-10,000 nodes
   - Parallel execution across all towers

2. **Batch Processing:**
   ```yaml
   serial: 100  # Process 100 nodes at a time per tower
   strategy: free  # Don't wait for slow nodes
   ```

3. **Asynchronous Upload:**
   - Facts streamed to central API as collected
   - Non-blocking HTTP calls
   - Fallback to local files if API unavailable

4. **Rate Limiting:**
   - Prevent overwhelming target nodes
   - Spread collection over time window if needed

## Coverage and Features

### Q: What's our current CIS coverage?

**A:** 90/338 controls (26.6%)

| Section | Controls | Role | Status |
|---------|----------|------|--------|
| 1.4.x | 3 | gather_grub_security | ✓ |
| 3.5.1.x | 7 | gather_firewalld_detailed | ✓ |
| 4.1.x | 25 | gather_auditd_facts | ✓ |
| 5.2.x | 21 | gather_ssh_config | ✓ |
| 5.3.x/5.4.x | 8 | gather_pam_config | ✓ |
| 5.5.x/6.2.x | 26 | gather_user_security | ✓ |

**Roadmap:**
- Phase 2: +126 controls → 216/338 (63.9%) - 2-3 weeks
- Phase 3: +44 controls → 260/338 (76.9%) - 2-3 weeks
- Phase 4: +78 controls → 338/338 (100%) - 1-2 weeks
- **Total: 6-8 weeks to 100% validation coverage**

### Q: How does this compare to Ansible Lockdown?

**A:** We're complementary, not competitive:

| Feature | Our Implementation | Ansible Lockdown |
|---------|-------------------|------------------|
| **Purpose** | Validation + Assessment | Remediation + Hardening |
| **Coverage** | 90/338 (growing to 338) | 338/338 |
| **Approach** | Fact collection + OPA | Direct system modification |
| **Risk** | Read-only, safe | Modifies systems |
| **Multi-Framework** | Yes (CIS, NIST, PCI, SOC2) | CIS only |
| **Historical Tracking** | Yes (13 months) | No |
| **Best For** | Assessment, verification, monitoring | Initial hardening |

**Recommended Workflow:**
1. Assess with our tool (baseline)
2. Remediate with Ansible Lockdown OR our remediation roles (Phase 2)
3. Verify with our tool (post-remediation check)
4. Monitor continuously with our tool (detect drift)

## Remediation

### Q: Can this fix issues automatically?

**A: Phase 2 (Future)** - Yes, with safety features:

**Current (Phase 1):** Validation only
- Collect facts
- Identify violations
- Generate reports with remediation guidance

**Future (Phase 2):** Targeted remediation
- Complementary roles: `gather_X` + `remediate_X`
- Safety features:
  - **Dry-run mode:** Show what would change
  - **Backup:** Automatic config backups
  - **Rollback:** Restore previous state
  - **Selective:** Fix only specific controls
  - **Verification:** Re-validate after fixes

**Example Workflow (Phase 2):**
```yaml
# Validate → Fix → Verify cycle
- import_role: gather_grub_security  # Assess
- uri: ...  # Validate with OPA
- import_role: remediate_grub_security  # Fix (if violations)
  vars:
    dry_run: false
    violations: "{{ opa_result.violations }}"
    backup_configs: true
- import_role: gather_grub_security  # Re-assess
```

### Q: Can I use Ansible Lockdown with this?

**A: Absolutely!** Recommended hybrid approach:

```yaml
# 1. Assess with our tool
- import_playbook: collect-cis-facts-with-roles.yml

# 2. Remediate with Ansible Lockdown
- import_playbook: ansible-lockdown/RHEL9-CIS/site.yml
  vars:
    rhel9cis_level: 1
    rhel9cis_apply_remediation: true

# 3. Verify with our tool
- import_playbook: collect-cis-facts-with-roles.yml

# 4. Compare results
- shell: python3 scripts/compliance_reporter.py --compare before.json after.json
```

## Reporting

### Q: What reports are generated?

**A:** Multiple report types for different audiences:

1. **Fleet Summary Report (`fleet_summary.html`)**
   - Executive overview of all 100,000 nodes
   - Average compliance percentage
   - Top 20 violations across fleet
   - Compliance by environment (prod, dev, test)
   - Prioritized remediation queue

2. **Node Detail Report (`node_<id>_detail.html`)**
   - Individual node compliance status
   - All violations with severity
   - Current vs expected values
   - Remediation guidance for each control
   - 30-day compliance trend graph

3. **Remediation Playbook (`remediation_queue.yml`)**
   - Auto-generated Ansible playbook
   - Groups nodes by violation for efficiency
   - Prioritized by severity and impact
   - Ready to execute (Phase 2)

4. **CSV Export (`violations_export.csv`)**
   - All violations in spreadsheet format
   - For analysis in Excel/BI tools
   - Includes node metadata (environment, datacenter, etc.)

5. **Trend Analysis**
   - Compliance over time (30 days, 90 days, etc.)
   - Drift detection
   - Configuration change history

### Q: Can I customize reports?

**A: Yes!** Reports use Jinja2 templates:

```python
# Custom report example
template = env.get_template('custom_report.html')
html = template.render(
    your_data=query_results,
    custom_filters=...,
    branding=company_logo
)
```

## Integration

### Q: Can this integrate with other tools?

**A: Yes**, multiple integration points:

1. **REST API for Fact Ingestion:**
   ```bash
   curl -X POST https://compliance-api.example.com/v1/facts \
        -H "Content-Type: application/json" \
        -d @node_facts.json
   ```

2. **OPA Policy API:**
   ```bash
   curl -X POST http://opa-lb:8181/v1/data/cis/rhel9/evaluate \
        -d '{"input": {...facts...}}'
   ```

3. **Database Queries:**
   ```sql
   -- Direct SQL access for custom analysis
   SELECT * FROM compliance_results WHERE ...
   ```

4. **Webhooks (Future):**
   - Trigger on new violations
   - Alert on compliance drops
   - Notify on drift detection

5. **SIEM Integration:**
   - Export violations to Splunk, ELK, etc.
   - Security incident correlation

6. **Ticketing Systems:**
   - Auto-create tickets for violations
   - Jira, ServiceNow integration

## Multi-Framework Support

### Q: Can I validate against multiple frameworks simultaneously?

**A: Yes!** That's a key advantage:

**Collect Facts Once:**
```bash
# Single fact collection run
ansible-playbook collect-cis-facts-with-roles.yml
```

**Validate Against Multiple Frameworks:**
```bash
# CIS RHEL 9
opa eval --data policies/cis_benchmarks/rhel_9/ --input facts.json

# NIST 800-53 Rev 5
opa eval --data policies/nist/sp_800_53/ --input facts.json

# PCI-DSS 4.0
opa eval --data policies/pci_dss/ --input facts.json

# SOC2 Type II
opa eval --data policies/soc2/ --input facts.json

# Custom policies
opa eval --data policies/corporate/ --input facts.json
```

**Storage:**
```sql
-- Facts stored once, validated against many frameworks
INSERT INTO compliance_facts (node_id, timestamp, framework, facts)
VALUES ('server-1', NOW(), 'CIS_RHEL9', {...}),
       ('server-1', NOW(), 'NIST_800_53', {...}),  -- Same facts, different validation
       ('server-1', NOW(), 'PCI_DSS', {...});
```

## Getting Started

### Q: How do I start using this for my environment?

**A:** Quick start guide:

1. **Clone Repository:**
   ```bash
   git clone https://github.com/ansible-automated-compliance/aac.git
   cd compliance
   ```

2. **Review Current Roles:**
   ```bash
   ls ansible/roles/
   # gather_grub_security/
   # gather_firewalld_detailed/
   # gather_auditd_facts/
   # gather_ssh_config/
   # gather_pam_config/
   # gather_user_security/
   ```

3. **Create Inventory:**
   ```ini
   # inventory/production
   [rhel9_servers]
   server-1.example.com
   server-2.example.com
   ...
   ```

4. **Run Fact Collection:**
   ```bash
   ansible-playbook -i inventory/production \
                    facts-repo/collect-cis-facts-with-roles.yml
   ```

5. **Review Output:**
   ```bash
   cat /root/facts-repo/collected/rhel9/server-1_cis_facts_2025-10-15.json
   cat /root/facts-repo/reports/server-1_report_2025-10-15.txt
   ```

6. **Validate with OPA (when policies ready):**
   ```bash
   opa eval --data policies/ --input facts.json 'data.cis.rhel9.violations'
   ```

### Q: What infrastructure do I need?

**A:** Depends on scale:

**Small (1-100 nodes):**
- 1 AAP instance (or standalone Ansible)
- PostgreSQL database (single instance)
- OPA standalone
- Total: ~3 servers

**Medium (100-10,000 nodes):**
- 2-5 AAP instances
- PostgreSQL cluster (primary + replica)
- OPA cluster (3 instances)
- API servers (2-3 load balanced)
- Total: ~10-15 servers

**Large (10,000-100,000 nodes):**
- 10-20 AAP instances
- PostgreSQL/TimescaleDB cluster (3-5 nodes)
- OPA cluster (5-10 instances)
- API servers (5-10 instances)
- Message queue (RabbitMQ/Kafka)
- Object storage (S3/MinIO)
- Total: ~30-50 servers

## Next Steps

### Q: What's the immediate priority?

**A:** Complete Phase 1 validation roles:

**Current Status:** 90/338 controls (26.6%)

**Next Priorities:**
1. **gather_filesystem_config** (50 controls) - Partitions, mount options
2. **gather_logging_config** (17 controls) - rsyslog, journald
3. **gather_file_permissions** (9 controls) - Critical file permissions
4. **gather_service_config** (30 controls) - Unnecessary services
5. **gather_network_config** (20 controls) - Network parameters

**Timeline:** 2-3 weeks to reach 216/338 (63.9%)

### Q: Where can I learn more?

**A:** Documentation:

- **README.md** - Project overview
- **CIS_TECHNICAL_COMPONENTS.md** - All 278 controls breakdown
- **COVERAGE_COMPARISON.md** - vs Ansible Lockdown analysis
- **VALIDATION_STRATEGY.md** - Our 3-phase approach
- **ENTERPRISE_ARCHITECTURE.md** - 100K node design
- **ansible/roles/README.md** - Role development guide
- **collections/ansible_collections/aac/cis_facts/roles/*/README.md** - Individual collector role docs

**Contact:**
- GitHub Issues: https://github.com/ansible-automated-compliance/aac/issues
- Project Repository: https://github.com/ansible-automated-compliance/aac

## Common Issues

### Q: What if fact collection fails on some nodes?

**A:** Built-in resilience:

1. **Non-blocking Execution:**
   ```yaml
   ignore_errors: yes  # Continue even if some nodes fail
   ```

2. **Retry Logic:**
   ```yaml
   retries: 3
   delay: 5
   ```

3. **Fallback Storage:**
   - If API unavailable, write to local files
   - Batch upload later

4. **Monitoring:**
   ```sql
   -- Track collection success rate
   SELECT
       collection_id,
       target_nodes,
       successful_nodes,
       failed_nodes,
       (successful_nodes * 100.0 / target_nodes) as success_rate
   FROM collection_jobs;
   ```

### Q: What about nodes behind firewalls?

**A:** AAP supports various connection methods:

- **SSH through jump hosts**
- **WinRM for Windows nodes** (future)
- **Agent-based collection** (future consideration)
- **Pull mode** (future consideration)

### Q: How do I secure the compliance database?

**A:** Security best practices:

1. **Network Security:**
   - VPN or private network
   - Firewall rules restricting access
   - TLS/SSL for all connections

2. **Database Security:**
   - Strong passwords
   - Role-based access control (RBAC)
   - Read-only access for reports
   - Audit logging enabled

3. **API Security:**
   - API keys or OAuth2
   - Rate limiting
   - IP whitelisting

4. **Data Protection:**
   - Encryption at rest
   - Encryption in transit
   - Regular backups

5. **Compliance:**
   - Facts may contain sensitive data
   - PII/PHI considerations
   - Data retention policies
   - GDPR compliance if applicable
