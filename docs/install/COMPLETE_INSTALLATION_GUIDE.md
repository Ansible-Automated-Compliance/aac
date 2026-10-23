> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: SPLIT-PORTSx13, AAP-2.5/2.6x11, HOST:8181x6, CONTAINERS-INTERNALx3, STALE-COUNTx2.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Automated Compliance (AAC) — Complete Installation Guide

**Version:** 3.0
**Date:** March 2026
**Estimated Time:** 4-6 hours
**Skill Level:** Intermediate Linux / Ansible administration

---

## Table of Contents

1. [Overview & Architecture](#1-overview--architecture)
2. [Prerequisites](#2-prerequisites)
3. [Phase 1: OS Preparation](#3-phase-1-os-preparation)
4. [Phase 2: Install AAP 2.6](#4-phase-2-install-aap-26)
5. [Phase 3: Clone Repository & Configure Vault](#5-phase-3-clone-repository--configure-vault)
6. [Phase 4: Deploy PostgreSQL](#6-phase-4-deploy-postgresql)
7. [Phase 5: Configure AAP](#7-phase-5-configure-aap)
8. [Phase 6: Build Custom Execution Environment](#8-phase-6-build-custom-execution-environment)
9. [Phase 7: Bootstrap Job Templates](#9-phase-7-bootstrap-job-templates)
10. [Phase 8: Deploy OPA Containers](#10-phase-8-deploy-opa-containers)
11. [Phase 9: Load OPA Policies](#11-phase-9-load-opa-policies)
12. [Phase 10: Deploy MCP Server](#12-phase-10-deploy-mcp-server)
13. [Phase 11: Deploy Grafana](#13-phase-11-deploy-grafana)
14. [Phase 12: Deploy Smart Meter Simulator](#14-phase-12-deploy-smart-meter-simulator)
15. [Phase 13: Demo Stability & Verification](#15-phase-13-demo-stability--verification)
16. [Troubleshooting](#16-troubleshooting)
17. [Quick Reference](#17-quick-reference)

---

## 1. Overview & Architecture

### What You Are Building

AAC is a policy-as-code compliance platform built on three integrated components:

```
┌─────────────────────────────────────────────────────────────────────┐
│                  ANSIBLE AUTOMATED COMPLIANCE (AAC)                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   Managed Systems                                                     │
│   (RHEL, Ubuntu, Windows, AWS, Smart Meters)                         │
│          │                                                            │
│          ▼  fact collection (SSH / WinRM)                            │
│   ┌─────────────────────────────────────────────────────────┐        │
│   │          Ansible Automation Platform 2.6                │        │
│   │   Schedules · Orchestrates · Stores audit trail         │        │
│   └───────────────┬─────────────────────────────────────────┘        │
│                   │  policy evaluation (REST)                        │
│          ┌────────┴────────────────────────────┐                     │
│          │                                     │                     │
│          ▼                                     ▼                     │
│   ┌─────────────────┐   ┌──────────────────────────────────┐        │
│   │  opa-security   │   │  opa-compliance   │  opa-ot       │        │
│   │  port 8181      │   │  port 8182        │  port 8183    │        │
│   │  CIS · NIST     │   │  ISO 27001 · SOC2 │  NERC-CIP     │        │
│   │  STIGs · Cloud  │   │  PCI-DSS · SOX    │  AI Gov       │        │
│   └─────────────────┘   └──────────────────────────────────┘        │
│                   │                                                   │
│                   ▼  store results (PostgreSQL wire protocol)        │
│   ┌───────────────────────────────────────────────────────────┐      │
│   │  PostgreSQL (compliance-db container · port 5432)         │      │
│   │  Historical tracking · Trending · Audit evidence          │      │
│   └───────────────────────────────────────────────────────────┘      │
│                   │                                                   │
│                   ▼  visualize                                       │
│   ┌───────────────────────────────────────────────────────────┐      │
│   │  Grafana (port 3000) · AMI Dashboard · NERC-CIP Dashboard │      │
│   └───────────────────────────────────────────────────────────┘      │
│                                                                       │
│   Additional Services:                                                │
│   • MCP Server (port 8004) — Claude Code ↔ AAP integration          │
│   • Smart Meter Simulator (ports 8085-8087) — NERC-CIP demo data    │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Summary

| Component | Container Name | Port | Purpose |
|-----------|---------------|------|---------|
| AAP 2.6 | (systemd-managed) | 443 | Orchestration, scheduling, RBAC |
| OPA Security | opa-security | 8181 | CIS Benchmarks, NIST, STIGs |
| OPA Compliance | opa-compliance | 8182 | ISO 27001, SOC 2, PCI-DSS, SOX, FISMA |
| OPA OT | opa-ot | 8183 | NERC-CIP, AI Governance |
| PostgreSQL | compliance-db | 5432 | Compliance results storage |
| MCP Server | aap-mcp | 8004 | Claude Code integration |
| Grafana | grafana | 3000 | Compliance dashboards |
| Smart Meter Sim | smart-meter-electric/gas/water | 8085-8087 | NERC-CIP demo data |

### Data Flow

```
Facts (Ansible) → Policy Evaluation (OPA) → Results (PostgreSQL) → Dashboards (Grafana)
```

All compliance logic lives in OPA Rego policies. Ansible only collects facts and stores results — it never makes policy decisions. This separation means policies can be updated without touching automation code.

### Key Design Principles

- **Read-only assessment** — AAC never modifies managed systems
- **Complete coverage** — 100% of infrastructure assessed (regulatory requirement)
- **All actions through AAP** — every operation runs as an AAP job with full audit trail
- **Always use podman** — never docker for any container operation
- **Policies in OPA** — never hardcode compliance logic in playbooks

---

## 2. Prerequisites

### Hardware Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 8 cores | 16 cores |
| RAM | 16 GB | 32 GB |
| Disk | 100 GB | 200 GB |
| Architecture | x86_64 (amd64) | x86_64 (amd64) |
| Network | 1 Gbps | 1 Gbps |

> **IMPORTANT:** x86_64 is required. The custom execution environment includes Terraform binaries built for linux/amd64. aarch64 (Apple Silicon, ARM) will not work for the EE build.

### Operating System

- **RHEL 9.x** (recommended — tested and supported)
- Rocky Linux 9.x or AlmaLinux 9.x are acceptable alternatives
- Active Red Hat subscription required for AAP 2.6

### Required Accounts

| Account | Purpose | Where to Get |
|---------|---------|--------------|
| Red Hat subscription | AAP 2.6 entitlement | console.redhat.com |
| GitHub account | Repository access | github.com |
| GitHub Personal Access Token | AAP project sync | GitHub → Settings → Developer Settings → PAT |
| quay.io account | Custom EE image storage | quay.io (free) |
| AWS account (optional) | Lab targets, Terraform demo | aws.amazon.com |

### GitHub PAT Scopes Required

When creating your GitHub PAT (classic), enable:
- `repo` — full repository access
- `read:packages` — if using GitHub Container Registry

### Network Ports (Firewall)

The following ports must be open on the AAP server:

| Port | Protocol | Service | Access From |
|------|----------|---------|-------------|
| 443 | TCP | AAP Web UI / API | Admin workstations |
| 8181 | TCP | OPA Security | AAP controller (localhost) |
| 8182 | TCP | OPA Compliance | AAP controller (localhost) |
| 8183 | TCP | OPA OT | AAP controller (localhost) |
| 5432 | TCP | PostgreSQL | AAP controller (localhost) |
| 8004 | TCP | MCP Server | Admin workstations (Claude Code) |
| 3000 | TCP | Grafana | Admin workstations |
| 8085-8087 | TCP | Smart Meter Sim | AAP controller (localhost) |

OPA, PostgreSQL, and Smart Meter ports only need to be accessible from localhost unless you have remote clients querying them directly.

### What to Have Ready Before You Start

1. Red Hat subscription credentials
2. AAP 2.6 installer bundle downloaded from access.redhat.com
3. GitHub PAT (write the value down — you will enter it during vault setup)
4. quay.io login credentials
5. AWS access key + secret key (if using AWS lab targets)
6. Desired passwords for: AAP admin, PostgreSQL, Grafana

---

## 3. Phase 1: OS Preparation

All commands in this phase run as root (or via sudo) on the AAP server.

### Step 1.1: Register with Red Hat

```bash
sudo subscription-manager register --username YOUR_RH_USERNAME --auto-attach
sudo subscription-manager repos --enable ansible-automation-platform-2.6-for-rhel-9-x86_64-rpms
```

Verify the AAP repo is enabled:
```bash
sudo subscription-manager repos --list-enabled | grep aap
```

### Step 1.2: System Updates

```bash
sudo dnf update -y
sudo reboot
```

### Step 1.3: Install Required Packages

```bash
sudo dnf install -y \
  podman \
  git \
  python3 \
  python3-pip \
  jq \
  curl \
  wget \
  unzip \
  ansible-builder \
  firewalld
```

Verify podman:
```bash
podman --version
# Should show: podman version 4.x.x
```

### Step 1.4: Configure Firewall

```bash
sudo systemctl enable --now firewalld

# AAP web UI
sudo firewall-cmd --permanent --add-service=https

# OPA containers
sudo firewall-cmd --permanent --add-port=8181/tcp
sudo firewall-cmd --permanent --add-port=8182/tcp
sudo firewall-cmd --permanent --add-port=8183/tcp

# MCP server (Claude Code)
sudo firewall-cmd --permanent --add-port=8004/tcp

# Grafana
sudo firewall-cmd --permanent --add-port=3000/tcp

# Smart meter simulator
sudo firewall-cmd --permanent --add-port=8085/tcp
sudo firewall-cmd --permanent --add-port=8086/tcp
sudo firewall-cmd --permanent --add-port=8087/tcp

sudo firewall-cmd --reload
sudo firewall-cmd --list-all
```

> **Note:** Port 5432 (PostgreSQL) should NOT be opened externally. It is accessed only from localhost by AAP jobs running inside the execution environment.

### Step 1.5: Configure SELinux

SELinux should remain in **enforcing** mode. Configure the correct contexts for container volumes:

```bash
# Create OPA policy directories
sudo mkdir -p /etc/opa/security /etc/opa/compliance /etc/opa/ot

# Set SELinux context so containers can read the policy files
sudo semanage fcontext -a -t container_file_t "/etc/opa(/.*)?"
sudo restorecon -Rv /etc/opa

# Create MCP server directory
sudo mkdir -p /opt/aap-mcp-server
sudo semanage fcontext -a -t container_file_t "/opt/aap-mcp-server(/.*)?"
sudo restorecon -Rv /opt/aap-mcp-server
```

Verify SELinux is enforcing:
```bash
getenforce
# Should show: Enforcing
```

### Step 1.6: Create the aapuser1 Account

AAP's containerized installer creates this user, but if you need it beforehand:

```bash
sudo useradd -m aapuser1
sudo passwd aapuser1
# Set to your desired password — this goes in vault as vault_aapuser1_password

# Add to sudoers (required for AAP installer and container operations)
echo "aapuser1 ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/aapuser1
```

### Checkpoint

```bash
podman --version          # 4.x.x
git --version             # 2.x.x
ansible-builder --version # 3.x.x
getenforce                # Enforcing
sudo firewall-cmd --list-ports
```

---

## 4. Phase 2: Install AAP 2.6

AAP 2.6 uses a containerized installer. All AAP services run as podman containers managed by systemd.

### Step 2.1: Download the Installer Bundle

Download the AAP 2.6 containerized setup bundle from the Red Hat Customer Portal:

```
https://access.redhat.com/downloads/content/480
```

Look for: **Ansible Automation Platform 2.6 Setup Bundle**
Filename pattern: `ansible-automation-platform-containerized-setup-bundle-2.6-<version>-x86_64.tar.gz`

Copy to the server:
```bash
scp ansible-automation-platform-containerized-setup-bundle-2.6-*-x86_64.tar.gz \
  aapuser1@YOUR_SERVER_IP:/home/aapuser1/
```

### Step 2.2: Extract the Bundle

```bash
sudo su - aapuser1
cd ~
tar xzf ansible-automation-platform-containerized-setup-bundle-2.6-*-x86_64.tar.gz

# The extracted directory will be named something like:
# ansible-automation-platform-containerized-setup-bundle-2.6-1-x86_64
INSTALL_DIR=$(ls -d ansible-automation-platform-containerized-setup-bundle-2.6-*-x86_64)
cd $INSTALL_DIR
```

### Step 2.3: Configure the Installer Inventory

Edit the inventory file in the extracted directory:

```bash
cp inventory inventory.bak
vi inventory
```

Minimum required configuration:

```ini
[automationcontroller]
YOUR_SERVER_IP ansible_connection=local

[automationhub]
YOUR_SERVER_IP ansible_connection=local

[automationeda]
YOUR_SERVER_IP ansible_connection=local

[database]
YOUR_SERVER_IP ansible_connection=local

[all:vars]
# Required: admin password for the AAP web UI
admin_password=$AAP_ADMIN_PASSWORD

# Required: PostgreSQL passwords (AAP internal database — separate from compliance DB)
pg_password=$PG_PASSWORD

# Required: Red Hat registry credentials (for pulling container images)
registry_url='registry.redhat.io'
registry_username='YOUR_RH_USERNAME'
registry_password=$RH_PASSWORD

# Optional: custom hostname
# routable_hostname=YOUR_SERVER_IP
```

> **Important:** The `admin_password` you set here is the AAP web UI password. Record it — you will need it for all subsequent steps. It is also the password stored in the installer inventory file at:
> `/home/aapuser1/ansible-automation-platform-containerized-setup-bundle-2.6-<version>-x86_64/inventory`

### Step 2.4: Run the Installer

```bash
# From inside the installer directory as aapuser1
ansible-playbook -i inventory collections/ansible_collections/ansible/containerized_installer/playbooks/install.yml
```

This takes 20-40 minutes. The installer pulls container images from registry.redhat.io and starts all AAP services.

### Step 2.5: Verify AAP is Running

```bash
# Check AAP gateway ping
curl -sk https://localhost/api/gateway/v1/ping/ | jq .

# Check controller API
curl -sk -u admin:$AAP_ADMIN_PASSWORD \
  https://localhost/api/controller/v2/ping/ | jq .version

# List running containers
podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

You should see containers for: automation-controller, automation-hub, automation-eda, and supporting services.

### Step 2.6: Log Into the Web UI

Open a browser and navigate to: `https://YOUR_SERVER_IP`

- **Username:** admin
- **Password:** the `admin_password` from your inventory file

Accept the SSL certificate warning (self-signed by default).

### Step 2.7: Apply the AAP Subscription

In the AAP web UI:
1. Navigate to **Administration → Subscription**
2. Click **Upload a subscription manifest** or **Login with Red Hat credentials**
3. Select your AAP subscription
4. Click **Save**

### Checkpoint

```bash
curl -sk https://localhost/api/gateway/v1/ping/ | jq .status
# Should show: "ok"

curl -sk -u admin:$ADMIN_PASSWORD \
  https://localhost/api/controller/v2/ping/ | jq .version
# Should show AAP version string
```

---

## 5. Phase 3: Clone Repository & Configure Vault

### Step 3.1: Clone the AAC Repository

```bash
sudo su - aapuser1
cd ~

# Clone using your GitHub PAT for authentication
git clone https://YOUR_GITHUB_PAT@github.com/ansible-automated-compliance/aac.git

# The repository will be at:
# /home/aapuser1/compliance/
ls compliance/
```

### Step 3.2: Install Ansible for Vault Operations

```bash
pip3 install --user ansible ansible-vault
```

### Step 3.3: Create the Vault Password File

```bash
# Choose a strong vault password and write it to a file
# This file protects all secrets — guard it carefully
echo '$VAULT_PASSWORD' > ~/.vault_pass
chmod 600 ~/.vault_pass
```

### Step 3.4: Create the Vault Secrets File

```bash
# Create and encrypt the vault secrets file
ansible-vault create ~/compliance/ansible/vars/vault_secrets.yml \
  --vault-password-file ~/.vault_pass
```

This opens an editor. Enter the following content with your actual values:

```yaml
---
# AAC Vault Secrets
# Edit with: ansible-vault edit ansible/vars/vault_secrets.yml --vault-password-file ~/.vault_pass

# PostgreSQL compliance database (set in Phase 4)
compliance_db_password: "{{ compliance_db_password }}"
compliance_reader_password: "{{ compliance_reader_password }}"

# AWS credentials (optional — required for AWS lab targets)
aws_access_key: "YOUR_AWS_ACCESS_KEY"
aws_secret_key: "YOUR_AWS_SECRET_KEY"
vault_windows_admin_password: "YOUR_WINDOWS_ADMIN_PASSWORD"

# Red Hat credentials (for EE builds and subscription)
vault_redhat_username: "YOUR_RH_USERNAME"
vault_redhat_offline_token: "{{ vault_redhat_offline_token }}"

# GitHub Personal Access Token (for AAP project sync)
vault_github_pat: "YOUR_GITHUB_PAT"

# AAP MCP server token (populated in Phase 10 after AAP is configured)
vault_aap_local_mcp_token: "{{ vault_aap_local_mcp_token }}"  # rotate in phase 10

# AAP aapuser1 SSH password (for EE build delegation)
vault_aapuser1_password: "YOUR_AAPUSER1_PASSWORD"

# quay.io credentials (for pushing/pulling custom EE)
vault_quay_username: "YOUR_QUAY_USERNAME"
vault_quay_password: "{{ vault_quay_password }}"

# Grafana admin password
# IMPORTANT: No special characters — bash quoting over SSH will drop them
grafana_admin_password: "{{ grafana_admin_password }}"
```

Save and close the editor. The file is now encrypted.

### Step 3.5: Verify Vault

```bash
ansible-vault view ~/compliance/ansible/vars/vault_secrets.yml \
  --vault-password-file ~/.vault_pass
# Should display the decrypted contents
```

### Step 3.6: Get a Red Hat Offline Token

The offline token is used for Red Hat registry authentication during EE builds:

1. Go to: https://access.redhat.com/management/api
2. Click **Generate Token**
3. Copy the offline token value
4. Update the vault: `ansible-vault edit ~/compliance/ansible/vars/vault_secrets.yml --vault-password-file ~/.vault_pass`
5. Set `vault_redhat_offline_token` to the copied value

### Vault Variable Reference

| Variable | Purpose | When Needed |
|----------|---------|-------------|
| `compliance_db_password` | PostgreSQL postgres superuser | Phase 4 onward |
| `compliance_reader_password` | PostgreSQL read-only user | Phase 4 onward |
| `aws_access_key` | AWS API access | AWS lab only |
| `aws_secret_key` | AWS API secret | AWS lab only |
| `vault_windows_admin_password` | Windows EC2 admin | Windows targets only |
| `vault_redhat_username` | Red Hat login | EE build (Phase 6) |
| `vault_redhat_offline_token` | Red Hat API token | EE build (Phase 6) |
| `vault_github_pat` | GitHub project sync | Phase 5 AAP config |
| `vault_aap_local_mcp_token` | MCP Bearer token | Phase 10 |
| `vault_aapuser1_password` | SSH for EE build | Phase 6 |
| `vault_quay_username` | quay.io login | Phase 6 |
| `vault_quay_password` | quay.io password | Phase 6 |
| `grafana_admin_password` | Grafana web UI | Phase 11 |

### Checkpoint

```bash
ansible-vault view ~/compliance/ansible/vars/vault_secrets.yml \
  --vault-password-file ~/.vault_pass | grep compliance_db_password
# Should show your password (not encrypted)

ls ~/compliance/policies/cis_benchmarks/rhel_9/*.rego | wc -l
# Should show 16
```

---

## 6. Phase 4: Deploy PostgreSQL

AAC uses a standalone PostgreSQL container for compliance data storage. This is **separate** from AAP's internal PostgreSQL database.

### Preferred method: AAP Template 114

Once job templates are seeded (Phase 7), deploy PostgreSQL with a single click:

- **Template 114: AAC - Initialize PostgreSQL Database** — runs `ansible/playbooks/postgres_database_init.yml`

This calls the `aac_compliance_db` Ansible role, which:
1. Pulls `registry.access.redhat.com/ubi9/postgresql-15`
2. Creates the `compliance_pgdata` named volume
3. Starts the `postgresql` container on port 5432
4. Creates all compliance schema tables (`compliance_results`, `compliance_facts`, `host_facts`, `sidecar_datasets`) — idempotent, safe to re-run
5. Creates the `compliance_reader` read-only role for Grafana
6. Generates a podman systemd unit for on-boot startup

**Role defaults** (`ansible/roles/aac_compliance_db/defaults/main.yml`):

| Variable | Default | Override to change |
|----------|---------|-------------------|
| `aac_db_image` | `registry.access.redhat.com/ubi9/postgresql-15` | Different PG version |
| `aac_db_container_name` | `postgresql` | Different container name |
| `aac_db_volume` | `compliance_pgdata` | Different volume |
| `aac_db_port` | `5432` | Non-standard port |
| `aac_db_generate_systemd` | `true` | Set `false` in container environments |
| `aac_db_skip_container_deploy` | `false` | Set `true` for schema-only runs |

Passwords come from `ansible/vars/vault_secrets.yml`:
- `compliance_db_password` → postgres superuser
- `compliance_reader_password` → compliance_reader role

### Bootstrap fallback (no AAP yet)

Before AAP is available, use the bash script:

```bash
cd /path/to/aac
./scripts/install_postgres.sh --password $COMPLIANCE_DB_PASSWORD
```

The script deploys the container only. Schema initialization still requires
running Template 114 (or `aac_init_facts_schema.yml`) once AAP is available.

### Verify PostgreSQL is Running

```bash
# Check container is up
podman ps | grep postgresql

# Test connection
podman exec postgresql psql -U postgres -c "SELECT version();"

# Verify tables were created
podman exec postgresql psql -U postgres -d compliance -c "\dt"
```

Expected output:
```
              List of relations
 Schema |          Name           | Type  |  Owner
--------+-------------------------+-------+----------
 public | compliance_facts        | table | postgres
 public | compliance_results      | table | postgres
 public | host_facts              | table | postgres
 public | sidecar_datasets        | table | postgres
```

### Checkpoint

```bash
podman ps | grep compliance-db   # Up and running
podman exec compliance-db psql -U postgres -d compliance \
  -c "SELECT COUNT(*) FROM compliance_results;"
# Should show: 0 (empty — that's correct)
```

---

## 7. Phase 5: Configure AAP

Log into the AAP web UI at `https://YOUR_SERVER_IP` as admin before starting this phase.

### Step 5.1: Create the GitHub Credential

**Automation Execution → Infrastructure → Credentials → +Create credential**

| Field | Value |
|-------|-------|
| Name | GitHub PAT |
| Organization | Default |
| Credential Type | Source Control |
| Username | your-github-username |
| Password | YOUR_GITHUB_PAT |

Click **Save**.

### Step 5.2: Create the Ansible Vault Credential

**Automation Execution → Infrastructure → Credentials → +Create credential**

| Field | Value |
|-------|-------|
| Name | Ansible Vault |
| Organization | Default |
| Credential Type | Vault |
| Vault Password | $VAULT_PASSWORD (same as ~/.vault_pass contents) |

Click **Save**.

### Step 5.3: Create the Machine Credential (aapuser1 SSH)

**Automation Execution → Infrastructure → Credentials → +Create credential**

| Field | Value |
|-------|-------|
| Name | aapuser1 SSH (local) |
| Organization | Default |
| Credential Type | Machine |
| Username | aapuser1 |
| Password | YOUR_AAPUSER1_PASSWORD |
| Privilege Escalation Method | sudo |

Click **Save**.

### Step 5.4: Create the AWS Credential (optional)

Skip this step if you are not using AWS lab targets.

**Automation Execution → Infrastructure → Credentials → Create credential**

| Field | Value |
|-------|-------|
| Name | AWS Compliance Lab |
| Organization | Default |
| Credential Type | Amazon Web Services |
| Access Key | YOUR_AWS_ACCESS_KEY |
| Secret Key | YOUR_AWS_SECRET_KEY |

Click **Save**.

### Step 5.5: Create the quay.io Credential

Required for the EE build phase.

**Automation Execution → Infrastructure → Credentials → +Create credential**

| Field | Value |
|-------|-------|
| Name | quay.io |
| Organization | Default |
| Credential Type | Container Registry |
| Authentication URL | quay.io |
| Username | YOUR_QUAY_USERNAME |
| Password | $QUAY_PASSWORD |

Click **Save**.

### Step 5.6: Create the AAP Project

**Automation Execution → Infrastructure → Credentials → +Create credential**
| Field | Value |
|-------|-------|
| Name | Compliance Automation |
| Organization | Default |
| Source Control Type | Git |
| Source Control URL | https://github.com/ansible-automated-compliance/aac.git |
| Source Control Branch | main |
| Source Control Credential | GitHub PAT |
| Options | ✅ Update revision on launch |

Click **Save**. AAP will immediately attempt a sync — wait for it to show **Successful**.

The project checkout will be at:
```
/home/aapuser1/aap/controller/data/projects/_<ID>__compliance_automation/
```

Note the project ID number (visible in the URL when viewing the project). You will need it for the seed playbook in Phase 7.

### Step 5.7: Create the Compliance Infrastructure Inventory

**Automation Execution → Infrastructure → Inventories → +Create inventory**

| Field | Value |
|-------|-------|
| Name | Compliance Infrastructure |
| Organization | Default |

Click **Save**.

Then add the AAP server as a host:

**Automation Execution → Infrastructure → Inventories → Compliance Infrastructure → Hosts → +Create host**

| Field | Value |
|-------|-------|
| Name | YOUR_SERVER_IP |
| Variables | `ansible_connection: local` |

Click **Save**.

### Step 5.8: Register the Custom Execution Environment

The custom EE (`aac-compliance-ee:v1.1.0`) must be registered in AAP before you build it — AAP stores the reference and you will build and push the image in Phase 6.

**Administration → Infastructure → Execution Environments → Add**

| Field | Value |
|-------|-------|
| Name | AAC Compliance EE |
| Image | quay.io/YOUR_QUAY_USERNAME/aac-compliance-ee:v1.1.0 |
| Pull | Always pull the image |
| Registry credential | quay.io |

Click **Save**. Note the ID assigned (visible in the URL). This is `ee_id` referenced in the seed playbook.

### Credential ID Reference

After completing this phase, note the IDs of the credentials you created. You can find them in the URL when viewing each credential in the AAP UI. Update the seed playbook variables in Phase 7 with the correct IDs.

| Credential | Typical ID | Used In |
|-----------|-----------|---------|
| Ansible Vault | 3 | All job templates |
| aapuser1 SSH (local) | (note yours) | Template 40 (Rotate MCP Token) |
| AWS Compliance Lab | (note yours) | AWS job templates |
| quay.io | (note yours) | EE build template |

### Checkpoint

```bash
# From the AAP server, verify project sync succeeded
curl -sk -u admin:$ADMIN_PASSWORD \
  https://localhost/api/controller/v2/projects/ | \
  jq '.results[] | select(.name=="Compliance Automation") | .status'
# Should show: "successful"
```

---

## 8. Phase 6: Build Custom Execution Environment

The custom EE adds `community.postgresql`, `Terraform 1.10.5`, and other dependencies that the default AAP EE does not include.

> **IMPORTANT:** The build MUST run on an x86_64 (amd64) machine. Building on Apple Silicon (aarch64) will fail because HashiCorp's Terraform package is not available for aarch64/Fedora. Run this phase on the AAP server itself.

### Step 6.1: Log In to quay.io

```bash
podman login quay.io
# Enter your quay.io username and password when prompted
```

### Step 6.2: Log In to Red Hat Registry

```bash
podman login registry.redhat.io
# Enter your Red Hat username and password (or use offline token)
```

### Step 6.3: Review the EE Definition

The EE definition is in the repository:

```bash
cat ~/compliance/ansible/execution-environments/aac-compliance-ee/execution-environment.yml
```

Contents:
```yaml
version: 3

images:
  base_image:
    name: quay.io/ansible/creator-ee:latest

dependencies:
  galaxy: requirements.yml
  python: requirements.txt
  ansible_core:
    package_pip: ansible-core>=2.15.0
  ansible_runner:
    package_pip: ansible-runner>=2.3.0

options:
  package_manager_path: /usr/bin/microdnf

additional_build_steps:
  append_final:
    - RUN microdnf install -y unzip && microdnf clean all
    - RUN curl -Lo /tmp/terraform.zip https://releases.hashicorp.com/terraform/1.10.5/terraform_1.10.5_linux_amd64.zip && cd /tmp && unzip terraform.zip && mv terraform /usr/local/bin/terraform && chmod +x /usr/local/bin/terraform && rm /tmp/terraform.zip
    - RUN terraform version
```

### Step 6.4: Build the EE

```bash
cd ~/compliance/ansible/execution-environments/aac-compliance-ee

# Build the EE image
ansible-builder build \
  --tag quay.io/YOUR_QUAY_USERNAME/aac-compliance-ee:v1.1.0 \
  --container-runtime podman \
  -v 3

# Verify the build succeeded
podman images | grep aac-compliance-ee
```

This takes 10-20 minutes on first run (downloads base images and collections).

### Step 6.5: Push the EE to quay.io

```bash
podman push quay.io/YOUR_QUAY_USERNAME/aac-compliance-ee:v1.1.0
```

### Step 6.6: Verify the EE in AAP

In the AAP web UI, navigate to **Administration → Execution Environments** and confirm the `AAC Compliance EE` entry shows your image path.

AAP will pull the image on first job run. You can also trigger a test pull:

```bash
podman pull quay.io/YOUR_QUAY_USERNAME/aac-compliance-ee:v1.1.0
```

### Alternative: Use the AAP Job Template

Once the seed templates are created in Phase 7, you can rebuild the EE using:
- **Template 45: AAC - Build Compliance EE**

This template runs `build_compliance_ee.yml` which handles login, build, and push automatically using vault credentials.

### Checkpoint

```bash
podman images | grep aac-compliance-ee
# Should show: quay.io/YOUR_QUAY_USERNAME/aac-compliance-ee  v1.1.0

# Verify Terraform is included
podman run --rm quay.io/YOUR_QUAY_USERNAME/aac-compliance-ee:v1.1.0 \
  terraform version
# Should show: Terraform v1.10.5
```

---

## 9. Phase 7: Bootstrap Job Templates

This phase creates all 48 AAP job templates by running the seed playbook directly on the server. This is a one-time bootstrap — after this, all further operations go through AAP job templates.

### Step 7.1: Find Your AAP Credential IDs

Before running the seed playbook, note the IDs of the resources you created in Phase 5. Find them via the AAP API:

```bash
AAP_PASS="$AAP_ADMIN_PASSWORD"

# Project ID
curl -sk -u admin:$AAP_PASS \
  https://localhost/api/controller/v2/projects/ | \
  jq '.results[] | {id, name}'

# Inventory ID
curl -sk -u admin:$AAP_PASS \
  https://localhost/api/controller/v2/inventories/ | \
  jq '.results[] | {id, name}'

# EE ID
curl -sk -u admin:$AAP_PASS \
  https://localhost/api/controller/v2/execution_environments/ | \
  jq '.results[] | {id, name}'

# Vault credential ID
curl -sk -u admin:$AAP_PASS \
  https://localhost/api/controller/v2/credentials/ | \
  jq '.results[] | {id, name, kind: .credential_type}'
```

### Step 7.2: Generate an AAP API Token

The seed playbook needs an AAP token to create job templates via the Controller API:

```bash
AAP_PASS="$AAP_ADMIN_PASSWORD"

curl -sk -X POST \
  -u admin:$AAP_PASS \
  -H "Content-Type: application/json" \
  -d '{"description": "Bootstrap token", "scope": "write"}' \
  https://localhost/api/controller/v2/tokens/ | jq .token
```

Save the token value — you will use it in the next step.

### Step 7.3: Update the Seed Playbook Variables

Edit the seed playbook to use your actual IDs:

```bash
vi ~/compliance/demos/sentinel/playbooks/seed_sentinel_demo_templates.yml
```

Update the `vars:` section near the top:

```yaml
vars:
  aap_controller_url: "https://YOUR_SERVER_IP"
  aap_token:          "{{ bootstrap_token }}"
  project_id:         YOUR_PROJECT_ID       # from Step 7.1
  inventory_id:       YOUR_INVENTORY_ID     # from Step 7.1
  ee_id:              YOUR_EE_ID            # from Step 7.1
  vault_cred_id:      YOUR_VAULT_CRED_ID    # from Step 7.1
```

### Step 7.4: Run the Seed Playbook

```bash
cd ~/compliance

ansible-playbook \
  demos/sentinel/playbooks/seed_sentinel_demo_templates.yml \
  --vault-password-file ~/.vault_pass
```

This creates all job templates in AAP. It is safe to run multiple times — it will update existing templates rather than creating duplicates.

### Step 7.5: Verify All Templates Were Created

```bash
AAP_PASS="$AAP_ADMIN_PASSWORD"

curl -sk -u admin:$AAP_PASS \
  https://localhost/api/controller/v2/job_templates/ | \
  jq '.count, [.results[] | {id, name}]'
```

Expected: 48 job templates. Key templates to verify:

| ID Range | Template Group |
|----------|----------------|
| 10-17 | CIS assessments + fact collection |
| 23-28 | AAC management (PostgreSQL, OPA, reporting) |
| 29-31 | AMI / smart meter |
| 32-36 | Sentinel demo |
| 37-43 | AMI NIST/Device/Head-End + seed + stability |
| 44-48 | EE build, Terraform enforcement |

### Step 7.6: Attach Credentials to Key Templates

Some templates need additional credentials. Do this via the AAP UI or API.

**Template 40 (AAC - Rotate MCP Token)** needs the machine credential to delegate SSH tasks:

```bash
AAP_PASS="$AAP_ADMIN_PASSWORD"
MACHINE_CRED_ID=YOUR_MACHINE_CRED_ID  # aapuser1 SSH (local)

curl -sk -X POST \
  -u admin:$AAP_PASS \
  -H "Content-Type: application/json" \
  -d "{\"id\": $MACHINE_CRED_ID}" \
  https://localhost/api/controller/v2/job_templates/40/credentials/
```

### Checkpoint

```bash
curl -sk -u admin:$ADMIN_PASSWORD \
  https://localhost/api/controller/v2/job_templates/ | jq .count
# Should show: 48 (or close to it)
```

---

## 10. Phase 8: Deploy OPA Containers

AAC uses three purpose-specific OPA containers. Each serves a different compliance domain and runs on a different port.

### Step 8.1: Create Policy Directories

```bash
sudo mkdir -p /etc/opa/security /etc/opa/compliance /etc/opa/ot
sudo chown -R aapuser1:aapuser1 /etc/opa
sudo semanage fcontext -a -t container_file_t "/etc/opa(/.*)?"
sudo restorecon -Rv /etc/opa
```

### Step 8.2: Copy Policies from Repository

```bash
PROJECT_CHECKOUT="/home/aapuser1/aap/controller/data/projects/_YOUR_PROJECT_ID__compliance_automation"

# opa-security: CIS Benchmarks, NIST, STIGs, Cloud, Network, OS
sudo rsync -av $PROJECT_CHECKOUT/policies/cis_benchmarks/ /etc/opa/security/cis_benchmarks/
sudo rsync -av $PROJECT_CHECKOUT/policies/nist/            /etc/opa/security/nist/
sudo rsync -av $PROJECT_CHECKOUT/policies/stig/            /etc/opa/security/stig/
sudo rsync -av $PROJECT_CHECKOUT/policies/server_software/ /etc/opa/security/server_software/
sudo rsync -av $PROJECT_CHECKOUT/policies/operating_systems/ /etc/opa/security/operating_systems/
sudo rsync -av $PROJECT_CHECKOUT/policies/devsecops_tools/ /etc/opa/security/devsecops_tools/
sudo rsync -av $PROJECT_CHECKOUT/policies/mobile_devices/  /etc/opa/security/mobile_devices/
sudo rsync -av $PROJECT_CHECKOUT/policies/cloud_providers/  /etc/opa/security/cloud_providers/
sudo rsync -av $PROJECT_CHECKOUT/policies/network_devices/  /etc/opa/security/network_devices/
sudo rsync -av $PROJECT_CHECKOUT/policies/ai_governance/    /etc/opa/security/ai_governance/

# opa-compliance: ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, Corporate, Sentinel
sudo rsync -av $PROJECT_CHECKOUT/policies/iso27001/  /etc/opa/compliance/iso27001/
sudo rsync -av $PROJECT_CHECKOUT/policies/soc2/      /etc/opa/compliance/soc2/
sudo rsync -av $PROJECT_CHECKOUT/policies/pci_dss/   /etc/opa/compliance/pci_dss/
sudo rsync -av $PROJECT_CHECKOUT/policies/sox/       /etc/opa/compliance/sox/
sudo rsync -av $PROJECT_CHECKOUT/policies/fisma/     /etc/opa/compliance/fisma/
sudo rsync -av $PROJECT_CHECKOUT/policies/corporate/ /etc/opa/compliance/corporate/
sudo rsync -av $PROJECT_CHECKOUT/policies/sentinel/  /etc/opa/compliance/sentinel/

# opa-ot: NERC-CIP, AI Governance, Security
sudo rsync -av $PROJECT_CHECKOUT/policies/nerc_cip/    /etc/opa/ot/nerc_cip/
sudo rsync -av $PROJECT_CHECKOUT/policies/ai_governance/ /etc/opa/ot/ai_governance/
sudo rsync -av $PROJECT_CHECKOUT/policies/security/    /etc/opa/ot/security/

# Fix SELinux contexts
sudo restorecon -Rv /etc/opa
```

### Preferred method: AAP Template 28

Once job templates are seeded (Phase 7), deploy all three OPA containers with a single click:

- **Template 28: AAC - Deploy OPA Containers** — runs `ansible/playbooks/deploy_opa_containers.yml`

This calls the `aac_opa_containers` Ansible role, which:
1. Creates `/etc/opa/{security,compliance,ot}` policy directories with SELinux contexts
2. Pulls `docker.io/openpolicyagent/opa:latest`
3. Stops/removes any existing containers and starts fresh
4. Polls each container's `/health` endpoint until healthy
5. Generates podman systemd units for on-boot startup

**Role defaults** (`ansible/roles/aac_opa_containers/defaults/main.yml`):

| Variable | Default | Override to change |
|----------|---------|-------------------|
| `aac_opa_image` | `docker.io/openpolicyagent/opa:latest` | Pin a specific OPA version |
| `aac_opa_policy_base_dir` | `/etc/opa` | Different policy directory |
| `aac_opa_generate_systemd` | `true` | Set `false` in container environments |
| `aac_opa_containers` | 3-container list | Add/remove containers |

After deployment, **policies are not yet loaded**. Run Template 27 next.

### Bootstrap fallback (no AAP yet)

Before AAP is available, use the bash script:

```bash
cd /path/to/aac
./scripts/install_opa.sh
```

The script creates the three containers with empty policy directories.
Policy loading still requires running Template 27 once AAP is available.

### Step 8.6: Verify All Three Containers Are Healthy

```bash
for port in 8181 8182 8183; do
  status=$(curl -s http://localhost:$port/health | jq -r '.status // "error"')
  echo "Port $port: $status"
done
```

Expected:
```
Port 8181: ok
Port 8182: ok
Port 8183: ok
```

### OPA Container Policy Routing Reference

| Container | Port | URL | Frameworks |
|-----------|------|-----|-----------|
| opa-security | 8181 | http://YOUR_SERVER_IP:8181 | CIS RHEL 9/8/Ubuntu/Windows, NIST, STIGs, Cloud, Network |
| opa-compliance | 8182 | http://YOUR_SERVER_IP:8182 | ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, Corporate, Sentinel |
| opa-ot | 8183 | http://YOUR_SERVER_IP:8183 | NERC-CIP (CIP-002 to CIP-015), AI Governance |

Use these URLs in the `opa_server_url` variable in your playbooks:

```yaml
# For CIS and NIST assessments:
opa_server_url: "http://YOUR_SERVER_IP:8181"

# For regulatory compliance audits:
opa_server_url: "http://YOUR_SERVER_IP:8182"

# For OT and NERC-CIP:
opa_server_url: "http://YOUR_SERVER_IP:8183"
```

### Checkpoint

```bash
curl -s http://localhost:8181/v1/policies | jq '.result | length'  # Should be > 0
curl -s http://localhost:8182/v1/policies | jq '.result | length'  # Should be > 0
curl -s http://localhost:8183/v1/policies | jq '.result | length'  # Should be > 0
```

Note: Policy counts will be low at this point. Phase 9 loads all policies via the AAP REST API.

---

## 11. Phase 9: Load OPA Policies

OPA loads policies from its mounted `/policies` directory on startup, but AAC also loads policies via the OPA REST API to give each policy an explicit name and to support the policy report (Template 25). This phase loads all 505 Rego policies across the three containers.

### Step 9.1: Run Template 27 (AAC - Load OPA Policies)

In the AAP web UI:

1. Navigate to **Resources → Templates**
2. Find **AAC - Load OPA Policies** (Template 27)
3. Click the **Launch** button
4. Wait for the job to complete (2-5 minutes)

Or via API:

```bash
curl -sk -X POST \
  -H "Authorization: Bearer $AAP_TOKEN" \
  -H "Content-Type: application/json" \
  https://localhost/api/controller/v2/job_templates/27/launch/ | jq .job
```

Monitor the job:
```bash
JOB_ID=YOUR_JOB_ID
curl -sk -H "Authorization: Bearer $AAP_TOKEN" \
  https://localhost/api/controller/v2/jobs/$JOB_ID/ | jq '{status, failed}'
```

### Step 9.2: Verify Policy Counts

After the job completes, check how many policies loaded into each container:

```bash
echo "opa-security  (8181):" $(curl -s http://localhost:8181/v1/policies | jq '.result | length') policies
echo "opa-compliance (8182):" $(curl -s http://localhost:8182/v1/policies | jq '.result | length') policies
echo "opa-ot         (8183):" $(curl -s http://localhost:8183/v1/policies | jq '.result | length') policies
```

Expected (approximate — may vary with repository updates):

| Container | Expected Policies |
|-----------|------------------|
| opa-security | ~50 |
| opa-compliance | ~34 |
| opa-ot | ~4 |

### Step 9.3: Run Template 25 (AAC - OPA Policy Report)

Verify the policy loading by running the policy report:

1. Navigate to **Resources → Templates → AAC - OPA Policy Report**
2. Click **Launch**
3. Review the output — it shows policy counts grouped by framework for each container

### Step 9.4: Test a Policy Evaluation

Verify OPA can evaluate policies by running a quick test:

```bash
# Test opa-security: query CIS RHEL 9 policy list
curl -s http://localhost:8181/v1/data/cis_rhel9 | jq 'keys'

# Test opa-compliance: query Sentinel policy
curl -s -X POST http://localhost:8182/v1/data/sentinel/ansible/result \
  -H "Content-Type: application/json" \
  -d '{"input": {"play_name": "Test", "hosts": "all", "tasks": []}}' | jq .

# Test opa-ot: query NERC-CIP
curl -s http://localhost:8183/v1/data/nerc_cip_main | jq 'keys'
```

### Reloading Policies After Updates

After pushing policy changes to GitHub and syncing the AAP project, reload policies by re-running Template 27. The playbook uses `PUT` requests to the OPA REST API, so it is idempotent — existing policies are updated, new policies are added.

### Checkpoint

```bash
# opa-security should have CIS RHEL 9 policies
curl -s http://localhost:8181/v1/policies | \
  jq '[.result[].id | select(startswith("cis_"))] | length'
# Should be > 10

# opa-compliance should have Sentinel policies
curl -s http://localhost:8182/v1/policies | \
  jq '[.result[].id | select(startswith("sentinel"))] | length'
# Should be 2
```

---

## 12. Phase 10: Deploy MCP Server

The MCP server enables Claude Code to interact with AAP directly — listing job templates, launching jobs, reading output, and more. It runs as a podman container on port 8004.

### Step 10.1: Build the MCP Server Image

The MCP server source is in the repository. Build it on the AAP server:

```bash
cd ~/compliance/services/mcp-server

# Review the source files
ls -la
# server.py, aap_client.py, requirements.txt, Containerfile

# Build the image
podman build -t aap-mcp-server:v1.0 .

# Tag for local registry (optional — if you have a local registry)
# Or push to quay.io:
podman tag aap-mcp-server:v1.0 quay.io/YOUR_QUAY_USERNAME/aap-mcp-server:v1.0
podman push quay.io/YOUR_QUAY_USERNAME/aap-mcp-server:v1.0
```

> **Note on MCP SDK version:** The requirements.txt must pin `mcp==1.25.0`. Version 1.26.0 broke the SSE session initialization protocol and causes all tool calls to fail with `MCP error -32602`. Do not upgrade past 1.25.0 unless this has been tested.

### Step 10.2: Create an AAP Token for MCP

```bash
AAP_PASS="$AAP_ADMIN_PASSWORD"

curl -sk -X POST \
  -u admin:$AAP_PASS \
  -H "Content-Type: application/json" \
  -d '{"description": "Claude Code MCP Token", "scope": "write"}' \
  https://localhost/api/controller/v2/tokens/ | jq .token
```

Save this token — you will use it in the next step and in Claude Code's configuration.

### Step 10.3: Create the MCP Environment File

```bash
sudo mkdir -p /opt/aap-mcp-server

# Write the environment file (contains the token — protect it)
sudo tee /opt/aap-mcp-server/mcp.env << EOF
# AAP MCP Server environment variables
AAP_TOKEN=$MCP_TOKEN_FROM_STEP_10_2
EOF

sudo chmod 600 /opt/aap-mcp-server/mcp.env
sudo chown aapuser1:aapuser1 /opt/aap-mcp-server/mcp.env
```

### Step 10.4: Copy the AAP OpenAPI Spec

The MCP server needs the AAP Controller OpenAPI spec to generate tools dynamically:

```bash
curl -sk -u admin:$AAP_ADMIN_PASSWORD \
  https://localhost/api/controller/v2/ \
  -o /opt/aap-mcp-server/aap-controller-api.json

# Verify it downloaded correctly
jq .info /opt/aap-mcp-server/aap-controller-api.json
```

### Step 10.5: Start the MCP Container

```bash
podman run -d \
  --name aap-mcp \
  -p 8004:8004 \
  --restart=always \
  -v /opt/aap-mcp-server:/app:rw \
  -e AAP_GATEWAY_URL=https://host.containers.internal \
  -e AAP_SERVICE_URL=https://host.containers.internal/api/controller/v2 \
  -e CONTROLLER_OPENAPI_SPEC_URL=file:///app/aap-controller-api.json \
  -e AAP_TOKEN=$MCP_TOKEN \
  -e PYTHONPATH=/app \
  -e HOST=0.0.0.0 \
  -e PORT=8004 \
  aap-mcp-server:v1.0 \
  python /app/server.py
```

> **Note:** `host.containers.internal` is how the container reaches the AAP server running on the same host. Do not use `localhost` or `127.0.0.1` inside the container — those refer to the container itself.

### Step 10.6: Verify the MCP Server is Responding

```bash
# A 404 on the root path is expected — the SSE endpoint is at /sse
curl -s -o /dev/null -w "%{http_code}" http://localhost:8004/
# Should show: 404

# The SSE endpoint should return 200 (streaming)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8004/sse
# Should show: 200
```

### Step 10.7: Enable MCP Container on Boot

```bash
podman generate systemd --name aap-mcp --files --new
sudo mv container-aap-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable container-aap-mcp
```

### Step 10.8: Configure Claude Code

On your Mac (or workstation), add the MCP server to `~/.claude.json`:

```bash
python3 << 'EOF'
import json

with open('/path/to/.claude.json', 'r') as f:
    config = json.load(f)

project_path = '/path/to/your/aac/checkout'

if 'projects' not in config:
    config['projects'] = {}
if project_path not in config['projects']:
    config['projects'][project_path] = {}
if 'mcpServers' not in config['projects'][project_path]:
    config['projects'][project_path]['mcpServers'] = {}

config['projects'][project_path]['mcpServers']['aap'] = {
    "type": "sse",
    "url": "http://YOUR_SERVER_IP:8004/sse",
    "headers": {
        "Authorization": "Bearer $MCP_TOKEN"
    }
}

with open('/path/to/.claude.json', 'w') as f:
    json.dump(config, f, indent=2)

print("Done")
EOF
```

Restart Claude Code after updating the config to establish a fresh SSE session.

### Step 10.9: Update vault_aap_local_mcp_token

Update the vault with the MCP token you created:

```bash
ansible-vault edit ~/compliance/ansible/vars/vault_secrets.yml \
  --vault-password-file ~/.vault_pass
# Set vault_aap_local_mcp_token to $MCP_TOKEN
```

### MCP Token Rotation

When the MCP token expires or becomes invalid, rotate it:

1. Create a new token via AAP API (Step 10.2)
2. Update `/opt/aap-mcp-server/mcp.env` on the server
3. Restart the container: `podman stop aap-mcp && podman start aap-mcp`
4. Update `~/.claude.json` on your workstation (Step 10.8)
5. Update the vault (Step 10.9)
6. Restart Claude Code

Or use **Template 40: AAC - Rotate MCP Token** (requires the aapuser1 machine credential to be attached).

### MCP SDK Version — Critical Note

```
mcp==1.25.0 is REQUIRED. Do not upgrade.

v1.26.0 changed the SSE session initialization protocol.
Symptom: "Received request before initialization was complete" and all tool calls return MCP error -32602.

If the container was rebuilt and picked up a newer version:
  podman exec aap-mcp pip install mcp==1.25.0 -q
  podman stop aap-mcp && podman start aap-mcp
  Restart Claude Code.
```

### Checkpoint

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8004/
# 404

podman logs aap-mcp | tail -5
# Should show server startup messages, no errors
```

---

## 13. Phase 11: Deploy Grafana

Grafana provides compliance dashboards sourcing data from the PostgreSQL compliance database. Two dashboards are included: AMI Compliance and NERC-CIP.

### Option A: Use AAP Template 31 (Recommended)

Once job templates are seeded (Phase 7), run:

1. Navigate to **Resources → Templates → AMI - Deploy Grafana Dashboard**
2. Click **Launch**
3. Wait for the job to complete

This runs `ansible/playbooks/deploy_grafana_dashboard.yml` which:
- Starts the Grafana container
- Creates the PostgreSQL datasource
- Provisions both the AMI and NERC-CIP dashboards

Skip to Step 11.4 to verify.

### Option B: Manual Deployment

If you need to deploy Grafana before job templates are available:

### Step 11.1: Start the Grafana Container

Run as `aapuser1` (rootless podman, network=host):

```bash
# Create storage volume
podman volume create grafana-storage

# Start Grafana
podman run -d \
  --name grafana \
  --network host \
  --restart=always \
  -v grafana-storage:/var/lib/grafana \
  -e GF_SECURITY_ADMIN_USER=admin \
  -e GF_SECURITY_ADMIN_PASSWORD=$GRAFANA_PASSWORD \
  -e GF_INSTALL_PLUGINS=grafana-postgresql-datasource \
  docker.io/grafana/grafana:latest
```

> **IMPORTANT:** Do not use special characters in `GF_SECURITY_ADMIN_PASSWORD`. When AAP passes this value over SSH, bash quoting can strip special characters silently, leaving the container with a different password than expected.
>
> **IMPORTANT:** Always use `grafana-storage` as the volume name. If you need to recreate the container (e.g., to change the password), you MUST delete the volume first — otherwise the old password hash blocks the new password: `podman volume rm grafana-storage`

### Step 11.2: Wait for Grafana to Start

```bash
sleep 15
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health
# Should show: 200
```

### Step 11.3: Create the PostgreSQL Datasource

```bash
curl -s -X POST http://localhost:3000/api/datasources \
  -u admin:$GRAFANA_PASSWORD \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AAC Compliance DB",
    "type": "grafana-postgresql-datasource",
    "url": "localhost:5432",
    "database": "compliance",
    "user": "postgres",
    "secureJsonData": {
      "password": "$COMPLIANCE_DB_PASSWORD"
    },
    "jsonData": {
      "sslmode": "disable",
      "postgresVersion": 1500
    }
  }'
```

Note the datasource UID from the response — you will need it if importing dashboards manually. Or use Template 31 which handles this automatically.

### Step 11.4: Verify Grafana

```bash
# Check health
curl -s http://localhost:3000/api/health | jq .

# List datasources
curl -s -u admin:$GRAFANA_PASSWORD \
  http://localhost:3000/api/datasources | jq '.[].name'
# Should show: "AAC Compliance DB"

# List dashboards
curl -s -u admin:$GRAFANA_PASSWORD \
  "http://localhost:3000/api/search?type=dash-db" | jq '.[].title'
# After Template 31 runs: "AMI Compliance Dashboard", "NERC CIP Compliance Dashboard"
```

Open in browser: `http://YOUR_SERVER_IP:3000`
- Username: admin
- Password: $GRAFANA_PASSWORD

### Step 11.5: Enable Grafana on Boot

```bash
podman generate systemd --name grafana --files --new
sudo mv container-grafana.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable container-grafana
```

### Checkpoint

```bash
curl -s http://localhost:3000/api/health | jq .database
# Should show: "ok"
```

---

## 14. Phase 12: Deploy Smart Meter Simulator

The smart meter simulator generates synthetic NERC-CIP compliance data for 10 electric, gas, and water meters. It powers the AMI (Advanced Metering Infrastructure) demo.

### Run Template 30 (Recommended)

1. Navigate to **Resources → Templates → AMI - Deploy Smart Meter Containers**
2. Click **Launch**
3. Wait for job to complete

This runs `ansible/playbooks/deploy_smart_meter_simulator.yml` which builds and starts all three simulator containers.

### Manual Deployment

If you need to deploy manually:

```bash
PROJECT_CHECKOUT="/home/aapuser1/aap/controller/data/projects/_YOUR_PROJECT_ID__compliance_automation"
cd $PROJECT_CHECKOUT

# Build the smart meter simulator image
sudo podman build -t smart-meter-sim:latest demos/rhpds/smart-meter/

# Kill any existing python3 processes on these ports
sudo fuser -k 8085/tcp 8086/tcp 8087/tcp 2>/dev/null || true

# Deploy electric meters (port 8085)
sudo podman run -d \
  --name smart-meter-electric \
  --restart=always \
  -p 8085:8085 \
  -e UTILITY_TYPE=electric \
  -e METER_COUNT=10 \
  -e PORT=8085 \
  smart-meter-sim:latest

# Deploy gas meters (port 8086)
sudo podman run -d \
  --name smart-meter-gas \
  --restart=always \
  -p 8086:8086 \
  -e UTILITY_TYPE=gas \
  -e METER_COUNT=10 \
  -e PORT=8086 \
  smart-meter-sim:latest

# Deploy water meters (port 8087)
sudo podman run -d \
  --name smart-meter-water \
  --restart=always \
  -p 8087:8087 \
  -e UTILITY_TYPE=water \
  -e METER_COUNT=10 \
  -e PORT=8087 \
  smart-meter-sim:latest
```

> **Note:** Smart meter containers run as **rootful podman** (`sudo podman`). This is intentional — they bind to specific ports and need elevated access.

### Verify Smart Meter Simulators

```bash
curl -s http://localhost:8085/api/health | jq .
curl -s http://localhost:8086/api/health | jq .
curl -s http://localhost:8087/api/health | jq .
# Each should show status: "healthy" with meter_count: 10
```

### Run the AMI Full Compliance Audit

Once simulators are running, run the full AMI audit to populate the Grafana dashboard:

1. Navigate to **Resources → Templates → AMI - Full Compliance Audit and Store**
2. Click **Launch** (Template 29)
3. Wait 3-5 minutes for all three frameworks (NIST IR 7628, Device Compliance, Head-End Security) to complete

Then open Grafana at `http://YOUR_SERVER_IP:3000/d/ami-compliance-001` to see the results.

### Checkpoint

```bash
for port in 8085 8086 8087; do
  status=$(curl -s http://localhost:$port/api/health | jq -r '.status // "error"')
  echo "Port $port: $status"
done
# Expected: healthy / healthy / healthy
```

---

## 15. Phase 13: Demo Stability & Verification

This phase runs two final templates that ensure all demo containers start on boot and verify the full stack is ready.

### Step 13.1: Run Template 39 (Demo Stability Setup)

This installs systemd units for all 8 demo containers so they survive reboots:

1. Navigate to **Resources → Templates → AAC - Demo Stability Setup**
2. Click **Launch**
3. Wait for completion

What it does:
- Creates `/etc/systemd/system/container-*.service` units for all containers
- Enables auto-start for: opa-security, opa-compliance, opa-ot, compliance-db, aap-mcp, grafana, smart-meter-electric, smart-meter-gas, smart-meter-water
- Runs `systemctl daemon-reload && systemctl enable` for each

### Step 13.2: Test a Reboot

```bash
sudo reboot
```

After the system comes back up, verify all services start automatically:

```bash
# Wait ~3 minutes after reboot for all containers to start
sleep 180

# Check all containers
podman ps --format "table {{.Names}}\t{{.Status}}"

# Check OPA
for port in 8181 8182 8183; do
  echo -n "OPA port $port: "
  curl -s http://localhost:$port/health | jq -r .status
done

# Check PostgreSQL
podman exec compliance-db psql -U postgres -c "SELECT 1" > /dev/null && echo "PostgreSQL: OK"

# Check MCP
curl -s -o /dev/null -w "MCP server: %{http_code}\n" http://localhost:8004/

# Check Grafana
curl -s -o /dev/null -w "Grafana: %{http_code}\n" http://localhost:3000/api/health

# Check smart meters
for port in 8085 8086 8087; do
  echo -n "Smart meter port $port: "
  curl -s http://localhost:$port/api/health | jq -r '.status // "error"'
done
```

### Step 13.3: Run Template 38 (Sentinel Demo Preflight)

This is the GO/NO-GO check for the complete environment. It tests all 9 required services and fails with a clear error if anything is not ready.

1. Navigate to **Resources → Templates → Sentinel Demo - Pre-flight Check**
2. Click **Launch**
3. Review the output

The preflight check verifies:
- OPA security (port 8181) — health + Sentinel policy loaded
- OPA compliance (port 8182) — health + Sentinel policy loaded
- OPA OT (port 8183) — health + NERC-CIP policy loaded
- PostgreSQL — reachable and compliance schema present
- MCP server (port 8004) — responding
- Grafana (port 3000) — health endpoint OK
- Smart meter simulators (8085-8087) — all healthy
- AAP project sync — Compliance Automation project is current

A **successful** preflight job means the environment is fully operational.

### Step 13.4: Run a CIS Assessment (First Real Compliance Check)

Verify end-to-end assessment against the AAP server itself:

1. Navigate to **Resources → Templates → CIS RHEL 9 Assessment** (Template 10)
2. Click **Launch**
3. Wait for completion

The job will:
1. Collect 338 CIS RHEL 9 facts from the AAP server
2. Send facts to OPA at port 8181 for evaluation
3. Store results to PostgreSQL
4. Print a compliance summary

After the job completes, check Grafana for the new data:
`http://YOUR_SERVER_IP:3000/d/aac-compliance-001`

### Full Service Status Reference

After a successful installation, all of the following should be running and healthy:

| Service | Check Command | Expected |
|---------|--------------|---------|
| AAP Gateway | `curl -sk https://localhost/api/gateway/v1/ping/` | `{"status":"ok"}` |
| AAP Controller | `curl -sk -u admin:$AAP_ADMIN_PASSWORD https://localhost/api/controller/v2/ping/` | version string |
| OPA Security | `curl -s http://localhost:8181/health` | `{"status":"ok"}` |
| OPA Compliance | `curl -s http://localhost:8182/health` | `{"status":"ok"}` |
| OPA OT | `curl -s http://localhost:8183/health` | `{"status":"ok"}` |
| PostgreSQL | `podman exec compliance-db psql -U postgres -c "SELECT 1"` | `1` |
| MCP Server | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8004/` | `404` |
| Grafana | `curl -s http://localhost:3000/api/health \| jq .database` | `"ok"` |
| Smart Meter Electric | `curl -s http://localhost:8085/api/health \| jq .status` | `"healthy"` |
| Smart Meter Gas | `curl -s http://localhost:8086/api/health \| jq .status` | `"healthy"` |
| Smart Meter Water | `curl -s http://localhost:8087/api/health \| jq .status` | `"healthy"` |

---

## 16. Troubleshooting

### OPA Container Not Starting

```bash
# Check logs
podman logs opa-security
podman logs opa-compliance
podman logs opa-ot

# Common issue: SELinux blocking volume mount
# Fix: relabel the policy directories
sudo chcon -R -t container_file_t /etc/opa

# Restart containers
podman restart opa-security opa-compliance opa-ot

# Verify ports are bound
ss -tlnp | grep -E '818[123]'
```

### Policy Evaluation Returns Empty Result

```bash
# Symptom: curl returns {} or {"result": null}
# Cause: policy not loaded, or wrong container queried

# Check which policies are loaded
curl -s http://localhost:8181/v1/policies | jq '[.result[].id]'

# Re-run Template 27 to reload all policies
curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" \
  https://localhost/api/controller/v2/job_templates/27/launch/ -d '{}'
```

### PostgreSQL Connection Refused

```bash
# Check container is running
podman ps | grep compliance-db

# Check port is bound
ss -tlnp | grep 5432

# Check logs
podman logs compliance-db

# Common issue: data directory permissions
ls -la /opt/postgresql/data
# Should be owned by aapuser1

# Restart
podman restart compliance-db
```

### MCP Server Returning Error -32602

This means the SSE session initialization failed. This is almost always the MCP SDK version:

```bash
# Check the installed version
podman exec aap-mcp pip show mcp | grep Version

# Downgrade if needed
podman exec aap-mcp pip install mcp==1.25.0 -q
podman stop aap-mcp && podman start aap-mcp

# Then restart Claude Code — the broken handshake is cached per session
```

### MCP Token Expired (401 Errors)

```bash
# Generate new token
curl -sk -X POST \
  -u admin:$AAP_ADMIN_PASSWORD \
  -H "Content-Type: application/json" \
  -d '{"description": "Claude Code MCP Token", "scope": "write"}' \
  https://localhost/api/controller/v2/tokens/ | jq .token

# Update mcp.env
sudo tee /opt/aap-mcp-server/mcp.env << EOF
AAP_TOKEN=NEW_TOKEN_HERE
EOF

# Restart container
podman stop aap-mcp && podman rm aap-mcp
# Re-run the podman run command from Phase 10, Step 10.5 with new token

# Update ~/.claude.json on your workstation
# Restart Claude Code
```

### AAP Project Sync Fails

```bash
# Check the project sync status
curl -sk -u admin:$AAP_ADMIN_PASSWORD \
  https://localhost/api/controller/v2/projects/ | \
  jq '.results[] | select(.name=="Compliance Automation") | {status, last_updated}'

# Common causes:
# 1. GitHub PAT expired — regenerate and update the credential in AAP UI
# 2. Network issue — curl https://github.com from the server
# 3. Repository URL changed — check in Resources → Projects

# Trigger manual sync
PROJECT_ID=11  # Replace with your project ID
curl -sk -X POST \
  -u admin:$AAP_ADMIN_PASSWORD \
  https://localhost/api/controller/v2/projects/$PROJECT_ID/update/ -d '{}'
```

### Grafana Has No Data

```bash
# Check the default time range — dashboards default to 7 days
# Click the time picker in Grafana and extend to 30d or All

# Check that the compliance_results table has data
podman exec compliance-db psql -U postgres -d compliance \
  -c "SELECT policy_name, COUNT(*), MAX(evaluation_timestamp) FROM compliance_results GROUP BY policy_name ORDER BY 3 DESC;"

# If empty, run an assessment:
# Template 10 (CIS RHEL 9), Template 29 (AMI audit), or Template 26 (NERC-CIP report)
```

### Grafana Cannot Connect to PostgreSQL

```bash
# Test datasource from Grafana UI:
# Configuration → Data Sources → AAC Compliance DB → Save & Test

# Or check from command line:
podman exec compliance-db psql -U postgres -d compliance \
  -c "SELECT 1"
# If this works but Grafana fails, it's a password or network issue

# Common fix: recreate datasource with correct password via Template 31
```

### Container Fails to Start After Reboot

```bash
# Check systemd service status
sudo systemctl status container-opa-security
sudo journalctl -u container-opa-security -n 50

# Common issue: podman socket not ready when systemd tries to start
# Fix: add After=network-online.target to the unit file
sudo systemctl edit container-opa-security
# Add: [Unit]
#      After=network-online.target

sudo systemctl daemon-reload
sudo systemctl restart container-opa-security
```

### AAP Admin Password Lost

The installer inventory file contains the admin password:

```bash
cat ~/ansible-automation-platform-containerized-setup-bundle-2.6-*-x86_64/inventory | grep admin_password
```

### EE Build Fails

```bash
# Common issue 1: Not logged into registries
podman login registry.redhat.io
podman login quay.io

# Common issue 2: Building on aarch64 (won't work — Terraform is amd64 only)
uname -m
# Must show: x86_64

# Common issue 3: microdnf can't find packages
# Check that the Red Hat repo is available inside the build context
ansible-builder build --tag test:latest --container-runtime podman -v 3 2>&1 | tail -30
```

---

## 17. Quick Reference

### Installation Order Summary

```
1. OS Preparation      — RHEL 9, packages, firewall, SELinux, podman
2. Install AAP 2.6     — containerized bundle installer
3. Clone Repo + Vault  — GitHub clone, vault_secrets.yml
4. Deploy PostgreSQL   — compliance-db container, schema
5. Configure AAP       — credentials, project, inventory, EE registration
6. Build Custom EE     — ansible-builder on amd64, push to quay.io
7. Bootstrap Templates — seed playbook → 48 job templates
8. Deploy OPA          — Template 28 (three containers)
9. Load Policies       — Template 27 (510 Rego policy files)
10. Deploy MCP Server  — aap-mcp container, Claude Code config
11. Deploy Grafana     — Template 31 (dashboards)
12. Deploy Smart Meter — Template 30 (NERC-CIP demo data)
13. Stability + Verify — Template 39, Template 38 (GO/NO-GO)
```

### Service Ports

| Port | Service | Container |
|------|---------|-----------|
| 443 | AAP Web UI / API | systemd-managed |
| 3000 | Grafana | grafana |
| 5432 | PostgreSQL | compliance-db |
| 8004 | MCP Server | aap-mcp |
| 8085 | Smart Meter Electric | smart-meter-electric |
| 8086 | Smart Meter Gas | smart-meter-gas |
| 8087 | Smart Meter Water | smart-meter-water |
| 8181 | OPA Security | opa-security |
| 8182 | OPA Compliance | opa-compliance |
| 8183 | OPA OT / NERC-CIP | opa-ot |

### Key AAP Job Templates

| ID | Name | When to Run |
|----|------|-------------|
| 12 | CIS RHEL 9 Compliance Assessment | CIS compliance check |
| 114 | AAC - Initialize PostgreSQL Database | First time / schema reset |
| 25 | AAC - OPA Policy Report | Verify policy load counts |
| 26 | AAC - NERC CIP Compliance Report | NERC-CIP assessment |
| 27 | AAC - Load OPA Policies | After repo sync / policy changes |
| 28 | AAC - Deploy OPA Containers | New install / container recreation |
| 29 | AMI - Full Compliance Audit and Store | Populate AMI dashboard |
| 30 | AMI - Deploy Smart Meter Containers | New install / container recreation |
| 31 | AMI - Deploy Grafana Dashboard | New install / dashboard update |
| 38 | Sentinel Demo - Pre-flight Check | Before running demo |
| 39 | AAC - Demo Stability Setup | After new install / reboot config |
| 40 | AAC - Rotate MCP Token | When MCP token expires |
| 45 | AAC - Build Compliance EE | When EE needs rebuild |

### OPA Endpoint Reference

| Framework | OPA Container | Endpoint |
|-----------|--------------|---------|
| CIS RHEL 9 | opa-security (8181) | POST /v1/data/cis_rhel9/compliance_assessment |
| CIS RHEL 9 Extended Hardening | opa-security (8181) | GET /v1/data/cis_rhel9/extended_hardening_summary |
| CIS RHEL 9 Storage Encryption | opa-security (8181) | POST /v1/data/cis_rhel9/storage_encryption/compliance_report |
| CIS RHEL 9 Certificates | opa-security (8181) | POST /v1/data/cis_rhel9/certificate_validation/compliance_report |
| CIS RHEL 9 Authorized Keys (EDA) | opa-security (8181) | POST /v1/data/cis_rhel9/authorized_keys/compliance_report |
| NIST 800-53 | opa-security (8181) | POST /v1/data/nist/sp_800_53 |
| ISO 27001 | opa-compliance (8182) | POST /v1/data/iso27001 |
| Sentinel Ansible | opa-compliance (8182) | POST /v1/data/sentinel/ansible/result |
| Sentinel Terraform | opa-compliance (8182) | POST /v1/data/sentinel/terraform/result |
| NERC-CIP Main | opa-ot (8183) | POST /v1/data/nerc_cip_main |
| CIP-015 INSM | opa-ot (8183) | POST /v1/data/nerc_cip_cip015/cip_015_compliance_report |
| AI Governance | opa-security (8181) | POST /v1/data/ai_governance/mcp |
| MCP Governance | opa-security (8181) | POST /v1/data/ai_governance/mcp/response |

### Vault Variable Reference

```bash
# View all vault variables
ansible-vault view ~/compliance/ansible/vars/vault_secrets.yml \
  --vault-password-file ~/.vault_pass

# Edit vault
ansible-vault edit ~/compliance/ansible/vars/vault_secrets.yml \
  --vault-password-file ~/.vault_pass
```

| Variable | Purpose |
|----------|---------|
| `compliance_db_password` | PostgreSQL postgres superuser |
| `compliance_reader_password` | Grafana datasource user |
| `aws_access_key` | AWS API access |
| `aws_secret_key` | AWS API secret |
| `vault_windows_admin_password` | Windows target admin |
| `vault_redhat_username` | Red Hat login |
| `vault_redhat_offline_token` | Red Hat API token |
| `vault_github_pat` | GitHub project sync |
| `vault_aap_local_mcp_token` | MCP Bearer token |
| `vault_aapuser1_password` | SSH for EE build |
| `vault_quay_username` | quay.io login |
| `vault_quay_password` | quay.io password |
| `grafana_admin_password` | Grafana web UI |

### Common Verification Commands

```bash
# All services in one shot
echo "=== AAP ===" && curl -sk https://localhost/api/gateway/v1/ping/ | jq .status
echo "=== OPA ===" && for p in 8181 8182 8183; do echo -n "  :$p "; curl -s http://localhost:$p/health | jq -r .status; done
echo "=== PG  ===" && podman exec compliance-db psql -U postgres -c "SELECT 1" 2>&1 | tail -1
echo "=== MCP ===" && curl -s -o /dev/null -w "  HTTP %{http_code}\n" http://localhost:8004/
echo "=== GRF ===" && curl -s http://localhost:3000/api/health | jq .database
echo "=== AMI ===" && for p in 8085 8086 8087; do echo -n "  :$p "; curl -s http://localhost:$p/api/health | jq -r '.status // "error"'; done
```

### Repository Structure (Key Paths)

```
compliance/
├── ansible/
│   ├── playbooks/          # All AAP job template playbooks
│   ├── vars/
│   │   └── vault_secrets.yml  # Encrypted credentials
│   └── roles/              # Fact collection roles
├── policies/               # 505 Rego policy files (git submodule)
│   ├── cis_benchmarks/     # CIS (134 files)
│   ├── nerc_cip/           # NERC-CIP
│   ├── iso27001/           # ISO 27001
│   ├── soc2/               # SOC 2
│   ├── sentinel/           # Sentinel enforcement
│   └── ai_governance/      # MCP + AI governance
├── demos/
│   └── sentinel/           # Sentinel demo scripts
├── ansible/execution-environments/  # EE definitions: aac-compliance-ee + aac-policy-tools-ee
├── examples/               # Sample assessment data
└── grafana/
    └── dashboards/         # Dashboard JSON files
```

---

**Document Version:** 3.1
**Last Updated:** March 27, 2026
**CIS RHEL 9 Coverage:** 338/338 (100%) ✅ + 3 extended hardening modules (STIG/NIST)
**Total OPA Policies:** 510 Rego policy files (587 including tests)
**AAP Job Templates:** 48
**Environments Supported:** Local (bare metal / VM) + RHPDS OpenShift
