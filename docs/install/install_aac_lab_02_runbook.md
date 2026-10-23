> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: SPLIT-PORTSx6, RETIRED-HOSTx5, HOST:8181x2, AAP-2.5/2.6x2.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAC Install Runbook — LAB_UTIL_HOST (LAB_UTIL_HOST)

**Target host:** AIBERZY XG1-370, RHEL 9, hostname `LAB_UTIL_HOST`, IP `LAB_UTIL_HOST`
**Reference:** `docs/install/COMPLETE_INSTALLATION_GUIDE.md` (the full 13-phase guide)
**Build date:** 2026-05-31
**Version:** v1.0

## Revision history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-06-02 | Initial runbook — captures the four installer gotchas hit during the 2026-05-31 LAB_UTIL_HOST build. |

This runbook is the **lab-tailored** version of the full install guide.
The instructions below are the sequence that actually worked on a clean
box; the ⚠️ callouts capture the four issues hit during the 2026-05-31
build that the upstream guide does not yet document.

---

## 0. What you need before you start

- Console + SSH access to LAB_UTIL_HOST as a sudo-capable user
- A Red Hat account (`rh-ee-tcoulter` works; offline token lives in vault)
- A **Registry Service Account token** from https://access.redhat.com/terms-based-registry/
  — required for the AAP installer to pull container images. ⚠️ **Do NOT use your Red Hat account password.** (See gotcha #3 below.)
- GitHub PAT with `repo` + `read:packages` scope
- AAP 2.6 containerized setup bundle downloaded to the box:
  `ansible-automation-platform-containerized-setup-bundle-2.6-1-x86_64.tar.gz`
- A vault password you've decided on, written down

---

## Phase 1 — OS preparation

Follow `COMPLETE_INSTALLATION_GUIDE.md §3 Phase 1` verbatim. No deviations
were needed on LAB_UTIL_HOST for this phase. Summary of the six steps:

| Step | What | Verify |
|---|---|---|
| 1.1 | `sudo subscription-manager register` with your Red Hat account | `subscription-manager status` shows "Current" |
| 1.2 | `sudo dnf update -y && sudo reboot` | system back up, new kernel running |
| 1.3 | Install `podman`, `git`, `python3.11`, `python3-pip`, `firewalld`, `policycoreutils-python-utils`, `jq` | `podman --version`, `python3.11 --version` |
| 1.4 | Open firewall ports — see table below | `sudo firewall-cmd --list-all` |
| 1.5 | Set SELinux to Enforcing, create `/opt/aac/policies/{security,compliance,ot}` with `container_file_t` context | `getenforce` → `Enforcing` |
| 1.6 | Create `aapuser1`, give it a password, add to sudoers (`%aapuser1 ALL=(ALL) NOPASSWD: ALL`) | `sudo -u aapuser1 sudo -l` |

**Required firewall ports** (1.4):

```
80, 443                   # AAP web UI
8181, 8182, 8183          # OPA security / compliance / OT
8004                      # MCP server
3000                      # Grafana
8085, 8086, 8087          # Smart meter sims (electric / gas / water)
5432                      # PostgreSQL (internal only — don't expose to LAN)
```

✅ **Checkpoint:** `getenforce` says `Enforcing`, `id aapuser1` returns a user, `podman info` runs.

---

## Phase 2 — Install AAP 2.6 ⚠️

**This is where the four gotchas hit.** Read all four boxes below
before you start the installer — the install dies ~8 minutes in if any
of these are wrong, and the partial state has to be torn down before
retry.

### Step 2.1 Download & 2.2 Extract the bundle

```bash
sudo -u aapuser1 -i
cd ~
# Bundle was downloaded as aapuser1's home directory earlier
tar xzf ansible-automation-platform-containerized-setup-bundle-2.6-1-x86_64.tar.gz
cd ansible-automation-platform-containerized-setup-bundle-2.6-1-x86_64
```

### Step 2.3 Configure the installer inventory

Edit `inventory` in the extracted bundle. The four required corrections
follow, in the order you'll hit them.

> ### ⚠️ Gotcha #1 — Required inventory variables the docs imply are optional
>
> The AAP_HOST prod install worked because that box had pre-existing
> artifacts from earlier attempts. **A clean box needs all four of
> these set explicitly**, or preflight fails:
>
> | Variable | Why required | Symptom if missing |
> |---|---|---|
> | `gateway_admin_password` | Unified gateway has its own admin user, separate from `admin_password` | *"gateway_admin_password must be set and not empty"* |
> | `gateway_pg_host` / `gateway_pg_port` / `gateway_pg_database` / `gateway_pg_username` / `gateway_pg_password` | Gateway has its own Postgres database | Gateway container starts but can't reach DB |
> | `postgresql_admin_username=postgres` + `postgresql_admin_password=<pw>` | When `[database]` is populated, the installer needs superuser creds to create per-component DBs | *"postgresql_admin_password must be set and not empty with managed database"* |
> | A host in the `[database]` group | Empty `[database]` makes the installer treat the DB as external and ping `localhost:5432`, which isn't up yet | *"could not connect to server: Connection refused"* |

> ### ⚠️ Gotcha #3 — Registry credentials must be a Service Account token
>
> Set `registry_password` to a **Registry Service Account token**, not
> your Red Hat account password. Create the token at:
> https://access.redhat.com/terms-based-registry/
>
> The AAP_HOST prod inventory still has the actual `rh-ee-tcoulter`
> account password in `registry_password=` — that's a known
> tech-debt item. Use a Service Account token for LAB_UTIL_HOST from day 1.

> ### ⚠️ Gotcha #4 — `[execution_nodes]` should stay empty
>
> Single-node hybrid setups use the controller node for execution. Do
> **not** add the controller's IP to `[execution_nodes]` — that causes
> double-registration and makes the deprovision step (see gotcha #2)
> fail even harder. Leave the group declared but empty.

**Reference inventory layout that worked on LAB_UTIL_HOST:**

```ini
[automationgateway]
LAB_UTIL_HOST

[automationcontroller]
LAB_UTIL_HOST

[automationhub]
LAB_UTIL_HOST

[automationeda]
LAB_UTIL_HOST

[database]
LAB_UTIL_HOST

[execution_nodes]
# intentionally empty — see gotcha #4

[all:vars]
admin_password=<aap admin pw>
gateway_admin_password=<gateway admin pw>
pg_database=awx
pg_username=awx
pg_password=<pg pw>
pg_host=LAB_UTIL_HOST
pg_port=5432
gateway_pg_host=LAB_UTIL_HOST
gateway_pg_port=5432
gateway_pg_database=gateway
gateway_pg_username=gateway
gateway_pg_password=<gateway pg pw>
postgresql_admin_username=postgres
postgresql_admin_password=<postgres superuser pw>
registry_username=<service-account-username>
registry_password=<service-account-token>
```

### Step 2.3b — Apply the installer patch BEFORE running it

> ### ⚠️ Gotcha #2 — Deprovision Instances bug (installer 2.6-1)
>
> The `automationcontroller : Deprovision Instances not listed in the
> inventory` task always fails on a fresh install with:
>
> ```
> CommandError: --hostname is a required argument
> ```
>
> **Cause:** `awx-manage list_instances` stdout includes a Django
> informational line (*"100 objects imported automatically (use -v 2
> for details)"*) and a trailing blank line. The installer treats those
> as hostnames in `_list_current_nodes`, the `difference()` filter
> doesn't drop them, and the task tries to deprovision an instance with
> no hostname.
>
> Without this patch, the install dies after ~8 minutes with only
> gateway + redis + postgres + receptor up. Controller / hub / EDA
> never start.
>
> **Patch** — edit before running `setup.sh`:
>
> File: `collections/ansible_collections/ansible/containerized_installer/roles/automationcontroller/tasks/init.yml`
>
> Find the task **"Deprovision Instances not listed in the inventory"**
> and append a `when:` clause that filters out empty / junk items:
>
> ```yaml
>   when: item | length > 0 and "objects imported" not in item and " " not in item
> ```
>
> Re-check on future bundles (2.6-2 and later) — this may be fixed
> upstream.

### Step 2.4 Run the installer

```bash
# Inside the extracted bundle directory, as aapuser1
./setup.sh
```

Expect ~25-35 minutes. If it dies at ~8 minutes on "Deprovision
Instances", the patch in gotcha #2 wasn't applied — apply it, then
**tear down the partial install** before retrying:

```bash
# As root or via sudo
sudo podman ps -a --format '{{.Names}}' | xargs -r sudo podman rm -f
sudo rm -rf /var/lib/pgsql /opt/ansible-automation-platform
# Then re-run ./setup.sh
```

### Step 2.5 / 2.6 / 2.7 — Verify, log in, apply subscription

Follow `COMPLETE_INSTALLATION_GUIDE.md §4 steps 2.5-2.7` verbatim.

```bash
curl -sk https://LAB_UTIL_HOST/api/gateway/v1/ping/         # expect 200
curl -sk https://LAB_UTIL_HOST/api/controller/v2/ping/      # expect JSON with "version"
sudo podman ps                                              # expect: gateway, controller, hub, eda, redis, postgres, receptor
```

Web UI: `https://LAB_UTIL_HOST` — username `admin`, password = the
`admin_password` you set in the inventory. Apply your AAP
subscription manifest at **Settings → Subscription**.

✅ **Checkpoint:** Gateway ping returns 200, controller API responds
with a version, all 7 podman containers are `Up`. The four gotchas are
behind you.

---

## Phase 3 — Clone repository & configure vault

Follow `COMPLETE_INSTALLATION_GUIDE.md §5 Phase 3` verbatim. Six
sub-steps, ~10 minutes:

1. Clone `ansible-automated-compliance/aac` to `/home/aapuser1/compliance` using your GitHub PAT
2. `dnf install ansible-core`
3. Write your vault password to `~/.vault_pass` (`chmod 600`)
4. Copy `ansible/vars/vault_secrets.yml.example` → `vault_secrets.yml` and edit (`ansible-vault edit ...`)
5. Verify with `ansible-vault view ansible/vars/vault_secrets.yml --vault-password-file ~/.vault_pass`
6. Generate / save a Red Hat **offline** token (for EE builds) at https://access.redhat.com/management/api

**Vault variables that must be set** (see CLAUDE.md "Vault Variables" for the full table):

```
compliance_db_password
compliance_reader_password
grafana_admin_password
vault_redhat_username        # rh-ee-tcoulter on this box
vault_redhat_offline_token   # from step 6 above
vault_github_pat             # from prerequisites
vault_aap_admin_password     # the AAP admin pw from Phase 2
vault_aapuser1_password      # set in Phase 1, step 1.6
```

---

## Phase 4 — Deploy PostgreSQL (compliance database, not AAP's)

Follow `COMPLETE_INSTALLATION_GUIDE.md §6 Phase 4`. Two options:

- **Preferred:** Run AAP template **114** (`AAC - Initialize PostgreSQL Database`) — creates the container, schema, `compliance_reader` role.
- **Bootstrap fallback** (no AAP templates yet): Run `ansible/roles/aac_compliance_db/` directly via `ansible-playbook`.

Verify: `podman exec postgresql psql -U postgres -d compliance -c '\dt'` shows `compliance_results`, `cve_events`, `remediation_rates`, `remediation_budgets`, etc.

---

## Phases 5–13 — Configure AAP, build EE, deploy OPA + MCP + Grafana + smart meters

These phases ran clean on LAB_UTIL_HOST with no further fixes needed.
Follow `COMPLETE_INSTALLATION_GUIDE.md` sections §7-§15 verbatim:

| Phase | What | Reference |
|---|---|---|
| 5 | Create AAP credentials (GitHub, Vault, machine, AWS, quay.io), project, inventory, EE registration | §7 |
| 6 | Build the custom Compliance EE (`quay.io/rh-ee-tcoulter/aac-compliance-ee:v1.2.0`) | §8 |
| 7 | Bootstrap job templates (run `seed_*` playbooks for ~48 templates) | §9 |
| 8 | Deploy three OPA containers (security :8181, compliance :8182, OT :8183) | §10 |
| 9 | Load Rego policies into all three containers (AAP template 27) | §11 |
| 10 | Deploy MCP server (port 8004) — pin `mcp==1.25.0` (newer versions break) | §12 |
| 11 | Deploy Grafana with PostgreSQL datasource | §13 |
| 12 | Deploy smart meter simulators (electric / gas / water) | §14 |
| 13 | Demo stability setup, reboot test, run a CIS assessment | §15 |

---

## Final verification

Run the AAC health check skill `/aac-verify`, or by hand:

```bash
curl -sk https://LAB_UTIL_HOST/api/gateway/v1/ping/          # 200
curl -sk https://LAB_UTIL_HOST/api/controller/v2/ping/       # 200
curl -s    http://LAB_UTIL_HOST:8181/health                  # 200
curl -s    http://LAB_UTIL_HOST:8182/health                  # 200
curl -s    http://LAB_UTIL_HOST:8183/health                  # 200
curl -s    http://LAB_UTIL_HOST:8085/api/health              # {"status":"healthy"}
curl -s -H "Authorization: Bearer $MCP_TOKEN" http://LAB_UTIL_HOST:8004/sse | head -c 50
# expect: "event: endpoint\ndata: /messages/?session_id=..."
```

All eight services up → install complete.

---

## Appendix A — Known issues hit during the 2026-05-31 build (and the fixes)

This is the chronological order in which the four gotchas were
discovered, for reference if you're debugging a future build that
hits the same path.

### Attempt sequence

| # | What I tried | What failed | Fix applied |
|---|---|---|---|
| 1 | Generic inventory copied from the AAP_HOST prod backup | Preflight: *"gateway_admin_password must be set and not empty"* | Added `gateway_admin_password` (gotcha #1, line item 1) |
| 2 | Added gateway_admin_password + gateway_pg_* | Preflight: postgres ping fails on `localhost:5432` (DB not up) | Added the box to `[database]` group (gotcha #1, line item 4) |
| 3 | Added host to `[database]` | Preflight: *"postgresql_admin_password must be set and not empty with managed database"* | Added `postgresql_admin_username=postgres` + `postgresql_admin_password=<pw>` (gotcha #1, line item 3) |
| 4 | Added postgresql_admin_* | Install ran for 8 min / 417 tasks, died on `Deprovision Instances`: *"--hostname is a required argument"* | Patched `init.yml` to filter empty / junk items from `_list_current_nodes` (gotcha #2) |
| 5 | Re-ran (idempotent) | Same failure, now with stale partial state | Tore down partial install (`podman rm -f` + `rm -rf /var/lib/pgsql /opt/ansible-automation-platform`), then re-ran with patch applied |
| 6 | Re-ran from scratch with all fixes | ✅ Completed — gateway + controller + hub + EDA + receptor + postgres + redis all up | |

### Notes for future builds

- The AAP_HOST prod inventory has `[database]` empty and works
  **only** because the postgres container from an older install was
  still on disk. From-scratch installs need the host listed there.
- `registry_password` on AAP_HOST is the actual rh-ee-tcoulter
  account password in plaintext — that account password should be
  rotated and the prod install switched to a Service Account token at
  the next maintenance window.
- Gotcha #2 (Deprovision Instances bug) is in installer **2.6-1**.
  When 2.6-2 or later ships, check `init.yml` first — the upstream
  may have fixed it and the patch will no longer be needed.
- `[execution_nodes]` stays empty for single-node hybrid. Putting the
  controller IP there causes double-registration and makes the
  deprovision step fail harder.

---

## Appendix B — Quick reference

**Service endpoints (LAB_UTIL_HOST):**

| Service | URL | Expected |
|---|---|---|
| AAP Gateway | `https://LAB_UTIL_HOST/api/gateway/v1/ping/` | 200 + JSON |
| AAP Controller | `https://LAB_UTIL_HOST/api/controller/v2/ping/` | 200 + JSON with `version` |
| OPA Security | `http://LAB_UTIL_HOST:8181/health` | 200 |
| OPA Compliance | `http://LAB_UTIL_HOST:8182/health` | 200 |
| OPA OT | `http://LAB_UTIL_HOST:8183/health` | 200 |
| MCP | `http://LAB_UTIL_HOST:8004/sse` (with auth header) | SSE stream |
| Smart Meter | `http://LAB_UTIL_HOST:8085/api/health` | `{"status":"healthy"}` |
| Grafana | `http://LAB_UTIL_HOST:3000/api/health` | 200 |

**Authored with Claude (Anthropic).**
