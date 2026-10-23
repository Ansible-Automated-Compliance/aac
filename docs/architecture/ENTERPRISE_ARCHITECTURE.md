> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

> [!NOTE]
> **2026-10-17:** the legacy `ansible/roles/gather_*` roles this document describes were removed
> from the tree (no playbook called them). The same roles live in the `aac.cis_facts` collection
> at `collections/ansible_collections/aac/cis_facts/roles/`; the production CIS path uses
> `ansible/roles/aac_facts_collector` and `ansible/playbooks/cis_rhel9_assessment.yml`.

# Enterprise-Scale Compliance Architecture

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025


## Scale Requirements

**Target Capacity:** 100,000 managed nodes
**Collection Frequency:** Daily/weekly/on-demand
**Storage:** Fact data for historical tracking and trending

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                    ENTERPRISE COMPLIANCE PLATFORM                     │
└──────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Step 1: FACT COLLECTION (Distributed)                              │
└─────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
    │ AAP Tower 1  │        │ AAP Tower 2  │   ...  │ AAP Tower N  │
    │ (10K nodes)  │        │ (10K nodes)  │        │ (10K nodes)  │
    └──────┬───────┘        └──────┬───────┘        └──────┬───────┘
           │                       │                       │
           ▼                       ▼                       ▼
    ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
    │   RHEL9-1    │        │   RHEL9-101  │   ...  │  RHEL9-99K   │
    │   RHEL9-2    │        │   RHEL9-102  │        │  RHEL9-100K  │
    │    ...       │        │    ...       │        │              │
    │   RHEL9-100  │        │   RHEL9-200  │        │              │
    └──────┬───────┘        └──────┬───────┘        └──────┬───────┘
           │                       │                       │
           │ Facts (JSON)          │ Facts (JSON)          │ Facts (JSON)
           ▼                       ▼                       ▼

┌─────────────────────────────────────────────────────────────────────┐
│ Step 2: FACT STORAGE (Centralized Time-Series Database)            │
└─────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────┐
    │                    Time-Series Database Cluster                  │
    │                   (PostgreSQL/TimescaleDB or similar)            │
    │                                                                   │
    │  Table: compliance_facts                                         │
    │  ┌────────┬──────────┬──────────────┬──────────┬──────────┐    │
    │  │ node_id│ timestamp│ framework    │ facts    │ metadata │    │
    │  ├────────┼──────────┼──────────────┼──────────┼──────────┤    │
    │  │ host-1 │ 2025-... │ CIS_RHEL9    │ {...}    │ {...}    │    │
    │  │ host-1 │ 2025-... │ NIST_800_53  │ {...}    │ {...}    │    │
    │  │ host-2 │ 2025-... │ CIS_RHEL9    │ {...}    │ {...}    │    │
    │  │  ...   │   ...    │    ...       │  ...     │   ...    │    │
    │  └────────┴──────────┴──────────────┴──────────┴──────────┘    │
    │                                                                   │
    │  Partitioned by: timestamp (monthly)                             │
    │  Indexed by: node_id, timestamp, framework                       │
    │  Retention: Configurable (e.g., 13 months)                       │
    │  Compression: Enabled for older data                             │
    └─────────────────────────────────────────────────────────────────┘
           │
           ▼

┌─────────────────────────────────────────────────────────────────────┐
│ Step 3: POLICY VALIDATION (Distributed OPA)                        │
└─────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
    │  OPA Node 1  │        │  OPA Node 2  │   ...  │  OPA Node N  │
    │ (Load Bal.)  │        │ (Load Bal.)  │        │ (Load Bal.)  │
    └──────┬───────┘        └──────┬───────┘        └──────┬───────┘
           │                       │                       │
           │ Validates facts       │ Validates facts       │ Validates
           │ against policies      │ against policies      │ against policies
           ▼                       ▼                       ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │            OPA Policy Bundle (Version Controlled)                │
    │  - CIS RHEL 9 v2.0.0      - NIST 800-53 Rev 5                   │
    │  - PCI-DSS 4.0            - SOC2 Type II                         │
    │  - HIPAA                  - Custom policies                      │
    └─────────────────────────────────────────────────────────────────┘
           │
           │ Results (violations)
           ▼

┌─────────────────────────────────────────────────────────────────────┐
│ Step 4: RESULTS STORAGE (Compliance Database)                      │
└─────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────┐
    │                    Compliance Results Database                   │
    │                         (PostgreSQL)                             │
    │                                                                   │
    │  Table: compliance_results                                       │
    │  ┌────────┬──────────┬──────────┬────────────┬──────────────┐  │
    │  │ node_id│ timestamp│framework │ total_ctrls│ violations   │  │
    │  ├────────┼──────────┼──────────┼────────────┼──────────────┤  │
    │  │ host-1 │ 2025-... │ CIS      │ 338        │ [1.4.1, ...] │  │
    │  │ host-2 │ 2025-... │ CIS      │ 338        │ []           │  │
    │  │  ...   │   ...    │  ...     │  ...       │  ...         │  │
    │  └────────┴──────────┴──────────┴────────────┴──────────────┘  │
    │                                                                   │
    │  Table: control_violations                                       │
    │  ┌────────┬──────────┬──────────┬────────────┬──────────────┐  │
    │  │ node_id│ timestamp│ control  │ severity   │ remediation  │  │
    │  ├────────┼──────────┼──────────┼────────────┼──────────────┤  │
    │  │ host-1 │ 2025-... │ 1.4.1    │ HIGH       │ run_cmd: ... │  │
    │  │ host-1 │ 2025-... │ 3.5.1.6  │ MEDIUM     │ assign_iface │  │
    │  │  ...   │   ...    │  ...     │  ...       │  ...         │  │
    │  └────────┴──────────┴──────────┴────────────┴──────────────┘  │
    └─────────────────────────────────────────────────────────────────┘
           │
           ▼

┌─────────────────────────────────────────────────────────────────────┐
│ Step 5: REPORTING & VISUALIZATION (Web Dashboard)                  │
└─────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────┐
    │                     Compliance Dashboard                         │
    │                      (Grafana/Custom UI)                         │
    │                                                                   │
    │  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
    │  │  Fleet Overview │  │  Node Details   │  │ Trend Analysis│  │
    │  │                 │  │                 │  │               │  │
    │  │ 100,000 nodes   │  │ Host: rhel9-123 │  │ Compliance %  │  │
    │  │ 95% compliant   │  │ CIS: 335/338 ✓  │  │ over time     │  │
    │  │ 5,000 violations│  │ Violations:     │  │               │  │
    │  │                 │  │ - 1.4.1 (HIGH)  │  │    [chart]    │  │
    │  └─────────────────┘  └─────────────────┘  └───────────────┘  │
    │                                                                   │
    │  ┌─────────────────────────────────────────────────────────────┐│
    │  │ Remediation Queue (Prioritized by severity and count)       ││
    │  │ 1. Control 1.4.1: 2,500 nodes need bootloader password      ││
    │  │ 2. Control 3.5.1.6: 1,800 nodes have unassigned interfaces  ││
    │  │ 3. Control 5.2.4: 500 nodes using weak SSH ciphers          ││
    │  └─────────────────────────────────────────────────────────────┘│
    └─────────────────────────────────────────────────────────────────┘
           │
           ▼

┌─────────────────────────────────────────────────────────────────────┐
│ Step 6: REMEDIATION (Optional - Phase 2)                           │
└─────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
    │ AAP Tower 1  │        │ AAP Tower 2  │   ...  │ AAP Tower N  │
    │ Remediation  │        │ Remediation  │        │ Remediation  │
    └──────┬───────┘        └──────┬───────┘        └──────┬───────┘
           │                       │                       │
           │ Apply fixes           │ Apply fixes           │ Apply fixes
           │ (targeted)            │ (targeted)            │ (targeted)
           ▼                       ▼                       ▼
    [Nodes with violations only - not all 100K at once]
```

## Detailed Workflow - Complete Steps

### Overview

```
Step 1: Collect facts from 100,000 nodes → Store in database
Step 2: Validate each node's facts against policies → Identify gaps
Step 3: Generate reports showing violations → Provide remediation guidance
Step 4: (Optional Phase 2) Execute targeted remediation
```

### Step 1: Distributed Fact Collection

**Scale Considerations:**
- **100,000 nodes** cannot be collected from single Ansible Tower
- Use **multiple AAP instances** (10-20 towers, ~5,000-10,000 nodes each)
- **Parallel execution** with rate limiting to avoid overwhelming nodes
- **Asynchronous collection** with callback to central storage

**Implementation:**

```yaml
---
# facts-repo/collect-cis-facts-distributed.yml
- name: CIS RHEL 9 Fact Collection - Enterprise Scale
  hosts: all
  gather_facts: yes
  become: yes
  serial: 100  # Process 100 nodes at a time per tower
  strategy: free  # Don't wait for all nodes in batch

  vars:
    collection_id: "{{ lookup('env', 'TOWER_JOB_ID') }}"
    facts_api_endpoint: "https://compliance-api.example.com/v1/facts"

  roles:
    - gather_grub_security
    - gather_firewalld_detailed
    - gather_auditd_facts
    - gather_ssh_config
    - gather_pam_config
    - gather_user_security

  post_tasks:
    - name: Combine all facts
      set_fact:
        node_compliance_facts:
          node_id: "{{ ansible_hostname }}"
          collection_timestamp: "{{ ansible_date_time.iso8601 }}"
          collection_id: "{{ collection_id }}"
          tower_instance: "{{ lookup('env', 'TOWER_HOST') }}"
          facts:
            grub: "{{ host_grub_facts }}"
            firewall: "{{ host_firewalld_facts }}"
            audit: "{{ host_auditd_facts }}"
            ssh: "{{ host_ssh_facts }}"
            pam: "{{ host_pam_facts }}"
            user_security: "{{ host_user_security_facts }}"

    # Stream facts to central API (non-blocking)
    - name: Send facts to central storage
      uri:
        url: "{{ facts_api_endpoint }}"
        method: POST
        body_format: json
        body: "{{ node_compliance_facts }}"
        status_code: [200, 201, 202]
        timeout: 10
      delegate_to: localhost
      retries: 3
      delay: 5
      ignore_errors: yes  # Don't fail playbook if API is temporarily down

    # Fallback: Write to local file if API unavailable
    - name: Write facts to local file (fallback)
      copy:
        content: "{{ node_compliance_facts | to_json }}"
        dest: "/var/local/compliance/facts_{{ ansible_hostname }}_{{ ansible_date_time.epoch }}.json"
      when: facts_api_result is failed
```

**Performance Estimates:**

| Metric | Value |
|--------|-------|
| Fact collection per node | 30-60 seconds |
| AAP instances needed | 10-20 (5K-10K nodes each) |
| Total collection time (parallel) | 30-60 minutes |
| Network bandwidth per node | ~100-500 KB |
| Total data per collection | 10-50 GB |

### Step 2: Centralized Fact Storage

**Database Schema:**

```sql
-- PostgreSQL with TimescaleDB extension for time-series data

-- Main facts table (hypertable for time-series)
CREATE TABLE compliance_facts (
    id BIGSERIAL,
    node_id VARCHAR(255) NOT NULL,
    collection_timestamp TIMESTAMPTZ NOT NULL,
    collection_id VARCHAR(255),
    tower_instance VARCHAR(255),
    framework VARCHAR(50) NOT NULL,  -- CIS, NIST, PCI, etc.
    facts JSONB NOT NULL,
    metadata JSONB,
    PRIMARY KEY (node_id, collection_timestamp, framework)
);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('compliance_facts', 'collection_timestamp',
    chunk_time_interval => INTERVAL '1 month'
);

-- Create indexes
CREATE INDEX idx_facts_node_id ON compliance_facts(node_id);
CREATE INDEX idx_facts_timestamp ON compliance_facts(collection_timestamp DESC);
CREATE INDEX idx_facts_framework ON compliance_facts(framework);
CREATE INDEX idx_facts_tower ON compliance_facts(tower_instance);

-- GIN index for JSON queries
CREATE INDEX idx_facts_jsonb ON compliance_facts USING GIN(facts);

-- Compression policy (compress data older than 7 days)
SELECT add_compression_policy('compliance_facts', INTERVAL '7 days');

-- Retention policy (drop data older than 13 months)
SELECT add_retention_policy('compliance_facts', INTERVAL '13 months');

-- Node inventory table
CREATE TABLE nodes (
    node_id VARCHAR(255) PRIMARY KEY,
    hostname VARCHAR(255),
    ip_address INET,
    os_version VARCHAR(50),
    environment VARCHAR(50),  -- prod, dev, test
    datacenter VARCHAR(100),
    business_unit VARCHAR(100),
    last_seen TIMESTAMPTZ,
    metadata JSONB
);

-- Collection jobs tracking
CREATE TABLE collection_jobs (
    collection_id VARCHAR(255) PRIMARY KEY,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    tower_instance VARCHAR(255),
    target_nodes INT,
    successful_nodes INT,
    failed_nodes INT,
    status VARCHAR(50),  -- running, completed, failed
    error_log TEXT
);
```

**REST API for Fact Ingestion:**

```python
# api/facts_ingestion.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import asyncpg
import json

app = FastAPI()

class NodeFacts(BaseModel):
    node_id: str
    collection_timestamp: str
    collection_id: str
    tower_instance: str
    facts: dict

@app.post("/v1/facts")
async def ingest_facts(facts: NodeFacts):
    """
    Ingest compliance facts from distributed AAP towers
    High-throughput endpoint with connection pooling
    """
    try:
        pool = await asyncpg.create_pool(
            host='compliance-db.example.com',
            port=5432,
            database='compliance',
            user='compliance_writer',
            password=REDACTED_EXAMPLE,
            min_size=10,
            max_size=100
        )

        async with pool.acquire() as conn:
            # Insert CIS facts
            await conn.execute('''
                INSERT INTO compliance_facts
                (node_id, collection_timestamp, collection_id, tower_instance,
                 framework, facts)
                VALUES ($1, $2, $3, $4, 'CIS_RHEL9', $5)
                ON CONFLICT (node_id, collection_timestamp, framework)
                DO UPDATE SET facts = EXCLUDED.facts
            ''', facts.node_id, facts.collection_timestamp, facts.collection_id,
                facts.tower_instance, json.dumps(facts.facts))

            # Update node last_seen
            await conn.execute('''
                INSERT INTO nodes (node_id, last_seen)
                VALUES ($1, $2)
                ON CONFLICT (node_id)
                DO UPDATE SET last_seen = EXCLUDED.last_seen
            ''', facts.node_id, datetime.now())

        return {"status": "success", "node_id": facts.node_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Storage Capacity Planning:**

| Component | Size |
|-----------|------|
| Facts per node | 50-500 KB |
| Total per collection | 5-50 GB (100K nodes) |
| Daily storage (1 collection) | 5-50 GB |
| Monthly storage | 150-1500 GB |
| 13-month retention | 2-20 TB |
| With compression | 0.5-5 TB |

### Step 3: Distributed Policy Validation with OPA

**OPA Cluster Architecture:**

```yaml
# docker-compose.yml for OPA cluster
version: '3.8'

services:
  opa-1:
    image: openpolicyagent/opa:latest
    command:
      - "run"
      - "--server"
      - "--bundle"
      - "--addr=0.0.0.0:8181"
    volumes:
      - ./policies:/policies
    deploy:
      replicas: 5  # Scale horizontally
      resources:
        limits:
          cpus: '2'
          memory: 4G
    networks:
      - compliance

  nginx-load-balancer:
    image: nginx:latest
    ports:
      - "8181:8181"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - opa-1
    networks:
      - compliance

networks:
  compliance:
    driver: bridge
```

**Validation Worker:**

```python
# workers/policy_validator.py
import asyncio
import asyncpg
import aiohttp
from datetime import datetime

class PolicyValidator:
    def __init__(self, opa_endpoint, db_pool):
        self.opa_endpoint = opa_endpoint
        self.db_pool = db_pool

    async def validate_node(self, node_id, facts):
        """Validate single node against CIS policies"""
        async with aiohttp.ClientSession() as session:
            # Query OPA
            async with session.post(
                f"{self.opa_endpoint}/v1/data/cis/rhel9/evaluate",
                json={"input": facts}
            ) as resp:
                result = await resp.json()

            violations = result.get('result', {}).get('violations', [])

            # Store results
            async with self.db_pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO compliance_results
                    (node_id, timestamp, framework, total_controls,
                     passing_controls, violations)
                    VALUES ($1, $2, 'CIS_RHEL9', 338, $3, $4)
                ''', node_id, datetime.now(), 338 - len(violations),
                    json.dumps(violations))

                # Insert individual violations
                for violation in violations:
                    await conn.execute('''
                        INSERT INTO control_violations
                        (node_id, timestamp, control, severity,
                         current_value, expected_value, remediation)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ''', node_id, datetime.now(), violation['control'],
                        violation.get('severity', 'MEDIUM'),
                        violation.get('actual'), violation.get('expected'),
                        violation.get('remediation'))

            return len(violations)

    async def process_collection(self, collection_id):
        """Process entire collection batch"""
        async with self.db_pool.acquire() as conn:
            # Get all facts from this collection
            rows = await conn.fetch('''
                SELECT node_id, facts
                FROM compliance_facts
                WHERE collection_id = $1 AND framework = 'CIS_RHEL9'
            ''', collection_id)

        # Validate in parallel (1000 concurrent tasks)
        tasks = [self.validate_node(row['node_id'], row['facts'])
                 for row in rows]

        # Process in batches to avoid overwhelming OPA
        batch_size = 1000
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            results = await asyncio.gather(*batch)
            print(f"Validated batch {i//batch_size + 1}, "
                  f"total violations: {sum(results)}")

# Run validation
async def main():
    pool = await asyncpg.create_pool(...)
    validator = PolicyValidator("http://opa-lb:8181", pool)
    await validator.process_collection("job-12345")

asyncio.run(main())
```

**Performance Estimates:**

| Metric | Value |
|--------|-------|
| OPA validation per node | 100-500ms |
| OPA cluster size | 5-10 instances |
| Throughput per OPA instance | 100-200 validations/sec |
| Total cluster throughput | 500-2000 validations/sec |
| Time to validate 100K nodes | 50-200 seconds (~1-3 min) |

### Step 4: Gap Analysis and Remediation Reporting

**Report Generation Architecture:**

```python
# scripts/compliance_reporter.py
import asyncpg
import jinja2
from datetime import datetime
import json

class ComplianceReporter:
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.template_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader('templates/')
        )

    async def generate_fleet_summary(self, output_file='reports/fleet_summary.html'):
        """
        Generate executive summary for entire 100K node fleet
        """
        async with self.db_pool.acquire() as conn:
            # Fleet-wide statistics
            fleet_stats = await conn.fetchrow('''
                SELECT
                    COUNT(DISTINCT node_id) as total_nodes,
                    AVG(passing_controls * 100.0 / total_controls) as avg_compliance,
                    SUM(CASE WHEN passing_controls = total_controls THEN 1 ELSE 0 END) as fully_compliant,
                    SUM(CASE WHEN passing_controls < total_controls THEN 1 ELSE 0 END) as non_compliant,
                    COUNT(DISTINCT cv.control) as unique_violations
                FROM compliance_results cr
                LEFT JOIN control_violations cv USING (node_id, timestamp)
                WHERE cr.timestamp > NOW() - INTERVAL '1 day'
                  AND cr.framework = 'CIS_RHEL9'
            ''')

            # Top 20 most common violations across fleet
            top_violations = await conn.fetch('''
                SELECT
                    control,
                    COUNT(DISTINCT node_id) as affected_nodes,
                    (COUNT(DISTINCT node_id) * 100.0 / $1) as percentage_affected,
                    severity,
                    MAX(current_value) as example_current,
                    MAX(expected_value) as example_expected,
                    MAX(remediation) as remediation_guidance
                FROM control_violations
                WHERE timestamp > NOW() - INTERVAL '1 day'
                GROUP BY control, severity
                ORDER BY affected_nodes DESC
                LIMIT 20
            ''', fleet_stats['total_nodes'])

            # Compliance by environment
            env_breakdown = await conn.fetch('''
                SELECT
                    n.environment,
                    COUNT(DISTINCT cr.node_id) as nodes,
                    AVG(passing_controls * 100.0 / total_controls) as avg_compliance
                FROM compliance_results cr
                JOIN nodes n USING (node_id)
                WHERE cr.timestamp > NOW() - INTERVAL '1 day'
                  AND cr.framework = 'CIS_RHEL9'
                GROUP BY n.environment
                ORDER BY avg_compliance ASC
            ''')

        # Render HTML report
        template = self.template_env.get_template('fleet_summary.html')
        html = template.render(
            report_date=datetime.now(),
            fleet_stats=fleet_stats,
            top_violations=top_violations,
            env_breakdown=env_breakdown
        )

        with open(output_file, 'w') as f:
            f.write(html)

        return output_file

    async def generate_node_detail_report(self, node_id, output_file=None):
        """
        Generate detailed report for single node showing all violations
        and remediation steps
        """
        if output_file is None:
            output_file = f'reports/node_{node_id}_detail.html'

        async with self.db_pool.acquire() as conn:
            # Node information
            node_info = await conn.fetchrow('''
                SELECT
                    node_id,
                    hostname,
                    ip_address,
                    os_version,
                    environment,
                    datacenter,
                    business_unit,
                    last_seen
                FROM nodes
                WHERE node_id = $1
            ''', node_id)

            # Latest compliance results
            compliance = await conn.fetchrow('''
                SELECT
                    timestamp,
                    total_controls,
                    passing_controls,
                    (passing_controls * 100.0 / total_controls) as compliance_pct
                FROM compliance_results
                WHERE node_id = $1
                  AND framework = 'CIS_RHEL9'
                ORDER BY timestamp DESC
                LIMIT 1
            ''', node_id)

            # All violations for this node
            violations = await conn.fetch('''
                SELECT
                    control,
                    severity,
                    current_value,
                    expected_value,
                    remediation
                FROM control_violations
                WHERE node_id = $1
                ORDER BY
                    CASE severity
                        WHEN 'CRITICAL' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        WHEN 'LOW' THEN 4
                    END,
                    control
            ''', node_id)

            # Compliance trend (last 30 days)
            trend = await conn.fetch('''
                SELECT
                    DATE(timestamp) as date,
                    (passing_controls * 100.0 / total_controls) as compliance_pct
                FROM compliance_results
                WHERE node_id = $1
                  AND framework = 'CIS_RHEL9'
                  AND timestamp > NOW() - INTERVAL '30 days'
                ORDER BY date
            ''', node_id)

        # Render HTML report
        template = self.template_env.get_template('node_detail.html')
        html = template.render(
            report_date=datetime.now(),
            node=node_info,
            compliance=compliance,
            violations=violations,
            trend=trend
        )

        with open(output_file, 'w') as f:
            f.write(html)

        return output_file

    async def generate_remediation_playbook(self, output_file='reports/remediation_queue.yml'):
        """
        Generate Ansible playbook for remediation based on violations
        Groups nodes by violation for efficient remediation
        """
        async with self.db_pool.acquire() as conn:
            # Group nodes by violation
            violations_by_control = await conn.fetch('''
                SELECT
                    control,
                    severity,
                    remediation,
                    array_agg(DISTINCT node_id) as affected_nodes,
                    COUNT(DISTINCT node_id) as node_count
                FROM control_violations
                WHERE timestamp > NOW() - INTERVAL '1 day'
                GROUP BY control, severity, remediation
                ORDER BY
                    CASE severity
                        WHEN 'CRITICAL' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        WHEN 'LOW' THEN 4
                    END,
                    node_count DESC
            ''')

        # Generate Ansible playbook
        playbook = {
            'name': 'CIS RHEL 9 Remediation - Auto-Generated',
            'hosts': 'all',
            'become': True,
            'tasks': []
        }

        for violation in violations_by_control:
            task = {
                'name': f"Remediate {violation['control']} ({violation['node_count']} nodes)",
                'debug': {
                    'msg': f"Control: {violation['control']}, Severity: {violation['severity']}, Remediation: {violation['remediation']}"
                },
                'when': f"inventory_hostname in {violation['affected_nodes'][:10]}",  # Limit for safety
                'tags': [violation['control'], violation['severity'].lower()]
            }
            playbook['tasks'].append(task)

        with open(output_file, 'w') as f:
            import yaml
            yaml.dump([playbook], f, default_flow_style=False)

        return output_file

    async def generate_executive_summary_pdf(self, output_file='reports/executive_summary.pdf'):
        """
        Generate executive PDF report with charts and high-level metrics
        """
        # Implementation using reportlab or weasyprint
        pass

    async def generate_csv_export(self, output_file='reports/violations_export.csv'):
        """
        Export all violations to CSV for spreadsheet analysis
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT
                    cv.node_id,
                    n.hostname,
                    n.environment,
                    n.datacenter,
                    cv.control,
                    cv.severity,
                    cv.current_value,
                    cv.expected_value,
                    cv.remediation,
                    cv.timestamp
                FROM control_violations cv
                JOIN nodes n USING (node_id)
                WHERE cv.timestamp > NOW() - INTERVAL '1 day'
                ORDER BY n.environment, cv.severity, cv.control
            ''')

        import csv
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Node ID', 'Hostname', 'Environment', 'Datacenter',
                           'Control', 'Severity', 'Current Value', 'Expected Value',
                           'Remediation', 'Timestamp'])
            for row in rows:
                writer.writerow(row)

        return output_file


# Main report generation
async def generate_all_reports():
    """Generate complete set of compliance reports"""
    pool = await asyncpg.create_pool(...)
    reporter = ComplianceReporter(pool)

    reports = await asyncio.gather(
        reporter.generate_fleet_summary(),
        reporter.generate_remediation_playbook(),
        reporter.generate_csv_export()
    )

    print(f"Generated reports: {reports}")

    # Generate top 100 worst-performing node reports
    async with pool.acquire() as conn:
        worst_nodes = await conn.fetch('''
            SELECT node_id
            FROM compliance_results
            WHERE timestamp > NOW() - INTERVAL '1 day'
              AND framework = 'CIS_RHEL9'
            ORDER BY (passing_controls * 100.0 / total_controls) ASC
            LIMIT 100
        ''')

    for row in worst_nodes:
        await reporter.generate_node_detail_report(row['node_id'])
```

**Report Templates:**

```html
<!-- templates/fleet_summary.html -->
<!DOCTYPE html>
<html>
<head>
    <title>CIS RHEL 9 Fleet Compliance Summary</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .metric { display: inline-block; margin: 20px; padding: 20px; background: #f0f0f0; border-radius: 5px; }
        .metric h3 { margin: 0; color: #333; }
        .metric .value { font-size: 2em; font-weight: bold; color: #007acc; }
        table { border-collapse: collapse; width: 100%; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        th { background-color: #007acc; color: white; }
        .critical { background-color: #ffcccc; }
        .high { background-color: #ffe6cc; }
        .medium { background-color: #ffffcc; }
        .low { background-color: #e6ffe6; }
    </style>
</head>
<body>
    <h1>CIS RHEL 9 Fleet Compliance Summary</h1>
    <p>Report Generated: {{ report_date }}</p>

    <div class="metrics">
        <div class="metric">
            <h3>Total Nodes</h3>
            <div class="value">{{ "{:,}".format(fleet_stats.total_nodes) }}</div>
        </div>
        <div class="metric">
            <h3>Average Compliance</h3>
            <div class="value">{{ "%.1f"|format(fleet_stats.avg_compliance) }}%</div>
        </div>
        <div class="metric">
            <h3>Fully Compliant</h3>
            <div class="value">{{ "{:,}".format(fleet_stats.fully_compliant) }}</div>
        </div>
        <div class="metric">
            <h3>Non-Compliant</h3>
            <div class="value">{{ "{:,}".format(fleet_stats.non_compliant) }}</div>
        </div>
    </div>

    <h2>Top 20 Violations Across Fleet</h2>
    <p>Prioritize remediation efforts on these controls affecting the most nodes:</p>
    <table>
        <thead>
            <tr>
                <th>Control</th>
                <th>Affected Nodes</th>
                <th>% of Fleet</th>
                <th>Severity</th>
                <th>Remediation Guidance</th>
            </tr>
        </thead>
        <tbody>
            {% for violation in top_violations %}
            <tr class="{{ violation.severity.lower() }}">
                <td><strong>{{ violation.control }}</strong></td>
                <td>{{ "{:,}".format(violation.affected_nodes) }}</td>
                <td>{{ "%.1f"|format(violation.percentage_affected) }}%</td>
                <td>{{ violation.severity }}</td>
                <td>
                    <strong>Expected:</strong> {{ violation.example_expected }}<br>
                    <strong>Action:</strong> {{ violation.remediation_guidance }}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <h2>Compliance by Environment</h2>
    <table>
        <thead>
            <tr>
                <th>Environment</th>
                <th>Nodes</th>
                <th>Average Compliance</th>
            </tr>
        </thead>
        <tbody>
            {% for env in env_breakdown %}
            <tr>
                <td>{{ env.environment }}</td>
                <td>{{ "{:,}".format(env.nodes) }}</td>
                <td>{{ "%.1f"|format(env.avg_compliance) }}%</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <h2>Recommended Actions</h2>
    <ol>
        <li><strong>Priority 1 (Critical):</strong> Address violations affecting >10% of fleet</li>
        <li><strong>Priority 2 (High):</strong> Focus on production environment gaps</li>
        <li><strong>Priority 3 (Medium):</strong> Remediate development/test environments</li>
        <li><strong>Use generated playbook:</strong> <code>reports/remediation_queue.yml</code></li>
    </ol>
</body>
</html>
```

### Step 5: Aggregated Metrics and Dashboards

**Aggregated Metrics Queries:**

```sql
-- Fleet-wide compliance summary
SELECT
    COUNT(DISTINCT node_id) as total_nodes,
    AVG(passing_controls * 100.0 / total_controls) as avg_compliance_pct,
    SUM(CASE WHEN passing_controls = total_controls THEN 1 ELSE 0 END) as fully_compliant,
    COUNT(*) - SUM(CASE WHEN passing_controls = total_controls THEN 1 ELSE 0 END) as non_compliant
FROM compliance_results
WHERE timestamp > NOW() - INTERVAL '1 day'
  AND framework = 'CIS_RHEL9';

-- Top violations across fleet
SELECT
    control,
    COUNT(DISTINCT node_id) as affected_nodes,
    severity,
    remediation
FROM control_violations
WHERE timestamp > NOW() - INTERVAL '1 day'
GROUP BY control, severity, remediation
ORDER BY affected_nodes DESC
LIMIT 20;

-- Compliance trend over time
SELECT
    DATE_TRUNC('day', timestamp) as date,
    AVG(passing_controls * 100.0 / total_controls) as compliance_pct
FROM compliance_results
WHERE framework = 'CIS_RHEL9'
  AND timestamp > NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', timestamp)
ORDER BY date;

-- Worst-performing nodes
SELECT
    node_id,
    n.hostname,
    n.environment,
    passing_controls,
    total_controls,
    (passing_controls * 100.0 / total_controls) as compliance_pct
FROM compliance_results cr
JOIN nodes n USING (node_id)
WHERE timestamp > NOW() - INTERVAL '1 day'
  AND framework = 'CIS_RHEL9'
ORDER BY compliance_pct ASC
LIMIT 100;
```

## System Requirements

### Infrastructure

| Component | Specification |
|-----------|---------------|
| **AAP Towers** | 10-20 instances, 8 vCPU / 32GB RAM each |
| **Database** | PostgreSQL 15+ with TimescaleDB, 32 vCPU / 128GB RAM, 5TB SSD |
| **OPA Cluster** | 5-10 instances, 4 vCPU / 8GB RAM each |
| **API Servers** | 5-10 instances (load balanced), 8 vCPU / 16GB RAM |
| **Message Queue** | RabbitMQ or Kafka for async processing |
| **Object Storage** | S3/MinIO for raw fact files (backup) |

### Network

| Metric | Requirement |
|--------|-------------|
| Bandwidth (collection) | 10-50 Gbps aggregate |
| API throughput | 10,000-50,000 requests/sec |
| Database connections | 500-1000 concurrent |

## Next Steps

1. **Immediate:** Complete Phase 1 validation roles (90 → 338 controls)
2. **Infrastructure:** Design and deploy enterprise-scale architecture
3. **Testing:** Validate with 1K → 10K → 100K node scale tests
4. **Phase 2:** Build targeted remediation capabilities
5. **Phase 3:** Continuous compliance monitoring platform
