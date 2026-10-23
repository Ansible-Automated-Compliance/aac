> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: SPLIT-PORTSx4, AAP-2.5/2.6x2, OLD-AAC-VERx1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Automated Compliance (AAC) — Installation Guide

**Version:** 2.6.0 | **Updated:** April 2026

AAC runs on top of Ansible Automation Platform (AAP). Installation has three phases:

1. **Check Requirements** — verify server meets all prerequisites
2. **Install AAP** — Red Hat containerized installer
3. **Deploy AAC** — load this repository into AAP

---

## Phase 0 — Check Requirements

Run this first on the target server before touching anything else:

```bash
git clone https://github.com/ansible-automated-compliance/aac.git
cd compliance
bash scripts/check_requirements.sh --fqdn aap.example.com
```

The script validates every requirement below and tells you exactly what to fix.

---

## Pre-Installation Planning

### FQDN (Required Before Installing AAP)

AAP uses TLS certificates tied to the server's hostname. **Set the FQDN before running the AAP installer** — changing it afterward requires certificate regeneration.

```bash
# Set the hostname
hostnamectl set-hostname aap.example.com

# Add to /etc/hosts if not in DNS
echo "$(hostname -I | awk '{print $1}') aap.example.com" >> /etc/hosts

# Verify
hostname -f   # must return aap.example.com, not 'localhost'
```

> **Important:** `localhost` does not work for AAP. AAP's gateway, controller, and
> execution nodes communicate using the FQDN. Using `localhost` causes certificate
> validation failures and routing errors between components.

### Port Planning

All ports must be available on the server before installation. Check for conflicts:

```bash
ss -tlnp | grep -E ':80 |:443 |:5432 |:818[1-3] '
```

#### Required Ports

| Port | Service | Traffic | Notes |
|------|---------|---------|-------|
| **80** | AAP Gateway | Inbound | HTTP → redirects to 443 |
| **443** | AAP Gateway | Inbound | Main UI and API (HTTPS) |
| **5432** | PostgreSQL | Internal only | Compliance history database — do not expose externally |
| **8181** | OPA Security | Internal only | CIS Benchmarks, NIST, STIGs |
| **8182** | OPA Compliance | Internal only | ISO 27001, SOC 2, PCI-DSS, SOX, FISMA |
| **8183** | OPA OT | Internal only | NERC-CIP, AI Governance |

#### Optional: MCP Server Port (Claude Code Integration)

| Port | Service | Traffic | Notes |
|------|---------|---------|-------|
| **8004** | AAP MCP Server | Inbound from dev workstation only | Required only for Claude Code + AAP integration |

> **Security note:** Port 8004 provides full AAP API access via Bearer token.
> Restrict it to your developer workstation IP — never open it broadly.

---

### Firewall Configuration

Configure firewalld after the OS is installed but **before** running the AAP installer.

#### Required Rules (all deployments)

```bash
# Allow AAP web UI and API
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https

# Apply changes
firewall-cmd --reload

# Verify
firewall-cmd --list-all
```

> **Do not** add firewalld rules for ports 5432, 8181, 8182, or 8183.
> These are internal-only — AAP playbooks reach them via localhost.
> Opening them to the network would expose compliance data and policy decisions.

#### Optional: MCP Server Rule (Claude Code integration only)

```bash
# Replace 203.0.113.10 with your actual developer workstation IP
DEV_IP="203.0.113.10"

firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='${DEV_IP}/32' port port='8004' protocol='tcp' accept"
firewall-cmd --reload

# Verify the rule was added
firewall-cmd --list-rich-rules
```

> If your workstation IP changes (e.g. on a laptop), update the rule:
> ```bash
> # Remove old rule
> firewall-cmd --permanent --remove-rich-rule="rule family='ipv4' source address='OLD.IP/32' port port='8004' protocol='tcp' accept"
> # Add new rule
> firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='NEW.IP/32' port port='8004' protocol='tcp' accept"
> firewall-cmd --reload
> ```

#### Complete Port Reference

| Port | Service | Firewall Rule | Direction |
|------|---------|--------------|-----------|
| 80 | AAP Gateway (HTTP) | `--add-service=http` | Inbound (all) |
| 443 | AAP Gateway (HTTPS) | `--add-service=https` | Inbound (all) |
| 5432 | PostgreSQL | **None — internal only** | Localhost only |
| 8181 | OPA Security | **None — internal only** | Localhost only |
| 8182 | OPA Compliance | **None — internal only** | Localhost only |
| 8183 | OPA OT | **None — internal only** | Localhost only |
| 8004 | MCP Server *(optional)* | Rich rule: dev IP only | Inbound (restricted) |

### Hardware Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| OS | RHEL 9.x | RHEL 9.x (latest minor) |
| Red Hat subscription | Active + AAP entitlement | — |
| CPU | 4 vCPUs | 8 vCPUs |
| RAM | 16 GB | 32 GB |
| Disk (`/`) | 40 GB free | 80 GB free |
| Podman | 4.x (included with RHEL 9) | — |

---

## Phase 1 — Install Ansible Automation Platform (Containerized)

### Step 1 — Download the AAP Installer

Log in to the Red Hat Customer Portal and download the **AAP 2.6 Containerized Setup Bundle**:

```
https://access.redhat.com/downloads/content/480
```

Select: **Ansible Automation Platform 2.6 Containerized Setup Bundle**

### Step 2 — Follow the Red Hat Containerized Install Guide

Red Hat's official documentation covers the full installation:

```
https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/containerized_installation
```

Key steps in the Red Hat guide:
1. Extract the installer bundle
2. Edit the `inventory` file — set your **FQDN** (not `localhost`), passwords, and subscription credentials
3. Run `ansible-playbook -i inventory ansible.containerized_installer.install`
4. Access the AAP Gateway UI at `https://<your-fqdn>/`

> **Note:** The Red Hat guide is the authoritative source. The scripts in this
> repository do not replace the official AAP installer — they deploy AAC on top
> of an already-running AAP.

### Step 3 — Verify AAP is Running

Once the installer completes, confirm AAP is healthy:

```bash
# Replace with your actual FQDN
AAP_FQDN="aap.example.com"

curl -sk "https://${AAP_FQDN}/api/gateway/v1/ping/"
curl -sk "https://${AAP_FQDN}/api/controller/v2/ping/"
```

Both should return HTTP 200 with JSON.

### 🔒 Checkpoint — Backup AAP Installer Inventory

The AAP installer `inventory` file contains all passwords set during installation.
Back it up immediately after a successful install — it cannot be recovered later.

```bash
# Back up the installer inventory (contains passwords — store securely)
bash scripts/backup.sh --skip-postgres --skip-vault

# Validate the backup was created
bash scripts/backup.sh --validate-only --skip-postgres --skip-vault
```

> Store the backup in a secure location outside this server (e.g. encrypted S3 bucket,
> secrets manager, or offline encrypted storage). Do not commit it to git.

---

## Phase 2 — Deploy AAC on Top of AAP

Once AAP is installed and healthy, deploy AAC by loading this repository as an AAP Project.

> **Role documentation:** For detailed variable references and advanced usage of the
> AAC Ansible roles (`aac_opa_containers`, `aac_compliance_db`, `aac_mcp_server`,
> `aac_store_results`, `aac_facts_collector`), see **[ROLES.md](ROLES.md)**.

### Step 1 — Add the AAC Project to AAP

In the AAP UI:

1. Go to **Resources → Projects → Add**
2. Set:
   - **Name:** Compliance Automation
   - **Source Control Type:** Git
   - **Source Control URL:** `https://github.com/ansible-automated-compliance/aac.git`
   - **Source Control Branch:** `main`
3. Save and sync the project

### Step 2 — Add the Ansible Vault Credential

AAC uses Ansible Vault to encrypt all secrets (passwords, API keys, certificates).

1. Go to **Resources → Credentials → Add**
2. **Credential Type:** Vault
3. **Vault Password:** obtain from your AAC administrator
4. Save as: `Ansible Vault`

### Step 3 — Run the AAC Setup Jobs

Once the project syncs, the following job templates will be available. Run them in order:

| Order | Template | Role | Purpose |
|-------|----------|------|---------|
| 1 | **114 — AAC - Initialize PostgreSQL Database** | `aac_compliance_db` | Deploy PostgreSQL container, create 4 schema tables, create `compliance_reader` role |
| 2 | **28 — AAC - Deploy OPA Containers** | `aac_opa_containers` | Deploy `opa-security :8181`, `opa-compliance :8182`, `opa-ot :8183` |
| 3 | **27 — AAC - Load OPA Policies** | *(playbook)* | Load all 327+ Rego policies from git into the three OPA containers |
| 4 | **50 — AAC - Seed Rotation Workflow** | *(playbook)* | Create the credential rotation workflow in AAP |
| 5 | **49 — AAC - Verify Installation** | *(playbook)* | Confirm all services are healthy (GO/NO-GO) |

### 🔒 Checkpoint — Initial AAC Backup

After the setup jobs complete successfully, take an initial backup of all AAC components:

```bash
# Full backup: vault + PostgreSQL + AAP inventory
bash scripts/backup.sh

# Validate everything backed up correctly
bash scripts/backup.sh --validate-only
```

Expected output:
```
✅ Vault backup created and decryption verified
✅ PostgreSQL backup created and integrity verified
✅ AAP inventory backed up
✅ Backup complete and validated
```

If any step fails, resolve it before proceeding.

### Step 4 — Verify the Installation

Run **AAC - Verify Installation** from the AAP UI. It checks all services and prints a GO / NO-GO report:

```
✅  OPA Security   (:8181) — CIS, NIST, STIGs — 167 policies
✅  OPA Compliance (:8182) — ISO 27001, SOC 2, PCI-DSS, FISMA, Sentinel — 78 policies
✅  OPA OT         (:8183) — NERC-CIP, AI Governance, AMI — 32 policies
✅  PostgreSQL     (:5432) — 4 tables, 0 rows
✅  AAP Gateway              — https://aap.example.com
✅  AAP Controller           — v4.x.x
✅  AAP MCP Token            — authenticated as admin
✅  MCP Server     (:8004)

🟢 GO — AAC is fully operational
```

If any item shows ❌, re-run the relevant setup job then re-run **AAC - Verify Installation**.

---

## Ongoing Backups

### What Gets Backed Up

| Component | Backup Method | Frequency | Notes |
|-----------|--------------|-----------|-------|
| Ansible Vault | `scripts/backup.sh` | Daily | Contains all secrets — most critical |
| PostgreSQL | `scripts/backup.sh` | Daily | Compliance history and audit evidence |
| OPA Policies | Git push | On every change | Git is the backup |
| AAP Platform | Red Hat installer backup playbook | Weekly | Job templates, credentials, inventories |
| AAP Inventory | `scripts/backup.sh` | After any change | Installer inventory with passwords |

### Schedule Daily Backups via AAP

Add a scheduled job in AAP to run backups automatically:

1. Create a job template using the playbook `ansible/playbooks/backup_aac.yml`
2. Set a schedule: **Daily at 02:00**
3. After each backup run, the job validates the backup automatically

Or run manually at any time:

```bash
# Full backup + validate
bash scripts/backup.sh

# Validate existing backups without creating new ones
bash scripts/backup.sh --validate-only

# Backup only the vault (fast — run before any vault changes)
bash scripts/backup.sh --skip-postgres
```

### AAP Platform Backup (Red Hat)

The Red Hat containerized installer includes its own backup playbook that captures
job templates, credentials, inventories, and AAP configuration:

```bash
cd /opt/ansible-automation-platform/<installer-bundle-dir>
ansible-playbook -i inventory \
  collections/ansible_collections/ansible/containerized_installer/playbooks/backup.yml
```

Run this **before any AAP upgrade or major configuration change**.

### Backup Retention

`scripts/backup.sh` automatically removes backups older than 30 days from `~/aac-backups/`.
For longer retention, copy backups to external storage before they expire.

### Restore Procedures

**Restore Ansible Vault:**
```bash
# Copy backup to vault location
cp ~/aac-backups/<timestamp>/vault_secrets_<timestamp>.yml \
   ansible/vars/vault_secrets.yml

# Verify it decrypts correctly
ansible-vault view ansible/vars/vault_secrets.yml \
  --vault-password-file ~/.vault_pass
```

**Restore PostgreSQL:**
```bash
# Restore from backup (this overwrites the current compliance database)
zcat ~/aac-backups/<timestamp>/compliance_<timestamp>.sql.gz | \
  podman exec -i postgresql psql -U postgres compliance

# Verify row count
podman exec postgresql psql -U postgres compliance \
  -c "SELECT COUNT(*) FROM compliance_results;"
```

---

## Credential Rotation

### Why Rotate Credentials

Rotating credentials limits the blast radius of a compromise. If a credential is
stolen, it is only useful until the next rotation. AAC enforces rotation by storing
all credentials in Ansible Vault and using a workflow to rotate, validate, and
re-commit them in a single auditable operation.

### Rotation Schedule

| Credential | Location | Rotate Every | Impact if Compromised |
|------------|----------|-------------|----------------------|
| AAP MCP Token | Vault + `~/.claude.json` + MCP container | 90 days | Full AAP API access from Claude Code |
| PostgreSQL password | Vault + PostgreSQL container | 90 days | Compliance database read/write |
| Grafana admin password | Vault + Grafana container | 90 days | Dashboard access |
| Ansible Vault password | `~/.vault_pass` (offline) | 180 days | Decrypts all other secrets |
| AAP admin password | AAP installer inventory | 90 days | Full platform administration |

> **Note:** The Ansible Vault password and AAP admin password are rotated manually
> (offline procedures). All other credentials are rotated via the AAP workflow.

### AAP Credential Rotation Workflow

AAC includes a 7-step workflow that rotates credentials, validates them, updates the
vault, commits to git, and takes a backup — all in a single auditable job.

**Setup (run once):**

```
AAP UI → Resources → Templates → AAC - Seed Rotation Workflow → Launch
```

This creates the `AAC - Rotate Credentials` workflow template with all 7 nodes.

**To rotate credentials:**

```
AAP UI → Resources → Templates → AAC - Rotate Credentials → Launch
```

Survey prompts:
- Which credentials to rotate (MCP Token / PostgreSQL / Grafana)
- AAP admin password (needed to create the new token)

**Workflow steps:**

| Step | Job Template | Purpose |
|------|-------------|---------|
| 1 | AAC - Rotation: Pre-Backup | Backup vault before any changes |
| 2 | AAC - Rotation: MCP Token | Generate + apply new AAP Bearer token |
| 3 | AAC - Rotation: PostgreSQL Password | Generate + apply new DB password |
| 4 | AAC - Rotation: Grafana Password | Generate + apply new Grafana password |
| 5 | AAC - Rotation: Update Vault | Write new values to vault, commit to git |
| 6 | AAC - Rotation: Validate | Test all rotated credentials work |
| 7 | AAC - Rotation: Post-Backup | Final backup + secure temp cleanup |

If any step fails, the workflow stops. Preceding steps are already applied to the
running services, so check the job output and re-run from the failed node.

### After MCP Token Rotation

The MCP server gets the new token automatically, but `~/.claude.json` on your Mac
must be updated manually (the server cannot reach your workstation):

```bash
# Get the new token from the server
ssh aapuser1@aap.example.com "sudo cat /opt/aap-mcp-server/mcp.env"

# Update ~/.claude.json with the new token
python3 -c "
import json
with open('/Users/YOUR_USER/.claude.json', 'r') as f: d = json.load(f)
d['projects']['/path/to/project']['mcpServers']['aap']['headers']['Authorization'] = 'Bearer NEW_TOKEN'
with open('/Users/YOUR_USER/.claude.json', 'w') as f: json.dump(d, f, indent=2)
"

# Restart Claude Code to establish a fresh MCP session
```

### Ansible Vault Password Rotation (Manual)

This is done offline — do not automate vault password rotation:

```bash
# On the AAP server
cd /path/to/compliance

# Re-encrypt vault with new password
ansible-vault rekey ansible/vars/vault_secrets.yml \
  --vault-password-file ~/.vault_pass \
  --new-vault-password-file /tmp/new_vault_pass

# Update the password file
cp /tmp/new_vault_pass ~/.vault_pass
chmod 600 ~/.vault_pass
shred -u /tmp/new_vault_pass

# Commit the re-encrypted vault
git add ansible/vars/vault_secrets.yml
git commit -m "Security: rekey Ansible Vault"
git push

# Update the AAP Vault credential with the new password
# AAP UI → Resources → Credentials → Ansible Vault → Edit
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| AAP installer fails on certificate step | Hostname is `localhost` or unresolvable | Set FQDN first: `hostnamectl set-hostname aap.example.com` |
| OPA container won't start | Port 8181/8182/8183 already in use | `ss -tlnp \| grep 818` to find conflict |
| PostgreSQL container won't start | Port 5432 already in use | Check for existing PostgreSQL: `ss -tlnp \| grep 5432` |
| AAP Gateway unreachable | Port 443 blocked by firewalld | `firewall-cmd --permanent --add-service=https && firewall-cmd --reload` |
| `hostname -f` returns `localhost` | FQDN not set | `hostnamectl set-hostname aap.example.com` |

---

## Getting Help

- **Red Hat AAP Documentation:** https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/
- **AAC Repository:** https://github.com/ansible-automated-compliance/aac
- **Requirements Check:** `bash scripts/check_requirements.sh`
- **Post-Install Verify:** Run **AAC - Verify Installation** (Template 49) in AAP
