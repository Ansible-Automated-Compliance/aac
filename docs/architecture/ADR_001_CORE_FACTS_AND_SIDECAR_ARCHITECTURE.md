# ADR-001: Core Facts Store + Sidecar Dataset Architecture

**Status:** Accepted
**Date:** March 19, 2026
**Authors:** Tim Coulter & Claude
**Deciders:** AAC Architecture Team

---

## Context

AAC assesses infrastructure against 15+ compliance frameworks including CIS, NIST, PCI-DSS,
SOC 2, HIPAA, ISO 27001, FISMA, NERC-CIP, Digital Sovereignty, and others. Early
implementations collected separate, framework-specific datasets for each standard — for
example, the Digital Sovereignty assessment required a hand-crafted JSON file covering
jurisdictions, key management, AI services, and BGP configuration.

This approach has several problems:

- **Duplication** — the same system facts (OS version, packages, services, network config)
  are collected multiple times for different frameworks
- **Inconsistency** — fact collection varies per framework, making cross-framework
  correlation impossible
- **Scalability** — adding a new compliance framework requires building a new data
  collection pipeline from scratch
- **Maintenance** — keeping multiple framework-specific datasets current is operationally
  expensive

---

## Decision

AAC adopts a **Core Facts Store + Sidecar Dataset** architecture:

1. **Core Facts Store** — a single comprehensive `gather_facts` collection runs nightly
   against every managed endpoint. All facts are stored as JSONB in PostgreSQL with a
   timestamp. This is the single source of truth for system state.

2. **Sidecar Datasets** — frameworks that require organizational context beyond what is
   discoverable from an endpoint provide a structured sidecar dataset. Sidecars are
   collected separately (either automated or manually maintained) and stored alongside
   core facts in PostgreSQL.

3. **OPA evaluation** — when a compliance assessment runs, OPA receives the merged input
   of core facts + any required sidecar data. The policy engine does not care where the
   data originated — it evaluates the combined dataset against the Rego policy.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CORE FACT STORE (PostgreSQL)                      │
│                                                                     │
│  Nightly gather_facts → complete system state per host              │
│                                                                     │
│  OS, packages, services, users, groups, network interfaces,         │
│  firewall rules, mount points, SSH configuration, audit rules,      │
│  file permissions, cron jobs, kernel parameters, running processes  │
│                                                                     │
│  Stored as JSONB with host_id + collected_at timestamp              │
│  Queryable via SQL across all hosts and all collection runs         │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
        ┌─────────────┼──────────────┬──────────────────┐
        │             │              │                  │
        ▼             ▼              ▼                  ▼
  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────────┐
  │   CIS    │  │  NIST    │  │   PCI-DSS    │  │   SOC 2      │
  │ Benchmarks│  │ 800-53   │  │              │  │              │
  │          │  │          │  │              │  │              │
  │ Uses core│  │ Uses core│  │  Uses core   │  │  Uses core   │
  │ facts    │  │ facts    │  │  facts       │  │  facts       │
  │ directly │  │ directly │  │  directly    │  │  directly    │
  └──────────┘  └──────────┘  └──────────────┘  └──────────────┘

        Frameworks requiring sidecar data:

  ┌──────────────────────┐  ┌──────────────────┐  ┌────────────────────┐
  │  Digital Sovereignty │  │    NERC-CIP      │  │  Hardware Supply   │
  │  Sidecar             │  │    Sidecar       │  │  Chain Sidecar     │
  │                      │  │                  │  │                    │
  │  approved_            │  │  bes_cyber_      │  │  manufacturer_     │
  │  jurisdictions        │  │  systems[]       │  │  country           │
  │  cloud_providers[]    │  │  protection_     │  │  firmware_origin   │
  │  key_management{}     │  │  levels{}        │  │  supply_chain_     │
  │  ai_services[]        │  │  control_        │  │  audit_status      │
  │  bgp_configuration{}  │  │  centers[]       │  │  known_backdoors   │
  │  hsm_configuration{}  │  │  esp_            │  │                    │
  │                      │  │  boundaries[]    │  │                    │
  └──────────────────────┘  └──────────────────┘  └────────────────────┘

                      │             │                  │
                      └─────────────┴──────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   OPA Policy Evaluation        │
                    │                               │
                    │  input = core_facts           │
                    │        + sidecar (if needed)  │
                    │                               │
                    │  → violations[]               │
                    │  → compliant: true/false      │
                    │  → score                      │
                    └───────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   Compliance Results           │
                    │   (PostgreSQL)                 │
                    │                               │
                    │  Timestamped, queryable,       │
                    │  cross-framework correlation   │
                    └───────────────────────────────┘
```

---

## Core Fact Domains

The following fact domains are collected by the standard AAC `gather_facts` playbook and
are available to **all** compliance frameworks without any additional collection:

| Domain | Facts Collected | Frameworks That Use It |
|--------|----------------|----------------------|
| **Operating System** | OS family, distribution, version, kernel, architecture | CIS, NIST, STIG, HIPAA, all |
| **Packages** | Installed packages, versions, sources | CIS, PCI-DSS, NIST, HIPAA |
| **Services** | Running services, enabled/disabled, startup type | CIS, NIST, STIG, SOC 2 |
| **Users & Groups** | Local users, groups, sudo config, password policy | CIS, NIST, HIPAA, PCI-DSS |
| **Network** | Interfaces, IP addresses, firewall rules, open ports | CIS, PCI-DSS, NIST, SOC 2 |
| **SSH Configuration** | sshd_config parameters, key algorithms, authentication | CIS, NIST, STIG |
| **Audit & Logging** | auditd rules, rsyslog config, journald settings | CIS, NIST, HIPAA, FISMA |
| **File Permissions** | Critical system file permissions and ownership | CIS, STIG, NIST |
| **Mount Points** | Filesystem mounts, options (noexec, nosuid, etc.) | CIS, NIST |
| **Kernel Parameters** | sysctl settings, kernel module status | CIS, NIST, STIG |
| **SELinux / AppArmor** | Mandatory access control mode and policy | CIS, NIST, STIG |
| **Cron & Scheduled Tasks** | Cron jobs, systemd timers, task scheduler | CIS, NIST |
| **PAM** | Password complexity, account lockout, MFA config | CIS, NIST, HIPAA, PCI-DSS |
| **Certificates & TLS** | Installed certificates, expiry, TLS configuration | PCI-DSS, HIPAA, SOC 2 |
| **Running Processes** | Active processes, listening ports, resource usage | Security, NERC-CIP |

---

## Sidecar Dataset Definitions

### When Is a Sidecar Required?

A sidecar is required when a compliance framework needs data that is:

1. **Organizational policy** — decisions made by the organization, not discoverable from
   an endpoint (e.g., which cloud jurisdictions are approved)
2. **Infrastructure topology** — relationships between systems that no single endpoint
   knows about (e.g., BES Cyber System boundaries in NERC-CIP)
3. **External service context** — data about third-party services the org uses (e.g., AI
   SaaS providers, cloud providers, HSM vendors)
4. **Architectural decisions** — key management approach, encryption standards, exit
   strategy — these are organizational, not per-host

### Sidecar: Digital Sovereignty

**Collection method:** Manually maintained + partial automation (cloud provider inventory
from AWS/Azure APIs, BGP config from network devices)
**Update frequency:** On architecture change, minimum quarterly review
**Applies to:** Organization-level assessment (one sidecar per org, not per host)

```yaml
# digital_sovereignty_sidecar.yml
approved_jurisdictions: [DE, FR, AT, NL, BE, GB]
approved_cloud_regions: [eu-central-1, eu-west-1, on_prem_de]

cloud_providers:
  - provider_id: aws
    hq_country: US
    subject_to_cloud_act: true
    data_processed_pct: 50

hsm_configuration:
  deployed: true
  type: fips_140_2_level3
  location_country: DE
  vendor_access_possible: false

key_management_policies:
  rotation_policy_documented: true
  rotation_frequency_days: 365
  dual_control_enforced: true

ai_services:
  - service_id: azure-openai-001
    provider: microsoft
    provider_hq_country: US
    data_used_for_training: false
    opt_out_of_training:
      enabled: true

bgp_configuration:
  rpki_deployed: true
  route_filtering_enabled: true
  autonomous_system_number_owned: true
```

### Sidecar: NERC-CIP

**Collection method:** Manually maintained (BES classifications require human judgment)
+ automated discovery for system inventory
**Update frequency:** On topology change, minimum annually
**Applies to:** OT/SCADA environments only

```yaml
# nerc_cip_sidecar.yml
bes_cyber_systems:
  - system_id: EMS-001
    name: Energy Management System
    impact_level: high
    esp_id: ESP-EAST-01

control_centers:
  - center_id: CC-001
    name: Primary Control Center
    reliability_standard: CIP-006

esp_boundaries:
  - esp_id: ESP-EAST-01
    electronic_access_points: [EAP-001, EAP-002]
    physical_security_perimeter: PSP-001
```

### Sidecar: Hardware Supply Chain

**Collection method:** Import from procurement system or CMDB
**Update frequency:** On hardware acquisition
**Applies to:** Physical servers and network equipment

```yaml
# hardware_supply_chain_sidecar.yml
hardware_components:
  - component_id: server-rack-de-001
    manufacturer_country: DE
    firmware_origin_country: DE
    supply_chain_audited: true
    known_vulnerabilities:
      hardware_backdoor: false
```

---

## Data Model

### PostgreSQL Schema

```sql
-- Core facts: one row per host per collection run
CREATE TABLE host_facts (
    id              SERIAL PRIMARY KEY,
    host_id         VARCHAR(255) NOT NULL,
    hostname        VARCHAR(255) NOT NULL,
    collected_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    facts           JSONB NOT NULL,
    collection_job  INTEGER  -- AAP job ID
);

-- Sidecar datasets: one row per sidecar type per entity
CREATE TABLE sidecar_datasets (
    id              SERIAL PRIMARY KEY,
    sidecar_type    VARCHAR(100) NOT NULL,  -- 'digital_sovereignty', 'nerc_cip', etc.
    entity_id       VARCHAR(255) NOT NULL,  -- org name, site ID, etc.
    collected_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    data            JSONB NOT NULL,
    source          VARCHAR(50)             -- 'manual', 'automated', 'api_import'
);

-- Compliance results: one row per framework per assessment run
CREATE TABLE compliance_results (
    id                  SERIAL PRIMARY KEY,
    assessed_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    framework           VARCHAR(100) NOT NULL,
    host_id             VARCHAR(255),        -- NULL for org-level assessments
    entity_id           VARCHAR(255),        -- org/site for sidecar-based assessments
    score               NUMERIC(5,2),
    level               VARCHAR(50),         -- SOVEREIGN, MODERATE_ASSURANCE, etc.
    domains_assessed    INTEGER,
    domains_passing     INTEGER,
    violations          JSONB,
    metadata            JSONB
);

-- Index for cross-framework queries
CREATE INDEX idx_compliance_framework ON compliance_results(framework);
CREATE INDEX idx_compliance_host ON compliance_results(host_id);
CREATE INDEX idx_compliance_date ON compliance_results(assessed_at);
CREATE INDEX idx_facts_host ON host_facts(host_id);
CREATE INDEX idx_facts_collected ON host_facts(collected_at);
```

### Cross-Framework Query Examples

```sql
-- Which hosts fail both CIS and NIST?
SELECT h.hostname
FROM compliance_results cis
JOIN compliance_results nist ON cis.host_id = nist.host_id
  AND DATE(cis.assessed_at) = DATE(nist.assessed_at)
JOIN host_facts h ON cis.host_id = h.host_id
WHERE cis.framework = 'CIS RHEL 9'
  AND nist.framework = 'NIST 800-53'
  AND cis.score < 100
  AND nist.score < 100
ORDER BY h.hostname;

-- 12-month sovereignty trend
SELECT DATE_TRUNC('month', assessed_at) as month,
       AVG(score) as avg_score,
       COUNT(*) FILTER (WHERE level = 'SOVEREIGN') as sovereign_count
FROM compliance_results
WHERE framework = 'Digital Sovereignty'
GROUP BY 1 ORDER BY 1;

-- Which systems are running OpenSSL 3.1.2?
SELECT hostname, facts->'packages'->'openssl'->>'version' as openssl_version
FROM host_facts
WHERE facts->'packages'->'openssl'->>'version' = '3.1.2'
  AND collected_at = (SELECT MAX(collected_at) FROM host_facts h2
                      WHERE h2.host_id = host_facts.host_id);
```

---

## Framework Classification

### Frameworks Using Core Facts Only

These frameworks evaluate entirely against `gather_facts` output. No sidecar required.

| Framework | What Core Facts Are Used |
|-----------|------------------------|
| CIS Benchmarks (all platforms) | OS config, packages, services, network, users, SSH, audit |
| NIST 800-53 | Full fact set mapped to control families |
| DISA STIGs | Same as CIS — detailed OS hardening checks |
| PCI-DSS | Network, services, users, audit logging, encryption config |
| SOC 2 | Services, users, access controls, logging |
| HIPAA | Access controls, audit logging, encryption, users |
| ISO 27001 | Broad system hardening mapped to Annex A controls |
| FISMA | Combines NIST controls with federal-specific requirements |

### Frameworks Requiring Sidecar Data

These frameworks assess organizational posture that cannot be derived from endpoint facts alone.

| Framework | Sidecar Contents | Collection Method |
|-----------|-----------------|-------------------|
| Digital Sovereignty | Jurisdictions, key management, AI services, BGP, HSM | Manual + cloud APIs |
| NERC-CIP | BES Cyber Systems, ESP boundaries, control centers | Manual + CMDB import |
| Hardware Supply Chain | Manufacturer provenance, firmware origin, audit status | Procurement import |
| Third-Party Risk | Vendor assessments, contracts, SLA data | Manual / GRC import |
| AI Governance | Approved AI services, training data classification | Manual + cloud APIs |

---

## Implementation Roadmap

### Phase 1 — Comprehensive Core Fact Collection (Current Gap)
Extend the existing `gather_facts` playbook to ensure complete coverage of all fact
domains listed above. Every framework should be able to run entirely from core facts
where the framework permits.

**Deliverables:**
- `ansible/playbooks/aac_gather_facts.yml` — comprehensive fact collection playbook
- Covers all 15 fact domains in the table above
- Runs nightly via AAP schedule
- Stores to `host_facts` table in PostgreSQL

### Phase 2 — Sidecar Schema Formalization
Define and document the canonical sidecar schema for each specialty framework. Convert
existing hand-crafted input JSON files (Digital Sovereignty, NERC-CIP) into validated
sidecar datasets stored in PostgreSQL.

**Deliverables:**
- `examples/sidecars/digital_sovereignty.yml` — canonical schema with documentation
- `examples/sidecars/nerc_cip.yml` — canonical schema with documentation
- `ansible/playbooks/store_sidecar.yml` — playbook to validate and store sidecar data
- Updated OPA policies to read merged core + sidecar input

### Phase 3 — Automated Sidecar Collection
For sidecar data that *can* be automated, build collection playbooks:

| Sidecar | Automatable Fields | Collection Method |
|---------|-------------------|-------------------|
| Digital Sovereignty | Cloud provider inventory, BGP config | AWS/Azure API + network device facts |
| NERC-CIP | System inventory, network topology | CMDB API, network discovery |
| Hardware Supply Chain | Installed hardware inventory | DMI/SMBIOS facts from gather_facts |

**Deliverables:**
- `ansible/playbooks/collect_sovereignty_sidecar.yml`
- `ansible/playbooks/collect_nerc_cip_sidecar.yml`

### Phase 4 — Sidecar Management UI
For sidecar data that requires human input (jurisdiction approvals, key management
policy decisions, BES classification), provide an AAP survey-based UI for data entry
and a validation playbook that checks completeness before assessment.

**Deliverables:**
- AAP survey on Digital Sovereignty Assessment template for sidecar fields
- Validation task that confirms required sidecar fields are populated
- Alerting when sidecar data is stale (>90 days without review)

---

## Benefits of This Architecture

### 1. Collect Once, Evaluate Many
A single nightly `gather_facts` run feeds every compliance framework. Adding a new
framework — when a new regulation comes out — requires only a new Rego policy. The
data collection pipeline is unchanged.

### 2. Cross-Framework Correlation
Because all facts and results land in PostgreSQL, cross-framework queries are standard
SQL. "Show me hosts that fail both CIS and PCI-DSS" is a join query, not a separate
tool or manual analysis.

### 3. True Historical Trending
Every fact collection is a timestamped snapshot. Every compliance result is stored with
its assessment date. You can answer any historical compliance question — "what was our
NIST score on January 1st?" — from the database, not from screenshots.

### 4. No Agent Proliferation
One collection mechanism (Ansible `gather_facts`) replaces per-framework agents.
Tanium requires an agent. Qualys requires an agent. Tenable requires an agent.
AAC requires SSH (or WinRM) — which is already present on every managed system.

### 5. Data Ownership
All facts and results live in a PostgreSQL database the customer owns and controls.
No vendor lock-in. No proprietary query language. Connect any BI tool — Grafana,
Tableau, Power BI, Splunk — via standard SQL.

### 6. Sidecar Pattern Is Self-Documenting
The existence of a sidecar schema makes explicit what organizational decisions a
framework requires. It forces the compliance team to consciously document and maintain
their policy positions — which is itself a compliance control.

---

## Comparison to Alternatives

| Approach | Collection | Cross-Framework | Historical | Data Ownership |
|----------|-----------|----------------|------------|----------------|
| **AAC (this ADR)** | Once (gather_facts) + sidecars | ✅ SQL joins | ✅ Unlimited | ✅ PostgreSQL |
| Per-framework tools (Qualys, Tenable) | Separate agent per tool | ❌ Siloed | Partial | ❌ Vendor DB |
| Tanium | Live endpoint query | ❌ Proprietary | ❌ Limited | ❌ Vendor DB |
| Manual audits | Spreadsheets per audit | ❌ Manual | ❌ None | ✅ (Excel) |
| Cloud-native (AWS Security Hub) | AWS-only | ❌ AWS only | Partial | ❌ AWS managed |

---

## Consequences

**Positive:**
- Single collection pipeline dramatically reduces operational overhead
- Cross-framework analysis becomes trivial SQL
- Historical trending is built-in, not an afterthought
- Adding frameworks is additive, not multiplicative
- Customer owns all data in standard PostgreSQL

**Negative / Trade-offs:**
- Core fact collection playbook must be comprehensive — gaps in fact collection mean
  gaps in framework coverage
- Sidecar data requires organizational discipline to keep current
- Sidecar schemas must be versioned and backward-compatible as frameworks evolve
- For real-time drift detection, EDA supplements but does not replace nightly collection

**Mitigations:**
- Sidecar staleness alerting (Phase 4) addresses discipline gap
- EDA-triggered collection closes the real-time window
- Schema versioning policy documented in sidecar schema files

---

**ADR Status:** Accepted
**Supersedes:** N/A (first architecture decision record for data model)
**Related Documents:**
- `docs/architecture/AAP_OPA_INTEGRATION_ARCHITECTURE.md`
- `docs/frameworks/DIGITAL_SOVEREIGNTY.md`
- `docs/frameworks/NERC_CIP_COVERAGE.md`
