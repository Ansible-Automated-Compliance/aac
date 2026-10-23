# AAC EDA Rulebooks

Event-Driven Ansible configuration for Ansible Automated Compliance.
All rulebooks live in `extensions/eda/rulebooks/` and are referenced by EDA
activations via the **AAC Compliance** EDA project (synced from this repo).

---

## Live environment (<aac-host>)

### EDA Project

| Field | Value |
|-------|-------|
| Name | AAC Compliance |
| URL | `https://github.com/ansible-automated-compliance/aac` |
| Branch | main |
| Credential | GitHub PAT (Sentinel Demo) |
| Import state | completed |

### Active Activations

| ID | Name | Rulebook | Port | Status |
|----|------|----------|------|--------|
| 13 | Golden Image Enforcement | `extensions/eda/rulebooks/golden_image_enforcement.yml` | 5004 | running |
| 14 | Sentinel GitHub Webhook | `extensions/eda/rulebooks/sentinel_github_webhook.yml` | 5003 | running |
| 12 | Webhook Compliance Triggers | `extensions/eda/rulebooks/compliance_webhook_events.yml` | 5000 | running |

All activations use:
- **Decision Environment:** Default Decision Environment (`registry.redhat.io/ansible-automation-platform-26/de-supported-rhel9:latest`)
- **Credential:** AAP Controller Token (Sentinel Demo) — oauth_token on `https://<aac-host>:8443`
- **Restart policy:** always

### Decision Environments

| ID | Name | Image |
|----|------|-------|
| 1 | Default Decision Environment | `registry.redhat.io/ansible-automation-platform-26/de-supported-rhel9:latest` |
| 2 | Hub Default Decision Environment | `<aac-host>/de-supported-rhel9:latest` |

### EDA Credentials

| ID | Name | Type | Notes |
|----|------|------|-------|
| 5 | AAP Controller Token (Sentinel Demo) | Red Hat Ansible Automation Platform | oauth_token (old-style PAT) — required by ansible-rulebook 1.1.7 |
| 2 | Decision Environment Container Registry | Container Registry | registry.redhat.io pull secret |
| 3 | Hub Default Decision Environment Container Registry | Container Registry | <aac-host> pull secret |
| 4 | GitHub PAT (Sentinel Demo) | Source Control | repo sync credential |

> **Note:** ansible-rulebook 1.1.7 (shipped with AAP 2.6) requires old-style PAT tokens.
> OAuth2 tokens are not supported. Create via: AAP Gateway → Settings → Users → Tokens → Add.

---

## Webhook port map

| Port | Activation | Triggered by |
|------|-----------|-------------|
| 5000 | Webhook Compliance Triggers | CI/CD pipelines, SIEM, external scanners |
| 5001 | AMI Events | Smart meter / AMI event stream |
| 5002 | AI Governance Enforcement | AI model registry push events |
| 5003 | Sentinel GitHub Webhook | GitHub push events (real or simulated) |
| 5004 | Golden Image Enforcement | `IntroduceDrift` playbook POST after modifying files |

---

## Rulebook inventory

| Rulebook | Purpose | Triggers |
|----------|---------|---------|
| `golden_image_enforcement.yml` | Drift webhook → `AAC_GoldenImage_Enforcement` workflow | POST to :5004 |
| `golden_image_enforcement_webhook.yml` | Alternate golden image webhook handler | POST to :5004 |
| `golden_image_demo.yml` | Demo-specific golden image rules | Demo controller |
| `sentinel_github_webhook.yml` | GitHub push → Sentinel Ansible/Terraform deny | GitHub webhook to :5003 |
| `aac_comply_webhook.yml` | Sentinel comply routing (Ansible vs Terraform) | POST to :5003 |
| `compliance_webhook_events.yml` | General compliance event routing | POST to :5000 |
| `compliance_drift_detection.yml` | Filesystem drift detection (inotify) | File change events |
| `compliance_scheduled_drift.yml` | Periodic drift check schedule | Timer |
| `compliance_system_events.yml` | System-level compliance events | Syslog / journald |
| `compliance_oracle_events.yml` | Oracle DB compliance events | Oracle log stream |
| `ami_events.yml` | AMI / smart meter event stream | POST to :5001 |
| `ai_governance_enforcement.yml` | AI model governance enforcement | POST to :5002 |
| `authorized_keys_drift.yml` | SSH authorized_keys change detection (primary EDA drift trigger) | inotify on ~/.ssh/ |
| `nerc_cip_events.yml` | NERC-CIP continuous 30-min check on `critical_infrastructure` group | Timer |

---

## Config as Code

Declarative definitions in `ansible/config_as_code/rhpds/`:

| File | Declares |
|------|---------|
| `eda_projects.yml` | AAC Compliance EDA project |
| `eda_decision_environments.yml` | Decision environment image + pull policy |
| `eda_credentials.yml` | AAP controller credential for launching templates |
| `eda_rulebook_activations.yml` | 3 activations: Golden Image, Sentinel, Compliance Webhook |

Apply with:
```bash
ansible-playbook ansible/config_as_code/rhpds/rhpds_bootstrap.yml \
  -e "controller_hostname=<aac-host>" \
  -e "controller_password=<aap-admin-password>" \
  -e "aac_demo_host_ip=<aac-host>" \
  --tags eda_projects,eda_decision_environments,eda_credentials,eda_rulebook_activations
```

---

## After repo changes (rulebook updates)

EDA does **not** automatically reload running activations when the repo is pushed.

After pushing rulebook changes:
1. Sync the EDA project: EDA UI → Projects → AAC Compliance → Sync
2. **Restart** each affected activation: EDA UI → Rulebook Activations → Restart

> Sync alone does not update running content. The activation must be restarted
> after sync to pick up the new rulebook version.

---

## Troubleshooting

**Activation stuck in "starting"**
- Check credential uses old-style PAT (oauth_token), not OAuth2
- Ensure activation is in "Default" organization
- Check DE image is pullable: `podman pull registry.redhat.io/ansible-automation-platform-26/de-supported-rhel9:latest`

**Webhook not firing**
- Verify port is open: `curl -X POST http://<aac-host>:<port>/endpoint -d '{}'`
- Check activation logs: EDA UI → Activations → name → History → Instance logs
- Verify firewall: `sudo firewall-cmd --list-ports | grep <port>`

**Golden Image enforcement not triggering**
- Local EDA (<aac-host>) watches `/opt/golden-image/` via inotify — verify the path exists
- RHPDS EDA cannot watch EC2 filesystem — `drift_trigger: manual` bypasses EDA on RHPDS
- Check activation 13 is running: `curl -sk -H "Authorization: Bearer <token>" https://<aac-host>/api/eda/v1/activations/13/`
