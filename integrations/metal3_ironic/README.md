# Metal3 / Ironic (bare-metal provisioning)

## At a glance

- **Customer system:** Metal3 (CNCF) — the bare-metal infrastructure provider for Cluster API. Wraps OpenStack Ironic for actual hardware control.
- **AAC pattern:** hybrid — apply Metal3 CRDs (push), watch BareMetalHost state events (event-driven), run hardware-level compliance scans (pull)
- **Status in AAC today:** ✗ greenfield — no Metal3-specific code; `openstack.cloud` collection for direct Ironic API exists in Galaxy but not in our EE
- **Effort estimate:** TBD — pending write-up
- **Required collections:**
  - `kubernetes.core` v6.4.0 — applies Metal3 CRDs (`BareMetalHost`, `Provisioning`, `HostFirmwareSettings`)
  - `openstack.cloud` v2.5.0 — direct Ironic API access if needed (bypassing Metal3's controller)
- **Customer-side prerequisites:**
  - Management cluster running Metal3 + Ironic in containers
  - BMC credentials (Redfish / IPMI) for the bare-metal hosts — stored as K8s Secrets
  - `BareMetalHost` CRDs already defined (often inventory-as-code)
  - For firmware compliance: `HostFirmwareSettings` CRDs

## Customer use case (1-sentence summary)

Customer's on-prem fleet runs on bare metal provisioned via Metal3
(typically as the CAPI infrastructure provider for an OCP cluster).
AAC's role is to (a) audit `BareMetalHost` definitions against
governance policy (HW vendor allow-list, firmware version floor),
(b) run CIS / STIG compliance on the provisioned OS image,
(c) capture an evidence record per host for regulatory audit
(serial number, BMC firmware version, BIOS settings, OS hash).

## Status

📝 **Pending full write-up.**

## Quick notes (for the eventual write-up)

- **Two distinct surfaces, pick one or both:**
  1. **Metal3 K8s API** (preferred for net-new) — apply `BareMetalHost` CRDs via `kubernetes.core.k8s`. The Metal3 controller does the Ironic dance.
  2. **Direct Ironic API** — for customers using Ironic standalone (no Metal3) or for low-level operations (boot to rescue, firmware flash). Use `openstack.cloud.baremetal_node` (community-maintained) or raw `uri`.
- **No dedicated Metal3 collection** on Galaxy — apply CRDs as YAML; the K8s API is the contract.
- **Hardware-level compliance is a different beast:**
  - HW vendor compliance (firmware versions, BMC config, secure boot state) — read via Redfish (HTTPS to BMC)
  - OS-level compliance (CIS RHEL 9 etc.) — AAC's standard playbooks once the host is provisioned and SSH-reachable
  - The integration write-up should cover both, separately.
- **Existing repo overlap:**
  - `policies/benchmarks/cis/os/linux/rhel_9/` — applies to the provisioned OS
  - `policies/critical_infrastructure/` — NERC-CIP / IEC 62443 hardware-level policies
- **EDA event source:** Metal3 emits k8s events on host state transitions (`Available` → `Provisioning` → `Provisioned`). Pattern is the same as `kubernetes_capi/` — an EDA plugin watching the management cluster.
- **BMC credentials trap:** `BareMetalHost.spec.bmc.credentialsName` references a K8s Secret. AAC will need to read those for hardware compliance scans. The customer-side IAM should grant AAC's service account `get` on `secrets` in the `metal3-system` namespace (not as scary as it sounds — it's already the controller's only secret).
- **Air-gapped:** Metal3 deployments are often air-gapped (factory floor, OT segment). The integration write-up should call out the air-gap mode: AAC + Metal3 + Ironic + a mirrored image registry, no outbound calls.

## See also

- [`../kubernetes_capi/`](../kubernetes_capi/) — Metal3 is a CAPI provider; many decisions shared
- `policies/critical_infrastructure/` — NERC-CIP and OT policy libraries for the hardware layer
- [`../_common/patterns.md`](../_common/patterns.md) — hybrid event-driven + push + pull
- Metal3 docs: https://book.metal3.io/
- Ironic API: https://docs.openstack.org/api-ref/baremetal/
