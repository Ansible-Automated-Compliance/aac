# AAP 2.6 → 2.7 Containerized Upgrade Runbook

*In-place upgrade of a containerized Ansible Automation Platform deployment — procedure, validation, and rollback*

Prepared by Tim Coulter with Claude (Anthropic) • **Version:** v1.2 — September 14, 2026

Target environment: **containerized AAP** (topology per your inventory)

---

# Executive Summary

This runbook covers an **in-place upgrade of an already-containerized** Ansible Automation Platform deployment from **2.6 to 2.7**. It is scoped deliberately narrowly: same install type (containerized), same hosts, one minor-version bump. It is **not** an RPM migration, **not** a fresh install, and **not** an OS migration.

**Bottom line:** the containerized upgrade is *back up → download the 2.7 setup bundle → re-run the installer against your existing inventory → verify* (back up **first** — see §6). The installer is idempotent and performs the in-place upgrade of every service (gateway, controller, EDA, metrics, Redis) using your current inventory. If your PostgreSQL is an **external managed database** (for example **AWS RDS**), the database side is handled by a snapshot **you** take before the run — the installer does not own that backup.

**Two things you own that this runbook only reserves space for:**
1. **Your pre-flight check** — insert it in §5 (placeholder marked). You know your environment; your checklist is authoritative.
2. **Your inventory file** — the procedure references the inventory that installed/last-upgraded your 2.6 deployment; keep it under version control and vault its secrets (§4.4).

---

# 1. Scope and assumptions

**In scope:** containerized AAP 2.6 → 2.7, in place, on the existing hosts, bundle (air-gap-friendly) or online install flow, external or installer-managed PostgreSQL.

**Assumptions (verify before starting):**
- The deployment is **currently on the latest 2.6.x** patch level. Upgrade 2.6.x → latest 2.6.x first if you are behind, then 2.6 → 2.7. Red Hat supports upgrading to 2.7 from a supported 2.6 release.
- You are the **non-root install user** with rootless Podman configured (the user the 2.6 install ran as).
- The **same inventory** that installed/last-upgraded 2.6 is available and current.
- Outbound access to `registry.redhat.io` **or** a complete **bundle** (`bundle_install=true`) is available on the installer host.

**Out of scope (call it out so no one expects it here):** RPM→containerized migration, RHEL major-version upgrade, OpenShift Operator deployments, and any AAP *configuration* change beyond what 2.7 requires.

---

# 2. Your environment at a glance — fill from your inventory

> This is a template. Read your actual inventory file and complete the table, then confirm it still matches production before cutover. The rows below are the groups a containerized AAP inventory typically defines; delete those you don't run.

| Role (inventory group) | Hosts | Notes |
|---|---|---|
| **Gateway** (`automationgateway`) | `<host(s)>` | Single or HA |
| **Controller** (`automationcontroller`) | `<host(s)>` | May be co-located with gateway |
| **EDA Controller** (`automationeda`) | `<host(s)>` | If deployed |
| **Execution node** (`execution_nodes`) | `<host(s)>` or *empty* | Receptor mesh node(s). **On a single-node / hybrid install, leave this empty — do not add the controller here (double registration).** Populate only for genuinely separate execution nodes. |
| **Automation metrics** (`automationmetrics`) | `<host>` | If deployed |
| **Redis** (`redis`) | `<host(s)>` | **≥3 nodes ⇒ cluster mode**; note single vs. clustered |
| **Automation Hub** (`automationhub`) | `<host(s)>` or *commented out* | Skip all hub steps if not deployed |
| **PostgreSQL** (`database` group) | **Installer-managed** (populate `[database]`) *or* **external managed** (e.g. AWS RDS) | **Installer-managed:** list the DB host(s) in `[database]`. **External:** leave `[database]` empty and point the `*_pg_host` vars at the managed endpoint — an empty `[database]` is what makes the installer treat PostgreSQL as external (a misconfigured mix can make pre-flight probe localhost). Set per-component TLS per the 2.7 appendix. |

**Topology facts that shape the procedure — determine which apply to you:**
- **External/managed DB (e.g. RDS)** → the pre-upgrade database backup is a **snapshot you take** (RDS snapshot or your provider's equivalent), not an installer task. The installer runs schema migrations against it during the upgrade; the snapshot is your rollback point.
- **Installer-managed DB** → the installer's backup playbook (§6.2) captures the database; still record a restore plan.
- **Clustered Redis (≥3 nodes)** → keep the `[redis]` group intact and identical; do not shrink it during the upgrade.
- **HA gateway/controller/EDA** → the installer handles the members from the inventory; plan the maintenance window for a brief control-plane interruption.
- **No Automation Hub** → ignore every hub reference in the Red Hat docs; keep `[automationhub]` commented out.
- **Bundle install** → stage the **2.7** bundle in `bundle_dir` (commonly computed as `$PWD/bundle`).

---

# 3. Maintenance window and roles

- **Change window:** one window; expect a short control-plane outage while gateway/controller containers are recreated. Running jobs on execution nodes will be interrupted — drain or quiesce scheduled work first.
- **Who:** the install user on the installer host; if the DB is external, someone with **database/console access** to take the snapshot and (if needed) restore; an app owner to smoke-test after.
- **Comms:** announce the window; pause external schedulers/webhooks that launch jobs (EDA activations will restart as part of the upgrade).

---

# 4. Prerequisites and version floors

> **Verify each against the AAP 2.7 release notes and the containerized upgrade guide (§12) — do not take a floor on faith for a production run.** The items below are the ones that bite.

## 4.1 Platform floors
- **RHEL:** a 2.7-supported RHEL on every host. The established containerized floor is **RHEL 9.4+ or RHEL 10** (same floor as the companion `aap_25_rpm_to_26_upgrade_runbook.md`) — treat **9.0–9.3 as below the floor**. Confirm the exact supported-OS matrix against the 2.7 docs, which may raise (not lower) this floor; don't assume 9-only.
- **PostgreSQL:** AAP 2.6/2.7 run on **PostgreSQL 15**. If external/managed, confirm the engine version meets the 2.7 floor **before** the window; a DB engine bump is its own change with its own outage.
- **ansible-core** on the installer host: the 2.7 containerized installer expects a specific ansible-core (2.6 used 2.16). Confirm and match before running.
- **Rootless Podman**, cgroups v2, and the per-user `linger`/subuid/subgid setup that 2.6 required remain in place.

## 4.2 Capacity
- Disk headroom on each host for the **new container images** pulled alongside the running ones (the old images are not removed until you prune). Bundle adds the extracted bundle size on the installer host.
- Database: headroom for schema migration; check free storage and IOPS.

## 4.3 Access / entitlements
- Valid Red Hat registry service-account credentials (online flow) **or** the complete 2.7 **bundle** (air-gap flow).
- SSH from the installer host to every inventory host as the install user; sudo where the installer needs it.

## 4.4 Secrets hygiene (do this before you ship the inventory anywhere)
If your inventory carries DB and admin passwords **inline as plaintext** (the various `*_pg_password` and `*_admin_password` values — use the **exact per-component names from the 2.7 inventory appendix**, don't rely on a remembered list; the names differ per component), then for a production upgrade:
- Move every secret into an **encrypted vault file** and pass it at run time: `-e @vault.yml --ask-vault-pass`.
- Keep only non-secret structure in the inventory.
- Enable TLS on **every component's** DB connection using the per-service TLS variables named in the 2.7 inventory appendix (`require` at minimum; `verify-full` with the provider CA for defense in depth). On a multi-service external database, set it for **all** components — configuring only one leaves the others in the clear.

---

# 5. Pre-flight checks (run these the week before, then again day-of)

## 5.1 General (platform)
```bash
# On each AAP host — confirm current version and health BEFORE touching anything.
# Gateway API ping (expect HTTP 200):
curl -sk -o /dev/null -w '%{http_code}\n' https://<gateway-host>/api/gateway/v1/ping/
# Controller API ping (expect 200); note the running controller version:
curl -sk https://<gateway-host>/api/controller/v2/ping/ | python3 -m json.tool | grep -i version
# Podman containers healthy (as the install user, on each host):
podman ps --format '{{.Names}}  {{.Status}}'
# Redis cluster state (from a redis node, if clustered):
podman exec -e REDISCLI_AUTH="$REDIS_PW" <redis-container> redis-cli cluster info | grep cluster_state   # expect cluster_state:ok
```

## 5.2 Database
- Confirm the **engine version** meets the 2.7 PostgreSQL floor.
- Confirm connectivity + TLS from each component host to the database endpoint with `sslmode=require`.
- Confirm free storage/IOPS headroom for migration.

## 5.3 Confirm you are on the latest 2.6.x
- If behind, patch 2.6.x → latest 2.6.x with the current bundle first (same procedure as §7 but with the 2.6 bundle), verify, then proceed to 2.7.

## 5.4 «INSERT YOUR ENVIRONMENT-SPECIFIC PRE-CHECK HERE»
> **Placeholder for your environment-specific pre-flight checklist.** You know your specifics — load-balancer/health-probe behavior, DNS, firewall egress to the registry/bundle mirror, database parameter-group specifics, backup SLAs, change-ticket references. Drop your checklist here; it is authoritative over the generic items above.

---

# 6. Back up first — this is the rollback point

**Order matters: back up before you download or stage anything for 2.7.**

## 6.1 Database snapshot (the database rollback point)
If your database is **external/managed**, take a snapshot and confirm it reaches `available` before proceeding. AWS RDS example:
```bash
# Compute ONE unique identifier and reuse it for both commands
# (avoids a date-rollover mismatch and a same-day repeat-run collision):
SNAP="aap-pre-27-upgrade-$(date +%Y%m%d-%H%M%S)"
aws rds create-db-snapshot \
  --db-instance-identifier <your-aap-db-instance> \
  --db-snapshot-identifier "$SNAP"
aws rds wait db-snapshot-available --db-snapshot-identifier "$SNAP"   # do NOT proceed until this returns
```
(For another managed provider, use its equivalent point-in-time snapshot. For an installer-managed DB, the platform backup in §6.2 captures it.)

## 6.2 Platform backup (installer-level)
Run the containerized installer's backup playbook from your **current 2.6** bundle, against your inventory:
```bash
cd <path-to-2.6-bundle>/ansible-automation-platform-containerized-setup-bundle-*/
ansible-playbook -i <your-inventory> \
  -e @vault.yml --ask-vault-pass -K \
  ansible.containerized_installer.backup
```
Copy the resulting backup artifact **off-host** to safe storage before proceeding. (This captures configuration/secret material; the snapshot captures the data.)

> **Preserve the exact 2.6 bundle build alongside this backup.** The §10 rollback must re-run this *precise* installer version, and downloading "a 2.6 bundle" later is not guaranteed to be the same build. Record the bundle's exact filename and checksum, and retain the artifact itself off-host with the rollback baseline:
> ```bash
> ls -1 <path-to-2.6-bundle>/ansible-automation-platform-containerized-setup-bundle-2.6*-x86_64.tar.gz
> sha256sum <that-file> | tee aap-2.6-bundle.sha256   # keep this with the backup + baseline
> ```
> Do not rely on `<path-to-2.6-bundle>` remaining valid — copy the tarball itself to the same safe storage as the platform backup.

## 6.3 Record current state for verification later
- Controller version string (from §5.1), gateway health, EDA activation list and their states, redis `cluster_state:ok` (if clustered), a couple of known job-template IDs you will re-launch as a smoke test.

---

# 7. The upgrade — cutover procedure

## Step 1 — Download and stage the 2.7 containerized setup bundle
```bash
# As the install user, on the installer host.
# Obtain the 2.7 "Containerized setup bundle" from access.redhat.com (or your internal mirror),
# then extract it:
tar -xzvf ansible-automation-platform-containerized-setup-bundle-2.7*-x86_64.tar.gz
cd ansible-automation-platform-containerized-setup-bundle-2.7*-x86_64/
```
If your inventory sets `bundle_install=true` and computes `bundle_dir` from the working directory (commonly `bundle_dir='{{ lookup("ansible.builtin.env","PWD") }}/bundle'`), run the installer **from the directory whose `./bundle` holds the 2.7 images** (i.e. from the extracted 2.7 bundle root so `$PWD/bundle` resolves to the 2.7 images, not the old ones).

## Step 2 — Reconcile the inventory for 2.7
> **Before editing anything, preserve an immutable copy of BOTH the pre-upgrade 2.6 inventory AND its vault file.** Together they are your rollback baseline (§10). Copy them aside and make the baseline read-only so the 2.7 edits below cannot alter it:
> ```bash
> cp <path-to-existing-2.6-inventory> inventory.2.6-preupgrade
> cp <path-to-existing-vault.yml> vault.2.6-preupgrade.yml
> chmod a-w inventory.2.6-preupgrade vault.2.6-preupgrade.yml
> ```
> The 2.6 re-run must use these preserved files, **never** the ones you edit below for 2.7. Preserving the vault matters: if the 2.7 working copy rotates any secret, the baseline still holds the exact 2.6 credentials rollback needs.
- Use a **working copy of your existing inventory** as the base (same hosts, same groups).
- Read the **2.7 inventory-file-variables appendix and release notes** (§12) for any **new required variables** introduced in 2.7, and add them. Do **not** invent variable names — take them from the 2.7 docs.
- Keep secrets in the vault file (§4.4), not inline.
- Leave `[automationhub]` commented out if you don't run hub.
- Keep clustered `[redis]` membership intact.

## Step 3 — Run the installer (performs the in-place upgrade)
```bash
# From the extracted 2.7 bundle root, as the install user:
ansible-playbook -i <your-inventory> \
  -e @vault.yml --ask-vault-pass -K -v \
  ansible.containerized_installer.install
```
- The installer detects the existing deployment and upgrades each service in place; it pulls the 2.7 images (from `./bundle` given `bundle_install=true`), recreates containers, and runs database schema migrations.
- **Confirm the exact upgrade entrypoint** in the 2.7 *"Upgrade your containerized deployment"* guide (§12) before the window — if 2.7 documents a dedicated upgrade playbook target, use the one the 2.7 guide names. The `install` entrypoint has been the in-place upgrade path for containerized AAP.
- `-K` prompts for the become password; `--ask-vault-pass` for the vault. Keep `-v` so you have a readable log if a step fails.

## Step 4 — Watch the run
- The control plane (gateway/controller) is upgraded before the execution node in the installer's ordering; expect a brief gateway/controller interruption while containers recreate.
- EDA activations are recreated/restarted as part of the run.
- If the run fails mid-way, **do not re-point DNS or delete anything** — go to §10 Rollback.

---

# 8. HA, Redis, and execution-node notes

- **HA gateway/controller/EDA:** the installer manages every member listed in the inventory groups; there is no separate manual per-node dance for a minor upgrade, but the control plane is briefly unavailable during recreation. If a member fails to come up, re-run the installer (idempotent) after addressing the host, rather than hand-editing containers.
- **Clustered Redis:** verify `cluster_state:ok` after the upgrade (§9). Do not change redis membership during the window.
- **Execution nodes:** confirm the receptor mesh re-establishes and each node shows healthy/available in the controller after the upgrade; a job launched in the smoke test should be schedulable to it.

---

# 9. Post-upgrade verification

```bash
# Version bumped — controller should report the 2.7-series version (controller 4.8.x):
curl -sk https://<gateway-host>/api/controller/v2/ping/ | python3 -m json.tool | grep -i version
# Gateway health (expect 200):
curl -sk -o /dev/null -w '%{http_code}\n' https://<gateway-host>/api/gateway/v1/ping/
# Containers healthy on every host (as install user):
podman ps --format '{{.Names}}  {{.Status}}'
# Redis cluster healthy (if clustered):
podman exec -e REDISCLI_AUTH="$REDIS_PW" <redis-container> redis-cli cluster info | grep cluster_state   # cluster_state:ok
```
UI / functional smoke test:
- Log in via the gateway; confirm all gateway members serve.
- **Launch a known job template** and confirm it runs to success (proves controller + execution node + mesh + DB).
- Confirm **EDA activations** are running (they restart during the upgrade; restart any that didn't come back).
- Confirm the **metrics service** is reporting (if deployed).
- Confirm the **database** shows the migration completed and no connection errors in the controller logs.
- Integration sweep: anything external that calls the AAP API (webhooks, schedulers, portals) — verify tokens still work and one end-to-end path succeeds.

---

# 10. Rollback plan

Trigger rollback if the control plane does not return healthy, jobs won't run, or DB migration errors surface.

**The two database models roll back differently — follow the branch that matches your topology. For an installer-managed DB the ordering is strict: reinstall 2.6 *first*, then restore.**

1. **Stop** the partially-upgraded services (do not delete images/volumes yet).

2. **Managed / external DB (e.g. RDS) — restore now (provider-side, independent of the installer).** Restore the §6.1 snapshot to a new instance and re-point the `*_pg_host` values, or restore in place per your provider's runbook. This does not depend on the AAP installer, so it can happen before the platform is reinstalled.

3. **Re-run the installer from the exact 2.6 bundle build that produced the known-good state** — the precise artifact and checksum you preserved in §6.2 (restore/rollback compatibility depends on the exact installer version — see the version-match warning in `aap_25_rpm_to_26_upgrade_runbook.md`). Run it against the **preserved pre-upgrade 2.6 inventory *and* vault** from §7 Step 2 (never the files you edited for 2.7). If the managed snapshot was restored to a new instance, use a temporary copy of that baseline with every `*_pg_host` set to the restored endpoint, or pass those endpoint overrides with `-e`; do not modify the immutable baseline. This reinstalls the known-good 2.6 deployment.

4. **Installer-managed DB — restore only *after* Step 3 has reinstalled 2.6.** The platform restore must run against an installed, version-matched 2.6 deployment (install-then-restore — same ordering as the companion runbook's Path C-1), never against the partially-upgraded 2.7:
   ```bash
   ansible-playbook -i inventory.2.6-preupgrade/<inventory> \
     -e @vault.2.6-preupgrade.yml --ask-vault-pass -K \
     ansible.containerized_installer.restore \
     -e backup_file=<§6.2 platform-backup artifact>
   ```
   Confirm the exact restore target and `backup_file`/artifact variable in the 2.7 guide before relying on it.
    **No §6.2 backup for an installer-managed DB = no rollback point.** §6.1 does not snapshot an installer-managed database, so there is no separate DB snapshot to fall back to on this path. If you did not (or cannot) take the §6.2 platform backup, then before starting the upgrade either take **complete, tested per-service database dumps together with the 2.6 AAP encryption keys and a documented restore procedure**, or treat the upgrade as **not rollbackable** and say so in the change record — do not assume a `pg_dump` alone can restore AAP.

5. Verify with the §9 checks against the 2.6 expectations (controller reports the 2.6-series version).
6. Only after a confirmed-good rollback, investigate the failure (installer `-v` log, controller/gateway container logs, DB logs) before re-attempting.

Keep the snapshot and platform backup until the 2.7 deployment has been healthy for at least one full business cycle.

---

# 11. Common pitfalls

1. **External/managed DB is not installer-managed.** The installer runs migrations but does **not** snapshot your DB. If you skip §6.1 you have no database rollback point. Take the snapshot.
2. **DB engine floor.** If the database is below the 2.7 PostgreSQL floor, the upgrade can fail mid-migration. Verify (and, if needed, bump the engine) in a **separate** earlier window.
3. **`bundle_dir` resolves from `$PWD`.** If `bundle_dir` is computed from the working directory, running the installer from the **wrong** directory points it at the **old** bundle. Always run from the extracted **2.7** bundle root.
4. **Clustered Redis membership.** Keep all nodes in `[redis]`. Shrinking the group or losing quorum during the window will wedge the platform.
5. **Inline plaintext secrets.** Vault DB/admin passwords before the run and before the inventory leaves your hands (§4.4).
6. **Hub steps when hub isn't deployed.** Don't add hub steps from the generic Red Hat guide if your `[automationhub]` group is commented out.
7. **New 2.7 inventory variables.** Skipping the 2.7 release-notes read for new **required** vars is the most common avoidable failure. Reconcile the inventory (§7 Step 2) from the 2.7 docs, not from memory.
8. **Latest-2.6.x first.** Upgrading to 2.7 from a back-level 2.6.x is not the supported entry; get current on 2.6.x first.

---

# 12. References (authoritative — read before the window)

- **Upgrade your containerized deployment of AAP (2.7):** https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.7/upgrade-proc_update_aap_container
- **Install containerized AAP (2.7):** https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.7/install-proc_installing_containerized_aap
- **Containerized installation intro (2.7):** https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.7/install-con_aap_containerized_installation_intro
- **Inventory file variables appendix (2.7):** https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.7/install-assembly_appendix_inventory_file_vars
- **AAP 2.7 release notes** (for supported source versions + new required inventory vars) — in the 2.7 documentation set.

---

# 13. Appendix — quick command card

```bash
# 1. Backup (from 2.6 bundle)
cd <2.6-bundle>/ansible-automation-platform-containerized-setup-bundle-*/
ansible-playbook -i <inventory> -e @vault.yml --ask-vault-pass -K ansible.containerized_installer.backup
# 2. Database snapshot (managed-DB example: AWS RDS) — one unique ID, and WAIT before upgrading
SNAP="aap-pre-27-$(date +%Y%m%d-%H%M%S)"
aws rds create-db-snapshot --db-instance-identifier <db> --db-snapshot-identifier "$SNAP"
aws rds wait db-snapshot-available --db-snapshot-identifier "$SNAP"
# 3. Stage 2.7 bundle
tar -xzvf ansible-automation-platform-containerized-setup-bundle-2.7*-x86_64.tar.gz
cd ansible-automation-platform-containerized-setup-bundle-2.7*-x86_64/
# 4. Upgrade (in place) — run from the 2.7 bundle root
ansible-playbook -i <inventory> -e @vault.yml --ask-vault-pass -K -v ansible.containerized_installer.install
# 5. Verify
curl -sk https://<gateway-host>/api/controller/v2/ping/ | python3 -m json.tool | grep -i version
```

---

*Prepared by Tim Coulter with Claude (Anthropic). Environment-neutral: no specific hostnames, inventories, or customer/lab/demo identifiers — fill §2 from your own inventory. Version floors and the exact upgrade entrypoint must be confirmed against the Red Hat AAP 2.7 documentation (§12) before execution. You supply §5.4 (pre-check) and the inventory file.*
