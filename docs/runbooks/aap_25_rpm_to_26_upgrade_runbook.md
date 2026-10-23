# AAP 2.5 RPM (RHEL 8) → 2.6 (RHEL 9): RPM & Containerized Upgrade Runbook

*Customer Upgrade Paths, Recommended Procedure, and Validation*

Prepared by Tim Coulter with Claude (Anthropic) • **Version:** v5 — July 18, 2026

# Executive Summary

This runbook addresses a customer scenario: they are running Ansible Automation Platform (AAP) 2.5 via the RPM-based installer on RHEL 8, and they need to migrate to RHEL 9. It documents the supported paths, identifies the recommended approach, and provides detailed runbooks for execution — **both the near-term RPM cutover and the strategic move to the containerized installer.** It also corrects several misconceptions about AAP 2.6 installer availability that commonly appear in field guidance.

**Bottom line: The recommended single-cutover path is AAP 2.5 RPM (RHEL 8) → AAP 2.6 RPM (RHEL 9). Red Hat shipped a 2.6 RPM installer specifically to support migrations like this; the bundled OS + AAP version upgrade lands the customer on the terminal supported RPM version and avoids two separate change windows.**

**The strategic end state is AAP 2.6 Containerized. RPM is deprecated and is removed entirely in AAP 2.7 — so every RPM customer must eventually move to the containerized installer (or the OpenShift Operator). Because Red Hat only supports an install-type change *within the same major version*, the clean route is: get to 2.6 RPM first (Path B), then migrate 2.6 RPM → 2.6 Containerized (Path C). Path C is documented in full below.**

*v5 changes: Added the full "Decision Matrix: Five Upgrade Paths" table that prior versions referenced but never rendered. Added Path C — the complete RPM 2.6 → Containerized 2.6 migration runbook (backup/restore path plus the external-DB + secret-key path), containerized pre-flight, three new containerized pitfalls (#10–#12), and containerized cutover timing. Key correction vs. Pitfall #9: the containerized installer DOES honor `*_secret_key` extra vars — unlike the RPM installer — so secret-key continuity is handled differently (and more easily) on the containerized side. Title broadened to reflect the containerized destination.*

*v4 changes: Pitfall #9 (Fernet / SECRET_KEY reuse) rewritten after field-verified evidence that the documented inventory variables (automationgateway_secret_key, automationcontroller_secret_key, automationedacontroller_secret_key) are silently overwritten by the installer roles' secret_key.yml tasks. The supported workaround is to pre-stage the SECRET_KEY files on disk before running setup.sh. Step 3 callout and the customer-questions list updated to match.*

# Critical Fact: AAP 2.6 RPM Does Exist (RHEL 9 only)

A common misconception is that AAP 2.6 is containerized-only. It is not. Red Hat ships both an RPM installer and a containerized installer for AAP 2.6 — with the RPM installer restricted to RHEL 9. The 2.6 RPM exists for exactly one reason: to give 2.5 RPM customers a supported migration path before RPM is removed entirely in AAP 2.7.

Corollary: AAP 2.6 is the **last** release with an RPM installer. Any customer landing on 2.6 RPM has bought time, not a destination. Plan the containerized migration (Path C) before 2.7 ships.

# Decision Matrix: Five Upgrade Paths

Five paths are technically discussable; four are supported, one is not. The right choice depends on cutover risk tolerance and how soon the customer wants to end up on the containerized installer.

| Path | Route | End state | Change windows | Supported? | When to choose |
|------|-------|-----------|:--:|:--:|----------------|
| **A** | 2.5 RPM (RHEL 8) → **2.5 RPM (RHEL 9)** | 2.5 RPM on RHEL 9 | 1 (OS only) | ✅ Yes | Large/complex portfolio + real fear an AAP version bump breaks something. Isolates the OS move from the version move. **Dead-end intermediate** — still needs a later 2.6 upgrade. |
| **B** | 2.5 RPM (RHEL 8) → **2.6 RPM (RHEL 9)** | 2.6 RPM on RHEL 9 | 1 (OS + AAP) | ✅ Yes | **DEFAULT.** One outage, lands on terminal supported RPM version. Best cost/risk balance for staying on RPM. |
| **C** | 2.5 RPM (RHEL 8) → 2.6 RPM (RHEL 9) → **2.6 Containerized** | 2.6 Containerized | 2 (B, then container migration) | ✅ Yes | Customer wants to reach the strategic end state. Path B first, then the same-major-version RPM→container migration. **Recommended route to containerized.** |
| **D** | 2.5 RPM (RHEL 8) → 2.5 Containerized → **2.6 Containerized** | 2.6 Containerized | 2 (container migration, then upgrade) | ✅ Yes | Only if the customer wants off RPM *immediately* and is willing to do the container migration at 2.5. More moving parts than C; rarely the better choice. |
| **E** | 2.5 RPM (RHEL 8) → **2.6 Containerized (one move)** | — | — | ❌ **No** | Never. Changes both major version *and* install type in a single migration. Red Hat locks install-type changes to the same major version. This is the "one that is not supported." |

**Why the unsupported path (E) matters:** field guidance sometimes assumes you can jump straight from 2.5 RPM to 2.6 containerized. You cannot. The install-type migration (RPM → container) is only supported *within a single major version*. That constraint is what forces the two-window shape of Paths C and D.

## Why Path B is the Default Recommendation

- Single planned outage instead of two — half the change-management overhead.
- Lands the customer on the supported terminal RPM version. They don't have to revisit until they choose to go containerized (which they should do before AAP 2.7 ships).
- AAP 2.5 RPM on RHEL 9 is technically possible, but it's a dead-end intermediate state. To later move to containerized, they would still need to upgrade to 2.6 RPM first (because the RPM → Containerized migration is locked to the same major version). Bundling avoids that extra step.
- AAP 2.6 brings real value the customer would want anyway: gateway architecture improvements, EDA enhancements, performance work.

Exception: If the customer's automation portfolio is large and complex (hundreds of templates, deep custom credential types, heavy survey usage), and they have any concern that an AAP version bump may break something, do Path A (OS-only, stay on 2.5 RPM) and isolate the AAP version upgrade to a separate maintenance window.

## Why Path C is the Strategic Recommendation

- RPM is deprecated and **removed in 2.7**. Containerized is the destination for every non-OpenShift customer; the only question is timing.
- Path C = Path B (which you should do anyway) + one additional, same-version, backup/restore migration. The second window is smaller and lower-risk than the first because there is no AAP version change involved.
- Containerized is **rootless by default** (all services run as unprivileged Podman containers under a non-root user) — a security and operability win.
- Doing B now and C later lets the customer validate on 2.6 RPM before taking on the install-type change, spreading risk across two controlled windows.

# Pre-flight Checks (One Week Before Cutover)

## Information to gather from the existing RHEL 8 host

- Exact AAP 2.5.x version (`sudo dnf list installed | grep automation-controller`).
- RHEL 8 minor version.
- Inventory file location and any customizations.
- Custom EE list (controller's local registry vs. hub).
- External integrations: SAML/OIDC, LDAP, Slack, GitHub webhooks, ServiceNow, monitoring scrape targets.
- Postgres location (embedded vs. external) and version.
- Hub content size (`du -sh /var/lib/pulp/`).
- Latest successful backup tarball (date, size, location).
- SECRET_KEY contents AND exact byte count from each RHEL 8 host (gateway / controller / EDA) — see Pitfall #9.

## Latest 2.5.x verification

Confirm the customer is on the most current 2.5.x release before starting. Red Hat's upgrade matrix supports "upgrades from the latest 2.5 version to 2.6." If they are on 2.5.0 and the current 2.5.x is 2.5.4, patch to 2.5.4 first, validate, then back up. This avoids edge cases in the cross-version restore.

## RHEL 9 floor

AAP 2.6 release notes raised the RHEL 9 floor from 9.2 to 9.4. The new RHEL 9 host must be on 9.4 or later — confirm before the build is finalized. (The containerized installer also supports RHEL 10; the RPM installer does not.)

## PostgreSQL floor (applies to both RPM and container)

AAP 2.6 requires PostgreSQL **15, 16, or 17**. If the customer runs an external Postgres on 13 or earlier, that database must be upgraded to 15+ *before* the AAP 2.6 upgrade — this is a hard gate, not a warning. Embedded/managed Postgres is handled by the installer; external Postgres is the customer's responsibility.

# Path B Runbook — Cutover Procedure

## Step 1: Patch to latest 2.5.x and back up

```bash
# On the existing RHEL 8 host
cd /opt/ansible-automation-platform/installer-2.5.x-<exact>/

# (Optional but recommended) patch to latest 2.5.x first
sudo ./setup.sh

# Take the full backup
sudo ./setup.sh -b

# Output: /var/backups/automation-platform/automation-platform-backup-<ts>.tar.gz
```

Copy the backup tarball AND the inventory file off-host immediately:

```bash
tar czf /tmp/aap-migration-payload.tar.gz \
  /var/backups/automation-platform/automation-platform-backup-<ts>.tar.gz \
  /opt/ansible-automation-platform/installer-2.5.x-<exact>/inventory
scp /tmp/aap-migration-payload.tar.gz user@safe-storage:/path/
```

## Step 2: Provision the new RHEL 9 host (same hostname/IP)

Use the same hostname and IP as the existing RHEL 8 host. Reusing the endpoint avoids hunting down GitHub webhooks, SAML redirect URIs, Slack tokens, and monitoring scrape targets that all reference the controller URL.

Schedule a maintenance window. During the window: power off RHEL 8, stand up RHEL 9 with the same hostname/IP, validate, then decommission RHEL 8 after 1–2 weeks of clean operation.

```bash
# On the new RHEL 9 host
sudo subscription-manager register
sudo subscription-manager attach --auto

# Enable the AAP 2.6 channel for RHEL 9 (note: 2.6 not 2.5)
sudo subscription-manager repos \
  --enable=rhel-9-for-x86_64-baseos-rpms \
  --enable=rhel-9-for-x86_64-appstream-rpms \
  --enable=ansible-automation-platform-2.6-for-rhel-9-x86_64-rpms

# Baseline updates
sudo dnf update -y
```

## Step 3: Install AAP 2.5 RPM on the new RHEL 9 host

Restoring a 2.5 backup requires AAP 2.5 to be installed first. The customer's existing 2.5 RPM installer bundle (the same one they had on RHEL 8) is what they need here. AAP 2.5 RPM supports both RHEL 8 and RHEL 9, so the installer runs cleanly on the new host.

Adjust the inventory file for the new host (mostly: confirm hostnames/IPs are correct; passwords and most variables can stay the same).

```bash
# Transfer the 2.5 installer bundle and inventory to the new host
cd ansible-automation-platform-installer-2.5.x-<exact>/
vi inventory   # confirm hostnames/IPs match the RHEL 9 host

# Install AAP 2.5 (will land in a fresh state)
sudo ./setup.sh
```

Validate the empty 2.5 install before restoring:

```bash
sudo systemctl status automation-controller automation-hub automation-eda-controller
curl -sk https://<host>/api/controller/v2/ping/ | jq .version
```

> **⚠ If you are pointing this fresh install at an existing live database instead of restoring from a tarball:**
>
> You MUST pre-stage the gateway / controller / EDA SECRET_KEY files on the RHEL 9 host filesystems BEFORE running `./setup.sh`, using the exact key values from the old RHEL 8 install. Setting the documented `automationgateway_secret_key` / `automationcontroller_secret_key` inventory variables DOES NOT WORK — the installer roles' `secret_key.yml` tasks read from disk if a file exists and otherwise generate a fresh random value, overwriting any inventory variable in either branch. Skipping the file pre-stage means the schema migration fails with `cryptography.exceptions.InvalidSignature` and `cryptography.fernet.InvalidToken` errors and the install aborts. The `setup.sh -r` restore path covered in Step 4 handles this automatically — this callout only applies if you are skipping `setup.sh -r` and pointing at the existing DB directly. See Pitfall #9 for the file paths and exact pre-staging commands.

## Step 4: Restore the backup into AAP 2.5

```bash
# Move backup to new host
scp user@safe-storage:/path/aap-migration-payload.tar.gz ~/
cd ~ && tar xzf aap-migration-payload.tar.gz

# Run restore using the 2.5 installer
cd ansible-automation-platform-installer-2.5.x-<exact>/
sudo ./setup.sh -r /home/<user>/var/backups/automation-platform/automation-platform-backup-<ts>.tar.gz
```

Restore time is dominated by hub content (Pulp). For a typical install: 15 minutes to 2 hours. For a heavy hub: up to 4–6 hours.

**Validation gate before continuing:**

- All services green: automation-controller, automation-hub, automation-eda-controller, automation-gateway
- Project count matches pre-migration
- Job template count matches pre-migration
- Manually launch a known-good template, confirm it runs to completion
- Confirm SCM project sync works (validates GitHub PAT survived)

## Step 5: In-place upgrade AAP 2.5 → AAP 2.6 RPM

Now run the AAP 2.6 RPM installer against the restored 2.5 install. Red Hat's in-place upgrade path handles the version transition cleanly.

```bash
# Pull AAP 2.6 RPM installer bundle from access.redhat.com
tar xf ansible-automation-platform-installer-2.6.x-<exact>.tar.gz
cd ansible-automation-platform-installer-2.6.x-<exact>/

# Most variables transfer; new gateway-specific vars may be required
# Read the 2.6 release notes for any new mandatory inventory variables
vi inventory

# Run the upgrade
sudo ./setup.sh
```

Post-upgrade validation:

```bash
# Confirm 2.6 is running
curl -sk https://<host>/api/controller/v2/ping/ | jq .version
# Expected: "4.7.x" (controller is internally version 4.7.x in AAP 2.6)

# Gateway health
curl -sk https://<host>/api/gateway/v1/ping/ | jq

# UI smoke test
# - Login via gateway
# - Launch a job template
# - Confirm hub content visible
# - Confirm EDA activations restart correctly (may need manual restart)
```

## Step 6: Integration sweep

After Step 5 passes validation, sweep the integrations to confirm none broke:

- SAML/OIDC login flow works end-to-end
- Slack notification fires from a test job
- GitHub webhook triggers expected template (test commit on a project repo)
- ServiceNow or other ticketing integration, if applicable
- Prometheus / external monitoring scrapes succeed
- Backup playbook runs successfully (on the 2.6 install — back up the new state)

## Step 7: Decommission RHEL 8 host

- Keep RHEL 8 host powered off (not deleted) for 1–2 weeks
- After 2 weeks of clean operation on RHEL 9, snapshot one last time and decommission

**At the end of Path B the customer is on the terminal supported RPM version. If the destination is containerized (Path C), continue to the next section — ideally in a separate, later maintenance window once 2.6 RPM has proven stable.**

# Path C Runbook — Migrate AAP 2.6 RPM → 2.6 Containerized

This is the second window of Path C. **Precondition: the customer is already on AAP 2.6 RPM (they completed Path B) and it has run cleanly.** The move from RPM to containerized is a *same-major-version, install-type* migration — Red Hat supports it only because both sides are 2.6. It is a **backup-and-restore migration onto a fresh containerized deployment**, not an in-place conversion of the RPM host.

Two supported approaches are documented below:

- **Path C-1 (recommended): installer backup → containerized restore.** Cleanest, closest in spirit to Path B. Use when the customer uses managed/embedded Postgres or is happy to let the containerized installer own the database.
- **Path C-2 (external-DB / surgical): pg_dump per service + secret-key injection.** Use when the customer runs an external Postgres they intend to keep, or needs fine-grained control. This is the flow in Red Hat's "RPM to container" developer article.

## Containerized Pre-flight (in addition to the general pre-flight above)

- **Target host OS:** RHEL 9.4+ **or RHEL 10**. The containerized installer supports RHEL 10; the RPM installer does not — this migration is the customer's first opportunity to move to RHEL 10 if they want it.
- **Non-root install user:** Containerized AAP runs **rootless**. Create a dedicated unprivileged user (e.g. `aap`) with passwordless `sudo` for the install, and enable systemd lingering so services survive logout/reboot:
  ```bash
  sudo loginctl enable-linger aap
  ```
- **Podman, not Docker:** `podman --version` must succeed. The containerized installer is built on rootless Podman; Docker is not interchangeable.
- **Container storage:** All images and volumes live under `~/.local/share/containers/` for the install user. Budget **~60 GB** of free space there, plus room for the restored hub content.
- **ansible-core:** `sudo dnf install ansible-core` from AppStream on the target host.
- **Registry credentials:** The install pulls images from `registry.redhat.io`. Have a Red Hat registry service-account username/token ready (`registry_username` / `registry_password` in the inventory).
- **PostgreSQL 15/16/17:** Confirm from the DB node as the postgres user: `psql -c 'SELECT version();'`. External Postgres < 15 must be upgraded first.
- **Capture the four secret keys from the 2.6 RPM host** (needed for both C-1 restore validation and mandatory for C-2 — see the callout in Step C-2.2).

## Step C.1: Back up the running 2.6 RPM deployment

```bash
# On the 2.6 RPM host
cd ansible-automation-platform-installer-2.6.x-<exact>/
sudo ./setup.sh -e 'backup_dest=/path/to/backups/' -e 'use_compression=True' -b

# Copy the resulting tarball off-host to the container build host
scp /path/to/backups/automation-platform-backup-<ts>.tar.gz aap@container-host:/home/aap/artifact/
```

## Step C.2: Provision the containerized host and lay down the installer

```bash
# On the new RHEL 9.4+/10 host, as the non-root install user (e.g. aap)
sudo loginctl enable-linger $(whoami)
sudo dnf install -y ansible-core
podman --version   # verify rootless podman is present

# Extract the containerized installer bundle
tar xvf ansible-automation-platform-containerized-setup-2.6-1.tar.gz
cd ansible-automation-platform-containerized-setup-2.6-1
```

Build the containerized `inventory` file. Unlike the RPM inventory, the containerized inventory uses `ansible_connection=local` and per-component groups. Minimum shape for a single-node all-in-one:

```ini
[automationgateway]
localhost ansible_connection=local

[automationcontroller]
localhost ansible_connection=local

[automationhub]
localhost ansible_connection=local

[automationeda]
localhost ansible_connection=local

[database]
localhost ansible_connection=local

[all:vars]
postgresql_admin_username=postgres
postgresql_admin_password=<pg-admin-pw>
registry_username=<redhat-registry-service-account>
registry_password=<redhat-registry-token>
gateway_admin_password=<gw-admin-pw>
controller_admin_password=<controller-admin-pw>
hub_admin_password=<hub-admin-pw>
eda_admin_password=<eda-admin-pw>
redis_mode=standalone
```

> Growth/HA topologies split gateway, controller, hub, EDA, Redis, and database onto separate hosts (each with its own `[group]` entry and `ansible_connection`), and set `redis_mode=cluster`. Read the 2.6 *Containerized installation* guide for the full variable set and any newly mandatory keys.

## Step C.2 (secret keys) — Extract the four keys from the 2.6 RPM host

**Do this before installing.** In the containerized world these keys are supplied to the installer as **extra vars and they are honored** — this is the important difference from the RPM installer (Pitfall #9), where the equivalent inventory variables are silently overwritten. Extract from the old RPM host and drop into a `secrets.yml`:

```bash
# On the 2.6 RPM host — capture the exact values (watch for trailing newlines)
cat /etc/tower/SECRET_KEY                                    # -> controller_secret_key
cat /etc/ansible-automation-platform/gateway/SECRET_KEY      # -> gateway_secret_key
grep '^SECRET_KEY' /etc/pulp/settings.py | awk -F'=' '{print $2}'   # -> hub_secret_key
cat /etc/pulp/certs/database_fields.symmetric.key            # -> hub_db_fields_encryption_key
```

`~/artifact/secrets.yml` on the container host:

```yaml
controller_secret_key: "<value from /etc/tower/SECRET_KEY>"
gateway_secret_key: "<value from gateway SECRET_KEY>"
hub_secret_key: "<value from pulp settings.py>"
hub_db_fields_encryption_key: "<value from database_fields.symmetric.key>"
```

## Path C-1: Installer backup → containerized restore (recommended)

Install the containerized platform, passing the preserved secret keys, then restore the backup tarball:

```bash
# 1. Install containerized AAP 2.6, honoring the preserved secret keys
ansible-playbook -i inventory ansible.containerized_installer.install \
  -e @~/artifact/secrets.yml

# 2. Restore the 2.6 RPM backup into the containerized deployment
ansible-playbook -i inventory ansible.containerized_installer.restore \
  -e backup_file=/home/aap/artifact/automation-platform-backup-<ts>.tar.gz
```

Proceed to **Step C.3 (validation)**.

## Path C-2: External-DB / surgical migration (pg_dump + restore)

Use when keeping an external Postgres or when C-1's tarball restore is not appropriate. Dump each service database from the old side, install containerized while injecting the secret keys, restore the dumps, then run the gateway cleanup.

```bash
# On the RPM gateway node, as the postgres user — dump each DB
pg_dump -h pg.example.com -U awx              -d awx             --clean --create -Fc -f awx.pgc
pg_dump -h pg.example.com -U automationhub    -d automationhub   --clean --create -Fc -f pah.pgc
pg_dump -h pg.example.com -U automationgateway -d automationgateway --clean --create -Fc -f gw.pgc

# Install containerized AAP 2.6 with the preserved secret keys
ansible-playbook -i inventory ansible.containerized_installer.install \
  -e @~/artifact/secrets.yml

# Restore each dump into the 2.6 Postgres (15/16/17)
pg_restore --clean --create --no-owner -h pg26.example.com -U awx              -d template1 awx.pgc
pg_restore --clean --create --no-owner -h pg26.example.com -U automationhub    -d template1 pah.pgc
pg_restore --clean --create --no-owner -h pg26.example.com -U automationgateway -d template1 gw.pgc
```

**Gateway post-migration cleanup** (removes stale service-node/port objects carried over from the RPM topology so the gateway rebuilds them for the container layout):

```bash
# Exec into the gateway container, then:
aap-gateway-manage migrate
aap-gateway-manage shell_plus
# In the shell:
#   HTTPPort.objects.all().delete()
#   ServiceNode.objects.all().delete()
#   ServiceCluster.objects.all().delete()
```

## Step C.3: Validate the containerized deployment

```bash
# Services are rootless systemd --user units — check as the install user
systemctl --user list-units 'automation-*' --type=service

# Gateway + controller health
curl -sk https://<host>/api/gateway/v1/ping/ | jq
curl -sk https://<host>/api/controller/v2/ping/ | jq .version
```

**Validation gate:**

- All containerized services active under `systemctl --user`
- Project and job-template counts match the pre-migration 2.6 RPM state
- A known-good template runs to completion
- Hub content is present and installable
- EDA activations restart cleanly
- Encrypted credentials decrypt (proves the secret keys carried over correctly — launch a job that uses a machine credential)

## Step C.4: Take a fresh containerized backup and decommission RPM

```bash
# Back up the new containerized state
ansible-playbook -i inventory ansible.containerized_installer.backup
```

- Keep the 2.6 RPM host powered off (not deleted) for 1–2 weeks.
- After clean operation on containerized, snapshot and decommission the RPM host.

# Network and IP Address Considerations

Short answer: the customer is not required to keep the same IP addresses on the new RHEL 9 cluster — but keeping them is dramatically less work. The AAP backup/restore process itself does not care about IPs. What cares is everything around AAP that has IP literals hard-coded somewhere.

## Three practical strategies (in order of preference)

### A. Same IP (lowest risk — recommended when possible)

Schedule a maintenance window. Drain users, stop AAP on RHEL 8, change RHEL 8's IP to a temporary address (so it can still be reached for backup retrieval if needed), give the new RHEL 9 host the original IP. Install AAP 2.5 RPM on RHEL 9, restore the backup, then upgrade in place to 2.6. Nothing external knows the difference. The customer's integrations team sees zero work.

### B. New IP + DNS pointer flip (medium effort)

Works if AAP is reached at an FQDN (e.g., aap.customer.com) rather than at an IP. At cutover, the DNS A record (or CNAME) gets pointed from old IP to new IP. Anything talking to AAP via FQDN auto-follows. The customer still has to audit for IP-literal references — every place where someone wrote the IP instead of the FQDN — and update those. Mature shops manage; 10-year-old installs with organic growth can take days.

### C. New IP + audit sweep (highest effort)

If neither DNS pointer flip nor same-IP is feasible (new VLAN, new datacenter, no DNS authority), the customer's integrations team owns the change. Build a checklist from the table above. Plan 2–3 weeks of integration work, not 1 day.

**Containerized note:** the Path C migration lands on a *fresh* host by definition, so it is effectively a new-endpoint event. Prefer FQDN + DNS flip (strategy B) so the container host can come up on its own IP and inherit the name at cutover. The gateway is still the front door (see below), so external integrations only need the one hostname.

# Cutover with a Load Balancer

Short answer: an LB in front of the AAP cluster dramatically simplifies the IP question and gives the customer a real parallel-run capability with rollback as a single LB pool weight change.

With an LB in front: the external world talks to the VIP, never to individual AAP nodes. Backend node IPs become an implementation detail of the LB pool. The new RHEL 9 cluster can stand up on completely different IPs without breaking a single external integration. Both clusters can run live behind the LB during cutover for safe canarying.

## AAP 2.6 gateway-specific considerations

AAP 2.6's architecture promotes the automation-gateway as the front door (it brokers auth and proxies to controller/hub/EDA). If the customer's LB was set up in the AAP 2.4 era, its health check probably hits the controller `/api/v2/ping/` — which now returns 404 against the gateway. This is the most common pre-cutover surprise.

Also note: in 2.6 the gateway listens on 443 only (HTTPS) by default — not 80 + 443 like 2.4. If the LB does TLS termination + re-encrypt to backend, the backend port is 443, not 80. This is true for both the RPM and containerized 2.6 gateway.

## Recommended cutover sequence with an LB

- Build the new RHEL 9 cluster with whatever IPs are convenient. Different subnet, different VLAN, different region — does not matter as long as the LB can reach them.
- Install AAP 2.5 RPM on RHEL 9 → restore the production backup → smoke-test by hitting the new nodes directly (bypassing the LB) to confirm everything restored cleanly.
- Run the 2.5 → 2.6 in-place upgrade on the new cluster. Smoke-test again, directly.
- Add the new RHEL 9 nodes to the LB pool — but set their weight to 0 initially. They are present but get no traffic.
- Verify the LB health check passes against the new nodes at weight 0. Fix the health-check path if needed (this is where the 2.4 → 2.6 gateway endpoint change bites).
- Canary: bump one new node's weight to ~10%. Watch for an hour. If clean, increase to 50%, then 100%.
- Drain the old RHEL 8 nodes to weight 0. Watch for a day.
- Remove the old nodes from the LB pool entirely. Decommission per Step 7 of the runbook.

Rollback at any step is a single LB pool weight change — back to old nodes. Zero downtime, zero external coordination.

**The same LB parallel-run pattern applies to the Path C container migration:** stand up the containerized cluster behind the LB at weight 0, validate directly, canary, then drain the RPM nodes. Rollback stays a single weight change back to the RPM pool.

# Common Pitfalls

### 1. Mismatched installer versions

The most common failure mode: trying to restore a 2.5.0 backup with a 2.5.4 installer. Versions must match exactly for the restore. Patch to the latest 2.5.x on the old host first, then back up.

### 2. Custom EEs not in the backup

EEs pushed only to the controller's local registry (never to hub) live in `/var/lib/awx/...`. Backup captures the registry, but verify the EE list pre-flight and re-push any that didn't make it. Custom EEs are the #2 source of post-migration job failures.

### 3. Inventory file customizations forgotten

Customers customize the inventory over years (timeout values, ad-hoc settings, organization-specific vars). Build extra time to diff their RHEL 8 inventory against the new RHEL 9 inventory and re-apply customizations. **Note:** this diff is *not* reusable for Path C — the containerized inventory is a different format (per-component groups, `ansible_connection=local`, registry creds); translate, don't copy.

### 4. GitHub webhooks pointing at old URL

If the IP/hostname does change despite recommendations, every GitHub webhook pointed at the old controller URL silently breaks. Audit GitHub project settings or grep webhook lists pre-cutover.

### 5. SELinux contexts on custom mounts

Customers running AAP on hosts with custom mounts for `/var/lib/awx` or `/var/lib/pulp` sometimes have hand-set SELinux contexts. RHEL 9 default policy may differ slightly. Audit custom contexts and recreate on RHEL 9.

### 6. Subscription-manager on the new host

New RHEL 9 host = new RHEL subscription attachment. AAP entitlement bundles RHEL for the AAP host, but the new host has to be registered. Verify with the customer's account team if there's any ambiguity.

### 7. Job runtime variance

AAP 2.6 dispatcher / receptor / podman lifecycle is slightly different from 2.5. Long-running jobs may see ±5–10% time variance. Tell automation owners in advance so it doesn't trip duration-based alerts.

### 8. Audit log gap during cutover

During the maintenance window, no events are recorded. If the customer has SIEM or compliance attestation that depends on continuous AAP audit logs, document the gap and have an out-of-band record of the window for auditors.

### 9. Reusing an existing database — SECRET_KEY / Fernet handling (the inventory variable does NOT work)

Symptom: `setup.sh` fails at the gateway DB schema migration step with:

```
TASK [ansible.automation_platform_installer.automationgateway : Migrate the gateway database schema]
cryptography.exceptions.InvalidSignature: Signature did not match digest
cryptography.fernet.InvalidToken
```

**Cause:** AAP encrypts secrets in the database (credentials, OAuth tokens, vault payloads, SAML/OIDC client secrets) with per-service Fernet keys. When you point a fresh install at an existing AAP database, the new install generates fresh keys — which cannot decrypt the rows written by the old install. The gateway's first migration touches those encrypted columns, fails to decrypt, and aborts.

When this hits: any scenario where the new RHEL 9 install is pointed at a pre-existing database. This includes (a) reusing a live external Postgres from the RHEL 8 cluster without using `setup.sh -r`, (b) restoring a Postgres dump into the new install and skipping the AAP restore wrapper, or (c) an aborted `setup.sh -r` run that left the DB partially migrated, followed by a re-run with regenerated keys. The supported `setup.sh -r` path handles this automatically — if you went around it, you have to handle it by hand.

**Critical: the documented inventory variables do not work (RPM installer).**

Field-verified against installer 2.5-22.1: setting `automationgateway_secret_key` (in `[all:vars]` or `[automationgateway:vars]`) is silently overwritten. The role's `tasks/secret_key.yml` unconditionally calls `set_fact` with either the slurped file contents or a freshly generated `lookup('password', ...)` value — neither branch checks whether the variable was already defined. The same pattern exists in the automationcontroller and automationedacontroller roles. Despite what some Red Hat docs and KB articles imply, you cannot inject a known SECRET_KEY through the inventory file. This is a real installer-vs-docs gap and is worth opening a Red Hat case so the next customer in this situation does not lose a day to it.

> **Contrast — the containerized installer is different.** In Path C the `controller_secret_key` / `gateway_secret_key` / `hub_secret_key` / `hub_db_fields_encryption_key` values *are* honored when passed as extra vars (`-e @secrets.yml`). So the pre-stage-on-disk workaround below is an RPM-only problem; on the containerized side you inject the keys through the installer as designed. See Path C, Step C.2 (secret keys).

**The supported workaround (RPM) — pre-stage the SECRET_KEY files on disk before running setup.sh.**

The stat/slurp/generate logic in `secret_key.yml` checks for an existing file at a fixed path. If the file is present, it slurps the contents (b64decode) and sets the fact from disk. Pre-creating the file with the old key bytes — root-owned, 0600 — works because slurp runs as root via become and does not care about ownership.

Pre-stage commands (run on EACH new RHEL 9 host of the matching role, before `./setup.sh`):

```bash
# --- Gateway hosts ---
sudo mkdir -p /etc/ansible-automation-platform/gateway
sudo touch /etc/ansible-automation-platform/gateway/SECRET_KEY
sudo chmod 0600 /etc/ansible-automation-platform/gateway/SECRET_KEY
sudo chown root:root /etc/ansible-automation-platform/gateway/SECRET_KEY
printf '%s' '<paste the EXACT raw key from the old RHEL 8 gateway>' | \
  sudo tee /etc/ansible-automation-platform/gateway/SECRET_KEY > /dev/null

# --- Controller hosts ---
sudo mkdir -p /etc/tower
sudo touch /etc/tower/SECRET_KEY
sudo chmod 0600 /etc/tower/SECRET_KEY
sudo chown root:root /etc/tower/SECRET_KEY
printf '%s' '<paste the EXACT raw key from the old RHEL 8 controller>' | \
  sudo tee /etc/tower/SECRET_KEY > /dev/null

# --- EDA hosts ---
sudo mkdir -p /etc/ansible-automation-platform/eda
sudo touch /etc/ansible-automation-platform/eda/SECRET_KEY
sudo chmod 0600 /etc/ansible-automation-platform/eda/SECRET_KEY
sudo chown root:root /etc/ansible-automation-platform/eda/SECRET_KEY
printf '%s' '<paste the EXACT raw key from the old RHEL 8 EDA host>' | \
  sudo tee /etc/ansible-automation-platform/eda/SECRET_KEY > /dev/null
```

**Byte-exact match is mandatory. A trailing newline produces a different decoded key.**

```bash
# On the old RHEL 8 host:
sudo wc -c /etc/ansible-automation-platform/gateway/SECRET_KEY

# On the new RHEL 9 host after pre-staging:
sudo wc -c /etc/ansible-automation-platform/gateway/SECRET_KEY

# Counts MUST match. If RHEL 9 is one byte larger, your shell added a \n —
# either fix the printf invocation or chop the last byte:
# sudo truncate -s <expected_size> /etc/ansible-automation-platform/gateway/SECRET_KEY
```

Use `printf '%s'` (NOT `echo`, and NOT `echo -n` in scripts where shell-builtin behavior is uncertain) to avoid trailing newlines. After staging, run `sudo sha256sum` on both old and new files and confirm they match.

**Stage all three even if only the gateway errored.** When the gateway migration aborts, the controller and EDA migrations have not yet attempted decryption — they have not yet failed. The moment you re-run `setup.sh`, they will. Stage all three keys up front to avoid a second round of fail-and-fix.

Verify the same stat/slurp/generate pattern in the controller and EDA roles before relying on the paths above (some installer builds shifted EDA to `/etc/ansible-automation-platform/eda-server/SECRET_KEY`):

```bash
cd <installer-bundle>/collections/ansible_collections/ansible/automation_platform_installer/roles/
cat automationcontroller/tasks/secret_key.yml
cat automationedacontroller/tasks/secret_key.yml
```

**Recovery if a partial migration already ran with the wrong keys:** take a fresh dump of the current (broken) DB for evidence; restore from the pre-migration backup (Step 1 of Path B); if using VM snapshots, restore the full VM snapshots taken BEFORE any install attempt (otherwise the bad SECRET_KEY files remain on disk and get re-read); pre-stage the three keys on the restored VMs; re-run `setup.sh`. Do not attempt to mix old and new keys to recover a half-migrated DB — per-row recovery is unsupported.

### 10. Containerized host: missing `enable-linger` kills services on logout (Path C)

Rootless Podman services run under the install user's systemd session. Without `sudo loginctl enable-linger <user>`, the containers stop when that user logs out and do not start at boot — the platform looks "installed" but dies the moment the installer's SSH session ends. Enable lingering before install and confirm with `loginctl show-user <user> | grep Linger`.

### 11. Containerized host: registry auth and container storage (Path C)

Two fresh-install snags unique to the container path: (a) image pulls from `registry.redhat.io` fail if `registry_username`/`registry_password` are wrong or point at a personal login instead of a **registry service account** — use a service account token; (b) `~/.local/share/containers/` needs ~60 GB *plus* the restored hub content. If `/home` is a small partition, images and volumes fill it mid-restore. Size the install user's home accordingly or relocate container storage before install.

### 12. Containerized host: stale gateway service objects after DB restore (Path C-2)

When you restore RPM-era databases into the container deployment (Path C-2), the gateway carries over `HTTPPort` / `ServiceNode` / `ServiceCluster` rows that describe the *old* topology. Run `aap-gateway-manage migrate` then delete those objects via `aap-gateway-manage shell_plus` (commands in Step C-2) so the gateway rebuilds routing for the container layout. Skipping this leaves the gateway proxying to endpoints that no longer exist.

# Cutover-Day Timing Template

## Path B — single-node AAP with ~50 templates and a modest hub

- Pre-flight verification: 30 min
- Backup creation (Step 1): 30 min
- RHEL 9 provision + subscription (Step 2): 20 min
- AAP 2.5 install on RHEL 9 (Step 3): 25 min
- Restore (Step 4): 60–90 min
- 2.5 → 2.6 in-place upgrade (Step 5): 30 min
- Integration sweep (Step 6): 30 min

**Total: approximately 3.5 hours for a clean single-node migration.**

Multi-node growth topologies (separate hub, EDA, gateway VMs) extend this proportionally — typically 5–7 hours, since each VM needs its own RHEL 9 cutover.

## Path C — 2.6 RPM → 2.6 Containerized (separate window, single-node)

- Containerized pre-flight (user, linger, podman, storage, registry creds): 30 min
- Backup the 2.6 RPM deployment (Step C.1): 30 min
- Provision container host + extract installer + build inventory (Step C.2): 40 min
- Extract + stage the four secret keys (Step C.2 secret keys): 15 min
- Containerized install (C-1 install): 30–45 min
- Restore into containerized (C-1 restore, hub-dominated): 60–90 min
- Validation + fresh backup (Steps C.3–C.4): 30 min

**Total: approximately 3.5–4 hours for a clean single-node container migration.** Path C-2 (external DB dump/restore + gateway cleanup) adds ~30–60 min. Growth topologies scale proportionally.

Always do a dry run in non-prod first. The first cutover always uncovers something — that is true even with careful planning. A dry run in a staging environment catches inventory translation gaps, EE registry issues, and integration breakage before the production window. **For Path C specifically, the dry run is where you validate that the containerized inventory translation and the secret-key injection actually work — do not discover a Fernet mismatch in the production window.**

# Questions to Ask the Customer Before Quoting Timeline

- AAP topology: single-node, or growth (separate controller / hub / EDA / database VMs)?
- Exact AAP 2.5.x version they are on today?
- Internal or external Postgres? If external, which version, who manages it? **(Must be 15/16/17 for 2.6 — plan a Postgres upgrade first if on 13/14.)**
- Will they reuse the existing database (live or via dump), or use the supported `setup.sh -r` backup/restore path? If reusing, see Pitfall #9.
- Hub content size (`du -sh /var/lib/pulp/`)?
- Number of external integrations: SAML/OIDC IdPs, Slack workspaces, webhook sources, ticketing systems?
- Subscription source: direct Red Hat CDN, or Satellite-managed?
- RHEL target version — 9.4+ for RPM; **9.4+ or RHEL 10** if going containerized?
- Have they ever tested a backup/restore? If not, this migration is when they find out their backup is broken — pre-validate with a restore drill into a throwaway VM first.
- **Destination: stay on RPM (Path A or B), or reach containerized (Path C, or D if they want off RPM immediately)? RPM is removed in 2.7 — if they stay on RPM now, when is the containerized window?**
- **For containerized (Path C): is there a dedicated non-root install user and a Red Hat registry service account available? Is `/home` sized for ~60 GB of container storage plus hub content?**
- Hostname/IP: can they reuse the existing endpoint, or are they forced to change?

# Sources

- Red Hat Ansible Automation Platform 2.6 RPM installation — https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html-single/rpm_installation/index
- AAP 2.6 RPM upgrade guide — https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/rpm_upgrade/aap-upgrading-platform
- AAP 2.6 Containerized installation — https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html-single/containerized_installation/index
- AAP 2.6 Back up and restore your containerized deployment — https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/administer-back_up_and_restore_your_containerized_deployment
- **Migrating AAP: From RPM to container on RHEL (Red Hat Developer)** — https://developers.redhat.com/articles/2025/12/04/migrating-ansible-automation-platform-rpm-container
- AAP 2.6 Release Notes — https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html-single/release_notes/index
- AAP 2.6 Planning Your Installation — https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html-single/planning_your_installation/index
- Installation and Upgrade Guide for AAP 2.6 (Red Hat blog) — https://www.redhat.com/en/blog/installation-and-upgrade-guide-ansible-automation-platform-26
- AAP 2.next preview release notes (RPM removal confirmation) — https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.next/html-single/ansible_automation_platform_preview_release_notes/index

---

*Authorship: prepared by Tim Coulter with Claude (Anthropic). Container-migration steps are grounded in Red Hat's 2.6 containerized-installation and RPM-to-container migration documentation (see Sources); confirm exact inventory variables and playbook names against the version-matched installer bundle before a production run.*
