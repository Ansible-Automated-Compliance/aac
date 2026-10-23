# Certified / Notable Ansible Collections — Integration Inventory

Reference table for the collections AAC integrations reach for. Use it
to pick the right collection when starting a new integration write-up.

**Last refreshed:** 2026-06-01 (versions age — verify before pinning a customer)

---

## Source of truth

- **Galaxy** (`galaxy.ansible.com`) — community + partner-published collections, no support contract
- **Automation Hub** (`console.redhat.com/ansible/automation-hub`) — Red Hat–signed + partner-certified collections, eligible for Red Hat support

Most enterprise customers prefer Automation Hub for production
deployments. Galaxy is fine for dev / lab and for collections that
aren't yet certified.

---

## In the AAC EE today

These ship with the `aac-compliance-ee` we already build (see
`ansible/execution-environments/aac-compliance-ee/requirements.yml`):

| Collection | Version pin in EE | Used in repo for |
|---|---|---|
| `infra.aap_configuration` | `>= 2.9.0` | AAP config-as-code (templates, workflows, EDA) |
| `community.postgresql` | `>= 3.0.0` | compliance DB queries (1300+ calls in playbooks) |
| `community.general` | `>= 8.0.0` | misc — mail, json_query, dict utilities |
| `ansible.posix` | `>= 1.5.0` | filesystem ops, mounts, sysctl |
| `ansible.utils` | `>= 2.10.0` | network mask / address validation |
| `ansible.windows` | `>= 2.0.0` | Windows-target playbooks (CIS Win 2022) |
| `community.windows` | `>= 2.0.0` | Windows extras |
| `amazon.aws` | `>= 8.0.0` | AWS dynamic inventory, EC2 lifecycle |

When adding a new integration, prefer reusing what's already in the EE
before adding a new collection — fewer EE rebuilds, fewer dep
conflicts.

---

## Common-integration collections (Galaxy availability + version)

| Collection | Vendor | Latest version (Galaxy) | On Automation Hub? | Used for |
|---|---|---|---|---|
| `servicenow.itsm` | Red Hat (partner) | **2.14.0** | ✓ certified | ServiceNow incident / change / problem record management |
| `splunk.es` | Splunk (partner) | **6.0.0** | ✓ certified | Splunk Enterprise Security data inputs + correlation searches |
| `microsoft.ad` | Red Hat / Microsoft | **1.11.0** | ✓ certified | Active Directory user / computer / group object management |
| `azure.azcollection` | Microsoft | **3.19.0** | ✓ certified | Azure resource lifecycle, IaC, RBAC |
| `community.hashi_vault` | Community | **7.1.0** | ✓ certified | HashiCorp Vault read (lookup plugin + `vault_read` module) |
| `kubernetes.core` | Red Hat | **6.4.0** | ✓ certified | kubectl-equivalent for any K8s cluster (incl. CAPI, OCP, Metal3) |
| `cloud.terraform` | Red Hat (cloud team) | **4.0.0** | ✓ certified | Terraform / Terraform Cloud / Terraform Enterprise runs from AAP |
| `openstack.cloud` | OpenStack (community) | **2.5.0** | partial | Ironic bare-metal API; OpenStack-based Metal3 backend |
| `awx.awx` | Community AWX | **24.6.1** | (use `ansible.controller` instead on AH) | AWX/AAP automation modules (alternative to `ansible.controller`) |
| `ansible.eda` | Red Hat | **2.12.0** | ✓ certified | EDA rulebook activations, projects, decision-env mgmt |
| `community.aws` | Community | **11.0.0** | ✓ certified | AWS modules not in `amazon.aws` (older / community-maintained) |
| `amazon.aws` | Red Hat / Amazon | **11.3.0** | ✓ certified (EE has 8.0+) | Core AWS — EC2, S3, IAM, SSM (`amazon.aws.ssm_*`) |
| `community.general` | Community | **13.0.1** | ✓ certified (EE has 8.0+) | misc — mail, jira, slack modules; many integration-helper plugins |
| `community.postgresql` | Community | **4.2.0** | ✓ certified (EE has 3.0+) | Postgres connector — used everywhere in AAC |

---

## Vendor partner collections on Automation Hub (certified)

The Red Hat AAP Certified Content catalog
(<https://access.redhat.com/articles/ansible-automation-platform-certified-content>)
publishes partner-maintained, Red Hat–certified collections. Re-check
the catalog at the start of every customer engagement — partner
content lands incrementally.

| Vendor / Collection | Source | Used for |
|---|---|---|
| **`bigpanda.incident`** | Automation Hub ([details](https://console.redhat.com/ansible/automation-hub/collections/published/bigpanda/incident/details)) | Create / update / resolve BigPanda incidents from AAP — replaces hand-rolled `uri` POSTs to `api.bigpanda.io/data/v2/alerts` |

> If you're building an integration in this folder and the closest
> partner collection lives in Automation Hub, prefer it over a custom
> `uri` integration: the partner ships modules with documented
> parameters, idempotency, and error handling. Add the EE-include
> instructions to the per-integration README so the engagement EE
> has the collection installed and authenticated to Automation Hub.

## Collections that DON'T exist (custom integration required)

| Vendor | Status on Galaxy / Automation Hub | Path |
|---|---|---|
| **xMatters** | not currently certified — verify against the Certified Content catalog at engagement kickoff | Custom — use `uri` against xMatters Events / Inbound Integrations API |
| **Metal3 specifically** | no dedicated collection; uses `kubernetes.core` against Metal3 CRDs | Apply `BareMetalHost` / `Cluster` CRDs via `kubernetes.core.k8s` |

For these, the integration write-up should specify the API endpoints,
auth scheme, and a minimal set of `uri`-based tasks. Future Galaxy /
Automation Hub collections may land — re-check before customer
kickoff.

---

## Red Hat–supported (Automation Hub only — not on Galaxy)

These need an Automation Hub entitlement (subscription-based). Common
ones for AAC enterprise customers:

| Collection | Purpose |
|---|---|
| `ansible.controller` | Official Red Hat AAP modules (alternative to `awx.awx`) |
| `ansible.platform` | Required by `infra.aap_configuration >= 4.x` for AAP 2.6 |
| `redhat.satellite` | Satellite 6 host registration, content view, sync |
| `redhat.insights` | Red Hat Insights API, system tag management |
| `redhat.rhel_system_roles` | Curated RHEL system roles bundle |
| `redhat.openshift` | OCP cluster operations (alternative to `kubernetes.core`) |
| `ibm.qradar` | QRadar SIEM event ingestion |
| `cisco.dnac` | Cisco DNA Center (network automation) |
| `f5networks.f5_modules` | F5 BIG-IP load balancer |

To install from Automation Hub:

```yaml
# in ee/requirements.yml
collections:
  - name: ansible.controller
    source: https://console.redhat.com/api/automation-hub/content/published/
    type: galaxy
```

…plus `ansible.cfg` configured with the AH token (`api_key`).

---

## Decision tree: which collection do I need?

1. **AAP / Tower / Controller / EDA management** → `infra.aap_configuration` (declarative) or `ansible.controller` (imperative, AH-only) / `awx.awx` (community)
2. **AWS** → `amazon.aws` first, `community.aws` for older/missing modules
3. **Azure** → `azure.azcollection`
4. **GCP** → `google.cloud` (similar shape to amazon.aws)
5. **Kubernetes (incl. OCP, EKS, AKS, GKE, CAPI, Metal3)** → `kubernetes.core`
6. **OpenShift-specific** → `redhat.openshift` (AH-only) or `kubernetes.core` (Galaxy)
7. **ITSM (ServiceNow)** → `servicenow.itsm`
8. **ITSM (Jira)** → `community.general` has a `community.general.jira` module
9. **SIEM (Splunk)** → `splunk.es`
10. **SIEM (Sentinel)** → `azure.azcollection` + REST API (no dedicated Sentinel collection)
11. **Secrets (HashiCorp Vault)** → `community.hashi_vault`
12. **Secrets (CyberArk)** → `cyberark.conjur` or `cyberark.pas` (both on Galaxy + AH)
13. **Active Directory** → `microsoft.ad`
14. **Network OS (Cisco / Juniper / Arista)** → `cisco.ios` / `junipernetworks.junos` / `arista.eos`
15. **F5 / Citrix / Palo Alto** → `f5networks.f5_modules` / `citrix.adc` / `paloaltonetworks.panos`

For everything else, search Galaxy first
(`galaxy.ansible.com/ui/search/?keywords=<vendor>`) and fall back to
custom `uri` module.

---

## How to add a new collection to the AAC EE

1. Add to `ansible/execution-environments/aac-compliance-ee/requirements.yml`
2. Run AAP template `AAC - Build Compliance EE` (template 45) to rebuild the EE
3. Update `aac-compliance-ee` tag (`v1.x.y`) and push to `quay.io/rh-ee-tcoulter/aac-compliance-ee:<new tag>`
4. Update the EE reference in AAP — `Settings → Automation Controller → Execution Environments → AAC Compliance EE → image`
5. Bump `aac_mcp_image` / equivalent vars in `site_config.yml` if affected

Verification: re-run a job that exercises the new collection, confirm
`ansible-galaxy collection list` inside the EE shows the new entry.

---

## How to verify a collection is current (you should do this at customer kickoff)

```bash
# Galaxy (one collection)
curl -s "https://galaxy.ansible.com/api/v3/plugin/ansible/content/published/collections/index/<namespace>/<collection>/" \
  | jq '.highest_version.version'

# Automation Hub — needs an offline_token, easier via UI
# https://console.redhat.com/ansible/automation-hub/repo/published/<namespace>/<collection>
```

Pin the version in the customer's EE requirements file once chosen —
don't float at `>=`.
