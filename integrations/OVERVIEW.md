# AAP Customer Integrations — Reference Overview

**Drafted:** 2026-06-01
**Version:** v1.2

## Revision history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-06-01 | Initial AAP-first overview covering 7 integrations (BigPanda, xMatters, Terraform Enterprise, HashiCorp Vault Enterprise, Kubernetes CAPI, Metal3 / Ironic, AWS SSM). AAC framed as secondary. |
| v1.1 | 2026-06-02 | Patterns.md: fixed dead refs (`aac_portal_feed.yml` → `compliance_scheduled_drift.yml`; `containers/aac-portal-bridge/` → `ansible/roles/aac_portal_bridge/`) and tightened OPA security wording per Copilot review on PR #211. |
| v1.2 | 2026-06-02 | **BigPanda**: certified `bigpanda.incident` collection added in Automation Hub — replaces hand-rolled `uri` integration; cited Pete Cruz's note that the collection also ships an EDA event-source plugin, so the BigPanda integration is **bidirectional** (push outbound + EDA inbound). Added "verify certified-collection status at engagement kickoff" banner pointing at the Red Hat Certified Content catalog. Updated `_common/certified_collections.md` accordingly. |

---

A tour of seven enterprise integrations for **Ansible Automation
Platform (AAP)**. For each one: what the system is, how AAP wires into
it for general automation, a concrete code sample, and a customer
scenario. Each integration also shows how Ansible Automated Compliance
(AAC) can build on the same integration for compliance use cases —
that's a secondary topic the customer can adopt later, after the AAP
foundation is in place.

**Who this is for:** customers getting started with AAP and scoping
which integrations to land first. AAC is mentioned for completeness;
nothing in AAC is required to start using these AAP integrations.

For deeper per-integration write-ups (architecture diagrams, full
integration steps, customer-engagement checklists), see each
integration's folder under `integrations/<slug>/`.

> **Verify certified-collection status at engagement kickoff.**
> The authoritative list of Red Hat–certified Ansible content lives at
> <https://access.redhat.com/articles/ansible-automation-platform-certified-content>
> (Automation Hub catalog: <https://console.redhat.com/ansible/automation-hub>).
> Partner content lands incrementally — what's listed as "no certified
> collection today" in a per-integration write-up may have one by the
> time you scope a customer. Always re-check both URLs before
> finalizing the engagement plan and the EE `requirements.yml`.

---

## Table of contents

1. [Integration patterns at a glance](#integration-patterns-at-a-glance)
2. [BigPanda — alert aggregation](#bigpanda)
3. [xMatters — on-call routing](#xmatters)
4. [Terraform Enterprise — IaC for cloud](#terraform-enterprise)
5. [HashiCorp Vault Enterprise — centralized secrets](#hashicorp-vault-enterprise)
6. [Kubernetes Cluster API (CAPI) — cluster provisioning](#kubernetes-cluster-api-capi)
7. [Metal3 / Ironic — bare-metal provisioning](#metal3--ironic)
8. [AWS SSM — EC2 management](#aws-ssm)
9. [Sequencing recommendation](#sequencing-recommendation)
10. [Appendix — certified collections referenced](#appendix--certified-collections-referenced)

---

## Integration patterns at a glance

Every AAP integration fits one of three architectural patterns:

| Pattern | What it means | Where it lives in AAP |
|---|---|---|
| **1. Event-driven** | External system emits an event (webhook / file change / message); EDA rulebook fires an AAP workflow | `ansible.eda` rulebooks + EDA Decision Environments |
| **2. Push from AAP** | AAP playbook calls an external API to inform / trigger the external system | Job templates running `uri` module or vendor-specific Ansible collection |
| **3. Pull from AAP** | External system reads from AAP's automation state; OR AAP reads from an external state store at runtime | Custom credentials, lookup plugins (e.g. Vault lookup), Postgres reads |

The 7 integrations mapped to their primary pattern:

| Integration | Primary AAP pattern | Notes |
|---|---|---|
| BigPanda | Push from AAP | AAP posts alerts on job state changes |
| xMatters | Hybrid (push + inbound) | AAP pages on call; xMatters callbacks trigger remediation |
| Terraform Enterprise | Hybrid | AAP triggers TFE runs + receives apply-completed webhooks |
| HashiCorp Vault Enterprise | Pull at runtime | AAP reads credentials / runtime secrets from Vault |
| Kubernetes CAPI | Hybrid | AAP applies CRDs + receives cluster-state events |
| Metal3 / Ironic | Hybrid | AAP manages BareMetalHost CRDs + reads BMC state |
| AWS SSM | Push from AAP | `aws_ssm` connection plugin replaces SSH for the fleet |

---

## BigPanda

### What it is

BigPanda is an alert correlation / aggregation platform. Customers
plug it between many monitoring sources (Splunk, Datadog, Nagios,
CloudWatch, Prometheus, AAP, etc.) and downstream paging (PagerDuty,
xMatters, OpsGenie). BigPanda dedupes related alerts so one underlying
issue produces one page instead of fifty.

### How AAP uses it

AAP posts events into BigPanda whenever automation jobs / workflows
hit interesting states — job failure, SLA breach, manual approval
pending, EDA rule fired. BigPanda's correlation engine groups these
with related signals from the customer's other monitoring stack
before any page goes out.

- **Pattern:** **bidirectional** — push from AAP **and** EDA event source (BigPanda webhook → AAP workflow)
- **Auth:** API token (BigPanda integration source key + access token); webhook bearer for the EDA inbound half
- **Endpoint:** `POST https://api.bigpanda.io/data/v2/alerts` (raw API) — or use the certified collection's modules
- **Collection:** **`bigpanda.incident`** — Red Hat–certified partner collection on Automation Hub ([details](https://console.redhat.com/ansible/automation-hub/collections/published/bigpanda/incident/details), [partner docs](https://docs.bigpanda.io/en/ansible-automation-platform)). Ships **both** the outbound incident-management modules **and** an EDA event-source plugin for inbound webhooks. Prefer this over hand-rolled `uri` integrations when the customer has Automation Hub entitlement; fall back to `ansible.builtin.uri` otherwise.
- **Where to hook in:**
  - **Outbound (push):** AAP notification templates (job-template-level "on failure" hook), standalone `notify_bigpanda_violations.yml` playbook, or EDA rulebook action `run_module` calling `bigpanda.incident.incident`
  - **Inbound (EDA):** EDA rulebook using the collection's event-source plugin listening on a webhook port; BigPanda is configured to POST incident lifecycle events to that URL; rules fire the appropriate AAP workflow when the payload matches criteria (severity, source, operator-supplied tag, etc.)
- **Closed-loop scenario:** BigPanda correlates an incident → EDA receives the webhook → AAP runs remediation → outbound module updates the BigPanda incident with evidence and closes it. Same collection, both directions.

#### Sample — AAP job-failure notification to BigPanda

A reusable task an Ansible job can call to send an alert. Often wired
in as the **workflow's failure node** so any failed automation in the
customer's environment produces a BigPanda alert.

**Preferred — using the certified `bigpanda.incident` collection:**

```yaml
- name: Open BigPanda incident for failed AAP job
  bigpanda.incident.incident:
    api_token: "{{ vault_bigpanda_api_token }}"
    component: "{{ awx_host | default('aap-controller') }} :: {{ awx_job_template_name }}"
    description: >-
      AAP automation job {{ awx_job_template_name }} (id {{ awx_job_id }})
      failed against inventory {{ awx_inventory_name }}.
      See {{ awx_host }}/#/jobs/playbook/{{ awx_job_id }}/output
    severity: critical
    state: present
    primary_property: component
```

**Fallback — raw `uri` (only if Automation Hub access is unavailable):**

```yaml
- name: Notify BigPanda of failed AAP job (uri fallback)
  ansible.builtin.uri:
    url: "https://api.bigpanda.io/data/v2/alerts"
    method: POST
    headers:
      Authorization: "Bearer {{ vault_bigpanda_api_token }}"
      Content-Type: "application/json"
    body_format: json
    body:
      app_key: >-
        {{ vault_bigpanda_integration_source_key }}
      status: critical
      host: "{{ awx_host | default('aap-controller') }}"
      check: "AAP job: {{ awx_job_template_name }}"
      incident_identifier: "aap-{{ awx_job_id }}"
      description: >-
        AAP automation job {{ awx_job_template_name }} (id {{ awx_job_id }})
        failed against inventory {{ awx_inventory_name }}.
        See {{ awx_host }}/#/jobs/playbook/{{ awx_job_id }}/output
      cluster: "{{ awx_inventory_name | default('default') }}"
      timestamp: "{{ ansible_date_time.iso8601 }}"
    status_code: [200, 201]
```

#### AAP customer scenario

Customer's day-2 operations team runs ~200 AAP job templates a week
across patching, backup, user provisioning, and on-prem firewall
config. When one of these jobs fails, the customer wants the right
team paged via their existing PagerDuty rotation — but ONLY when no
other signal from Splunk or Nagios already indicates the same
underlying outage. AAP fires the failure event into BigPanda;
BigPanda's correlation rule "same host + alerts within 5min" decides
whether to forward to PagerDuty.

### AAC compliance sub-case

When the customer adopts AAC for compliance automation later, the
*same* BigPanda integration carries compliance signals: AAC posts a
compliance-violation alert (e.g. "CIS RHEL 9 5.2 violation on host X")
using the same task shape and the same BigPanda integration source.
Correlation in BigPanda groups the compliance alert with whatever
log-source alert triggered the same underlying drift.

```yaml
# AAC playbook that posts compliance violations - exact same shape
# as the AAP example, but the body fields carry compliance context:
body:
  status: critical
  host: "{{ row.hostname }}"
  check: "AAC compliance — {{ row.framework }}"
  description: "Score: {{ row.compliance_percentage }}%, {{ row.failed_controls }} failed"
  framework: "{{ row.framework }}"   # custom dimension for BigPanda
```

This is reuse, not a new integration — the customer doesn't have to
re-design anything to extend BigPanda from "AAP failures" to "AAP +
AAC alerts."

---

## xMatters

### What it is

xMatters is an on-call / paging platform similar to PagerDuty. It
manages on-call rotations, escalation policies, notification channels
(phone / SMS / push / Teams), and bidirectional callbacks — when an
engineer acknowledges or "remediates" a page from their phone,
xMatters can POST back to a webhook to trigger downstream action.

### How AAP uses it

Two halves:

1. **AAP → xMatters (paging):** AAP playbook fires a page for any
   automation outcome that needs human attention — failed deployment,
   pending approval node, capacity alert from custom code.
2. **xMatters → AAP (closed-loop):** On-call engineer clicks a button
   on the page; xMatters POSTs to AAP's EDA webhook; AAP launches a
   canned playbook (rollback, restart service, escalate to higher
   tier).

- **Pattern:** hybrid (push from AAP + event-driven inbound)
- **Auth:** xMatters Inbound Integration URL with a token (per integration source)
- **Endpoint:** customer-defined inbound integration URL on the xMatters tenant
- **Collection:** none — `ansible.builtin.uri` outbound + `ansible.eda.webhook` inbound
- **Where to hook in:**
  - AAP notification template firing on workflow approval-pending state
  - Standalone "page on-call" play within any incident-response job template
  - EDA rulebook listening for xMatters webhook callbacks on port 5006

#### Sample — outbound page from AAP

```yaml
- name: Page on-call via xMatters
  ansible.builtin.uri:
    url: "{{ vault_xmatters_inbound_integration_url }}"
    method: POST
    headers:
      Authorization: "Bearer {{ vault_xmatters_token }}"
      Content-Type: "application/json"
    body_format: json
    body:
      properties:
        severity: critical
        source: "AAP"
        host: "{{ inventory_hostname }}"
        job: "{{ awx_job_template_name }}"
        description: "{{ page_description }}"
        remediate_action: "{{ remediate_action | default('manual') }}"
      recipients:
        - targetName: "OnCall-DevOps"
    status_code: [200, 202]
```

#### Sample — inbound EDA rulebook for "Remediate" callback

```yaml
# extensions/eda/rulebooks/xmatters_remediate.yml
- name: xMatters callback → fire remediation workflow
  hosts: all
  sources:
    - ansible.eda.webhook:
        host: 0.0.0.0
        port: 5006
  rules:
    - name: "Remediate clicked — launch the named playbook"
      condition: >-
        event.payload is defined
        and event.payload.action == "remediate"
        and event.payload.remediate_action is defined
      action:
        run_job_template:
          name: "{{ event.payload.remediate_action }}"
          organization: "Default"
          job_args:
            extra_vars:
              triggered_by_xmatters: "{{ event.payload.user | default('') }}"
              hostname: "{{ event.payload.host }}"
```

#### AAP customer scenario

When AAP's nightly patching workflow fails on a host, AAP pages the
infrastructure on-call rotation via xMatters. The engineer gets a
message with two buttons: **Retry** (POSTs back to AAP, which
re-launches the patching job template against just that host) and
**Escalate** (creates a ServiceNow incident assigned to the next-tier
team). No tickets, no SSH'ing to investigate at 3am — the customer
gets minimum-viable autonomous response.

### AAC compliance sub-case

Same xMatters integration, different trigger. AAC fires a critical
page when a KEV-listed CVE is detected on a regulated host. The page
includes an **Approve remediation** button that POSTs back to AAP's
EDA webhook, which fires the AAC CVE auto-apply workflow. The customer
gets sub-minute remediation of audit-critical CVEs without standing
on-call review meetings.

---

## Terraform Enterprise

### What it is

HashiCorp Terraform Enterprise (TFE) is the self-hosted enterprise
edition of Terraform Cloud. Customers manage all cloud and on-prem
infrastructure as code: workspaces define what gets deployed, runs
are plans + applies orchestrated by the TFE server, policies (via
HashiCorp Sentinel) gate runs before apply.

### How AAP uses it

AAP and TFE are complementary, not competing:

- **TFE handles infrastructure provisioning** — declaratively
  describe and create cloud resources, manage state, gate via Sentinel
- **AAP handles configuration + day-2 ops** — once TFE provisions a
  host, AAP installs / configures / patches / monitors it

AAP integrates with TFE in three ways:

1. **AAP triggers TFE runs:** an AAP playbook calls the TFE API to
   start a workspace run (provision a new dev environment, scale a
   tier, decommission stale resources)
2. **TFE triggers AAP via webhook:** TFE's run-notification feature
   POSTs to an AAP EDA endpoint when a run completes; AAP then runs
   post-apply configuration jobs against the new resources
3. **Shared state:** AAP reads TFE workspace outputs (instance IPs,
   resource names) to drive its dynamic inventory

- **Pattern:** hybrid (push from AAP + event-driven inbound)
- **Auth:** Team token (preferred for service identity) or User token
- **Endpoint:** `https://<tfe-host>/api/v2/`
- **Collection:** `cloud.terraform` v4.0.0 (Galaxy + Automation Hub certified)
- **Where to hook in:**
  - Job template using `cloud.terraform.terraform_run` to trigger runs
  - Dynamic inventory plugin reading TFE workspace outputs
  - EDA webhook receiver listening on port 5007 for TFE notifications

#### Sample — AAP triggers a TFE run

```yaml
- name: Trigger TFE run on workspace {{ workspace_name }}
  cloud.terraform.terraform_run:
    workspace: "{{ workspace_name }}"
    organization: "{{ vault_tfe_org }}"
    token: >-
      {{ vault_tfe_team_token }}
    base_url: "https://{{ vault_tfe_host }}/api/v2/"
    message: "Triggered by AAP job {{ awx_job_template_name }} ({{ awx_job_id }})"
    auto_apply: false              # require human approval in TFE UI
  register: tfe_run

- name: Wait for TFE run to complete
  cloud.terraform.terraform_run_info:
    workspace: "{{ workspace_name }}"
    organization: "{{ vault_tfe_org }}"
    token: >-
      {{ vault_tfe_team_token }}
    run_id: "{{ tfe_run.run_id }}"
  register: tfe_run_status
  until: tfe_run_status.run.status in ['applied', 'errored', 'canceled']
  retries: 60
  delay: 15
```

#### Sample — EDA receives TFE webhook

```yaml
# extensions/eda/rulebooks/tfe_apply_complete.yml — claim port 5007
- name: TFE apply complete → run post-apply config
  hosts: all
  sources:
    - ansible.eda.webhook:
        host: 0.0.0.0
        port: 5007
  rules:
    - name: "TFE apply succeeded — run post-provision config"
      condition: >-
        event.payload.notification_configuration.events is defined
        and "run:completed" in event.payload.notification_configuration.events
        and event.payload.run.status == "applied"
      action:
        run_workflow_template:
          name: "AAP_PostTFE_Configure"
          job_args:
            extra_vars:
              tfe_workspace: "{{ event.payload.workspace.name }}"
              tfe_run_id: "{{ event.payload.run.id }}"
```

#### AAP customer scenario

Customer's developer self-service portal lets engineers request a new
dev environment by filling a form. The form fires an AAP workflow:
(1) AAP calls TFE to provision the AWS infrastructure for the
environment, (2) waits for TFE to complete, (3) configures the EC2s
with the customer's standard config (CIS-hardened user, sudo policy,
monitoring agent), (4) registers the environment in ServiceNow CMDB.
TFE owns the infrastructure layer; AAP owns the human-facing workflow
and everything above the OS install.

### AAC compliance sub-case

AAC's Rego policies (in `policies/enforcement/terraform/`) validate
Terraform plan JSON against compliance frameworks (FedRAMP, NERC-CIP)
that Sentinel doesn't cover out of the box. The integration adds a
pre-apply hook in TFE that calls out to AAC for policy validation
before any apply. Same TFE API, additional gating layer.

---

## HashiCorp Vault Enterprise

### What it is

HashiCorp Vault Enterprise (HVE) is a centralized secrets-management
platform. Customers store credentials, API tokens, certificates, and
encryption keys in Vault instead of in config files / git / sticky
notes. Enterprise edition adds namespaces (multi-tenancy), performance
replication (multi-DC), audit-log streaming, HSM support.

### How AAP uses it

Two distinct surfaces:

1. **AAP Credential Plugin (UI-only, no playbook code):** AAP itself
   reads its Machine / Cloud / Source Control credentials from Vault
   at the moment a job launches. Configured via Settings → Credentials.
   This is the path the customer already has working for AWX.
2. **Playbook-runtime secret lookups:** inside a playbook, a `lookup`
   call resolves a value from Vault at task-execution time. Used when
   a playbook needs more secrets than the small set AAP wires in via
   the credential plugin (e.g. per-environment API keys, certificates
   for `community.crypto.openssl_certificate`).

- **Pattern:** pull from external system (AAP reads at runtime)
- **Auth methods:** AppRole (recommended for service identity), JWT/OIDC (when AAP runs in OCP), Token (dev only)
- **Endpoint:** customer's Vault cluster URL (e.g. `https://vault.acme.com:8200`)
- **Collection:** `community.hashi_vault` v7.1.0 (Galaxy + Automation Hub certified) — for the playbook-runtime path
- **Where to hook in:**
  - Customer-side: AAP Settings → Credentials → External Credential Source (no Ansible code)
  - Playbooks: `lookup('community.hashi_vault.vault_kv2_get', ...)` for runtime secrets

#### Sample — playbook runtime secret lookup

```yaml
- name: Use API key from Vault for an HTTP call
  ansible.builtin.uri:
    url: "https://internal-api.acme.com/v1/widgets"
    method: GET
    headers:
      X-API-Key: >-
        {{ lookup(
             'community.hashi_vault.vault_kv2_get',
             'aap/prod/internal_api_key',
             url='https://vault.acme.com:8200',
             auth_method='approle',
             role_id=lookup('env', 'VAULT_ROLE_ID'),
             secret_id=lookup('env', 'VAULT_SECRET_ID'),
             namespace='aap/prod'
           ).data.value }}
```

#### Sample — AAP Credential Plugin setup (UI shape, no playbook code)

```
AAP UI → Settings → Credentials → Create
  Credential Type: Machine
  Name: Linux SSH (prod)
  Username: ansible-svc
  Password / SSH Key: → click "External Secret"
    Credential Type: HashiCorp Vault Secret Lookup
    Path: kv/data/aap/prod/ssh/ansible-svc
    Field: private_key
```

After this, the credential's "Password / SSH Key" field is resolved
from Vault every time a job using this credential launches. AAP never
stores the plaintext.

#### AAP customer scenario

Customer's policy: no plaintext secrets in any tool. Their AWX (the
predecessor to AAP) already has the Vault credential plugin set up.
Migrating to AAP 2.6 preserves the same Vault credential bindings —
nothing changes from the credential-management perspective. New AAP
playbooks just use `community.hashi_vault.vault_kv2_get` lookups for
any secret AAP doesn't natively manage as a credential.

### AAC compliance sub-case

AAC's playbooks currently rely on a plaintext `vault_secrets.yml`
file (intentionally not ansible-vault-encrypted, per the AAC repo's
README). For the customer's production deployment, AAC playbooks
adopt the same Vault-lookup pattern AAP already uses — the
compliance DB password, ServiceNow service account, and AAC's other
runtime secrets all resolve from Vault at job-launch time.

---

## Kubernetes Cluster API (CAPI)

### What it is

Kubernetes Cluster API (CAPI) is a CNCF project that provides
declarative APIs for cluster lifecycle. Operators apply YAML to a
"management cluster"; CAPI controllers reconcile those manifests into
actual K8s clusters across cloud providers (CAPA for AWS / EKS, CAPZ
for Azure / AKS, CAPG for GCP / GKE) and bare metal (Metal3).

### How AAP uses it

Customers typically run a GitOps tool (ArgoCD or Flux) to apply CAPI
manifests, but AAP fills the gaps GitOps doesn't:

- **Ad-hoc / event-driven cluster provisioning** — when a developer
  request comes through ServiceNow or a Slack form, AAP applies the
  matching `Cluster` CRD via `kubernetes.core.k8s` and waits for
  `Ready`
- **Cluster decommission workflows** — multi-step process (drain
  workloads, snapshot state, delete cluster, archive logs); AAP
  orchestrates the sequence
- **Post-provision configuration** — once CAPI reports `Ready`, AAP
  runs the customer's standard "first day" config (deploy operators,
  apply ConfigMaps, run a smoke test workload)

- **Pattern:** hybrid (push CRDs + event-driven cluster events + pull/read state)
- **Auth:** kubeconfig for the management cluster
- **Endpoint:** management cluster's K8s API
- **Collection:** `kubernetes.core` v6.4.0 (Galaxy + Automation Hub certified)

#### Sample — AAP applies a CAPI Cluster CRD and waits

```yaml
- name: Apply Cluster CRD to management cluster
  kubernetes.core.k8s:
    state: present
    kubeconfig: "{{ mgmt_cluster_kubeconfig }}"
    definition:
      apiVersion: cluster.x-k8s.io/v1beta1
      kind: Cluster
      metadata:
        name: "{{ cluster_name }}"
        namespace: "{{ cluster_namespace }}"
      spec:
        infrastructureRef:
          apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
          kind: AWSCluster
          name: "{{ cluster_name }}-infra"
        controlPlaneRef:
          apiVersion: controlplane.cluster.x-k8s.io/v1beta1
          kind: KubeadmControlPlane
          name: "{{ cluster_name }}-control-plane"

- name: Wait for Cluster.status.phase=Provisioned
  kubernetes.core.k8s_info:
    kubeconfig: "{{ mgmt_cluster_kubeconfig }}"
    api_version: cluster.x-k8s.io/v1beta1
    kind: Cluster
    name: "{{ cluster_name }}"
    namespace: "{{ cluster_namespace }}"
  register: cluster_info
  until: cluster_info.resources[0].status.phase == 'Provisioned'
  retries: 60
  delay: 15
```

#### AAP customer scenario

Customer's platform team owns the management cluster and the CAPI
control loop. Application teams self-serve cluster requests through a
ServiceNow catalog item that fires an AAP workflow. AAP applies the
`Cluster` CRD, waits for CAPI to provision, extracts the workload
cluster's kubeconfig, deploys the customer's standard operator set,
and hands the kubeconfig to the requesting team via a Vault-stored
secret. Total automation, no platform-team manual work per request.

### AAC compliance sub-case

After AAP provisions a cluster, AAC runs CIS Kubernetes Benchmark +
the customer's regulatory framework (FedRAMP / NIST 800-204) against
it before users get access. Same `kubernetes.core` collection, same
kubeconfig handoff — the assessment is just additional steps in the
AAP workflow.

---

## Metal3 / Ironic

### What it is

Metal3 is the CNCF project that brings declarative bare-metal
provisioning to Kubernetes. Operators define `BareMetalHost` and
`Provisioning` CRDs; Metal3 controllers talk to OpenStack Ironic
(containerized as part of Metal3) which handles actual hardware
control via BMC protocols (Redfish, IPMI). Metal3 is the standard
CAPI infrastructure provider for bare-metal clusters and powers
OpenShift bare-metal IPI installations.

### How AAP uses it

For customers running on-prem bare-metal fleets, AAP integrates
with Metal3 to:

- **Provision bare-metal hosts** — apply `BareMetalHost` CRDs from
  AAP playbooks, monitor state transitions through to `Provisioned`
- **Read hardware inventory** — query BMHs and their associated
  `HostFirmwareSettings` CRDs to populate AAP's dynamic inventory
- **Bulk operations** — power-cycle, re-image, or firmware-update
  fleets through a single AAP job rather than per-host BMC CLI

- **Pattern:** hybrid (push CRDs + read host state + invoke BMC APIs)
- **Auth:** kubeconfig for the management cluster + BMC credentials (stored as K8s Secrets)
- **Collection:** `kubernetes.core` (CRDs) + optionally `openstack.cloud` (direct Ironic API)
- **Where to hook in:**
  - Job templates applying CAPI + Metal3 manifests for new clusters
  - Inventory plugin reading BMH CRDs
  - Playbooks doing Redfish calls for hardware-level operations

#### Sample — AAP reads BareMetalHost inventory + queries BMC

```yaml
- name: List all BareMetalHosts in the metal3-system namespace
  kubernetes.core.k8s_info:
    kubeconfig: "{{ mgmt_cluster_kubeconfig }}"
    api_version: metal3.io/v1alpha1
    kind: BareMetalHost
    namespace: metal3-system
  register: bmh_list

- name: Add BMHs to AAP inventory at runtime
  ansible.builtin.add_host:
    name: "{{ bmh.metadata.name }}"
    groups: bare_metal
    bmc_address: "{{ bmh.spec.bmc.address }}"
    bmc_secret_name: "{{ bmh.spec.bmc.credentialsName }}"
    serial_number: "{{ bmh.status.hardware.systemVendor.serialNumber }}"
    state: "{{ bmh.status.provisioning.state }}"
  loop: "{{ bmh_list.resources }}"
  loop_control:
    loop_var: bmh
    label: "{{ bmh.metadata.name }}"
```

#### AAP customer scenario

Customer operates 200 bare-metal hosts across two datacenters for an
on-prem OpenShift platform. Provisioning, decommissioning, and
firmware updates happen via Metal3 from a management OCP cluster.
AAP runs the day-2 workflows: when a host's RAID controller starts
reporting warnings (signal from Prometheus → BigPanda → AAP),
AAP queries the BMH CRD for the host's BMC address, calls Redfish
to schedule a firmware update, and creates a ServiceNow change
ticket for the platform team to approve.

### AAC compliance sub-case

NERC-CIP CIP-010 (configuration management) requires evidence that
every host's BIOS settings and firmware versions match the documented
baseline. AAC runs the same BMH-read + Redfish-query pattern AAP uses,
plus an OPA policy check on each result. Output is a compliance row
in the AAC database for each host, daily.

---

## AWS SSM

### What it is

AWS Systems Manager (SSM) is AWS's all-purpose EC2 management
platform. Key components for AAP: Session Manager (SSH replacement
without inbound ports), RunCommand (execute commands on many EC2s
at once), Patch Manager (patch baselines + scheduled patching),
Parameter Store (config + secrets), State Manager (drift detection
for AWS-native config).

### How AAP uses it

For customers whose EC2 fleet is SSM-only (no inbound SSH from the
corporate network — common in regulated environments), AAP can run
playbooks against those instances using the `aws_ssm` connection
plugin instead of SSH. The playbooks themselves don't change;
only the inventory's connection plugin does.

Beyond connectivity, AAP can also call SSM RunCommand directly
(`amazon.aws.ssm_send_command`) when fleet-scale execution matters
more than per-host playbook semantics — e.g. "execute this script
on 500 hosts; just tell me the count of successes."

- **Pattern:** push from AAP — fleet-scale alternative to SSH transport
- **Auth:** AWS IAM role with `ssm:SendCommand` + `ssm:GetCommandInvocation` + `ssm:DescribeInstanceInformation`
- **Endpoint:** AWS SSM service in each target region
- **Collection:** `amazon.aws` v11.3.0 (Galaxy + Automation Hub certified; AAP EE typically has v8.0+). Modules include `amazon.aws.ssm_send_command`, `amazon.aws.ssm_inventory`, `amazon.aws.ssm_parameter`, and the `aws_ssm` connection plugin.
- **Where to hook in:**
  - Inventory plugin `amazon.aws.aws_ec2` with `compose: ansible_connection: aws_ssm` to switch transport per-host
  - Job templates calling `amazon.aws.ssm_send_command` for fleet-wide commands
  - Lookups reading from `amazon.aws.ssm_parameter` (Parameter Store)

#### Sample — switch existing playbook from SSH to SSM transport

Just change the inventory; the playbook is unchanged:

```yaml
# ansible/inventory/aws_ssm.yml
plugin: amazon.aws.aws_ec2
regions:
  - us-east-1
filters:
  tag:Managed: "true"
hostnames:
  - tag:Name
compose:
  ansible_connection:               "aws_ssm"
  ansible_aws_ssm_bucket_name:      "{{ vault_aws_ssm_bucket }}"
  ansible_aws_ssm_region:           "us-east-1"
  ansible_aws_ssm_instance_id:      instance_id
```

```bash
ansible-playbook ansible/playbooks/patch_baseline.yml \
    -i ansible/inventory/aws_ssm.yml
```

#### Sample — AAP issues a fleet-wide RunCommand

```yaml
- name: Push `sudo dnf -y update kernel` to a tagged fleet
  amazon.aws.ssm_send_command:
    region: "{{ aws_region }}"
    instance_ids: "{{ ec2_target_ids }}"
    document_name: "AWS-RunShellScript"
    parameters:
      commands:
        - "sudo dnf upgrade -y kernel"
        - "sudo systemctl reboot"
    timeout: 600
  register: ssm_apply
```

#### AAP customer scenario

Customer's cloud team disabled inbound SSH on every EC2 in their prod
VPCs after an audit finding. Engineers connect via SSM Session
Manager only. AAP's existing playbooks (patching, user management,
log forwarding config) were SSH-based and started failing when the
team migrated to AAP 2.6. Swapping the inventory to use the `aws_ssm`
connection plugin makes every playbook work again; the customer's
IAM team sees AAP's activity in CloudTrail as legitimate SSM
sessions, satisfying the audit requirement that prohibited inbound
SSH.

### AAC compliance sub-case

AAC's CIS RHEL 9 / STIG assessment playbooks become drop-in
compatible with the SSM-managed fleet — same code, different
inventory. Compliance evidence collection works without SSH access
to the regulated hosts.

---

## Sequencing recommendation

Suggested order for a customer just getting started with AAP, sized
for a single-quarter rollout:

| Sprint | Integrations | Why this order |
|---|---|---|
| **Sprint 1** | HashiCorp Vault Enterprise | Foundational — every other integration's credentials lives here. Lowest-blast-radius work. Customer already has the AWX→Vault plumbing. |
| **Sprint 2** | AWS SSM | Unblocks reaching the EC2 fleet without SSH (often a hard blocker for any subsequent automation). Trivial swap once Vault holds the AWS creds. |
| **Sprint 3** | BigPanda | Routes AAP job-failure signals through the customer's existing alert pipeline. Low effort, high visibility. |
| **Sprint 4** | xMatters | After BigPanda is wired so paging is deduped properly. |
| **Sprint 5** | Terraform Enterprise | Larger lift — requires API token, workspace mapping, and a TFE-side webhook setup. |
| **Sprint 6** | Kubernetes CAPI | After TFE if the customer uses TFE → CAPI sequencing for cluster IaC. |
| **Sprint 7** | Metal3 / Ironic | Last because most bare-metal segments are also air-gapped (additional complexity), and the CAPI patterns from sprint 6 are reused. |

Adjust by what unblocks the customer's audit / business deadline. If
the auditor is asking about hardware compliance by Q3, Metal3 jumps
ahead.

**Adding AAC on top** is independent of this sequence. Once any of
these AAP integrations are working, AAC can layer compliance
playbooks on the same plumbing without re-doing the integration
work.

---

## Appendix — certified collections referenced

Versions current as of 2026-06-01. Re-check Galaxy / Automation Hub
at customer kickoff:

| Collection | Latest version (Galaxy) | Source | Used by integration(s) |
|---|---|---|---|
| `community.hashi_vault` | 7.1.0 | Galaxy + Automation Hub (certified) | HashiCorp Vault Enterprise |
| `kubernetes.core` | 6.4.0 | Galaxy + Automation Hub (certified) | Kubernetes CAPI, Metal3 / Ironic |
| `cloud.terraform` | 4.0.0 | Galaxy + Automation Hub (certified) | Terraform Enterprise |
| `amazon.aws` | 11.3.0 (EE typically 8.0+) | Galaxy + Automation Hub (certified) | AWS SSM |
| `community.aws` | 11.0.0 | Galaxy + Automation Hub (certified) | AWS SSM (older modules) |
| `openstack.cloud` | 2.5.0 | Galaxy | Metal3 / Ironic (direct Ironic API only) |
| `ansible.builtin.uri` | core | bundled | BigPanda, xMatters (no dedicated collection) |
| `ansible.eda` | 2.12.0 | Galaxy + Automation Hub (certified) | All event-driven inbound patterns |

**No Galaxy collection exists** for BigPanda or xMatters — both are
custom REST integrations using `ansible.builtin.uri`. The lack of a
dedicated collection isn't a blocker; the `uri` module is fully
supported and the per-integration write-ups document the exact API
shapes.

---

## What's NOT in this document

Three deliberate omissions so the customer can scope their first AAP
engagement without distraction:

1. **AAP install topology** — single-node vs clustered, on-prem vs
   OCP, HA / DR pairing. Those are AAP architecture decisions
   independent of which integrations land.
2. **AAC adoption sequencing** — the AAC sub-cases above are
   forward-looking. None of them are required to get value from the
   integrations in their primary AAP form.
3. **Per-customer customizations** — service account naming, custom
   field mappings, network paths. Those live in each integration's
   per-customer `notes/` folder (gitignored).
