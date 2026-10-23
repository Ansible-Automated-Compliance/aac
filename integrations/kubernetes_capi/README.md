# Kubernetes Cluster API (CAPI)

## At a glance

- **Customer system:** Kubernetes Cluster API (CAPI) — declarative K8s cluster lifecycle. Providers include CAPA (AWS), CAPZ (Azure), CAPG (GCP), CAPI Operator + Metal3 (bare metal), and various vendor wrappers.
- **AAC pattern:** hybrid — AAC applies CAPI manifests (push), watches new cluster events (event-driven), runs compliance scans on the resulting clusters (pull/scan)
- **Status in AAC today:** ✗ greenfield — no CAPI-specific playbooks; generic `kubernetes.core.k8s` modules are available via the EE if added
- **Effort estimate:** TBD — pending write-up
- **Required collections:**
  - `kubernetes.core` v6.4.0 (Galaxy + Automation Hub certified) — needed for any K8s CRD work
  - `cluster_api` provider-specific Helm charts / CRDs (no Ansible collection per provider — applied as YAML)
- **Customer-side prerequisites:**
  - A "management cluster" running CAPI + the relevant provider CRDs
  - kubeconfig + service account token for AAC to apply / read from the management cluster
  - For provider integrations: cloud credentials (CAPA needs AWS, CAPZ needs Azure SP)
  - Cluster templates (`ClusterClass` + `ClusterResourceSet`) defined by the customer

## Customer use case (1-sentence summary)

Customer provisions K8s clusters (EKS / AKS / GKE / OCP / Metal3) by
applying CAPI manifests. AAC's role is to (a) gate manifest changes
against AAC's Rego policies before apply, (b) scan the resulting
clusters for OPA-defined compliance (CIS Kubernetes, NSA hardening,
NIST 800-204), and (c) emit per-cluster compliance dashboards into
Grafana / the customer's existing K8s observability stack.

## Status

📝 **Pending full write-up.**

## Quick notes (for the eventual write-up)

- **Three distinct workflows:**
  1. **Pre-apply policy gate** — `kubernetes.core.k8s` dry-run a manifest, run OPA against the JSON output, fail the PR if policy violates
  2. **Cluster provisioning trigger** — apply `Cluster` + `MachineDeployment` CRDs, wait for `Ready` condition
  3. **Post-provision compliance scan** — once `Ready`, register the new cluster in AAC's inventory and run CIS Kubernetes assessment via `kubernetes.core.k8s_info`
- **Existing repo overlap:**
  - `policies/benchmarks/cis/kubernetes/` — CIS Kubernetes Benchmark Rego (re-use)
  - `policies/governance/kubernetes_admission/` — admission-controller-style policies (re-use)
  - No CAPI-specific seeder yet
- **Watch for the CAPI provider zoo:** the integration write-up will need to clarify the auth pattern per provider (CAPA = IRSA / IAM role chain; CAPZ = Service Principal; CAPG = workload identity). Per-provider sections.
- **Metal3 overlap:** Metal3 is a CAPI infrastructure provider for bare metal. See [`../metal3_ironic/`](../metal3_ironic/) for the bare-metal-specific gotchas. Many decisions are shared; the integration write-ups will cross-reference.
- **GitOps coupling:** customers typically use Argo CD or Flux to apply CAPI manifests. AAC's role is upstream of GitOps (policy gate at PR time) rather than competing with it. Don't reinvent.
- **EDA opportunity:** CAPI emits k8s events (`Cluster.Ready`, `MachineDeployment.Healthy`). Could plug in an EDA source plugin watching the management cluster's event stream and triggering downstream compliance assessments. Net-new EDA plugin work; not trivial.

## See also

- [`../metal3_ironic/`](../metal3_ironic/) — Metal3 is a CAPI infrastructure provider; deep dependencies
- [`../terraform_enterprise/`](../terraform_enterprise/) — some customers TFE → CAPI (TFE manages the management cluster's IaC; CAPI manages workload clusters)
- [`../aws_ssm/`](../aws_ssm/) — for EC2 worker nodes provisioned by CAPA, AAC reaches them via SSM
- `policies/benchmarks/cis/kubernetes/` — existing CIS Kubernetes policy library
- [`../_common/patterns.md`](../_common/patterns.md) — combines all three patterns
