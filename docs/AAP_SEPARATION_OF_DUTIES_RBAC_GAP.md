# Separation of Duties in AAP RBAC — Test Findings and Product Gap

### Can an identity-administration role be defined without automation privileges?

**Version:** v1.0
**Date:** 2026-08-14
**Platform tested:** Ansible Automation Platform 2.7, controller **4.8.4**, gateway RBAC (DAB)
**Method:** direct API testing against a live controller — every result below is a verbatim API response
**Conclusion:** **Not achievable in the product today.** Four independent enforcement points block it.

---

> ## ⚠️ v1.0's conclusion is too strong — corrected 2026-08-20
>
> Re-verified read-only against the same lab controller. **Two findings below do not survive
> re-testing, and the headline conclusion should not be sent to Red Hat or a customer as written.**
>
> **1. A managed `Team Admin` role exists with zero automation permissions.**
> `GET /api/gateway/v1/role_definitions/?name=Team Admin` returns a managed role,
> `content_type: shared.team`, with exactly four permissions —
> `shared.change_team`, `shared.delete_team`, `shared.member_team`, `shared.view_team` — and **no**
> job-template, project, inventory, credential or workflow permission. That is team-scoped identity
> administration without automation privileges, which §3 says does not exist.
>
> **The caveat matters and v1.0's absolutism obscured it.** The role description is *"Can manage a
> single team **and inherits all role assignments to the team**."* So a Team Admin inherits whatever
> automation roles are assigned to that team. It is clean separation only where the team itself
> holds no automation roles. "Not achievable" is wrong; "solved by Team Admin" would also be wrong.
>
> **2. LDAP delegation achieves the split today**, refuting finding #5 ("external identity cannot
> substitute"). `OPTIONS /api/gateway/v1/authenticator_maps/` shows `organization` and `team` as
> plain **strings with no choice list** — so both are created on demand from directory attributes —
> while `role` must resolve to a pre-existing `RoleDefinition`. That asymmetry is the mechanism:
> orgs and teams come from the directory, the capability catalogue stays change-controlled in AAP.
> `MANAGE_ORGANIZATION_AUTH` is `True` on this gateway.
>
> The resulting split is a stronger story than the RFE this document proposes:
>
> | Driven from LDAP | Stays in AAP, change-controlled |
> |---|---|
> | Users, organizations, teams | Role **definitions** — the capability catalogue |
>
> The API transcripts in §§2–4 are accurate as recorded; it is the generalisation from them that
> overreached.

---

## 1. The question

> Can we define a custom role in AAP that has the ability to manage **users, teams, organizations
> and credentials**, but *cannot* perform automation tasks — creating projects, job templates,
> rulebook activations and so on?

The intent is a **security administrator** role. Platform Admin can do this, but Platform Admin can
do everything, which is precisely the problem.

---

## 2. Premise — why this is being asked

**Separation of duties (SoD)** is a standard control in regulated industries: the person who
administers *who has access* should not also be able to *change what the system does*. Otherwise a
single account can grant itself capability and then exercise it, with no second pair of eyes.

It is a named requirement, not a preference:

| Framework | Control |
|---|---|
| **NIST SP 800-53** | **AC-5 Separation of Duties** — explicit named control; also AC-6 Least Privilege |
| **FedRAMP** | Inherits AC-5 at Moderate and High baselines |
| **PCI DSS v4.0** | Requirement 7 — restrict access by business need to know |
| **SOX (ITGC)** | Segregation of duties over access administration is a standard test area |
| **NERC CIP** | CIP-004 personnel and access management; CIP-007 R5 system access control |
| **HIPAA** | §164.308(a)(3)–(4) workforce security and access authorization |

In banking and fintech in particular, an access-administration function that also holds change
capability is a routine audit finding.

---

## 3. What was tested

All testing was performed against the live gateway and controller APIs. No result below is
inferred. Probe objects created during testing were deleted; the platform was returned to its
starting state (85 role definitions, 0 authenticator maps).

### 3.1 What content types support custom roles at all?

`GET /api/controller/v2/role_metadata/` → `allowed_permissions`

```
awx.credential            awx.notificationtemplate
awx.executionenvironment  awx.project
awx.instancegroup         awx.workflowjobtemplate
awx.inventory             shared.organization
awx.jobtemplate           shared.team
```

**There is no user content type.** No `shared.user`, and no `*_user` permission exists anywhere in
the custom-role permission set. User lifecycle is not delegable by any means.

The complete set of `shared.*` permissions that exist:

```
shared.add_team         shared.audit_organization
shared.change_team      shared.change_organization
shared.delete_team      shared.delete_organization
shared.member_team      shared.member_organization
shared.view_team        shared.view_organization
```

These are exactly the permissions an identity-administration role would need — and they are visible
in the metadata, which is what makes the blocks below surprising.

### 3.2 Test results

| # | Test | Result |
|---|---|---|
| 1 | Global (system-wide) custom role including team permissions | ❌ `Permissions "add_team", "change_team" are not valid for global role roles` |
| 2 | Org-scoped custom role with the 10 identity permissions | ❌ `Creating custom roles that include team permissions is disabled` |
| 3 | Org-scoped custom role, org write permissions only (no team) | ❌ `Local custom roles can only include view permission for shared models` |
| 4 | Org write permissions + credential administration | ❌ same error as #3 |
| 5 | Org-scoped custom role, **view only** | ✅ **Created** — establishes that `view` is the ceiling for `shared.*` |
| 6 | Custom role over `awx.credential` (no `shared.*`) | ✅ **Created** — automation content types support full CRUD |
| 7 | Edit the managed **Organization Admin** to remove automation | ❌ `System roles can only have permissions for the 'galaxy' service. Invalid permissions: 'view_organization' (service: shared)` |

**Every construction path is closed.** Building up from permissions fails; subtracting down from a
built-in role fails; the built-in roles cannot be edited.

### 3.3 The built-in role that *does* have these rights

`Organization Admin` (managed, `content_type: shared.organization`) holds **76 permissions**:

| Category | Count | Contents |
|---|---|---|
| **Identity** | **10** | `shared.{view,change,delete,member,audit}_organization` + `shared.{view,add,change,delete,member}_team` |
| **Automation** | **66** | `eda.*` activations, decision environments, event streams; `awx.*` projects, job templates, workflows, inventories, credentials, EEs, instance groups, notification templates |

The capability exists inside the platform. It is bundled, and the bundle cannot be split.

### 3.4 Can external identity (LDAP/SAML/OIDC) supply what AAP cannot?

The gateway supports 15 authenticator plugins (`ldap`, `saml`, `oidc`, `keycloak`, `azuread`,
`radius`, `tacacs`, and others) with `authenticator_maps` translating IdP group membership into AAP
assignments. This is the obvious workaround, so it was tested directly.

| Test | Result |
|---|---|
| Map referencing a role name that does not exist in AAP | ❌ `RoleDefinition ... doesn't exist` |
| `map_type: team` **without** a role | ❌ `You must specify a role with the selected map type` |
| `map_type: organization` **without** a role | ❌ `You must specify a role with the selected map type` |
| `map_type: team` **with** `Team Member` | ✅ Created |
| `map_type: allow` (login gate) | ✅ Created — no role needed |
| `map_type: is_superuser` | ✅ Created — no role needed |

**External identity cannot inject a capability AAP does not already define.** Every scoped map type
validates against the existing `RoleDefinition` table. The only two role-free map types are binary:
*can this user log in*, and *is this user a superuser*. There is no middle ground.

Supporting constraints:

- A **team requires an organization** (`organization: required=True`) — the hierarchy is fixed.
- Only **two** roles exist for `shared.team`: **Team Member** and **Team Admin**, both managed. No
  third option can be created.
- **23** roles exist for `shared.organization` — but they are `Organization Member`,
  `Organization Admin`, and narrow **automation** slices (`Organization Credential Admin`,
  `Organization Inventory Admin`, `Organization JobTemplate Admin`, `Organization Project Admin`…).
  **There is no identity-administration slice.**

That last point is the crux: **the platform has already decomposed Organization Admin — but only
along the automation axis.** The identity axis was left whole.

### 3.5 Incidental finding

Creating a custom role over an `awx.*` content type succeeded via
`POST /api/controller/v2/role_definitions/` but returned **HTTP 503 repeatedly** via
`POST /api/gateway/v1/role_definitions/`. Anyone automating role creation should use the controller
endpoint for `awx.*` content types. Worth confirming whether this is expected routing behaviour or
a defect.

---

## 4. Summary of findings

1. **No user-management permission exists** in the custom-role system. User lifecycle is Platform
   Admin only, by any route.
2. **Team permissions are explicitly disabled** for custom roles, though they exist and are used by
   managed roles.
3. **`shared.*` permissions in custom roles are limited to `view`.** No `change`, `member`, `add` or
   `delete`.
4. **Managed roles cannot be edited**, so the built-in Organization Admin cannot be reduced.
5. **External identity cannot substitute.** Scoped LDAP/SAML maps require a pre-existing AAP role;
   only binary login and superuser flags bypass role definitions.
6. **Organization Admin is the smallest indivisible unit** that includes identity administration —
   and it carries 66 automation permissions with it.

### What *is* achievable today

- Fine-grained **automation** roles over any `awx.*` content type — full CRUD, object-scoped.
- **`Organization Credential Admin`** — a managed role covering credential lifecycle without
  automation execution. This is the one element of the original requirement that is satisfiable.
- **View-only** custom roles over organizations and teams.
- Identity *operations* relocated to an IdP — with the important caveat that the map configuration
  itself remains a Platform Admin function, and any group mapped to `is_superuser` becomes a
  privileged group in the directory.

### The likely design rationale

This is probably deliberate rather than an oversight. **Team membership management is effectively
privilege granting**: anyone who can add users to a team can add themselves and inherit whatever
that team holds. A custom role carrying `member_team` is a privilege-escalation primitive.
Restricting it to managed roles keeps the blast radius understood.

The rationale is sound. It is also what makes the requirement unsatisfiable, and the two facts need
to be held together — the ask below is for a *bounded* relaxation, not removal of the guard.

---

## 5. Commercial impact

### 5.1 It creates a named audit finding in regulated accounts

**NIST 800-53 AC-5** is an explicit, named control, inherited by every FedRAMP Moderate and High
baseline. An assessor asking *"demonstrate separation of duties for platform administration"* cannot
be shown a role — only a compensating narrative. That converts a checkbox into an argument, and
arguments cost time and credibility in an audit.

For SOX ITGC and PCI DSS Requirement 7, access administration is a standard test area. "The role
that administers access also administers automation" is the finding an auditor is trained to look
for.

### 5.2 It forces customers to over-privilege — the opposite of the intended outcome

The practical consequence is predictable: customers who need someone to onboard teams and manage
org structure grant **Organization Admin** or **Platform Admin**, because there is no smaller unit.
Every such grant carries 66 automation permissions that the person does not need and often should
not have.

**The absence of a restrictive role produces less restrictive deployments.** These accounts are
enumerable and an assessor will find them.

### 5.3 It is friction in enterprise security review

Nearly every enterprise and public-sector deal passes a security architecture review. RBAC
granularity is a standard line of questioning. "Show me how you separate identity administration
from automation administration" currently has no product answer — only an IdP integration project
with residual gaps. That is a slower, more expensive conversation than a role definition, and it
arrives at the point in the cycle where friction is most costly.

### 5.4 It is a competitive gap on a table-stakes control

Comparable platforms permit fine-grained custom roles that include user and group administration —
Kubernetes RBAC, ServiceNow, GitLab and Terraform Enterprise all allow an identity-administration
role distinct from a workload-administration role. AAP's decomposition is genuinely good on the
automation axis and absent on the identity axis, which is visible in any side-by-side evaluation.

### 5.5 It constrains managed-service and platform-team operating models

An MSP, or an internal platform team running AAP for multiple business units, needs a **tenant
onboarding** function: create the organization, create teams, assign membership — and touch no
automation. Today that requires Platform Admin for routine onboarding work. That is both a security
concern and an operational bottleneck, because the work cannot be delegated to a service desk tier.

### 5.6 It is awkward when AAP underpins compliance tooling

Where AAP is the execution engine for a compliance or audit platform, the platform's own access
model comes into scope. Assessors do examine the controls of the tooling that produces their
evidence. A compliance solution whose underlying platform cannot demonstrate SoD invites a question
that is difficult to answer well.

### 5.7 The workaround has real cost and does not fully close the gap

The IdP route requires directory integration, mapping configuration, change control over that
configuration, break-glass procedures and periodic access review. That is a project, not a setting.
And it leaves two residual exposures: **map configuration remains a Platform Admin function**, and
**any directory group mapped to `is_superuser` becomes a privileged group** — relocating the risk
rather than removing it.

---

## 6. Proposed enhancement

**Ask:** permit object-scoped custom role definitions to include organization and team management
permissions, without requiring automation permissions.

Concretely — allow a custom role with `content_type: shared.organization` to carry:

```
shared.view_organization    shared.view_team
shared.change_organization  shared.add_team
shared.member_organization  shared.change_team
shared.audit_organization   shared.member_team
                            shared.delete_team
```

while carrying **no** `awx.*` or `eda.*` permissions.

**Why this is a bounded change rather than a new capability:** every permission listed already
exists, is already implemented, and is already granted together by the managed `Organization Admin`
role. The request is to make the existing decomposition — already done for credentials, inventories,
job templates and projects — available on the identity axis as well.

**On the escalation concern:** `member_team` is genuinely privilege-granting, so a reasonable
implementation might scope such a role to a single organization, exclude the ability to grant roles
that the holder does not themselves possess, or emit an explicit audit event on each membership
change. Any of those preserves the guard while making the control expressible.

**Minimum viable version**, if the full ask is too broad: ship a managed
**`Organization Identity Admin`** role containing exactly the 10 identity permissions from
Organization Admin and none of the 66 automation permissions. That requires no change to the custom
role engine at all — only a new managed role definition — and it would satisfy the majority of the
SoD requirement immediately.

---

## 7. Reproducing these results

```bash
B=https://<gateway>

# what content types support custom roles, and what shared.* permissions exist
curl -sk -u <user>:<pass> "$B/api/controller/v2/role_metadata/"

# the 76-permission composition of Organization Admin
curl -sk -u <user>:<pass> "$B/api/gateway/v1/role_definitions/?name=Organization%20Admin"

# attempt the SoD role (expect: team permissions disabled)
curl -sk -u <user>:<pass> -X POST "$B/api/gateway/v1/role_definitions/" \
  -H 'Content-Type: application/json' -d '{
   "name":"Org Security Admin","content_type":"shared.organization",
   "permissions":["shared.change_organization","shared.member_organization",
                  "shared.add_team","shared.change_team","shared.member_team"]}'

# attempt to edit the managed role (expect: system roles restricted)
curl -sk -u <user>:<pass> -X PATCH "$B/api/gateway/v1/role_definitions/4/" \
  -H 'Content-Type: application/json' -d '{"permissions":["shared.view_organization"]}'

# confirm scoped IdP maps require an existing role
curl -sk -u <user>:<pass> -X POST "$B/api/gateway/v1/authenticator_maps/" \
  -H 'Content-Type: application/json' -d '{
   "name":"probe","authenticator":1,"map_type":"team",
   "organization":"Default","team":"probe","triggers":{"groups":{"has_or":["cn=nope"]}}}'
```

> **Caution when reproducing:** an `authenticator_map` with `map_type: role` or `is_superuser` and a
> broad trigger takes effect on the next login for every matching user. Use a trigger that cannot
> match, and delete probe objects immediately.

---

## 8. Authorship and status

Prepared by **Tim Coulter** with **Claude (Anthropic, Claude Opus 5)** as co-author.

Findings are empirical and specific to **AAP 2.7 / controller 4.8.4** as tested on 2026-08-14.
Behaviour may differ in other releases — re-run §7 before relying on these results. This is an
internal technical finding intended to support an enhancement request; it is not a statement of
Red Hat product direction, and it is not audit advice.
