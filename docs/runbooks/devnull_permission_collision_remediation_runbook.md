# AAP Container-Host `/dev/null` Permission Collision — Remediation Runbook

**Version:** v1.3
**Audience:** Platform / Linux administrators and the AAP service-account owner on a container-host (rootless podman) AAP install.
**Authored with Claude (Anthropic)**

> This runbook starts from a **broken current state and assumes nothing has been remediated yet.** Follow it top to bottom. Every command is labelled with the **user it must run as** — mixing them up is the most common way this goes wrong.

---

## 1. Symptom & current state

- Ansible Automation Platform (**container-host / rootless podman** topology) shows intermittent **gateway 503 "No Healthy Upstream"** in the console.
- `/dev/null` on the container host has lost its world-writable bit — it is `rw-rw-r--` (0664) instead of the correct `rw-rw-rw-` (0666).
- A periodic **security / CIS hardening sweep** is what changes it, and it **recurs** after every manual fix.

## 2. Why this happens (root cause — a two-party collision)

Neither party alone causes the outage:

1. **Podman (before `5.8.2-6.el9_8`) creates the link.** During rootless image-layer extraction, podman's container storage under the service account's home (`~/.local/share/containers/`) ends up with a path that shares the **inode of the host `/dev/null` device**. It is a podman bug byproduct — **not** an AAP configuration artifact, so there is no AAP installer knob for it.
2. **The `/home` hardening sweep pulls the trigger.** A CIS/STIG policy that strips "other" permissions under `/home` chmods that linked path. Because it shares an inode with `/dev/null`, the chmod lands on the **real device**: `rw-rw-rw-` → `rw-rw-r--`. Every process that redirects to `/dev/null` **as another user** then fails → the gateway's upstream services die → console 503.

`/dev/null` is 0666 by design, which is exactly what made it hard-linkable in the first place.

**Key consequence for this runbook:** fixing only one party is not durable. Updating podman stops **new** links but leaves **existing** residue that the sweep keeps striking; clearing residue without fixing podman lets it come back on the next image pull; and restoring `/dev/null` permissions without doing either just resets the clock until the next sweep.

## 3. Placeholders used below

| Placeholder | Meaning | Example |
|---|---|---|
| `<container-host>` | The RHEL host running rootless podman + AAP | — |
| `<service-account>` | The non-root user that ran the containerized AAP installer and owns the podman storage | e.g. `aapsvc` |
| `<storage-path>` | New rootless container-storage location off `/home` | `/var/lib/aap-containers` |

Run everything **on `<container-host>`** unless stated otherwise. Two identities are used throughout:
- **root** — device, package, `/etc`, SELinux, and the audit watch.
- **`<service-account>`** — anything touching podman/AAP container storage. Rootless storage belongs to this user; running podman as root would operate on the wrong storage.

---

## Phase 0 — Confirm you are hitting this exact issue

**Step 0.1 — Check `/dev/null` integrity.**
**User: root**
```bash
stat -c 'type=%F mode=%a links=%h major:minor=%t:%T' /dev/null
```
Healthy = `type=character special file mode=666 links=1 major:minor=1:3`.
- `mode` ≠ `666` → the device has already been struck.
- `links` > `1` → hard-linked residue exists somewhere on `/dev/null`'s filesystem.

**Step 0.2 — Identify what is changing it (the definitive step).**
**User: root**
```bash
auditctl -w /dev/null -p a -k devnull_watch      # arm the watch — -p a = ATTRIBUTE changes only
auditctl -l | grep devnull                       # confirm it loaded
```
Use `-p a` (attribute changes), **not** `-p wa`: AAP processes write to `/dev/null` constantly, and the `w` (write) events flood `ausearch` and can make ordinary writes look like the culprit. `chmod` is an attribute change, so `-p a` catches it cleanly.

Then **run the security scan** (or wait for the next scheduled run). After it runs:
```bash
ausearch -k devnull_watch -i -ts recent
```
Read three fields from the record:
- `syscall=` — expect `chmod` / `fchmodat` / `fchmodat2` / `setxattr`.
- `name=` (on the `type=PATH` line) — the exact path the process operated on.
  - `name="/dev/null"` → the scan chmods the device **directly**. This alone does **not** prove the host is residue-free — check Step 0.1's **link count**: if it is `> 1`, hard-link residue is *also* present and must still be cleared (Phases 2–3), or the collision recurs after the next image pull. Only if the link count is `1` is the fix Phase 6 (scope the sweep) alone.
  - `name="/home/<service-account>/.local/share/containers/…"` → **that** path is the podman residue.
- `comm=` / `exe=` / `proctitle=` — the tool doing it (e.g. `oscap`, a CIS `chmod`, an ansible task). Note whether it is the scanner vs. `systemd-tmpfiles`/`(udev)` — the latter means a different root cause than this runbook.

> The `-w` watch is runtime-only and does **not** survive a reboot. Re-arm it if the host reboots before you finish.

**Step 0.3 — Locate the residue statically (corroborates 0.2).**
**User: root**
```bash
# Scoped to the service account, one filesystem (-xdev) — same scope as the
# preflight. (Avoid `find -L`: following symlinks can wander into unrelated
# filesystems or a huge tree via a symlinked directory.)
find /home/<service-account> -xdev -samefile /dev/null 2>/dev/null
# stray char-device nodes that look like /dev/null (major:minor 1:3):
find /home/<service-account> -xdev -type c -exec stat -c '%n %t:%T' {} + 2>/dev/null | grep ' 1:3$'
```
Empty results do **not** prove the host is clean — a true hard link to `/dev/null` cannot exist on `/home`'s filesystem (hard links can't cross filesystems), so rely on Step 0.2 (auditd) as the source of truth.

**Which variant are you in? — it changes the fix.** Read the Step 0.1 `stat` and the two `find` results together:

- **Hard-link collision** — `links` on `/dev/null` is **> 1**, *or* a stray `1:3` char node turns up under `/home`. Residue lives inside container storage → **Phases 3–6** (podman update, `podman system reset`, relocate storage off `/home`) are the real fix.
- **Direct-chmod drift** — `/dev/null` is the correct `1:3` device with **`links=1`** and **no** stray nodes, but the **mode is wrong** (e.g. `664`). Nothing hard-linked it — a hardening job `chmod`'d `/dev/null` directly (or a recursive `chmod` reached it). **Skip Phases 3, 4, and 5** — `podman system reset`, storage relocation, and the AAP reinstall all fix nothing here and Phase 5 is disruptive. The fix path is: **Phase 1** (restore the mode) → **Step 0.2** (name the culprit) → **Phase 6** (scope the hardening job at its source — this is the real fix) → **Phase 7** (verify + soak). Do **not** fall through top-to-bottom from Phase 1 into the destructive Phases 3–5. Phase 2 (update podman) is **not** part of this fix, but is still worth doing as hygiene on any container-host carrying an old podman, so a latent hard-link collision can't be stacked on top of this one at the next image pull.

When in doubt, Step 0.2 (auditd) names the offending process either way.

---

## Phase 1 — Immediate mitigation (restore service now)

**Step 1.1 — Restore the device.**
**User: root**
```bash
# GUARD FIRST: only repair if this really IS /dev/null — a character device at
# major:minor 1:3. If it is missing, a regular file, or a different device, do
# NOT chmod (you would be modifying a replacement object) — recreate the node.
if [ "$(stat -c '%F|%t:%T' /dev/null 2>/dev/null)" = "character special file|1:3" ]; then
    # Check the chmod exit status — if it fails (e.g. /dev read-only) a later
    # stat would still succeed and mask it, reporting success while /dev/null
    # is still broken. Fail closed instead.
    chmod 666 /dev/null || { echo "STOP: chmod failed (is /dev read-only?) — /dev/null NOT repaired"; exit 1; }
    [ "$(stat -c '%a' /dev/null)" = "666" ] || { echo "STOP: /dev/null did not reach mode 666"; exit 1; }
else
    echo "STOP: /dev/null is not a 1:3 char device — do NOT chmod (you would modify a"
    echo "replacement object). Recreate it — REMOVE the wrong node first, or mknod fails"
    echo "with 'File exists' unless the node is simply missing:"
    echo "  rm -f /dev/null && mknod -m 666 /dev/null c 1 3   # atomically replace, then re-run Step 0.1 + 1.1"
    echo "  # (or, if udev manages the node: udevadm trigger --name-match=null)"
    exit 1
fi
```
This clears the 503s immediately. It is **temporary** — the next sweep will strike it again until Phases 2–6 are done. (A reboot also restores `/dev/null` from devtmpfs, but `chmod` avoids the disruption.)

**Step 1.2 — Confirm the platform recovers.**
**User: root**
```bash
curl -sk -o /dev/null -w '%{http_code}\n' https://<container-host>/api/gateway/v1/ping/   # expect 200
```

> **A `chmod` repairs the device; it does not restart the processes that already
> failed while it was broken.** If the ping still returns **503 after** Step 1.1
> succeeded (and Step 0.1 confirms `/dev/null` is now `666`), the platform needs a
> restart — services that were writing to a broken `/dev/null` crashed or wedged and
> do not self-heal when the device is fixed under them. **The ping above hits the
> gateway, so restart the gateway too — not just the controller**, or a wedged
> gateway keeps returning 503 even after the controller is healthy. Restart per
> install type, then re-run the ping:
> - **Containerized (RHEL):** `systemctl --user restart 'automation-*'` under the
>   platform service account — the `automation-*` glob covers `automation-gateway`
>   and the controller units together (or use the containerized-installer's
>   documented restart).
> - **RPM / bundle:** restart **all** AAP services, not only the controller —
>   `systemctl restart automation-gateway automation-controller automation-hub automation-eda-controller`
>   (drop any unit not installed).
> - **Operator on OpenShift:** `oc -n <aap-namespace> rollout restart deploy --all`
>   (the namespace is dedicated to AAP; `deploy` alone selects nothing — you must
>   pass `--all` or name the AAP deployments explicitly).
>
> If it is still 503 after a full restart with `/dev/null` at `666`, the 503 is a
> *separate* platform problem — `/dev/null` is no longer the cause; move to the
> controller/gateway logs.

---

## Phase 2 — Update podman (stop NEW links from ever forming)

**Step 2.1 — Check the current version.**
**User: root**
```bash
rpm -q --qf '%{VERSION}-%{RELEASE}\n' podman
```
Required: the fix shipped in **`5.8.2-6.el9_8`**. Note the AAC preflight compares the **base release `5.8.2-6`** with `sort -V`, so an earlier dist tag (e.g. `5.8.2-6.el9_7`) would *pass* the preflight while failing this runbook's floor — verify the full fixed release (`.el9_8`) here rather than trusting the preflight's base-release check alone.

**Step 2.2 — Update if below that.**
**User: root** (or the site's patch process)
```bash
dnf update -y podman
rpm -q --qf '%{VERSION}-%{RELEASE}\n' podman     # confirm it is now >= 5.8.2-6.el9_8
```

> Updating podman does **not** remove residue from earlier installs. Continue to Phase 3.

---

## Phase 3 — Clear the leftover residue (guaranteed-clean)

The residue lives **inside live container storage**. Do **not** hand-`rm` paths under `~/.local/share/containers/storage/…` on a running stack — that can corrupt storage. Tear it down cleanly instead.

**Step 3.1 — Quiesce AAP (actually stop it, then verify nothing runs).**
**User: `<service-account>`**
```bash
# `podman ps` only LISTS — it does not stop anything. Containerized AAP is
# ROOTLESS: its services run under the SERVICE ACCOUNT's *user* systemd session,
# not the system manager. Stop them with `systemctl --user` AS that account (or
# the install's exact compose teardown) — NOT `sudo systemctl` (wrong manager),
# and do NOT `|| true` (that hides a failed stop). Then ASSERT nothing remains.
systemctl --user stop 'automation-*' 'aap-*'     # as <service-account>; or: podman-compose -f <compose> down
podman ps -q                                      # MUST print nothing
test -z "$(podman ps -q)" || { echo "STOP: containers still running — do NOT reset"; exit 1; }
echo "quiesced"
```

**Step 3.2 — Back up AAP off-host, THEN reset the container storage.**
**User: `<service-account>`** *(critical — must be this user, not root)*

> ⛔ **STOP.** `podman system reset` is **irreversible** and removes **all** images,
> containers, and volumes for `<service-account>` — **including deployed AAP
> controller and database state**, not just the bad link. On any host that is not
> a disposable/rebuildable install, take a **supported AAP platform + database
> backup, copy it OFF this host, and confirm it restores — before** running the
> reset. Do not proceed without an off-host backup.

```bash
# 1) Take the supported AAP backup, RECORD its checksum and the EXACT installer
#    bundle version here, copy it off-host, and test-restore it on a scratch host
#    USING THE SAME BUNDLE VERSION (restore requires an exact match — a mismatched
#    bundle can make the only recovery artifact unusable):
#      <run the containerized-installer backup.yml, or your topology's backup>
#      sha256sum aap-backup.tar.gz > aap-backup.sha256                          # keep on THIS host
#      rpm -q ansible-automation-platform-installer > aap-bundle-version.txt    # carry into Phase 5
# 2) The reset REFUSES unless the OFF-HOST copy's checksum matches THIS backup —
#    `test -s` alone would pass any stale/unrelated non-empty file:
BACKUP_ARCHIVE=/path/on/backup-host/aap-backup.tar.gz     # the off-host copy
EXPECT_SHA=$(cut -d' ' -f1 aap-backup.sha256 2>/dev/null)
REMOTE_SHA=$(ssh <backup-host> "sha256sum '${BACKUP_ARCHIVE}' 2>/dev/null | cut -d' ' -f1")
if [ -n "$EXPECT_SHA" ] && [ "$REMOTE_SHA" = "$EXPECT_SHA" ]; then
    podman system reset
else
    echo "STOP: off-host backup checksum mismatch ('$REMOTE_SHA' != '$EXPECT_SHA') — do NOT reset"; exit 1
fi
```
⚠️ **Destructive** (see the stop-gate above). It removes the residue along with everything else; a reinstall (Phase 5) restores service and, if needed, you restore data from the backup taken above.

**Step 3.3 — Confirm storage is gone.**
**User: `<service-account>`**
```bash
ls -la ~/.local/share/containers 2>/dev/null || echo "storage cleared"
```

---

## Phase 4 — Relocate rootless storage off `/home` (take `/home` policy out of the blast radius)

Do this **before** reinstalling so new layers extract into the new location, never `/home`.

**Step 4.1 — Create the new storage directory.**
**User: root**
```bash
mkdir -p <storage-path>
chown <service-account>:<service-account> <storage-path>
chmod 700 <storage-path>
```

**Step 4.2 — Fix the SELinux label** (relocating container storage without this breaks containers).
**User: root**
```bash
semanage fcontext -a -e /home/<service-account>/.local/share/containers <storage-path>
restorecon -Rv <storage-path>
```

**Step 4.3 — Point rootless storage at it (prefer the per-user config).**
**User: `<service-account>`** — set it in the account's own `~/.config/containers/storage.conf`:
```ini
[storage]
driver = "overlay"
rootless_storage_path = "<storage-path>"
```
Prefer per-user over the system-wide `/etc/containers/storage.conf`: `<storage-path>` is mode 700 owned only by `<service-account>`, so a system-wide setting would redirect *every other* rootless user on the host to a graphroot they cannot read. Use the system-wide file only if this account is the sole rootless user.

**Step 4.3b — Relocate EVERY AAP storage override, not just the default.**
**User: `<service-account>`**
AAP does not put everything under `~/.local/share/containers` — the receptor/mesh store is set via `CONTAINERS_STORAGE_CONF` (e.g. `~/aap/containers/storage.conf`), which `rootless_storage_path` above does **not** cover. Enumerate and repoint each one off `/home`, or `podman system reset` + the default graphroot will still leave layers under `/home`:
```bash
# The DEFAULT `podman system reset` (Step 3.2) and `podman info` (Step 4.4) do
# NOT touch override stores. Enumerate EVERY one — under the account's home AND
# from the user systemd environment (a CONTAINERS_STORAGE_CONF set in a unit is
# not under /home) — reset + verify each, and FAIL CLOSED if any graphroot is
# still under /home. (Run after the backup gate in Step 3.2 — this resets stores.)
mapfile -t CONFS < <(
  { grep -RIl 'graphroot\|rootless_storage_path' /home/<service-account> 2>/dev/null
    systemctl --user show-environment 2>/dev/null | sed -n 's/^CONTAINERS_STORAGE_CONF=//p'
    grep -RhoE 'CONTAINERS_STORAGE_CONF=[^[:space:]"]+' /home/<service-account> ~/.config/systemd 2>/dev/null | cut -d= -f2
  } | sort -u )
bad=0
for c in "${CONFS[@]}"; do
  CONTAINERS_STORAGE_CONF="$c" podman system reset                                 # clear residue in that store
  gr=$(CONTAINERS_STORAGE_CONF="$c" podman info --format '{{.Store.GraphRoot}}')
  case "$gr" in /home/*) echo "STILL UNDER /home: $c -> $gr"; bad=1 ;; *) echo "ok: $c -> $gr" ;; esac
done
[ "$bad" = 0 ] || { echo "STOP: an override store is still under /home — repoint it before reinstalling"; exit 1; }
# (The receptor/mesh store used by build_compliance_ee.yml is one such override.)
```

**Step 4.4 — Verify podman will use it.**
**User: `<service-account>`**
```bash
podman info --format '{{.Store.GraphRoot}}'      # DEFAULT store — expect: <storage-path>...
# Verify EACH override store from Step 4.3b too (the default check misses them):
#   CONTAINERS_STORAGE_CONF=<file> podman info --format '{{.Store.GraphRoot}}'   # expect: OFF /home
```

---

## Phase 5 — Reinstall AAP (fixed podman + relocated storage)

**Step 5.1 — Run the container-host install** per your standard AAP process, as the account that owns the install.
**User: `<service-account>`** (or per your install runbook)

> Use the **same installer bundle version** you recorded with the backup (`aap-bundle-version.txt`, Step 3.2). If you restore data from that backup, the restore bundle version must match the backup's **exactly** — a mismatch can make the archive unrestorable.

**Step 5.2 — Verify health.**
**User: root**
```bash
curl -sk -o /dev/null -w '%{http_code}\n' https://<container-host>/api/gateway/v1/ping/   # expect 200
stat -c 'mode=%a links=%h' /dev/null                                                       # expect: mode=666 links=1
```

---

## Phase 6 — Make the hardening sweep collision-proof (the version-independent class-killer)

Even with fixed podman, a sweep that chmods **non-regular files** will eventually collide with container tooling again. Fix the sweep once, for all future hosts and tools. **This is the only step that prevents the class of problem, not just this instance.**

**Step 6.1 — Determine the sweep's scope** from the `comm=`/`proctitle=` captured in Step 0.2, and which root paths it walks.

**Step 6.2 — Scope the sweep** in the owning hardening content (e.g. `ansible-lockdown` RHEL9-CIS/STIG, `redhat.rhel_system_roles`, or the site's custom CIS remediation):
- Restrict the permission sweep to **regular files only** — add `-type f` to the `find`, and/or
- **Exclude container storage** (`<storage-path>` and `~/*/.local/share/containers/`).

A permission remediation that targets device nodes / symlinks at all is the underlying hazard; `-type f` removes it.

> If Step 0.2 showed `name="/dev/null"` (a direct chmod), Phase 6 is the **primary** fix — the policy has a rule explicitly resetting `/dev/null`; scope or remove that rule.

---

## Phase 7 — Verify and soak

**Step 7.1 — Integrity check.**
**User: root**
```bash
stat -c 'type=%F mode=%a links=%h' /dev/null      # expect: character special file 666 1
```

**Step 7.2 — Prove the sweep no longer strikes it.**
**User: root**
```bash
# Use a FRESH key (Step 0.2's devnull_watch may still hold Step 1.1's chmod
# event, which would make this look like a failure). -p a again.
auditctl -w /dev/null -p a -k devnull_soak
armed=$(date '+%H:%M:%S')
# run the security scan
ausearch -k devnull_soak -i -ts "$armed"           # expect: no matching events since arming
auditctl -W /dev/null -p a -k devnull_soak         # remove the soak watch when done
```

**Step 7.3 — Preflight (if using the AAC installer preflight).**
The AAC preflight checks the podman version and the **full** `/dev/null` integrity tuple (char-device + mode 666 + link-count 1), delegated to the container host, and returns **GO**. (A bug where a link-count-only probe overwrote the mode check — so mode 664 passed as GO — was fixed in `install_preflight.yml` via #572, now merged; ensure your checkout includes it.)

**Step 7.4 — Soak.** Let at least one full **scheduled** sweep cycle run (e.g. the nightly job), then repeat Step 7.1. Clean after a real scheduled run = fixed.

---

## Appendix A — Who runs what (quick reference)

| Step | User | Command (abbrev.) | Purpose |
|---|---|---|---|
| 0.1 | root | `stat … /dev/null` | Confirm the device state |
| 0.2 | root | `auditctl -w /dev/null …` → `ausearch -k devnull_watch` | Identify the culprit definitively |
| 0.3 | root | `find /home/<svc> -xdev -samefile /dev/null` | Locate residue statically |
| 1.1 | root | `chmod 666 /dev/null` | Immediate service restore |
| 2.2 | root | `dnf update podman` | Stop new links (≥ 5.8.2-6) |
| 3.2 | **`<service-account>`** | `podman system reset` | Clear existing residue |
| 4.1–4.3 | root | mkdir/chown, `semanage`/`restorecon`, edit `storage.conf` | Relocate storage off `/home` |
| 4.4 | **`<service-account>`** | `podman info … GraphRoot` | Confirm relocation |
| 5.1 | `<service-account>` | AAP install | Reinstall on fixed podman + new storage |
| 6.2 | policy owner | add `-type f` / exclude container storage | Durable class-killer |
| 7.1–7.4 | root | `stat`, `auditctl`/`ausearch`, preflight, soak | Verify + soak |

## Appendix B — Do-not-do list

- **Do not `chmod` or `rm` the residue link/device directly on a running stack** to "fix" it — operating on it risks the real `/dev/null` inode (for chmod) or storage corruption (for rm inside live storage). Use `podman system reset` (Phase 3).
- **Do not run `podman system reset` as root** — rootless storage belongs to `<service-account>`; as root you would reset the wrong (or no) storage and leave the residue in place.
- **Do not treat "updated podman" as done** — it only stops new links; existing residue persists (this is why the scan hit `/dev/null` again).
- **Do not skip SELinux relabelling** (Step 4.2) when relocating storage — containers will fail to start.
- **Do not rely on empty `find … -samefile` output as proof of clean** — use the audit watch (Step 0.2) as the source of truth.
