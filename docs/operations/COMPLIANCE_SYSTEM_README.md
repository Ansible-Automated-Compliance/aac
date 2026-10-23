> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx30, HOST:8181x8, AAP-2.5/2.6x1, STALE-COUNTx1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Compliance Automation System - Setup Documentation

**Last Updated**: April 2026
**Status**: ✅ Production Ready
**Version**: 1.1

---

## System Overview

This is a complete **OPA-based compliance automation system** for CIS benchmark assessment of RHEL systems, with PostgreSQL for centralized facts storage and Ansible Automation Platform (AAP) integration.

### Architecture

```
┌─────────────────────────────────────────┐
│  Ansible / AAP                          │
│  - Collects CIS facts                   │
│  - Stores in PostgreSQL                 │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│  PostgreSQL Database (Container)        │
│  Host: AAP_HOST                     │
│  - compliance_facts                     │
│  - compliance_results                   │
│  - policy_violations                    │
│  - compliance_audit_trail               │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│  OPA Server (Container)                 │
│  Host: AAP_HOST:8181                │
│  - CIS RHEL 9 policies loaded           │
│  - Evaluates facts → violations         │
└─────────────────────────────────────────┘
```

---

## Infrastructure Details

### 1. PostgreSQL Database (CONTAINERIZED)

**Container Runtime**: Podman (rootless)
**Container Name**: `postgresql`
**Running As**: `aapuser1` user
**Host**: AAP_HOST
**Port**: 5432 (localhost only)
**Database**: compliance

#### Access Container:
```bash
# On AAP_HOST
sudo -u aapuser1 podman ps | grep postgresql
sudo -u aapuser1 podman exec -it postgresql psql -U postgres -d compliance
```

#### Database Schema:
- `compliance_facts` - Stores Ansible facts (JSONB, 180KB+ per host)
- `compliance_results` - Policy evaluation results
- `policy_violations` - Individual control violations
- `compliance_audit_trail` - Activity logging
- `compliance_trends` - Materialized view for analytics

#### Database Users:
- **postgres** - Superuser
- **compliance_writer** - INSERT/UPDATE/SELECT (password: set via Ansible Vault)
- **compliance_reader** - SELECT only (password: set via Ansible Vault)

⚠️ **IMPORTANT**: Change default passwords in production!

#### Current Data:
```sql
SELECT id, hostname, collection_timestamp, checksum
FROM compliance_facts;
```
- ID 1: ocptesttc (collected Nov 4, 2025)

---

### 2. OPA Server (CONTAINERIZED)

**Container Runtime**: Podman (rootless)
**Container Name**: `opa`
**Running As**: `aapuser1` user
**Host**: AAP_HOST
**Port**: 8181
**Status**: Running

#### Check OPA Status:
```bash
curl http://AAP_HOST:8181/health
```

#### Policies Loaded:
- **Package**: cis_rhel9
- **Modules**:
  - filesystem_validation
  - logging_validation
  - file_permissions_validation
  - service_validation
  - network_validation
- **Main Policy**: cis_rhel9_complete

#### Policy Files Location:
- **On Server**: `/tmp/cis_rhel9/`
- **On Local**: `<aac-repo>/policies/cis_rhel9/`

---

### 3. Ansible Automation Platform (AAP)

**Version**: 2.6 (Containerized)
**Host**: AAP_HOST
**Web UI**: https://AAP_HOST
**Admin User**: admin
**Inventory File**: `/tmp/aap_inventory`

#### AAP Components (All Containerized under aapuser1):
- Controller
- Automation Hub
- PostgreSQL (separate from compliance DB)
- Redis
- Receptor

---

## Key Files and Locations

### On AAP_HOST (Remote Server)

#### Scripts:
- `/tmp/opa_eval_from_db.py` - OPA evaluation script
- `/tmp/setup_compliance_db.sh` - Database setup (used)
- `/tmp/collect_cis_facts_to_db.sh` - Facts collection bash script
- `/tmp/run_compliance_via_aap.sh` - AAP API workflow script

#### Data Files:
- `/tmp/ansible_facts_ocptesttc.json` - Latest collected facts (181KB)
- `/tmp/cis_rhel9/` - OPA policy files

#### Container Verification:
```bash
# As aapuser1
podman ps

# Should show:
# - postgresql (port 5432)
# - opa (port 8181)
# - AAP containers (controller, hub, etc.)
```

### On Local Machine

#### Playbooks:
- `<aac-repo>/playbooks/collect_and_store_cis_facts_rhel.yml` - **Primary facts collection playbook**
- `<aac-repo>/playbooks/inventory_AAP_HOST` - Ansible inventory

#### Policies:
- `<aac-repo>/policies/cis_rhel9/` - CIS RHEL 9 policies
  - `cis_rhel9_complete.rego`
  - `modules/*.rego`

#### Documentation:
- `<docs-dir>/OPA_SCALING_GUIDE.md` - Architecture guide (v2.0)
- `/tmp/aap_compliance_workflow.md` - AAP integration guide
- `/tmp/compliance_workflow_complete_summary.md` - Complete summary

---

## System Configuration

### Passwordless Sudo

**User**: tcoulter
**Configuration**: `/etc/sudoers.d/tcoulter`

```bash
# Test passwordless sudo
ssh AAP_HOST "sudo -n whoami"
# Should return: root
```

### Ansible Inventory

**File**: `<aac-repo>/playbooks/inventory_AAP_HOST`

```ini
[rhel_hosts]
AAP_HOST

[rhel_hosts:vars]
ansible_user=tcoulter
ansible_python_interpreter=/usr/bin/python3
platform_type=rhel
```

### Python Dependencies

**Installed on AAP_HOST**:
- `psycopg2-binary` - PostgreSQL Python driver
- `requests` - HTTP library for OPA calls

**Installed Locally**:
- `community.postgresql` - Ansible collection

---

## Usage

### 1. Collect CIS Facts

#### Method A: Ansible Playbook (Recommended)
```bash
cd <aac-repo>/playbooks
ansible-playbook -i inventory_AAP_HOST collect_and_store_cis_facts_rhel.yml
```

**What it does**:
- Collects comprehensive CIS benchmark facts
- Saves to `/tmp/ansible_facts_<hostname>.json`
- Stores in PostgreSQL database
- Logs to audit trail

#### Method B: Direct on Server
```bash
# On AAP_HOST
sudo /tmp/collect_cis_facts_to_db.sh
```

### 2. Verify Facts in Database

```bash
# On AAP_HOST
cd /tmp
sudo -u aapuser1 podman exec postgresql psql -U postgres -d compliance -c \
  "SELECT id, hostname, platform, collection_timestamp,
   pg_size_pretty(pg_column_size(facts_data)) as size
   FROM compliance_facts
   ORDER BY collection_timestamp DESC;"
```

### 3. Run OPA Evaluation

```bash
# On AAP_HOST
python3 /tmp/opa_eval_from_db.py ocptesttc cis_rhel9
```

**What it does**:
1. Loads facts from database
2. Evaluates against CIS RHEL 9 policies
3. Calculates compliance percentage
4. Stores results in compliance_results table
5. Stores violations in policy_violations table

### 4. Query Compliance Results

```bash
# On AAP_HOST
cd /tmp
sudo -u aapuser1 podman exec postgresql psql -U postgres -d compliance << 'EOF'
SELECT
  cf.hostname,
  cr.policy_name,
  cr.compliance_percentage,
  cr.passed_controls,
  cr.failed_controls,
  cr.evaluation_timestamp
FROM compliance_results cr
JOIN compliance_facts cf ON cr.facts_id = cf.id
ORDER BY cr.evaluation_timestamp DESC
LIMIT 10;
EOF
```

### 5. View Violations

```bash
sudo -u aapuser1 podman exec postgresql psql -U postgres -d compliance << 'EOF'
SELECT
  pv.control_id,
  pv.severity,
  pv.control_description,
  pv.finding,
  cf.hostname
FROM policy_violations pv
JOIN compliance_results cr ON pv.result_id = cr.id
JOIN compliance_facts cf ON cr.facts_id = cf.id
WHERE pv.severity = 'critical'
ORDER BY cf.hostname, pv.control_id;
EOF
```

---

## AAP Integration

### Run via AAP API

```bash
# Set password
export AAP_PASSWORD="{{ vault_aap_admin_password }}"

# Run workflow
/tmp/run_compliance_via_aap.sh ocptesttc
```

### Create AAP Job Template

1. Log into AAP: https://AAP_HOST
2. Navigate to: **Resources → Templates**
3. Click **Add → Add job template**
4. Configure:
   - **Name**: Collect CIS Facts
   - **Job Type**: Run
   - **Inventory**: Compliance Hosts
   - **Project**: (create project pointing to playbooks directory)
   - **Playbook**: collect_and_store_cis_facts_rhel.yml
   - **Credentials**: SSH (tcoulter) with sudo
   - **Variables**:
     ```yaml
     postgres_host: localhost
     postgres_db: compliance
     postgres_user: compliance_writer
     postgres_password: "{{ vault_pg_password }}"  # Required: set via Ansible Vault
     ```

---

## Troubleshooting

### PostgreSQL Container Issues

```bash
# Check container is running
sudo -u aapuser1 podman ps | grep postgresql

# View container logs
sudo -u aapuser1 podman logs postgresql

# Restart container
sudo -u aapuser1 podman restart postgresql

# Connect to database
sudo -u aapuser1 podman exec -it postgresql psql -U postgres -d compliance
```

### OPA Container Issues

```bash
# Check container is running
sudo -u aapuser1 podman ps | grep opa

# Test OPA health
curl http://AAP_HOST:8181/health

# View OPA policies
curl http://AAP_HOST:8181/v1/policies | jq 'keys'

# Reload policies
cd /tmp/cis_rhel9
for file in modules/*.rego cis_rhel9_complete.rego; do
  curl -X PUT http://AAP_HOST:8181/v1/policies/$(basename $file .rego) \
    --data-binary @$file
done
```

### Facts Collection Issues

```bash
# Check if facts file was created
ls -lh /tmp/ansible_facts_*.json

# Validate JSON
python3 -m json.tool /tmp/ansible_facts_ocptesttc.json > /dev/null
echo $?  # Should return 0

# Check facts in database
sudo -u aapuser1 podman exec postgresql psql -U postgres -d compliance \
  -c "SELECT COUNT(*) FROM compliance_facts;"
```

### Permission Issues

```bash
# Verify passwordless sudo
sudo -n whoami  # Should return: root

# Check aapuser1 can access containers
sudo -u aapuser1 podman ps

# Grant database permissions if needed
cd /tmp
sudo -u aapuser1 podman exec postgresql psql -U postgres -d compliance -c \
  "GRANT SELECT ON ALL TABLES IN SCHEMA public TO compliance_writer;"
```

---

## Important Notes

### Container Persistence

All services run in **rootless Podman containers** under `aapuser1`:
- Containers survive reboots (set as systemd services by AAP installer)
- Data is persistent in container volumes
- Container images stored in: `/home/aapuser1/.local/share/containers/storage/`

### Database Backups

```bash
# Backup database
sudo -u aapuser1 podman exec postgresql pg_dump -U postgres compliance \
  > /tmp/compliance_backup_$(date +%Y%m%d).sql

# Restore database
sudo -u aapuser1 podman exec -i postgresql psql -U postgres compliance \
  < /tmp/compliance_backup_20251103.sql
```

### Network Access

- **PostgreSQL**: Only listens on localhost (127.0.0.1:5432)
- **OPA**: Listens on all interfaces (0.0.0.0:8181)
- **AAP**: Accessible via HTTPS on port 443

To enable external PostgreSQL access:
1. Configure `postgresql.conf`: `listen_addresses = '*'`
2. Update `pg_hba.conf` with network access rules
3. Restart PostgreSQL container

---

## System Health Check

Run this quick health check:

```bash
# On AAP_HOST
cd /tmp

echo "=== Container Status ==="
sudo -u aapuser1 podman ps

echo ""
echo "=== PostgreSQL Health ==="
sudo -u aapuser1 podman exec postgresql psql -U postgres -c "SELECT version();" | head -3

echo ""
echo "=== OPA Health ==="
curl -s http://localhost:8181/health | jq '.'

echo ""
echo "=== Facts Count ==="
sudo -u aapuser1 podman exec postgresql psql -U postgres -d compliance \
  -tAc "SELECT COUNT(*) || ' facts records' FROM compliance_facts;"

echo ""
echo "=== Passwordless Sudo ==="
sudo -n whoami 2>&1

echo ""
echo "=== System Ready ==="
```

---

## Quick Reference

### Common Commands

```bash
# Collect facts
ansible-playbook -i inventory_AAP_HOST collect_and_store_cis_facts_rhel.yml

# Run evaluation
python3 /tmp/opa_eval_from_db.py ocptesttc cis_rhel9

# Query results
sudo -u aapuser1 podman exec postgresql psql -U postgres -d compliance \
  -c "SELECT * FROM compliance_results ORDER BY evaluation_timestamp DESC LIMIT 5;"

# Check containers
sudo -u aapuser1 podman ps

# View policies
curl -s http://AAP_HOST:8181/v1/data/cis_rhel9 | jq 'keys'
```

### File Paths Cheat Sheet

| Component | Location |
|-----------|----------|
| Ansible Playbook | `<aac-repo>/playbooks/collect_and_store_cis_facts_rhel.yml` |
| Inventory | `<aac-repo>/playbooks/inventory_AAP_HOST` |
| OPA Policies (local) | `<aac-repo>/policies/cis_rhel9/` |
| OPA Policies (server) | `/tmp/cis_rhel9/` |
| Evaluation Script | `/tmp/opa_eval_from_db.py` |
| Facts File | `/tmp/ansible_facts_<hostname>.json` |
| AAP Inventory | `/tmp/aap_inventory` |
| This README | `<aac-repo>/COMPLIANCE_SYSTEM_README.md` |

---

## Documentation and Resources

### Primary Documentation (Local System)

- **This README**: `<aac-repo>/COMPLIANCE_SYSTEM_README.md`
- **AAP Integration Guide**: `<aac-repo>/AAP_INTEGRATION_GUIDE.md` ⭐ NEW
- **OPA Scaling Guide**: `<docs-dir>/OPA_SCALING_GUIDE.md`
- **AAP Workflow Guide**: `/tmp/aap_compliance_workflow.md`
- **Complete Summary**: `/tmp/compliance_workflow_complete_summary.md`
- **Database Setup**: `/tmp/compliance_database_setup_complete.md`

### Git Repository Documentation

**Repository**: https://github.com/ansible-automated-compliance/aac

#### Core Documentation
- **Repository Contents**: [REPOSITORY_CONTENTS.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/reference/REPOSITORY_CONTENTS.md)
- **Documentation Index**: [DOCUMENTATION_INDEX.md](https://github.com/ansible-automated-compliance/aac/blob/main/DOCUMENTATION_INDEX.md)
- **Main README**: [README.md](https://github.com/ansible-automated-compliance/aac/blob/main/README.md)
- **FAQ**: [docs/reference/FAQ.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/reference/FAQ.md)

#### AAP/EDA Integration (AAP 2.6)
- **AAP Integration Overview**: [aap-integration/README.md](https://github.com/ansible-automated-compliance/aac/blob/main/aap-integration/README.md)
- **EDA Setup Guide**: [aap-integration/eda-setup/README.md](https://github.com/ansible-automated-compliance/aac/blob/main/aap-integration/eda-setup/README.md)
- **Quick Start Containerized**: [aap-integration/eda-setup/QUICK_START_CONTAINERIZED.md](https://github.com/ansible-automated-compliance/aac/blob/main/aap-integration/eda-setup/QUICK_START_CONTAINERIZED.md)
- **AAP 62 Usage Guide**: [docs/integration/AAP_62_USAGE_GUIDE.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/integration/AAP_62_USAGE_GUIDE.md)
- **EDA/OPA Integration**: [docs/integration/EDA_OPA_INTEGRATION.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/integration/EDA_OPA_INTEGRATION.md)
- **Install on AAP_HOST**: [aap-integration/eda-setup/INSTALL_AAP_HOST.md](https://github.com/ansible-automated-compliance/aac/blob/main/aap-integration/eda-setup/INSTALL_AAP_HOST.md)
- **Manual Project Setup**: [aap-integration/eda-setup/MANUAL_PROJECT_SETUP.md](https://github.com/ansible-automated-compliance/aac/blob/main/aap-integration/eda-setup/MANUAL_PROJECT_SETUP.md)
- **Private Automation Hub**: [docs/integration/PRIVATE_AUTOMATION_HUB_INTEGRATION.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/integration/PRIVATE_AUTOMATION_HUB_INTEGRATION.md)

#### Compliance Framework Documentation
- **CIS Implementation Timeline**: [docs/frameworks/CIS_BENCHMARK_IMPLEMENTATION_TIMELINE.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/frameworks/CIS_BENCHMARK_IMPLEMENTATION_TIMELINE.md)
- **CIS Technical Components**: [docs/frameworks/CIS_TECHNICAL_COMPONENTS.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/frameworks/CIS_TECHNICAL_COMPONENTS.md)
- **CIS Gaps Analysis**: [docs/frameworks/CIS_GAPS_ANALYSIS.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/frameworks/CIS_GAPS_ANALYSIS.md)
- **CIS Directory Structure**: [CIS_DIRECTORY_STRUCTURE.md](https://github.com/ansible-automated-compliance/aac/blob/main/CIS_DIRECTORY_STRUCTURE.md)
- **NIST Integration**: [NIST_INTEGRATION.md](https://github.com/ansible-automated-compliance/aac/blob/main/NIST_INTEGRATION.md)
- **NIST Directory Structure**: [NIST_DIRECTORY_STRUCTURE.md](https://github.com/ansible-automated-compliance/aac/blob/main/NIST_DIRECTORY_STRUCTURE.md)
- **Compliance Frameworks**: [docs/frameworks/COMPLIANCE_FRAMEWORKS.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/frameworks/COMPLIANCE_FRAMEWORKS.md)
- **Regulatory Mapping**: [docs/frameworks/REGULATORY_MAPPING.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/frameworks/REGULATORY_MAPPING.md)
- **Coverage Comparison**: [docs/frameworks/COVERAGE_COMPARISON.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/frameworks/COVERAGE_COMPARISON.md)

#### Architecture & Enterprise
- **OPA Scaling Guide**: [docs/operations/OPA_SCALING_GUIDE.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/operations/OPA_SCALING_GUIDE.md)
- **Enterprise Architecture**: [docs/architecture/ENTERPRISE_ARCHITECTURE.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/architecture/ENTERPRISE_ARCHITECTURE.md)
- **Enterprise Governance**: [docs/operations/ENTERPRISE_COMPLIANCE_GOVERNANCE.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/operations/ENTERPRISE_COMPLIANCE_GOVERNANCE.md)
- **Validation Architecture**: [compliance-validation-architecture.md](https://github.com/ansible-automated-compliance/aac/blob/main/compliance-validation-architecture.md)
- **Styra DAS Integration**: [operations/STYRA_DAS_INTEGRATION.md](https://github.com/ansible-automated-compliance/aac/blob/main/operations/STYRA_DAS_INTEGRATION.md)

#### Operations & Reporting
- **Compliance Reporting**: [docs/operations/COMPLIANCE_REPORTING.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/operations/COMPLIANCE_REPORTING.md)
- **Audit Evidence Collection**: [docs/operations/AUDIT_EVIDENCE_COLLECTION.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/operations/AUDIT_EVIDENCE_COLLECTION.md)
- **Update Schedule**: [docs/operations/COMPLIANCE_UPDATE_SCHEDULE.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/operations/COMPLIANCE_UPDATE_SCHEDULE.md)
- **Cost Analysis**: [operations/COST_ANALYSIS.md](https://github.com/ansible-automated-compliance/aac/blob/main/operations/COST_ANALYSIS.md)
- **Operations README**: [operations/README.md](https://github.com/ansible-automated-compliance/aac/blob/main/operations/README.md)

#### Testing & Validation
- **Testing & Validation**: [docs/operations/TESTING_AND_VALIDATION.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/operations/TESTING_AND_VALIDATION.md)
- **Validation Strategy**: [docs/operations/VALIDATION_STRATEGY.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/operations/VALIDATION_STRATEGY.md)
- **Git Approval Workflow**: [docs/operations/GIT_APPROVAL_WORKFLOW.md](https://github.com/ansible-automated-compliance/aac/blob/main/docs/operations/GIT_APPROVAL_WORKFLOW.md)

#### Business & Consulting
- **Business Opportunity**: [aap-integration/docs/BUSINESS_OPPORTUNITY.md](https://github.com/ansible-automated-compliance/aac/blob/main/aap-integration/docs/BUSINESS_OPPORTUNITY.md)

### Ansible Playbooks

#### Facts Collection (Primary)
- **CIS RHEL Facts**: `playbooks/collect_and_store_cis_facts_rhel.yml`
- **Git Repo**: [facts_collection/cis/collect_cis_rhel_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/collect_cis_rhel_facts.yml)

#### Additional Facts Collection Playbooks
- **AWS**: [facts_collection/cis/collect_cis_aws_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/collect_cis_aws_facts.yml)
- **Azure**: [facts_collection/cis/collect_cis_azure_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/collect_cis_azure_facts.yml)
- **GCP**: [facts_collection/cis/collect_cis_gcp_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/collect_cis_gcp_facts.yml)
- **Docker**: [facts_collection/cis/collect_cis_docker_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/collect_cis_docker_facts.yml)
- **Kubernetes**: [facts_collection/cis/collect_cis_kubernetes_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/collect_cis_kubernetes_facts.yml)
- **Oracle**: [facts_collection/cis/collect_cis_oracle_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/collect_cis_oracle_facts.yml)
- **Ubuntu**: [facts_collection/cis/collect_cis_ubuntu_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/collect_cis_ubuntu_facts.yml)
- **Windows**: [facts_collection/cis/collect_cis_windows_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/collect_cis_windows_facts.yml)
- **NIST**: [facts_collection/nist/collect_nist_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/nist/collect_nist_facts.yml)

#### Network Device Facts Collection
- **Cisco IOS**: [facts_collection/cis/network_devices/collect_cisco_ios_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/network_devices/collect_cisco_ios_facts.yml)
- **Juniper**: [facts_collection/cis/network_devices/collect_juniper_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/network_devices/collect_juniper_facts.yml)
- **Fortinet**: [facts_collection/cis/network_devices/collect_fortinet_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/network_devices/collect_fortinet_facts.yml)
- **Palo Alto**: [facts_collection/cis/network_devices/collect_paloalto_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/network_devices/collect_paloalto_facts.yml)
- **Arista**: [facts_collection/cis/network_devices/collect_arista_facts.yml](https://github.com/ansible-automated-compliance/aac/blob/main/facts_collection/cis/network_devices/collect_arista_facts.yml)

### OPA Policies

#### CIS RHEL 9 (Current Production)
- **Local**: `<aac-repo>/policies/cis_rhel9/`
- **Server**: `/tmp/cis_rhel9/`
- **Git**: [policies/cis_rhel9/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/cis_rhel9)
  - [cis_rhel9_complete.rego](https://github.com/ansible-automated-compliance/aac/blob/main/policies/cis_rhel9/cis_rhel9_complete.rego)
  - [modules/filesystem_validation.rego](https://github.com/ansible-automated-compliance/aac/blob/main/policies/cis_rhel9/modules/filesystem_validation.rego)
  - [modules/logging_validation.rego](https://github.com/ansible-automated-compliance/aac/blob/main/policies/cis_rhel9/modules/logging_validation.rego)
  - [modules/file_permissions_validation.rego](https://github.com/ansible-automated-compliance/aac/blob/main/policies/cis_rhel9/modules/file_permissions_validation.rego)
  - [modules/service_validation.rego](https://github.com/ansible-automated-compliance/aac/blob/main/policies/cis_rhel9/modules/service_validation.rego)
  - [modules/network_validation.rego](https://github.com/ansible-automated-compliance/aac/blob/main/policies/cis_rhel9/modules/network_validation.rego)

#### Other CIS Benchmarks
- **RHEL 8**: [policies/cis_benchmarks/rhel_8/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/cis_benchmarks/rhel_8)
- **RHEL 10**: [policies/cis_benchmarks/rhel_10/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/cis_benchmarks/rhel_10)
- **Ubuntu 20.04**: [policies/cis_benchmarks/ubuntu_20_04_lts/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/cis_benchmarks/ubuntu_20_04_lts)
- **Windows Server 2019**: [policies/cis_benchmarks/windows_server_2019/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/cis_benchmarks/windows_server_2019)
- **Windows Server 2022**: [policies/cis_benchmarks/windows_server_2022/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/cis_benchmarks/windows_server_2022)
- **AWS**: [policies/cis_benchmarks/aws/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/cis_benchmarks/aws)
- **Azure**: [policies/cis_benchmarks/azure/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/cis_benchmarks/azure)
- **GCP**: [policies/cis_benchmarks/gcp/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/cis_benchmarks/gcp)
- **Docker**: [policies/cis_benchmarks/docker/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/cis_benchmarks/docker)
- **Kubernetes**: [policies/cis_benchmarks/kubernetes/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/cis_benchmarks/kubernetes)
- **Oracle**: [policies/cis_oracle/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/cis_oracle)

#### Compliance Framework Policies
- **NIST 800-53**: [policies/nist/sp_800_53/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/nist/sp_800_53)
- **NIST 800-171**: [policies/nist/sp_800_171/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/nist/sp_800_171)
- **NIST CSF 2.0**: [policies/nist/cybersecurity_framework_2.0/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/nist/cybersecurity_framework_2.0)
- **ISO 27001**: [policies/iso27001/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/iso27001)
- **SOC 2**: [policies/soc2/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/soc2)
- **PCI-DSS**: [policies/pci_dss/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/pci_dss)
- **SOX**: [policies/sox/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/sox)
- **FISMA**: [policies/fisma/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/fisma)
- **NERC CIP**: [policies/nerc_cip/](https://github.com/ansible-automated-compliance/aac/tree/main/policies/nerc_cip)

### Scripts and Tools

- **Compliance Reporter**: [scripts/compliance_reporter.py](https://github.com/ansible-automated-compliance/aac/blob/main/scripts/compliance_reporter.py)
- **Policy Validator**: [scripts/validate_policies.py](https://github.com/ansible-automated-compliance/aac/blob/main/scripts/validate_policies.py)
- **Evidence Collector**: [scripts/audit_evidence_collector.py](https://github.com/ansible-automated-compliance/aac/blob/main/scripts/audit_evidence_collector.py)
- **Executive Dashboard**: [scripts/executive_dashboard.py](https://github.com/ansible-automated-compliance/aac/blob/main/scripts/executive_dashboard.py)
- **Performance Tester**: [scripts/performance_tester.py](https://github.com/ansible-automated-compliance/aac/blob/main/scripts/performance_tester.py)

### EDA Rulebooks

- **Compliance File Monitoring**: [eda/rulebooks/compliance_file_monitoring.yml](https://github.com/ansible-automated-compliance/aac/blob/main/eda/rulebooks/compliance_file_monitoring.yml)
- **System Events**: [eda/rulebooks/compliance_system_events.yml](https://github.com/ansible-automated-compliance/aac/blob/main/eda/rulebooks/compliance_system_events.yml)
- **Scheduled Drift Detection**: [eda/rulebooks/compliance_scheduled_drift.yml](https://github.com/ansible-automated-compliance/aac/blob/main/eda/rulebooks/compliance_scheduled_drift.yml)
- **Webhook Events**: [eda/rulebooks/compliance_webhook_events.yml](https://github.com/ansible-automated-compliance/aac/blob/main/eda/rulebooks/compliance_webhook_events.yml)
- **Oracle Events**: [eda/rulebooks/compliance_oracle_events.yml](https://github.com/ansible-automated-compliance/aac/blob/main/eda/rulebooks/compliance_oracle_events.yml)

---

## Version History

- **v1.0** (Nov 3-4, 2025): Initial production deployment
  - PostgreSQL database operational
  - OPA server with CIS RHEL 9 policies
  - Ansible facts collection playbook
  - AAP API integration
  - Complete documentation

---

**System Status**: ✅ Production Ready (fresh install 2026-03-28)
**CIS RHEL 9**: 338/338 controls (100% coverage) — 14 core + 3 extended modules
**Policies Loaded**: 505 Rego v1 policies across 3 OPA containers
**Major Frameworks**: CIS, NIST, ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, FedRAMP, CMMC, GDPR, HIPAA, NCSC CAF, NERC-CIP, IEC 62443, AMI/NIST IR 7628, Digital Sovereignty, AI Governance (see `CLAUDE.md` for full list)

---

*Updated: April 2026*
*Maintained by: Claude & Tim Coulter*
*Repository: github.com:ansible-automated-compliance/aac*
