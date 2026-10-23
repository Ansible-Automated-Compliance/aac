# Standard install — EC2 provisioning path

Provisions a fresh EC2 instance (or pattern-equivalent bare-metal RHEL 9) and installs AAP +
AAC on it, driven from an existing AAP controller. This absorbs the former `install/from-scratch`
method into the standard path (restructure Phase 4); the standard preflight/verify gates apply
before and after.

> **Honest status (2026-08-31, from the handover audit):** this chain has **no recorded
> end-to-end execution on the current reference environment**. The playbooks exist and phase 06
> ends in a well-designed GO/NO-GO gate, but treat the path as unvalidated until a full
> exercise is recorded — and read the Known gaps section before pointing it at anything real.

**Time:** ~45 minutes end-to-end (phase 04's AAP install dominates)
**Playbooks:** `ansible/playbooks/fresh_install_0x_*.yml`

## Prerequisites

- An AAP controller reachable from where you run this, with credentials configured
- `ansible/vars/vault_secrets.yml` populated — copy `vault_secrets.yml.example`
- `AWS Compliance Lab` AAP credential created
- Compliance Automation project synced in AAP
- The AAP 2.6 containerized installer bundle, transferred to the target (phase 03 verifies it
  and prints copy instructions if missing)

## The pipeline — what each phase actually does

| Phase | Playbook | What it does |
|-------|----------|-------------|
| 00 | `fresh_install_00_teardown.yml` | Terminates the named EC2 instance + deletes the install security group (cleanup) |
| 01 | `fresh_install_01_provision_ec2.yml` | Latest RHEL 9 AMI → **t3.2xlarge** (no Elastic IP); creates a security group opening the service ports — **see the security warning below** |
| 02 | `fresh_install_02_prepare_os.yml` | subscription-manager registration, enables the AAP 2.6 repo, dnf update, base packages, firewalld, SELinux contexts, user linger |
| 03 | `fresh_install_03_verify_bundle.yml` | Verifies the AAP installer bundle + manifest are on the target; fails with copy-paste remediation if not |
| 04 | `fresh_install_04_install_aap.yml` | Extracts the bundle, writes the AAP 2.6 installer inventory, runs the containerized installer (~90 min async), waits for gateway/controller |
| 05 | `fresh_install_05_install_aac.yml` | Clones this repository onto the target and runs `scripts/install.sh` (OPA ×3 + PostgreSQL init + policy load) and `scripts/configure_aap.sh` (AAP objects). Grafana and MCP are **not** part of this phase |
| 06 | `fresh_install_06_validate.yml` | GO/NO-GO: OPA ×3 health + policy minimums, PostgreSQL tables, gateway/controller ping, required templates — with fix hints per failure |

> **Security warning (phase 01):** the generated security group currently opens the service
> ports — **including PostgreSQL 5432 — to 0.0.0.0/0**. For anything beyond a throwaway
> evaluation instance, restrict the source ranges before or immediately after provisioning.

## Running it

**Step 1 — seed the templates.** Launch **"AAC - Seed Fresh Install Templates"** (or run
`ansible/playbooks/seed_fresh_install_templates.yml`). This creates **seven standalone job
templates**, one per phase.

**Step 2 — launch the phases in order (00 → 06).** There is **no "AAC - Full Fresh Install"
workflow today** — earlier versions of this document described one that was never created
(handover audit v1.1). Each phase is launched individually and prompts for what it needs
(`target instance`, passwords); carry the target host forward between phases. Chaining them
into a real workflow with `set_stats` hand-off is a known, scoped improvement.

**Step 3 — validate.** Phase 06 is the gate. After GO, run the standard path's
`verify_install.yml` as well — it is the stricter, consolidated verifier.

```bash
# Verify policy count (count at the pinned commit — never quote a number from docs)
curl http://<new-host-ip>:8181/v1/policies | jq '.result | length'
```

## Known gaps (tracked, not hidden)

- **Never exercised end-to-end** on the current reference environment.
- **Maintainer-specific residue**: the bundle-transfer instructions printed by phases 01/03
  currently reference the maintainer's local paths and subscription manifest — parameterize
  before customer use.
- Phase 04's gateway/controller waits tolerate failure (`ignore_errors`) — a failed AAP install
  surfaces one phase late.
- Phase 05 clones a hardcoded repository URL and does not init the `policies/` submodule —
  policy load can silently load nothing on a fork or a shallow clone.
- Phases 02/04/05 are not fully idempotent (raw shell steps); prefer teardown + fresh run over
  re-running a half-completed install.

## Key vault variables

| Variable | Purpose |
|----------|---------|
| `aws_lab_access_key` / `aws_lab_secret_key` | AWS credentials for the install |
| `compliance_db_password` | PostgreSQL compliance DB password |
| `vault_github_pat` | GitHub PAT for project sync |
| `grafana_admin_password` | Grafana admin password |
| `vault_redhat_username` / offline token | Subscription registration (phase 02) |

## Troubleshooting

**Phase 01 — instance type not available:** t3.2xlarge availability varies by AZ; the playbook
constrains the zone. Check IAM permissions if it persists.
**Phase 03/04 — bundle not found:** download the AAP containerized bundle from
access.redhat.com and place it at the path phase 03 names in its error message.
**Phase 06 — OPA health fails:** `ssh ec2-user@<ip> "podman ps | grep opa"` and check
`podman logs opa-security`.
