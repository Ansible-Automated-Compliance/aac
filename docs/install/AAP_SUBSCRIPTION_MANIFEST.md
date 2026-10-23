# Activating Ansible Automation Platform — Subscription Manifest

**Version:** v1.0
**Date:** 2026-08-10
**Audience:** Internal delivery teams, and customers under NDA installing AAC on their own
infrastructure.
**Scope:** Getting AAP entitled, by manifest or by service account, across the three
topologies AAC is installed into.

---

> ### Terminology — two different things are called a "manifest"
>
> | Term | What it is | Where it appears |
> |---|---|---|
> | **Subscription manifest** | A `.zip` of entitlement certificates from the Red Hat Hybrid Cloud Console. Licenses AAP. | This document |
> | **Kubernetes manifest** | A YAML file applied with `oc apply -f`. Deploys workloads. | `install/` manifests, `oc apply -f manifests/<name>.yaml` |
>
> They are unrelated. An AAC install uses both, often in the same session. Where this
> document says "manifest" without qualification, it means the **subscription** manifest.

---

## 1. Decide first: connected or disconnected

This is the only decision that changes the procedure, and it is worth making deliberately
before touching either console.

| | **Service account** | **Subscription manifest** |
|---|---|---|
| Requires outbound internet from AAP | **Yes** — AAP calls Red Hat to fetch entitlements | **No** |
| What you carry to the host | A Client ID and secret | A `.zip` file |
| Renewal | Automatic on subscription change | Re-export and re-upload |
| Air-gapped / restricted networks | Not usable | **This is what it exists for** |
| Best for | Connected labs, cloud installs, PoCs | Production, regulated estates, OT/DMZ segments |

**The manifest path exists for disconnected environments.** If the AAP host has outbound
internet, the service account route (§6) is less to maintain and does not go stale. Most
AAC customers in scope — utilities, financial services, anything with an OT segment — are
not connected, which is why the manifest is the default assumption in the rest of this
document.

---

## 2. What changed since the 2.4-era instructions

Internal notes and the AAP 2.4 documentation describe a **Subscriptions → Subscription
Allocations** tab on `access.redhat.com`. **That page no longer exists under that name.**

| Then (2.4 docs, `access.redhat.com`) | Now (verified 2026-08-10) |
|---|---|
| Subscriptions → **Subscription Allocations** tab | **Manifests**, at [console.redhat.com/subscriptions/manifests](https://console.redhat.com/subscriptions/manifests) |
| Hosted on `access.redhat.com` | Migrated to `console.redhat.com`; migration completed 30 Jan 2026 |
| "New subscription allocation" | "Create new manifest" |
| Type list pinned to a specific Satellite version | Type list still offers Satellite versions, but **the version offered moves** — see §3 |

The mechanics are unchanged. Only the navigation and the labels moved. Anyone following
the older wording will land on a page that does not exist and conclude the entitlement is
missing.

---

## 3. Obtaining the manifest

**Prerequisites**

- A Red Hat account with an **active AAP subscription**. Not a lapsed trial — see §3.4.
- The **Subscriptions administrator** role in
  [User Access](https://console.redhat.com/iam/my-user-access). Without it the create
  button is inactive *even when the entitlement exists*, which presents identically to
  having no subscription at all.
- Your organisation's Red Hat **account number**. Customers use their own; it is visible
  under the account menu on the console.

### 3.1 Create the manifest

1. Go to [console.redhat.com/subscriptions/manifests](https://console.redhat.com/subscriptions/manifests).
2. **Create new manifest.**
3. Name it something that identifies the destination cluster, not the date — you will
   have several, and `prod-controller` is findable where `manifest_2026_08_10` is not.
4. **Type:** choose the most recent **Satellite** version offered.

   > This looks wrong and is not. AAP manifests use the Satellite manifest format, so a
   > Satellite type is the correct selection for an AAP subscription. Older documentation
   > names a specific version (2.4 says "Satellite 6.8"); **do not pin to that number** —
   > the list advances, and the version you select does not need to match any Satellite
   > you run, because you are not running Satellite.

5. **Create**, then open the **Subscriptions** tab.
6. **Add subscriptions** → find your Ansible Automation Platform subscription → set the
   entitlement count (§3.2) → **Submit**.
7. **Export manifest.** You get `manifest_<name>_<date>.zip`. Keep the `.zip` intact —
   do not unzip, rename the inner files, or re-zip it.

### 3.2 How many entitlements

**One entitlement per node AAP will manage** — servers, network devices, storage
controllers, OT endpoints. Not per AAP component, and not per user.

For AAC specifically, count the **managed estate**, not the platform. If the inventory
follows the AAC taxonomy (`ansible/inventory/aac_inventory_template.yml`), that number is
exactly `managed_estate` and excludes `aac_product` by construction:

```bash
ansible-playbook -i <inventory> ansible/playbooks/inventory_report.yml
# "managed_estate : N host(s) — assessed"  ← N is your entitlement count
```

Size with headroom. Exceeding the count does not stop automation, but the controller
reports the subscription **out of compliance**, and that surfaces in an audit as a
licensing finding at the same time an assessor is looking at your compliance evidence.

### 3.3 Include the infrastructure nodes

If the environment has execution nodes, hop nodes, or a separate controller/hub/EDA tier,
**those subscriptions must be added to the manifest too**.

> **This fails silently.** A manifest missing the infrastructure-node entitlements exports
> cleanly, uploads cleanly, and reports success. The failure surfaces later and elsewhere
> — nodes that will not come up, or capacity that never registers — with nothing pointing
> back at the manifest. Check the entitlement list on the **Subscriptions** tab before
> exporting; that is the last point where the omission is cheap to see.

### 3.4 If "Create new manifest" is greyed out

Three causes, in order of likelihood:

| Cause | Check | Fix |
|---|---|---|
| No active AAP subscription in the account | [console.redhat.com/subscriptions](https://console.redhat.com/subscriptions) | Obtain an entitlement |
| Missing the Subscriptions administrator role | [User Access](https://console.redhat.com/iam/my-user-access) | Org admin grants it |
| Expired trial, inside the cooldown | Trial history | The 60-day trial cannot be restarted until **90 days after its last expiration** |

That last one catches people who evaluated a couple of months ago: the trial lapses, the
button greys out, and re-running the trial is blocked for a further quarter. Plan
entitlement before the evaluation window closes, not after.

---

## 4. Applying the manifest

Three topologies. Pick the row that matches the install.

| Topology | When the manifest is applied | Method |
|---|---|---|
| **A** — RHEL, containerized installer | During install | Inventory variable (§4.1) |
| **B** — OpenShift / CRC, AAP operator | After the operator deploys AAP | UI or API (§4.2) |
| **C** — Any running AAP | Any time; also how you renew | UI or API (§4.2) |

**AAC's own environments (lab CRC, mac CRC, RHPDS) are topology B.** The operator has no
manifest input, so entitlement is always a post-deployment step there.

### 4.1 Topology A — supply it to the installer

Put the manifest on the installer host and reference it by absolute path in the inventory:

```ini
controller_license_file=/full_path_to/manifest_file.zip
```

The installer picks it up and the platform comes up entitled — no post-install step, and
no window where the controller rejects host creation with *"License is missing."*

For a disconnected install this is the better choice: the manifest is already on the host
alongside the bundle, so there is no separate transfer of a file into the secure zone.

Adding execution nodes later is the same pattern — add the node to the inventory and
re-run the installer. See [Containerized installation](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html-single/containerized_installation/index).

### 4.2 Topologies B and C — upload to a running platform

**UI** — Settings → Subscription → Browse → select the `.zip` → confirm.

**API** — for scripted installs and rebuilds. Base64-encode the `.zip` and POST it:

```bash
# Linux (RHEL) — -w 0 is REQUIRED. Without it base64 wraps at 76 columns
# and the embedded newlines break the JSON body.
MANIFEST_B64=$(base64 -w 0 /path/to/manifest.zip)

# macOS — no -w flag; use -i instead
MANIFEST_B64=$(base64 -i /path/to/manifest.zip)

curl -sk -u admin:"$AAP_ADMIN_PASSWORD" -X POST \
  "https://<aap-host>/api/controller/v2/config/" \
  -H 'Content-Type: application/json' \
  -d "{\"manifest\": \"$MANIFEST_B64\"}"
```

> **Verify this endpoint against your own controller before scripting it.** The
> `POST /api/controller/v2/config/` shape is documented for 2.6/2.7 but has not been
> re-confirmed against a live AAC controller at the time of writing — `.62` was
> unreachable. The UI path is authoritative; treat the API form as a convenience to
> validate once per environment, then reuse.

---

## 5. Verify

Do not accept the UI's success banner as proof. Read it back from the API:

```bash
curl -sk -u admin:"$AAP_ADMIN_PASSWORD" \
  "https://<aap-host>/api/controller/v2/config/" \
  | jq '{type:        .license_info.license_type,
         expires:     .license_info.license_date,
         compliant:   .license_info.compliant,
         entitled:    .license_info.instance_count,
         consumed:    .license_info.current_instances}'
```

| Field | What good looks like |
|---|---|
| `type` | `enterprise` (or `trial` on an evaluation). **Never `open`** — that means unentitled |
| `compliant` | `true` |
| `entitled` vs `consumed` | `consumed` below `entitled`, with headroom |
| `expires` | Far enough out to survive the next audit cycle |

A functional check that entitlement actually took: **create a host in an inventory.** An
unentitled controller rejects it with *"License is missing"*, which is the symptom most
installs hit first.

---

## 6. The connected alternative — service account

Where the platform has outbound internet, skip manifests entirely. Nothing to export,
nothing to re-upload at renewal.

1. [console.redhat.com/iam/service-accounts](https://console.redhat.com/iam/service-accounts)
   → create one → record the **Client ID** and **Client secret** (the secret is shown
   **once**).
2. Add the service account to a User Access group carrying a role that can read
   subscriptions.
3. AAP → Settings → Subscription → **Service Account** tab → Client ID + secret → select
   the subscription.

> If the credentials are accepted but the subscription list comes back empty, it is step 2
> — the service account lacks subscription-read permission. Red Hat documents this exact
> failure: [Configure AAP to authenticate through service account credentials](https://access.redhat.com/articles/7112649).

Superseded note: AAP 2.6+ uses a service account here. Plain Red Hat username/password on
this tab is the older mechanism and is not the current path.

---

## 7. What differs for customers

Everything above is the same procedure. What changes is what you must **not** assume:

| Assumption from an internal lab | Customer reality |
|---|---|
| Our Red Hat account number | **Theirs.** Never carry an internal account number into customer material — it identifies the wrong organisation and will not resolve for them |
| Console access is available | Their console access may sit with a procurement or licensing team, not the engineer installing. Identify who holds the Subscriptions administrator role **before** the install day |
| The host can reach Red Hat | Frequently false. Assume disconnected until proven otherwise — this is why §4.1 is the primary path for customer installs |
| A trial is fine to start on | A trial expires mid-engagement and cannot be restarted for 90 days. Customers need a real entitlement before the pilot, not during |
| Entitlement count is approximate | It is a contractual number. Agree the managed-node count with them in writing before creating the manifest |
| One manifest is enough | Non-production, production and DR each want their own. A single manifest reused across clusters makes renewal an outage |

**For AAC engagements specifically:** the entitlement count is the size of the estate
under *assessment*, which is normally larger than the estate under *automation* — AAC
reads everything, including systems no one automates. Size against `managed_estate`, and
raise it with the customer early: it is the most common source of a surprise at
renewal.

---

## 8. What comes next

Manifest activation is the prerequisite; these are the setup tasks that usually follow on
a customer install.

| Task | Reference |
|---|---|
| LDAP for user authentication | [Access management and authentication](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/access_management_and_authentication/index) |
| GitHub as a project source | [Managing projects](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/using_automation_execution/controller-projects) |
| Automation Hub / private hub | [Managing automation content](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/managing_automation_content/index) |
| TLS certificate regeneration | [Configuring AAP](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/access_management_and_authentication/assembly-gw-settings) |
| Adding execution nodes | Add to the installer inventory and re-run — see §4.1 |
| Getting started with automation | [Red Hat automation e-book](https://www.redhat.com/en/engage/redhat-ansible-automation-202108061218) |

Then continue into the AAC install itself — [`install/README.md`](../../install/README.md)
selects the path.

---

## Authorship

Prepared by **Tim Coulter** with **Claude (Anthropic, Claude Opus 5)** as co-author.

Console URLs and the `controller_license_file` variable verified 2026-08-10. The
`POST /api/controller/v2/config/` payload shape is documented but **not** re-verified
against a live controller — see the note in §4.2.
