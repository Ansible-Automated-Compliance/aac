# Install via Config as Code

Declares the entire AAC environment — credentials, job templates, workflows, EDA activations — as YAML and applies them to AAP via the `infra.aap_configuration` collection. Idempotent and pipeline-friendly.

**Time:** ~15 minutes (assumes AAP and the AAC stack are already deployed)  
**Config files:** `ansible/config_as_code/rhpds/`  
**Entry point:** `ansible/config_as_code/rhpds/rhpds_bootstrap.yml`

---

## When to use this

| Use case | This path |
|----------|-----------|
| Rebuild AAP templates after wiping a cluster | ✅ |
| Apply configuration changes across multiple clusters | ✅ |
| CI/CD pipeline that provisions AAP on every PR | ✅ |
| First-time install with no AAP running yet | ❌ Use [From Scratch](../from-scratch/README.md) |
| No `ansible-playbook` available locally | ❌ Use the [RHPDS](../rhpds/README.md) single-workflow |

---

## Prerequisites

- AAP 2.6 running (controller + EDA + gateway accessible)
- `ansible-galaxy collection install -r ansible/config_as_code/rhpds/requirements.yml`
- AAP gateway URL, gateway password, and controller password

---

## Config files

All 14 YAML files live in `ansible/config_as_code/rhpds/`:

| File | What it declares |
|------|-----------------|
| `controller_execution_environments.yml` | AAC Compliance EE (quay.io image, v1.2.0) |
| `controller_credentials.yml` | 3 credentials: GitHub PAT, Ansible Vault, AAC Demo Host (SSH) |
| `controller_projects.yml` | Compliance Automation project (this repo) |
| `controller_inventories.yml` | Compliance Infrastructure inventory |
| `controller_hosts.yml` | Inventory hosts (localhost, aap-controller-ssh) |
| `controller_templates.yml` | 54 AAC job templates with surveys, credentials, EE |
| `controller_workflows.yml` | 3 workflows: `AAC_GoldenImage_Enforcement`, `AAC_DS_FullAssessment`, `AAC_NERC_FullAudit` |
| `controller_schedules.yml` | Nightly audit schedule, NERC-CIP recurring check |
| `eda_decision_environments.yml` | EDA decision environment registration |
| `eda_credentials.yml` | EDA controller credential (old-style PAT, required by ansible-rulebook) |
| `eda_projects.yml` | EDA project (same GitHub repo) |
| `eda_rulebook_activations.yml` | 3 EDA rulebook activations (`golden_image_enforcement` :5004, `sentinel_github_webhook` :5003, `compliance_webhook_events` :5000) |
| `requirements.yml` | `infra.aap_configuration` + `awx.awx` + `ansible.eda` + `amazon.aws` + `community.postgresql` collections |
| `rhpds_bootstrap.yml` | Orchestrates all 12 config files in correct dependency order |

---

## Step 1 — Install collections

```bash
ansible-galaxy collection install \
  -r ansible/config_as_code/rhpds/requirements.yml \
  --force
```

This installs:
- `infra.aap_configuration` — declarative AAP config roles
- `awx.awx` — community AAP modules (Galaxy equivalent of `ansible.controller`)

A symlink is created automatically by `rhpds_bootstrap.yml`:
```
~/.ansible/collections/ansible_collections/ansible/controller
  → awx/awx
```

---

## Step 2 — Run the bootstrap

```bash
ansible-playbook ansible/config_as_code/rhpds/rhpds_bootstrap.yml \
  -e "rhpds_cluster=<cluster-name>" \
  -e "rhpds_gateway_password=<password>" \
  -e "rhpds_controller_password=<password>" \
  -e "aac_demo_host_ip=<demo-host-ip>"
```

For a non-OpenShift AAP, the cluster variables are not needed — use:

```bash
ansible-playbook ansible/config_as_code/rhpds/rhpds_bootstrap.yml \
  -e "controller_hostname=<aap-host>" \
  -e "controller_password=<aap-admin-password>" \
  -e "aac_demo_host_ip=<demo-host>"
```

---

## What gets created

The bootstrap dispatches to `infra.aap_configuration` roles in two role groups; every role is idempotent so the bootstrap is safe to re-run:

| Group | Dispatch role | Objects created |
|-------|--------------|----------------|
| Controller | `execution_environments` | 1 EE: AAC Compliance EE (`quay.io/rh-ee-tcoulter/aac-compliance-ee:v1.2.0`) |
| Controller | `credentials` | 3 credentials: GitHub PAT, Ansible Vault, AAC Demo Host (SSH) |
| Controller | `projects` | Compliance Automation project (synced from GitHub) |
| Controller | `inventories` | Compliance Infrastructure inventory |
| Controller | `hosts` | localhost, aap-controller-ssh |
| Controller | `job_templates` | 54 AAC job templates (Infra ×7, Comply ×11, GoldenImage ×6, AMI ×7, NERC ×5, DS ×3, etc.) |
| Controller | `workflow_job_templates` | 3 workflows: `AAC_GoldenImage_Enforcement`, `AAC_DS_FullAssessment`, `AAC_NERC_FullAudit` |
| Controller | `schedules` | Nightly OPA reload, NERC-CIP recurring, AMI audit, tech debt |
| EDA | `eda_decision_environments` | Default decision environment registration |
| EDA | `eda_credentials` | AAC Controller Credential (old-style PAT) |
| EDA | `eda_projects` | Compliance Automation EDA project |
| EDA | `eda_rulebook_activations` | 3 activations: Golden Image :5004, Sentinel GitHub :5003, Compliance Webhook :5000 |

A post-task summary prints all created object names and the recommended manual follow-ups (set demo host IP, upload SSH private key, sync project, run database seed, deploy dashboards, verify).

---

## Updating configuration

To change a template, workflow, or schedule, edit the relevant YAML file and re-run the bootstrap. The `infra.aap_configuration` roles are idempotent — unchanged objects are left alone, changed objects are updated.

```bash
# Example: add a new job template
# Edit ansible/config_as_code/rhpds/controller_templates.yml
# Then re-apply:
ansible-playbook ansible/config_as_code/rhpds/rhpds_bootstrap.yml \
  -e "controller_hostname=<aap-host>" \
  -e "controller_password=<aap-admin-password>" \
  -e "aac_demo_host_ip=<demo-host>" \
  --tags controller_job_templates
```

Available tags: `controller_execution_environments`, `controller_credentials`, `controller_projects`, `controller_inventories`, `controller_job_templates`, `controller_workflow_job_templates`, `controller_schedules`, `eda_projects`, `eda_credentials`, `eda_rulebook_activations`

---

## Troubleshooting

**`ansible.controller` module not found**
The `ansible.controller` collection on Galaxy is a stub with no actual modules. The bootstrap auto-symlinks `awx.awx` → `ansible/controller`. If this fails:
```bash
mkdir -p ~/.ansible/collections/ansible_collections/ansible
ln -sf ~/.ansible/collections/ansible_collections/awx/awx \
        ~/.ansible/collections/ansible_collections/ansible/controller
```

**EDA activation won't start — token error**
EDA credential must use an old-style PAT token (Settings → Users → Tokens → Add in AAP gateway). OAuth2 tokens are not supported by `ansible-rulebook` 1.1.7.

**"Object already exists" errors**
These are warnings, not failures — the `infra.aap_configuration` roles handle existing objects with `state: present` (update in place). If you want a clean slate, delete the objects from AAP UI first.

**Project sync fails**
Ensure the GitHub PAT credential has read access to the repo and the SCM URL in `controller_projects.yml` matches exactly.
