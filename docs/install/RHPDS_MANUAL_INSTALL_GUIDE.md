> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: SPLIT-PORTSx19, RETIRED-HOSTx9, CONTAINERS-INTERNALx1, AAP-2.5/2.6x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# RHPDS Demo Environment — Manual Installation Guide

**Version:** 1.3  
**Last Updated:** 2026-04-28  
**Purpose:** Step-by-step guide for setting up the AAC demo environment on a fresh RHPDS
OpenShift cluster with an AWS EC2 demo host. Includes expected results and validation
commands at each step.

---

## Overview

The AAC RHPDS demo environment consists of two pieces:

| Component | Location | What It Runs |
|-----------|----------|-------------|
| **AAP 2.6** | RHPDS OpenShift cluster | Job templates, workflows, EDA activations |
| **EC2 Demo Host** | AWS (us-east-1) | OPA ×3, Grafana, PostgreSQL, smart meters, demo-rhel9 container |

The EC2 host is always a RHEL 9 t3.xlarge with an **Elastic IP** so the address never
changes across stop/start cycles.

**Total install time:** ~30–45 minutes (mostly waiting on AAP jobs)

---

## Quick Validation

Once installed, validate the entire environment with a single script:

```bash
# From the repo root on your local machine:
./scripts/check_rhpds_demo.sh <EC2_IP> \
  --ssh-key ~/.ssh/rhpds-demo-host-key.pem \
  --cluster <CLUSTER_NAME>.dynamic.redhatworkshops.io \
  --gw-password <GATEWAY_PASSWORD>
```

This script checks all services, database tables, podman containers, systemd units,
linger status, and RHPDS AAP objects. See the script's `--help` for all options.

The AAP verify playbook (`AAC - Verify RHPDS Install`) runs the same checks via Ansible
and also validates golden image baselines and EDA configuration.

---

## Prerequisites Checklist

Before starting, confirm you have:

- [ ] RHPDS OCP cluster provisioned. Collect:
  - [ ] Cluster name (e.g. `cluster-abc123.dynamic.redhatworkshops.io`)
  - [ ] AAP gateway admin password
  - [ ] AAP controller admin password
- [ ] Local AAP (AAP_HOST) running with:
  - [ ] `ansible/vars/vault_secrets.yml` containing: `aws_access_key`, `aws_secret_key`, `vault_github_pat`
  - [ ] AWS Compliance Lab credential (ID 5) active
  - [ ] Compliance Automation project synced from GitHub (`ansible-automated-compliance/aac`, main branch)
- [ ] AWS IAM user with permissions:
  - [ ] `ec2:*` (instance launch, security groups, key pairs, VPC)
  - [ ] `ec2:AllocateAddress`, `ec2:AssociateAddress`, `ec2:DescribeAddresses` (Elastic IP)
- [ ] `jq` and `curl` installed locally (needed for check script)

---

## Section 1 — AWS EC2 Setup

### 1.1 Choose Region and Availability Zone

- **Region:** `us-east-1`
- **AZ:** `us-east-1a` (recommended)

> ⚠️ **Do not use `us-east-1e`** — t3.xlarge is not available there and launch will fail
> with "Your requested instance type is not supported in your requested Availability Zone."

### 1.2 Find the Latest RHEL 9 AMI

```bash
aws ec2 describe-images \
  --owners 309956199498 \
  --filters "Name=name,Values=RHEL-9*_HVM-*-x86_64-*" \
  --query 'sort_by(Images, &CreationDate)[-1].{ID:ImageId,Name:Name}' \
  --output table \
  --region us-east-1
```

> **Expected result:** A table with one row showing an AMI ID (e.g. `ami-0abcdef1234567890`)
> and a name like `RHEL-9.4.0_HVM-20240605-x86_64-82-Hourly2-GP3`.
> Note this AMI ID — you will use it in Section 1.5.

### 1.3 Create SSH Key Pair

```bash
aws ec2 create-key-pair \
  --key-name rhpds-demo-host-key \
  --query 'KeyMaterial' \
  --output text \
  --region us-east-1 > rhpds-demo-host-key.pem
chmod 600 rhpds-demo-host-key.pem
```

> **Expected result:** File `rhpds-demo-host-key.pem` is created locally, starts with
> a PEM header line, has mode `600`.

Copy the key to the AAP controller — it is needed for the SSH credential:

```bash
scp rhpds-demo-host-key.pem aapuser1@AAP_HOST:/home/aapuser1/.ssh/rhpds-demo-host-key.pem
```

> ⚠️ **If this key is lost, the EC2 instance becomes inaccessible.** There is no recovery
> without AWS console serial access. Keep a backup.

### 1.4 Create Security Group

```bash
VPC_ID=$(aws ec2 describe-vpcs \
  --filters "Name=isDefault,Values=true" \
  --query 'Vpcs[0].VpcId' --output text --region us-east-1)

SG_ID=$(aws ec2 create-security-group \
  --group-name rhpds-demo-host-sg \
  --description "RHPDS AAC demo host" \
  --vpc-id $VPC_ID \
  --region us-east-1 \
  --query 'GroupId' --output text)

# Individual ports
for PORT in 22 3000 5432 8004 8181 8182 8183; do
  aws ec2 authorize-security-group-ingress \
    --group-id $SG_ID --protocol tcp --port $PORT \
    --cidr 0.0.0.0/0 --region us-east-1
done

# EDA webhook range (5000–5004)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID --protocol tcp --port 5000-5004 \
  --cidr 0.0.0.0/0 --region us-east-1

# Smart meter simulators (8085–8087)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID --protocol tcp --port 8085-8087 \
  --cidr 0.0.0.0/0 --region us-east-1

echo "Security group: $SG_ID"
```

> **Expected result:** The `echo` prints a security group ID like `sg-0abc1234def56789a`.
> Verify with:
> ```bash
> aws ec2 describe-security-groups --group-ids $SG_ID \
>   --query 'SecurityGroups[0].IpPermissions[].{From:FromPort,To:ToPort}' \
>   --output table --region us-east-1
> ```
> You should see rows for ports 22, 3000, 5000–5004, 5432, 8004, 8085–8087, 8181, 8182, 8183.

### 1.5 Launch EC2 Instance

```bash
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id <AMI_ID_FROM_STEP_1.2> \
  --instance-type t3.xlarge \
  --key-name rhpds-demo-host-key \
  --security-group-ids $SG_ID \
  --subnet-id <SUBNET_ID_IN_us-east-1a> \
  --associate-public-ip-address \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":50,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
  --tag-specifications \
    'ResourceType=instance,Tags=[{Key=Name,Value=rhpds-demo-host},{Key=Project,Value=aac}]' \
  --region us-east-1 \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "Instance: $INSTANCE_ID"
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region us-east-1
echo "Instance is running"
```

> **Expected result:** The first `echo` prints `i-0abc...`, then after ~30–60 seconds the
> second `echo` prints "Instance is running".
> Verify:
> ```bash
> aws ec2 describe-instances --instance-ids $INSTANCE_ID \
>   --query 'Reservations[0].Instances[0].{State:State.Name,Type:InstanceType,AZ:Placement.AvailabilityZone}' \
>   --output table --region us-east-1
> ```
> Expected: `State=running`, `Type=t3.xlarge`, `AZ=us-east-1a`.

### 1.6 Allocate and Associate Elastic IP

```bash
ALLOC_ID=$(aws ec2 allocate-address \
  --domain vpc \
  --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Name,Value=rhpds-demo-host-eip},{Key=Project,Value=aac}]' \
  --region us-east-1 \
  --query 'AllocationId' --output text)

aws ec2 associate-address \
  --instance-id $INSTANCE_ID \
  --allocation-id $ALLOC_ID \
  --region us-east-1

EIP=$(aws ec2 describe-addresses \
  --allocation-ids $ALLOC_ID \
  --query 'Addresses[0].PublicIp' \
  --output text --region us-east-1)

echo "Elastic IP (permanent): $EIP"
```

> **Expected result:** The final `echo` prints a stable public IP like `54.123.45.67`.
> This IP **does not change** when the EC2 instance is stopped and started — it is associated
> with your AWS account, not the instance lifecycle.
>
> Verify the tag is set (used for auto-discovery):
> ```bash
> aws ec2 describe-addresses \
>   --filters "Name=tag:Name,Values=rhpds-demo-host-eip" \
>   --query 'Addresses[0].{IP:PublicIp,AllocationId:AllocationId,InstanceId:InstanceId}' \
>   --output table --region us-east-1
> ```
> Expected: IP shows, InstanceId matches your EC2 instance.

### 1.7 Verify SSH Access

```bash
ssh -i rhpds-demo-host-key.pem ec2-user@$EIP "echo 'SSH OK' && hostname"
```

> **Expected result:** `SSH OK` followed by the EC2 hostname (e.g. `ip-172-31-10-5.ec2.internal`).
> If connection hangs, the security group rule for port 22 may not have propagated yet — wait
> 30 seconds and retry.

---

## Section 2 — EC2 Software Install

SSH into the instance and run the following as `ec2-user` (commands that need root use `sudo`).

```bash
ssh -i rhpds-demo-host-key.pem ec2-user@$EIP
```

### 2.1 System Update and Packages

```bash
sudo dnf update -y
sudo dnf install -y podman podman-compose python3-pip python3-psycopg2 firewalld git
```

> **Expected result:** All packages install without errors. Verify:
> ```bash
> podman --version   # podman version 4.x.x
> git --version      # git version 2.x.x
> ```

### 2.2 PostgreSQL 15

```bash
# Add PostgreSQL 15 repository
sudo dnf install -y \
  https://download.postgresql.org/pub/repos/yum/reporpms/EL-9-x86_64/pgdg-redhat-repo-latest.noarch.rpm

# Disable built-in module (would conflict)
sudo dnf module disable -y postgresql

# Install
sudo dnf install -y postgresql15 postgresql15-server

# Initialize the cluster
sudo /usr/pgsql-15/bin/postgresql-15-setup initdb

# Allow remote MD5 authentication
echo "host all all 0.0.0.0/0 md5" | sudo tee -a /var/lib/pgsql/15/data/pg_hba.conf

# Listen on all interfaces
sudo sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" \
  /var/lib/pgsql/15/data/postgresql.conf

# Start and enable
sudo systemctl enable --now postgresql-15

# Create compliance user and database
sudo -u postgres psql <<EOF
CREATE USER postgres WITH SUPERUSER PASSWORD 'compliance';
CREATE DATABASE compliance OWNER postgres;
EOF
```

> **Expected result:**
> ```bash
> sudo systemctl is-active postgresql-15   # active
> sudo -u postgres psql -c '\l'            # shows "compliance" database in the list
> ```

### 2.3 Firewall

```bash
sudo systemctl enable --now firewalld

for PORT in 22 3000 5432 8004 8181 8182 8183; do
  sudo firewall-cmd --permanent --add-port=${PORT}/tcp
done
sudo firewall-cmd --permanent --add-port=5000-5004/tcp
sudo firewall-cmd --permanent --add-port=8085-8087/tcp
sudo firewall-cmd --reload
```

> **Expected result:**
> ```bash
> sudo firewall-cmd --list-ports
> # Expected output (order may vary):
> # 22/tcp 3000/tcp 5432/tcp 8004/tcp 8085-8087/tcp 8181/tcp 8182/tcp 8183/tcp 5000-5004/tcp
> ```
> All ports must be open with `--permanent` — they survive reboot. If `firewall-cmd --list-ports`
> shows empty after reboot, the permanent flag was not set; repeat and reload.

### 2.4 Bind-Mount Directories (Golden Image Demo)

The `demo-rhel9` container bind-mounts `/opt/golden-image/etc/` so the Golden Image demo
can mutate configuration files that the Check playbook reads via `podman exec`.

```bash
sudo mkdir -p /opt/golden-image/etc/selinux
sudo mkdir -p /opt/golden-image/etc/ssh
sudo mkdir -p /opt/golden-image/etc/audit
sudo mkdir -p /opt/golden-image/etc/sysctl.d
sudo mkdir -p /opt/golden-image/etc/pam.d
sudo mkdir -p /opt/golden-image/etc/security

# Seed golden state SELinux config
sudo tee /opt/golden-image/etc/selinux/config <<EOF
# This file controls the state of SELinux on the system.
SELINUX=enforcing
SELINUXTYPE=targeted
EOF

sudo chown -R aapuser1:aapuser1 /opt/golden-image
```

> **Expected result:**
> ```bash
> cat /opt/golden-image/etc/selinux/config
> # SELINUX=enforcing
> # SELINUXTYPE=targeted
>
> ls -la /opt/golden-image/etc/
> # All subdirs owned by aapuser1
> ```

### 2.5 Create `aapuser1` OS User

The AAP job templates SSH into the EC2 host as `aapuser1` (not `ec2-user`). This user must
exist with the correct SSH key and passwordless sudo before running any AAP templates that
target the EC2 host.

```bash
# Create the user
sudo useradd -m -s /bin/bash aapuser1

# Copy the SSH public key from ec2-user's key pair
# (The private key is rhpds-demo-host-key.pem — extract the public key from it)
PUB_KEY=$(ssh-keygen -y -f /home/ec2-user/.ssh/authorized_keys 2>/dev/null || \
          cat /home/ec2-user/.ssh/authorized_keys)

sudo mkdir -p /home/aapuser1/.ssh
echo "$PUB_KEY" | sudo tee /home/aapuser1/.ssh/authorized_keys
sudo chmod 700 /home/aapuser1/.ssh
sudo chmod 600 /home/aapuser1/.ssh/authorized_keys
sudo chown -R aapuser1:aapuser1 /home/aapuser1/.ssh

# Grant passwordless sudo
echo "aapuser1 ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/aapuser1
sudo chmod 440 /etc/sudoers.d/aapuser1
```

> **Expected result:**
> ```bash
> # Test SSH login from your local machine (using the same key as ec2-user):
> ssh -i rhpds-demo-host-key.pem aapuser1@<EIP> "sudo whoami"
> # root
> ```
> If `sudo whoami` returns `root` without a password prompt, `aapuser1` is correctly configured.

> ⚠️ **Critical:** The AAP SSH credential for the EC2 host (`AAC Demo Host SSH`) uses the
> `rhpds-demo-host-key.pem` private key with username `aapuser1`. If this user doesn't exist
> or the key isn't in its `authorized_keys`, every golden image job template will fail with
> `Permission denied (publickey)`.

### 2.6 Enable Systemd Linger

Without linger, user-level systemd services only start when a user logs in interactively.
This means OPA, Grafana, and `demo-rhel9` go down after an EC2 reboot and do not come back
up until someone SSHes in. Linger must be enabled for **both users**.

```bash
# aapuser1 — owns the golden-image-pod systemd unit (created by SeedWorkflow)
sudo loginctl enable-linger aapuser1

# ec2-user — owns OPA, Grafana, MCP systemd units (created by deploy playbooks)
sudo loginctl enable-linger ec2-user
```

> **Expected result:**
> ```bash
> loginctl show-user aapuser1 | grep Linger   # Linger=yes
> loginctl show-user ec2-user  | grep Linger   # Linger=yes
> ```
> If you see `Linger=no` for either user, run the command again. This is one of the most
> critical settings for production reliability — if linger is off, every EC2 stop/start
> will require manual intervention to restart containers.

---

## Section 3 — Deploy OPA + Grafana Stack

Run these AAP job templates from **local AAP (AAP_HOST)**. Pass `aac_host=<ELASTIC_IP>`
as an extra variable or survey value.

| Template | What it does |
|----------|-------------|
| `AAC_Infra_DeployOPAContainers` | Deploys opa-security :8181, opa-compliance :8182, opa-ot :8183 with systemd units |
| `AAC_Infra_DeployAllDashboards` | Deploys Grafana :3000 with all 6 compliance dashboards |
| `AAC_Infra_LoadOPAPolicies` | Pushes all Rego policies to the 3 OPA containers |

> **Expected result after all three templates complete:**
> ```bash
> # Run from your local machine:
> curl http://<EIP>:8181/health   # → {}
> curl http://<EIP>:8182/health   # → {}
> curl http://<EIP>:8183/health   # → {}
> curl http://<EIP>:3000/api/health | python3 -m json.tool
> # → {"database":"ok","version":"10.x.x","commit":"..."}
>
> # Policy count (should be 100+ per container):
> curl -s http://<EIP>:8181/v1/policies | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['result']), 'policies')"
> # → 120 policies (or similar)
> ```
>
> On the EC2 host, verify systemd units are enabled and active:
> ```bash
> export XDG_RUNTIME_DIR=/run/user/$(id -u)
> systemctl --user is-active opa-security opa-compliance opa-ot grafana
> # active
> # active
> # active
> # active
> ```

### 3.1 Grafana Datasource UID

**This is handled automatically** by `AAC_Infra_DeployAllDashboards`. The playbook creates
or updates the PostgreSQL datasource with the fixed UID `aac-compliance-db` on every run,
so all 6 dashboards find the correct datasource. No manual action needed.

> **Verify:**
> ```bash
> curl -s http://admin:$GRAFANA_PASSWORD@<EIP>:3000/api/datasources/uid/aac-compliance-db \
>   | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['uid'], d['name'])"
> # → aac-compliance-db  AAC Compliance DB
> ```
> If you get 404 here, the deploy job failed to set the UID. Re-run `AAC_Infra_DeployAllDashboards`.

---

## Section 4 — Seed Database

Run `AAC_Infra_SeedRHPDSDatabase` from **local AAP** with `rhpds_demo_host_ip=<ELASTIC_IP>`.

This job:
1. Dumps the full compliance PostgreSQL database from local AAP (AAP_HOST)
2. SCPs the dump to the EC2 host
3. Restores it — providing pre-populated compliance history, debt items, golden image data

> **Expected result:**
> ```bash
> # From local machine (requires psql) or via SSH on EC2:
> PGPASSWORD=compliance psql -h <EIP> -U postgres -d compliance -c '\dt'
> # Expected tables (7 minimum):
> #  compliance_results
> #  technical_debt_items
> #  technical_debt_summary
> #  remediation_rates
> #  golden_image_baselines
> #  helpdesk_tickets
> #  remediation_log
>
> # Row counts:
> PGPASSWORD=compliance psql -h <EIP> -U postgres -d compliance \
>   -c "SELECT table_name, (SELECT count(*) FROM information_schema.tables t2
>       WHERE t2.table_name = t.table_name LIMIT 1)
>       FROM information_schema.tables t WHERE table_schema='public'"
> ```
> At minimum: `compliance_results` ≥1 row, `remediation_rates` ≥6 rows,
> `technical_debt_items` ≥1 row, `technical_debt_summary` ≥1 row.

---

## Section 5 — Bootstrap RHPDS AAP

Bootstrap is a single `ansible-playbook` command run from your local machine (the one that
has this repo checked out and Python/Ansible installed). It uses the config-as-code playbook
at `ansible/config_as_code/rhpds/rhpds_bootstrap.yml` which drives `infra.aap_configuration`
to declaratively configure the RHPDS AAP cluster.

### Step 5.1 — Install required collections (first time only)

```bash
ansible-galaxy collection install -r ansible/config_as_code/rhpds/requirements.yml
```

This installs `infra.aap_configuration`, `awx.awx`, and `ansible.eda`. Safe to re-run — Galaxy
skips already-installed versions.

### Step 5.2 — Run the bootstrap

```bash
ansible-playbook ansible/config_as_code/rhpds/rhpds_bootstrap.yml \
  -e "rhpds_cluster=<cluster> rhpds_gateway_password=<pw> rhpds_controller_password=<pw>" \
  --vault-password-file ~/.vault_pass
```

Replace `<cluster>` with your full cluster hostname (e.g. `cluster-abc123.dynamic.redhatworkshops.io`)
and both passwords with the RHPDS AAP admin credentials.

The playbook connects directly to the RHPDS AAP controller over HTTPS — no need to log into
RHPDS AAP first. It is fully idempotent and safe to re-run if interrupted.

This single run creates:
- Execution Environment: `quay.io/rh-ee-tcoulter/aac-compliance-ee:v1.2.0`
- Credentials: GitHub PAT, Ansible Vault, AAC Demo Host SSH
- Project: Compliance Automation (synced from GitHub, `ansible-automated-compliance/aac`)
- Inventory: Compliance Infrastructure + 2 hosts (`localhost`, `aap-controller-ssh`)
- ~54 job templates across all demo groups (Golden Image, NERC-CIP, AMI, DS, Technical Debt, Generic)
- 3 workflows (GoldenImage Enforcement, NERC/AMI Nightly Audit, Digital Sovereignty Full Assessment)
- 4 nightly schedules
- EDA project, EDA credential (old-style PAT), 3 EDA activations (ports 5004, 5003, 5000)

> **Expected runtime:** ~10–15 minutes.
>
> Spot-check in RHPDS AAP UI after completion:
> - **Templates:** Should see all 6 `AAC_GoldenImage_*` templates
> - **Workflows:** Should see `AAC_GoldenImage_Enforcement`
> - **EDA → Rulebook Activations:** `Golden Image Enforcement` should be **running** and
>   in the **Default** org
>
> **Known requirements (bootstrap handles these automatically):**
> - EDA credential uses an old-style PAT token — ansible-rulebook 1.1.7 calls
>   `/api/v2/config/` which only works with controller-style tokens, not gateway Bearer tokens
> - EDA activation is placed in the **Default** org — EDA 1.1.7 ignores org filters when
>   resolving workflow names; placing it in the wrong org causes enforcement workflow lookups
>   to fail silently

> **After bootstrap completes, run `AAC - Load OPA Policies` from RHPDS AAP.**
> This pushes all Rego policies into the three OPA containers on the EC2 host. Without this,
> every OPA call returns `{}` and compliance assessments produce no data.
>
> Verify after loading:
> ```bash
> curl -s http://<EIP>:8182/v1/policies | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['result']), 'policies in opa-compliance')"
> # Expected: 100+ policies
> ```

---

## Section 6 — Configure AAP with EC2 IP

Run `AAC_Infra_ConfigureRHPDSAAP` from RHPDS AAP with:

| Variable | Value |
|----------|-------|
| `rhpds_cluster` | same as above |
| `rhpds_gateway_password` | same as above |
| `rhpds_demo_host_ip` | Elastic IP (or leave blank — auto-discovered from EIP tag) |
| `ec2_private_key` | Full PEM contents of `rhpds-demo-host-key.pem` |

This patches all job templates that reference `aac_host` and `pg_host` with the EC2 IP,
updates the `aap-controller-ssh` inventory host's `ansible_host` variable, and stores the
SSH private key in the Machine credential.

> **Expected result:** Job completes in ~2–3 minutes.
>
> Verify one template was updated (replace `<token>` and `<ctrl_url>` with your values):
> ```bash
> curl -sk -H "Authorization: Bearer <token>" \
>   "<ctrl_url>/api/controller/v2/job_templates/?name=AAC_GoldenImage_Check" \
>   | python3 -c "
> import sys,json
> d=json.load(sys.stdin)
> vars = json.loads(d['results'][0]['extra_vars'])
> print('aac_host:', vars.get('aac_host'))
> print('pg_host: ', vars.get('pg_host'))
> "
> # Expected: both print the Elastic IP
> ```
>
> Verify inventory host:
> ```bash
> curl -sk -H "Authorization: Bearer <token>" \
>   "<ctrl_url>/api/controller/v2/hosts/?name=aap-controller-ssh" \
>   | python3 -c "
> import sys,json
> d=json.load(sys.stdin)
> vars = d['results'][0]['variables']
> print(vars)
> "
> # Expected: ansible_host=<ELASTIC_IP>
> ```

### 6.1 Create Long-Lived Token for IntroduceDrift

The `AAC_GoldenImage_IntroduceDrift` template uses `drift_trigger: manual`. On RHPDS,
EDA runs inside OpenShift pods and cannot watch files on the external EC2 host, so
IntroduceDrift calls the AAP controller API directly to launch the enforcement workflow
instead of waiting for EDA to detect file changes. This requires a long-lived write-scope
token that does not expire with the MCP session.

**Step 1 — Create the token in RHPDS AAP UI:**

1. Log in to RHPDS AAP Gateway as `admin`
2. Navigate to **Access Management → Users → admin → Tokens**
3. Click **Create Token**
4. Set **Application** to blank (personal access token)
5. Set **Scope** to **Write**
6. Copy the generated token value — it is shown only once

**Step 2 — Find the enforcement workflow ID:**

```bash
curl -sk -H "Authorization: Bearer <TOKEN>" \
  "https://aap-controller-aap.apps.<cluster>.dynamic.redhatworkshops.io/api/controller/v2/workflow_job_templates/?name=AAC_GoldenImage_Enforcement" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Workflow ID:', d['results'][0]['id'])"
# Expected: Workflow ID: <number>
```

**Step 3 — Patch both values into the IntroduceDrift template:**

```bash
# Get the current extra_vars:
CURRENT_VARS=$(curl -sk -H "Authorization: Bearer <TOKEN>" \
  "https://aap-controller-aap.apps.<cluster>.dynamic.redhatworkshops.io/api/controller/v2/job_templates/?name=AAC_GoldenImage_IntroduceDrift" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['results'][0]['extra_vars'])")

# Get the template ID:
TMPL_ID=$(curl -sk -H "Authorization: Bearer <TOKEN>" \
  "https://aap-controller-aap.apps.<cluster>.dynamic.redhatworkshops.io/api/controller/v2/job_templates/?name=AAC_GoldenImage_IntroduceDrift" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['results'][0]['id'])")

# Merge in the bearer token and workflow ID:
NEW_VARS=$(echo "$CURRENT_VARS" | python3 -c "
import sys, json
d = json.load(sys.stdin)
d['aap_bearer_token'] = '<TOKEN>'
d['aap_enforcement_wf_id'] = <WORKFLOW_ID>
print(json.dumps(d))
")

# Patch:
curl -sk -X PATCH \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  "https://aap-controller-aap.apps.<cluster>.dynamic.redhatworkshops.io/api/controller/v2/job_templates/${TMPL_ID}/" \
  -d "{\"extra_vars\": $(echo "$NEW_VARS" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")}"
```

> **Expected result:** `curl` returns the updated template JSON.
>
> Verify both values are now set:
> ```bash
> curl -sk -H "Authorization: Bearer <TOKEN>" \
>   "https://aap-controller-aap.apps.<cluster>.dynamic.redhatworkshops.io/api/controller/v2/job_templates/${TMPL_ID}/" \
>   | python3 -c "
> import sys, json
> d = json.load(sys.stdin)
> ev = json.loads(d['extra_vars'])
> bearer_val = ev.get('aap_bearer_token', '')
> status = 'SET' if bearer_val else 'MISSING'
> print('aap_bearer_token:    ', status)
> print('aap_enforcement_wf_id:', ev.get('aap_enforcement_wf_id', 'MISSING'))
> "
> # Expected:
> # aap_bearer_token:     SET
> # aap_enforcement_wf_id: <number>
> ```
>
> **Why `drift_trigger: manual`?** EDA runs inside OCP pods and has no filesystem visibility
> into the EC2 host, so webhook events from EDA file-watch rules never fire. The manual mode
> has IntroduceDrift call the AAP API directly after introducing drift. This is set
> automatically by `bootstrap_rhpds_environment.yml` — do not change it to `eda`.

---

## Section 7 — Seed the Demo Container

Run `AAC_GoldenImage_SeedWorkflow` from **RHPDS AAP**.

This single job:
1. Creates/truncates DB tables: `golden_image_baselines`, `helpdesk_tickets`, `remediation_log`
2. Writes hardened config files into `/opt/golden-image/etc/` bind-mount directories
3. Creates a **pod** called `golden-image-pod` and launches `demo-rhel9` inside it:
   - Image: `registry.access.redhat.com/ubi9/ubi` (Red Hat UBI 9 — RHEL 9-based)
   - Command: `sleep infinity` (keeps container alive for `podman exec` access)
   - Bind mounts: ssh, audit, selinux, sysctl.d, pam.d, security, aide config directories
4. Generates and enables a user-level systemd unit `pod-golden-image-pod.service` so the
   pod auto-restarts after EC2 reboot
5. Captures all bound file contents as the golden image baseline in `golden_image_baselines`

> **Expected result (check on EC2 host via SSH):**
> ```bash
> export XDG_RUNTIME_DIR=/run/user/$(id -u)
>
> # Pod is running
> podman pod ps
> # EXPECTED: golden-image-pod    Running
>
> # Container is running
> podman ps
> # EXPECTED: demo-rhel9   registry.access.redhat.com/ubi9/ubi   Up N minutes
>
> # Systemd unit is enabled (will restart on reboot)
> systemctl --user is-enabled pod-golden-image-pod.service
> # EXPECTED: enabled
>
> # Exec works and golden state is correct
> podman exec demo-rhel9 cat /etc/selinux/config
> # EXPECTED:
> # SELINUX=enforcing
> # SELINUXTYPE=targeted
>
> # DB baseline was captured
> PGPASSWORD=compliance psql -h localhost -U postgres -d compliance \
>   -c "SELECT baseline_label, is_current FROM golden_image_baselines WHERE hostname='demo-rhel9'"
> # EXPECTED: one row with is_current=t
> ```

**Why UBI 9?** `registry.access.redhat.com/ubi9/ubi` is the Red Hat Universal Base Image
built from RHEL 9 sources — it is the correct distributable container image. Full RHEL
cannot be shipped as a public container image.

---

## Section 8 — Verification

Run `AAC - Verify RHPDS Install` on **local AAP (AAP_HOST)**.

This AAP job checks 25+ items in order and prints a GO/NO-GO report:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RHPDS Install Verification — cluster-abc123...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[✅ PASS]  OPA Security (:8181)
[✅ PASS]  OPA Compliance (:8182)
[✅ PASS]  OPA OT (:8183)
[✅ PASS]  Grafana (:3000)
[✅ PASS]  aap-controller-ssh host
[✅ PASS]  template: AAC_GoldenImage_SeedWorkflow
...
[✅ PASS]  PostgreSQL connectivity
[✅ PASS]  DB table golden_image_baselines (golden image baseline)
[✅ PASS]  Golden image current baseline (demo-rhel9)
[✅ PASS]  EDA activation: Golden Image Enforcement
[✅ PASS]  EDA activation in Default org (EDA 1.1.7 requirement)
[✅ PASS]  EDA project: Compliance Automation EDA
[✅ PASS]  EDA credential: AAC Controller Credential
[✅ PASS]  IntroduceDrift fallback: aap_bearer_token + aap_enforcement_wf_id
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Result: 25 passed, 0 failed
✅ All checks passed — demo is ready to run
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Alternatively, run the bash check script directly from your laptop (see top of guide):

```bash
./scripts/check_rhpds_demo.sh <EIP> \
  --ssh-key ~/.ssh/rhpds-demo-host-key.pem \
  --cluster <CLUSTER>.dynamic.redhatworkshops.io \
  --gw-password <GW_PW>
```

---

## Section 9 — Demo Run Order (Golden Image)

Once `AAC - Verify RHPDS Install` shows all green, run the demo in this order:

### Step 1: Reset to Golden State
Run `AAC_GoldenImage_ResetDemo` — restores all bind-mount files to the known-good state.
Run before every demo to ensure a clean baseline.

> **Expected result:** Job completes in ~30 seconds. Final task shows files restored.

### Step 2: Introduce Drift
Run `AAC_GoldenImage_IntroduceDrift` with survey:
- `drift_type` = `selinux`

This sets `SELINUX=permissive` in the bind-mount SELinux config and triggers the EDA
enforcement webhook.

> **Expected result:**
> ```bash
> # On EC2 host (verify drift was introduced):
> podman exec demo-rhel9 cat /etc/selinux/config | grep SELINUX=
> # SELINUX=permissive   ← drift introduced
> ```
>
> The enforcement workflow is launched **directly via the AAP API** (`drift_trigger: manual`),
> not via the EDA webhook. You will see the workflow appear in RHPDS AAP **Jobs** within
> seconds of IntroduceDrift completing — no EDA event is required on RHPDS.
>
> (On local AAP_HOST the EDA path is used instead, because local EDA can watch the
> `/opt/golden-image/` directory directly. The two environments use different trigger paths
> but produce identical demo outcomes.)

### Step 3: Watch Enforcement
In RHPDS AAP, navigate to **Jobs** and watch the enforcement workflow run:

| Node | Template | Expected Result |
|------|----------|----------------|
| 1 | AAC_GoldenImage_Check | Finds SELinux drift, prints violation details, exits FAIL |
| 2 (on failure) | AAC_GoldenImage_Rollback | Restores `SELINUX=enforcing`, exits SUCCESS |
| 3 (always) | AAC_GoldenImage_NotifyHelpDesk | Creates helpdesk ticket in PostgreSQL, exits SUCCESS |

> **Expected result:** All 3 nodes show green. Total runtime: ~90 seconds.
>
> Verify remediation:
> ```bash
> podman exec demo-rhel9 cat /etc/selinux/config | grep SELINUX=
> # SELINUX=enforcing   ← restored to golden state
>
> # Helpdesk ticket was created:
> PGPASSWORD=compliance psql -h <EIP> -U postgres -d compliance \
>   -c "SELECT id, issue_type, severity, status FROM helpdesk_tickets ORDER BY id DESC LIMIT 1"
> # EXPECTED: a row with issue_type=selinux_drift, status=open
> ```

---

## Section 10 — After EC2 Restart

**If using an Elastic IP (recommended):** The IP is stable. After restart, all containers
should come back automatically because linger is enabled and systemd units are set to
`enabled`. Wait ~60 seconds after the instance reaches "running" state.

> ⚠️ **OPA policies must be reloaded after every EC2 restart.**
> OPA stores all Rego policies in memory — they are not persisted to disk. When the OPA
> containers restart, they start empty and return `{}` for all policy queries until policies
> are pushed back in. **Always run `AAC - Load OPA Policies` on RHPDS AAP after an EC2
> restart before running any compliance demo.**
>
> Dashboards that show "No data" after a restart are almost always caused by this — the
> assessment ran but OPA returned `{}` instead of a real result.

### 10.1 Restart Recovery Checklist

After the EC2 instance reaches "running" state (~60 seconds):

**Step 1 — Verify containers are up:**
```bash
# Quick service check (replace <EIP> with your Elastic IP):
for port in 8181 8182 8183; do
  result=$(curl -s --max-time 5 http://<EIP>:${port}/health && echo "OK" || echo "DOWN")
  echo "OPA :${port} → ${result}"
done
curl -s --max-time 5 http://<EIP>:3000/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('Grafana →', d['database'])"

# If any service is down, SSH in and check linger + systemd:
export XDG_RUNTIME_DIR=/run/user/$(id -u)
loginctl show-user ec2-user | grep Linger     # must be Linger=yes
systemctl --user status opa-security opa-compliance opa-ot grafana pod-golden-image-pod
```

If linger is `no` (e.g. after a bare-metal host migration), re-enable it:
```bash
sudo loginctl enable-linger ec2-user
# Then start all units:
systemctl --user start opa-security opa-compliance opa-ot grafana pod-golden-image-pod
```

**Step 2 — Reload OPA policies (required every restart):**

On RHPDS AAP: run `AAC - Load OPA Policies` (template 25).

```bash
# Or verify policies are loaded (should return count > 0):
curl -s http://<EIP>:8181/v1/policies | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['result']), 'policies loaded on :8181')"
curl -s http://<EIP>:8182/v1/policies | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['result']), 'policies loaded on :8182')"
curl -s http://<EIP>:8183/v1/policies | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['result']), 'policies loaded on :8183')"
# Expected: ~100+ policies per container
# If 0: run AAC - Load OPA Policies before running any demo
```

**Step 3 — Verify EDA activation is still running:**

On RHPDS AAP: EDA → Rulebook Activations → Golden Image Enforcement → confirm `status: running`.
If it shows `failed` or `error`, run `AAC - Bootstrap RHPDS Environment` again (it force-deletes
and recreates failed activations automatically).

**Step 4 — Before running any demo:**

Run `AAC_GoldenImage_ResetDemo` to restore the bind-mount files to golden state (the
`demo-rhel9` container state persists across restarts, but drift introduced in a prior
demo session is also persisted).

**If NOT using an Elastic IP:**
1. Look up the new public IP:
   ```bash
   aws ec2 describe-instances \
     --filters "Name=tag:Name,Values=rhpds-demo-host" \
     --query 'Reservations[].Instances[].PublicIpAddress' \
     --output text --region us-east-1
   ```
2. Re-run `AAC_Infra_ConfigureRHPDSAAP` with `rhpds_demo_host_ip=<NEW_IP>`
3. If Grafana datasource shows "No data", re-run `AAC_Infra_DeployAllDashboards`

---

## Section 11 — Troubleshooting

### OPA containers not responding

```bash
# Check status on EC2
ssh ec2-user@<EIP>
export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user status opa-security    # check for errors
podman ps | grep opa
podman logs opa-security | tail -20

# Restart all OPA containers:
systemctl --user restart opa-security opa-compliance opa-ot

# Or re-run from local AAP:
# Template: AAC_Infra_DeployOPAContainers
```

> **Expected state:** All three OPA units show `active (running)`. `podman ps` shows
> three `opa-*` containers with status `Up N minutes`.

### Grafana shows "No data" on dashboards

There are three causes — check in order:

**1. OPA policies not loaded (most common after a restart):**
```bash
curl -s http://<EIP>:8182/v1/policies | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['result']), 'policies')"
# If 0: run AAC - Load OPA Policies, then re-run the relevant assessment template
```

**2. Assessment template not yet run:**
The Grafana dashboards show PostgreSQL data. If an assessment has never run (or ran before
OPA policies were loaded), the database has no rows. Run the relevant assessment:
- NCSC CAF dashboard: run `AAC - CAF Demo Assessment` on RHPDS AAP
- Other dashboards: run the corresponding assessment template

**3. Grafana datasource UID randomized:**
This happens when Grafana is restarted without the deploy playbook running first.
```bash
# Verify the UID is set:
curl -s http://admin:$GRAFANA_PASSWORD@<EIP>:3000/api/datasources/uid/aac-compliance-db
# If 404: run AAC_Infra_DeployAllDashboards (it sets the fixed UID automatically)
```

### NCSC CAF 4.0 dashboard shows "No data"

Run `AAC - CAF Demo Assessment` (template 27) on RHPDS AAP. This is NOT run automatically
during provisioning — it must be triggered manually to populate the dashboard. If it fails
with `{}` from OPA, run `AAC - Load OPA Policies` first, then retry.

### EDA activation shows `project: null` or `rulebook: null` in API

This is a cosmetic OpenShift quirk — it does **not** mean the activation is broken. The EDA
API response shows null for the project and rulebook fields on OCP even when the activation is
running correctly. Confirm by checking the activation **status**:

```bash
curl -sk -H "Authorization: Bearer <TOKEN>" \
  "https://aap-aap.apps.<cluster>.dynamic.redhatworkshops.io/api/eda/v1/activations/?name=Golden+Image+Enforcement" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); a=d['results'][0]; print('status:', a['status'], '| project:', a.get('project'), '| rulebook:', a.get('rulebook_file_path'))"
# Expected: status: running | project: None | rulebook: None
# "project: None" here is normal on OCP — if status=running, activation is working
```

If `status` is `failed` or `error` (not `running`), the activation needs to be deleted and
recreated. Bootstrap handles this automatically on re-runs (force-delete if failed).

### EDA enforcement workflow not triggering

Check in order:

1. **Activation is running:**
   RHPDS AAP → EDA → Rulebook Activations → Golden Image Enforcement → status = **running**

2. **Activation is in Default org:**
   The activation must be in the "Default" organization, not a custom one. EDA 1.1.7
   ignores org filters when resolving workflow names — if the activation is in a different
   org, the enforcement workflow lookup fails silently.

3. **EDA credential has old-style token:**
   The `AAC Controller Credential` must use an old-style PAT token (controller-issued,
   not gateway Bearer). ansible-rulebook 1.1.7 hits `/api/v2/config/` which requires
   controller tokens. Gateway Bearer tokens return 401.

4. **IntroduceDrift template has fallback vars set:**
   Check that `aap_bearer_token` and `aap_enforcement_wf_id` are set (non-empty) in the
   template's extra_vars. On RHPDS, the EDA webhook is internal to OCP and not reachable
   from outside — the template falls back to direct AAP API launch when the webhook call fails.

5. **Check the EDA activation log:**
   In RHPDS AAP: EDA → Rulebook Activations → Golden Image Enforcement → History tab →
   click the most recent activation entry → view event log

### Golden Image Check fails with PostgreSQL timeout

Template `AAC_GoldenImage_Check` has wrong `pg_host`. Re-run `AAC_Infra_ConfigureRHPDSAAP`.

```bash
# Verify pg_host is set:
curl -sk -H "Authorization: Bearer <token>" \
  "<ctrl_url>/api/controller/v2/job_templates/?name=AAC_GoldenImage_Check" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.loads(d['results'][0]['extra_vars']).get('pg_host'))"
# Expected: <ELASTIC_IP>
```

### demo-rhel9 container missing or stopped

```bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)
podman pod ps                         # check golden-image-pod state
podman pod start golden-image-pod     # if Stopped or Exited
podman ps | grep demo-rhel9           # verify container is Up
```

If the pod itself is missing, re-run `AAC_GoldenImage_SeedWorkflow` on RHPDS AAP.

### "Failed to connect to bus" when checking systemd over SSH

This is the `XDG_RUNTIME_DIR` issue. User systemd requires the D-Bus socket at
`/run/user/<UID>/bus`. Over non-interactive SSH, this variable is not set automatically.
Always prefix systemd user commands with:

```bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user ...
```

The `check_rhpds_demo.sh` script handles this automatically for all SSH commands.

---

## Quick Reference: Key Addresses

| Service | URL Pattern |
|---------|------------|
| AAP Gateway | `https://aap-aap.apps.<cluster>.dynamic.redhatworkshops.io` |
| AAP Controller | `https://aap-controller-aap.apps.<cluster>.dynamic.redhatworkshops.io` |
| EDA | `https://aap-eda-aap.apps.<cluster>.dynamic.redhatworkshops.io` |
| OPA Security | `http://<EC2_IP>:8181` |
| OPA Compliance | `http://<EC2_IP>:8182` |
| OPA OT | `http://<EC2_IP>:8183` |
| Grafana | `http://<EC2_IP>:3000` (admin / $GRAFANA_PASSWORD) |
| PostgreSQL | `<EC2_IP>:5432` (postgres / compliance) |
| Smart Meters | `http://<EC2_IP>:8085` (electric), `:8086` (gas), `:8087` (water) |
| EDA Golden Image webhook (OCP-internal only) | `http://golden-image-enforcement.aap.svc.cluster.local:5004/endpoint` |

---

## Summary Checklist

Use this list to track a fresh install end-to-end:

### AWS Setup
- [ ] RHEL 9 t3.xlarge launched in `us-east-1a`
- [ ] SSH key pair created and backed up to AAP controller
- [ ] Security group open on ports: 22, 3000, 5000–5004, 5432, 8004, 8085–8087, 8181–8183
- [ ] Elastic IP allocated, tagged `rhpds-demo-host-eip`, associated with instance
- [ ] SSH access verified: `ssh ec2-user@<EIP>` returns a shell

### EC2 Host
- [ ] `postgresql-15` running and accepting connections to `compliance` database
- [ ] Firewall open on all required ports (permanent — `--permanent` flag set)
- [ ] `/opt/golden-image/etc/selinux/config` contains `SELINUX=enforcing`
- [ ] `loginctl show-user ec2-user | grep Linger` → `Linger=yes`

### Local AAP (AAP_HOST) — runs against EC2
- [ ] `AAC_Infra_DeployOPAContainers` completed → OPA :8181/:8182/:8183 respond with `{}`
- [ ] `AAC_Infra_DeployAllDashboards` completed → Grafana :3000 `database: ok`, datasource UID `aac-compliance-db` set
- [ ] `AAC_Infra_LoadOPAPolicies` completed → 100+ policies per OPA container
- [ ] `AAC_Infra_SeedRHPDSDatabase` completed → 7 tables present with row minimums

### RHPDS AAP — bootstrap and configure
- [ ] `AAC - Bootstrap RHPDS Environment` completed → 6 templates, 1 enforcement workflow, EDA activation running in Default org
- [ ] `AAC_Infra_ConfigureRHPDSAAP` completed → all templates have correct `aac_host`/`pg_host`
- [ ] `AAC_GoldenImage_SeedWorkflow` completed → `demo-rhel9` container running, golden image baseline in DB

### Final Verification
- [ ] `AAC - Verify RHPDS Install` → all green, 0 failures
- [ ] OR `./scripts/check_rhpds_demo.sh <EIP> --ssh-key ... --cluster ... --gw-password ...` → all green
- [ ] End-to-end test: ResetDemo → IntroduceDrift → Enforcement workflow → 3 nodes green
- [ ] NCSC CAF dashboard: run `AAC - CAF Demo Assessment` → `http://<EIP>:3000/d/ncsc-caf-001` shows data

### After Every EC2 Restart
- [ ] Wait ~60s for containers to start, verify OPA/Grafana respond
- [ ] Run `AAC - Load OPA Policies` on RHPDS AAP (policies are in-memory only — lost on restart)
- [ ] Check EDA activation status = `running`
- [ ] Run `AAC_GoldenImage_ResetDemo` to restore golden state before demo

---

## Appendix A — From-Scratch Install (No Local AAP)

Use this path when you do **not** have a local AAP controller at AAP_HOST.
All steps run directly from your laptop using `ansible-playbook`.

The only functional difference from the standard install is **Step 3**: instead of
seeding the database from the local controller's PostgreSQL, you initialize a fresh
schema. Pre-loaded historical trending data (6-month compliance graphs) will not be
present, but everything needed to run all demos works immediately.

---

### A.1 — One-time prerequisites

**Software required on your laptop:**

```bash
# Python 3.11+ and Ansible
pip install ansible

# Required collections
ansible-galaxy collection install \
  amazon.aws \
  community.postgresql \
  community.general \
  ansible.posix

# Config-as-code collections (for the bootstrap step)
ansible-galaxy collection install -r ansible/config_as_code/rhpds/requirements.yml
```

**Credentials — populate `ansible/vars/vault_secrets.yml`:**

| Variable | Where to get it |
|----------|----------------|
| `aws_access_key` | AWS IAM → your user → Security credentials |
| `aws_secret_key` | Same |
| `vault_github_pat` | GitHub → Settings → Developer settings → Personal access tokens |
| `compliance_db_password` | Set to any password (e.g. `compliance`) |
| `grafana_admin_password` | Set to any password (e.g. `$GRAFANA_PASSWORD`) |
| `vault_redhat_offline_token` | [access.redhat.com](https://access.redhat.com/management/api) → Generate token |
| `vault_redhat_username` | Your Red Hat account email |

**AWS IAM permissions required:**

```
ec2:RunInstances, ec2:TerminateInstances, ec2:DescribeInstances
ec2:CreateKeyPair, ec2:DeleteKeyPair, ec2:DescribeKeyPairs
ec2:CreateSecurityGroup, ec2:AuthorizeSecurityGroupIngress, ec2:DescribeSecurityGroups
ec2:AllocateAddress, ec2:AssociateAddress, ec2:DescribeAddresses
ec2:CreateTags
```

**`~/.vault_pass` file** (if your `vault_secrets.yml` is encrypted):

```bash
echo 'your-vault-password' > ~/.vault_pass
chmod 0600 ~/.vault_pass
```

If `vault_secrets.yml` is plaintext, omit `--vault-password-file` from all commands below.

---

### A.2 — Clone the repo

```bash
git clone https://github.com/ansible-automated-compliance/aac
cd compliance
```

---

### A.3 — Step 1: Provision EC2 demo host

```bash
ansible-playbook ansible/playbooks/provision_rhpds_demo_host.yml \
  --vault-password-file ~/.vault_pass
```

The playbook creates a RHEL 9 t3.xlarge in AWS (us-east-1a), allocates an Elastic IP,
installs podman + PostgreSQL 15, creates the `aapuser1` OS user, and sets up the
`/opt/golden-image/` directories.

**After it completes:**

- Note the **Elastic IP** printed in the final summary — you need it for every step below.
- The SSH private key is saved to `~/.ssh/rhpds-demo-host-key.pem` automatically.
  (The playbook falls back to local save when `host.containers.internal` is unreachable.)

> **Verify:**
> ```bash
> ssh -i ~/.ssh/rhpds-demo-host-key.pem ec2-user@<ELASTIC_IP> "hostname && podman --version"
> ```

---

### A.4 — Step 2: Deploy OPA + Grafana + MCP stack

```bash
ansible-playbook ansible/playbooks/deploy_rhpds_stack.yml \
  -e "rhpds_demo_host_ip=<ELASTIC_IP>" \
  -e "rhpds_gateway_url=https://aap-aap.apps.<CLUSTER>.dynamic.redhatworkshops.io" \
  -e "rhpds_gateway_token=PLACEHOLDER" \
  --private-key ~/.ssh/rhpds-demo-host-key.pem \
  --vault-password-file ~/.vault_pass
```

> `rhpds_gateway_token` can be `PLACEHOLDER` for now — you'll update it after bootstrap
> creates a real token. The MCP server env file is updated by a later step.

> **Verify:**
> ```bash
> curl -s http://<ELASTIC_IP>:8181/health   # {"status":"ok"}
> curl -s http://<ELASTIC_IP>:8182/health   # {"status":"ok"}
> curl -s http://<ELASTIC_IP>:8183/health   # {"status":"ok"}
> curl -s http://<ELASTIC_IP>:3000/api/health | python3 -m json.tool
> ```

---

### A.5 — Step 3: Initialize fresh database schema

> **This replaces the "Seed Database" step** that requires AAP_HOST.
> A fresh schema is created; demo data is populated in Step 8 (SeedWorkflow + CAF).

```bash
ansible-playbook ansible/playbooks/postgres_database_init.yml \
  -e "pg_host=<ELASTIC_IP>" \
  -e "aac_db_skip_container_deploy=true" \
  --vault-password-file ~/.vault_pass
```

> **Verify:**
> ```bash
> PGPASSWORD=compliance psql -h <ELASTIC_IP> -p 5433 -U postgres compliance \
>   -c "\dt"
> # Expected: compliance_results, compliance_facts, remediation_rates,
> #           technical_debt_items, technical_debt_summary, sidecar_datasets
> ```

---

### A.6 — Step 4: Load OPA policies

```bash
ansible-playbook ansible/playbooks/load_opa_policies.yml \
  -e "rhpds_demo_host_ip=<ELASTIC_IP>" \
  --vault-password-file ~/.vault_pass
```

> **Verify:**
> ```bash
> curl -s http://<ELASTIC_IP>:8182/v1/policies | \
>   python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['result']), 'policies')"
> # Expected: 100+
> ```

---

### A.7 — Step 5: Bootstrap RHPDS AAP

```bash
ansible-playbook ansible/config_as_code/rhpds/rhpds_bootstrap.yml \
  -e "rhpds_cluster=<CLUSTER>.dynamic.redhatworkshops.io" \
  -e "rhpds_gateway_password=<GW_PASSWORD>" \
  -e "rhpds_controller_password=<CTRL_PASSWORD>" \
  --vault-password-file ~/.vault_pass
```

Creates all ~54 templates, 3 workflows, 4 schedules, and 3 EDA activations on the RHPDS
AAP cluster. Runs entirely over HTTPS — no need to SSH into or log into RHPDS AAP first.

> **Verify in RHPDS AAP UI:**
> - Templates → should see all `AAC_GoldenImage_*` templates
> - Workflows → should see `AAC_GoldenImage_Enforcement`
> - EDA → Rulebook Activations → `Golden Image Enforcement` should be **running**

---

### A.8 — Step 6: Wire EC2 IP into all templates

Read the private key content for the `ec2_private_key` variable:

```bash
EC2_KEY=$(cat ~/.ssh/rhpds-demo-host-key.pem)

ansible-playbook ansible/playbooks/configure_rhpds_aap.yml \
  -e "rhpds_cluster=<CLUSTER>.dynamic.redhatworkshops.io" \
  -e "rhpds_gateway_password=<GW_PASSWORD>" \
  -e "rhpds_demo_host_ip=<ELASTIC_IP>" \
  -e "ec2_private_key=${EC2_KEY}" \
  --vault-password-file ~/.vault_pass
```

This patches `aac_host`, `pg_host`, and `opa_host` into every template that needs them,
updates the SSH credential username and key, creates a long-lived enforcement bearer token,
and wires `aap_bearer_token` + `aap_enforcement_wf_id` into `IntroduceDrift`.

---

### A.9 — Final steps on RHPDS AAP

Log into the RHPDS AAP UI and run these templates in order:

| # | Template | What it does |
|---|----------|-------------|
| 1 | `AAC_GoldenImage_SeedWorkflow` | Creates `demo-rhel9` container + captures golden image baseline |
| 2 | `AAC - CAF Demo Assessment` | Populates NCSC CAF 4.0 Grafana dashboard |
| 3 | `AAC - Verify RHPDS Install` | Runs all health checks — should be all green |

Then run the golden image demo end-to-end to confirm:

```
ResetDemo → IntroduceDrift (drift_type=selinux) → Enforcement WF
→ Check ✅ → Rollback ✅ → NotifyHelpDesk ✅
```

---

### A.10 — From-scratch summary checklist

- [ ] `vault_secrets.yml` populated with AWS, GitHub PAT, RH token, passwords
- [ ] Collections installed (`amazon.aws`, `community.postgresql`, `infra.aap_configuration`, etc.)
- [ ] RHPDS cluster provisioned — have cluster name + gateway/controller passwords
- [ ] Step 1: EC2 provisioned — Elastic IP noted, key at `~/.ssh/rhpds-demo-host-key.pem`
- [ ] Step 2: OPA ×3, Grafana, MCP deployed — all health endpoints return `{"status":"ok"}`
- [ ] Step 3: Database schema initialized — 6 tables present
- [ ] Step 4: OPA policies loaded — 100+ policies per container
- [ ] Step 5: RHPDS AAP bootstrapped — all templates and EDA activation present
- [ ] Step 6: AAP configured — EC2 IP wired into all templates, SSH credential updated
- [ ] `AAC_GoldenImage_SeedWorkflow` completed — `demo-rhel9` container running
- [ ] `AAC - CAF Demo Assessment` completed — CAF dashboard populated
- [ ] `AAC - Verify RHPDS Install` — all checks green
- [ ] Golden image demo end-to-end confirmed

---

*Version 1.3 — 2026-04-28*
