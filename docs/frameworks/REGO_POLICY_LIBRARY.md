# Rego Policy Library (submodule)

The `policies/` directory in this repository is a git submodule pointing to:
**[ynotbhatc/rego_policy_libraries](https://github.com/ynotbhatc/rego_policy_libraries)**

---

## Why a Separate Repository?

- **Independent versioning** — policy updates don't couple with automation code changes
- **Standalone consumption** — other projects (CI/CD pipelines, standalone OPA deployments,
  customer-managed forks) can import the policy library without pulling all of AAC
- **Cleaner git history** — policy library PRs stay separate from AAC playbook PRs
- **Three-axis taxonomy** — scales naturally to new standards (NIS2, DORA, new CIS benchmarks)

---

## Taxonomy

```
policies/                         ← submodule root
├── benchmarks/                   ← technical security baselines
│   ├── cis/                      ← CIS Benchmarks (200+ files)
│   │   ├── os/linux/             ← RHEL 8/9/10, Ubuntu 20/22/24, Debian, Rocky, Amazon
│   │   ├── os/windows/           ← Server 2016/2019/2022, Win 10/11
│   │   ├── cloud/                ← AWS, Azure, GCP
│   │   ├── containers/           ← Docker, Kubernetes, OpenShift
│   │   ├── databases/            ← MySQL, Oracle, PostgreSQL
│   │   ├── web_servers/          ← Apache, Nginx
│   │   ├── network/              ← Cisco, Juniper, Palo Alto, Fortinet, Arista
│   │   ├── mobile_devices/       ← iOS, Android
│   │   └── virtualization/vmware/
│   └── stig/                     ← DISA STIGs (8 files)
│       ├── os/linux/             ← RHEL 8/9, Ubuntu 20.04
│       └── os/windows/           ← Server 2016/2019/2022, Win 10/11
│
├── frameworks/                   ← regulatory/compliance frameworks
│   ├── federal/                  ← NIST, FISMA, FedRAMP, CMMC
│   ├── management/               ← ISO 27001, SOC 2, Corporate
│   ├── financial/                ← PCI-DSS, SOX
│   ├── privacy/                  ← GDPR, HIPAA
│   ├── critical_infrastructure/  ← NERC-CIP, IEC 62443, AMI/NIST IR 7628
│   └── sovereignty/              ← Digital Sovereignty (7 domains)
│
├── enforcement/                  ← gate-style policy-as-code
│   ├── ansible/                  ← sentinel_ansible.rego
│   ├── terraform/                ← sentinel_terraform.rego
│   ├── dockerfile/               ← sentinel_dockerfile.rego
│   ├── kubernetes/               ← sentinel_kubernetes.rego
│   └── git/                      ← git approval/audit policies
│
├── governance/                   ← operational governance decisions
│   ├── ai/                       ← AI agent action classification
│   └── mcp/                      ← MCP tool-call enforcement
│
└── threat_detection/
    └── crypto_mining/            ← unauthorized crypto miner detection
```

---

## OPA Container Routing

| OPA Container | Port | Loads from |
|---------------|------|-----------|
| `opa-security` | 8181 | `benchmarks/` + `frameworks/federal/nist` |
| `opa-compliance` | 8182 | `frameworks/` (excl. critical_infrastructure) + `enforcement/` + `governance/mcp` |
| `opa-ot` | 8183 | `frameworks/critical_infrastructure/` + `governance/ai` + `threat_detection/` |

**Two-tier evaluation model:** The central OPA containers above handle batch evaluation of facts stored in PostgreSQL. For EDA real-time drift detection (inotifywait/auditd triggers), a local OPA sidecar on each execution node evaluates the policy for that host immediately. The sidecar loads only the relevant modules — primarily `benchmarks/cis/os/linux/rhel_9/` — for sub-second evaluation latency.

## CIS RHEL 9 — Extended Hardening (STIG/NIST)

The `benchmarks/cis/os/linux/rhel_9/` directory contains 19 files: 14 core CIS v2.0.0 modules plus 3 extended hardening modules that cover controls from DISA STIG and NIST SP 800-53 not present in the CIS baseline:

| File | Standards | EDA trigger |
|------|-----------|-------------|
| `storage_encryption_validation.rego` | STIG RHEL-09-231xxx/672xxx, NIST SC-28 | `/etc/crypttab`, `/etc/fstab`, LUKS changes |
| `certificate_validation.rego` | NIST SC-17/IA-5/SC-13, CIS 1.8 | `/etc/pki/ca-trust`, `/etc/ssl/certs` |
| `authorized_keys_validation.rego` | CIS 5.2, STIG RHEL-09-255xxx, NIST IA-3 | `/root/.ssh/authorized_keys`, `/home/*/.ssh/authorized_keys` |

These modules are orchestrated by `cis_rhel9_complete.rego` via `extended_hardening_summary`. Their results are **separate from the 338-control CIS compliance score** — `compliant` reflects only the 14 core CIS modules; `hardening_compliant` and `fully_hardened_compliant` cover the extended checks.

---

## Working with the Submodule

### Initial clone with submodule

```bash
git clone --recurse-submodules https://github.com/ansible-automated-compliance/aac.git
```

### Update submodule to latest library version

```bash
git submodule update --remote policies
git add policies
git commit -m "Update policy library to latest"
git push
```

### Pin to a specific library version

```bash
cd policies
git checkout v1.2.0
cd ..
git add policies
git commit -m "Pin policy library to v1.2.0"
```

### AAP Project Configuration

In AAP Project settings (ID 11 — Compliance Automation):
- **SCM Update Options:** Check "Update Revision on Launch"
- Set `scm_update_submodules: true` in the project config so the submodule is
  checked out automatically on every project sync

---

## Contributing a New Policy

1. Clone `ynotbhatc/rego_policy_libraries` directly
2. Place the `.rego` file in the appropriate taxonomy path
3. Ensure `import rego.v1` is at the top
4. Run `make lint` to verify syntax
5. Open a PR to `rego_policy_libraries` — CI validates automatically
6. Once merged, update the submodule pointer in AAC:
   ```bash
   git submodule update --remote policies
   git add policies
   git commit -m "Update policy library: add <policy name>"
   ```
7. Sync the AAP project and run Template 27 (AAC - Load OPA Policies)

**Note on policy directory setup:** The `/etc/opa/{security,compliance,ot}` directories
on the AAC host are created and SELinux-labeled by the `aac_opa_containers` Ansible role
(called by Template 28 — AAC - Deploy OPA Containers). You do not need to create these
directories manually; run Template 28 before Template 27 on a fresh install.
