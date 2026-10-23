# Third-Party Licenses

AAC is Apache-2.0 licensed (see `LICENSE`). This document attributes
third-party tools and libraries we orchestrate or depend on. We do not
vendor copyrighted source code into this repository; tools listed below
are pulled from upstream at customer-install or EE-build time.

## Runtime tools bundled in the AAC execution environments

These binaries are downloaded from upstream releases and installed into
their respective EE container images at build time. AAC uses **multiple
EEs split by domain** so updating one set of tools doesn't force a
rebuild of the others.

### aac-compliance-ee

Defined at `ansible/execution-environments/aac-compliance-ee/`. Used by
AAC's core demos (CIS, NERC-CIP, AMI, Digital Sovereignty, Sentinel,
Technical Debt, Golden Image, etc.).

| Tool | Version pinned | License | Upstream | Purpose |
|---|---|---|---|---|
| Terraform | 1.10.5 | BSL-1.1 | https://github.com/hashicorp/terraform | Sentinel demo: Terraform plan validation |

### aac-policy-tools-ee

Defined at `ansible/execution-environments/aac-policy-tools-ee/`. Used
by the trivy + kubescape state-assessment playbooks
(`integrations/external_policy_libraries/`).

| Tool | Version pinned | License | Upstream | Purpose |
|---|---|---|---|---|
| Trivy | 0.69.3 | Apache-2.0 | https://github.com/aquasecurity/trivy | State assessment of K8s/Dockerfile/IaC/cloud artifacts (uses MIT-licensed `trivy-checks` policy library) |
| Kubescape | 3.0.40 | Apache-2.0 | https://github.com/kubescape/kubescape | State assessment of K8s manifests / clusters against NSA-CISA / MITRE ATT&CK / CIS K8s |

### Trivy policy library (trivy-checks)

Trivy uses a separate, MIT-licensed policy library:
https://github.com/aquasecurity/trivy-checks — Copyright (c) 2024 Aqua
Security. The policies execute within Trivy's runtime; we orchestrate
the `trivy` CLI from Ansible playbooks (see
`ansible/playbooks/trivy_assess_artifact.yml`) and store JSON results
in `compliance_results`.

### Kubescape policy library (regolibrary)

Kubescape uses its own Apache-2.0 licensed policy library:
https://github.com/kubescape/regolibrary — Copyright (c) ARMO. The
policies execute within Kubescape's runtime; we orchestrate the
`kubescape` CLI from Ansible playbooks (see
`ansible/playbooks/kubescape_assess.yml`).

### Why not Gatekeeper Library (Open Policy Agent)?

The OPA Gatekeeper Library (https://github.com/open-policy-agent/gatekeeper-library,
Apache-2.0) is designed for Gatekeeper-the-admission-controller, not
standalone OPA evaluation. Its Rego is embedded in ConstraintTemplate
YAML and expects `AdmissionReview`-shaped input. AAC intentionally
**does not install or operate admission controllers** (see
`feedback_assessment_not_runtime.md` memory) — that's runtime
enforcement, not state measurement. Customers who want live admission
control should install the Red Hat Gatekeeper Operator from OperatorHub
directly.

## Rego policy library (this repo's `policies/` submodule)

Our own Rego policy library at `policies/` is also Apache-2.0
licensed and lives at https://github.com/ynotbhatc/rego_policy_libraries.
See `policies/LICENSE` for full text.

## Other dependencies

Python dependencies (`requirements.txt`) and Ansible Galaxy collections
(`requirements.yml`) in each EE directory carry their own licenses;
refer to each upstream project's `LICENSE` file. AAC ships none of
their source code; we pip-install / galaxy-install at EE build time.
