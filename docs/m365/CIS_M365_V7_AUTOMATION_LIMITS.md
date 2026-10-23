# CIS Microsoft 365 v7.0.0 — What Cannot Be Automated, and Why

**Version:** v1.1  
**Benchmark:** CIS Microsoft 365 Foundations Benchmark v7.0.0 (released 2026-05-20)  
**Date:** 2026-08-25  
**Authored with Claude (Anthropic)**

---

## 1. Why this document exists

The POC commits to complete coverage of the benchmark's 160 recommendations.
"Complete" is only meaningful if we can say precisely which controls a
collector can establish, which need a human, and — critically — **why**.

This document records that boundary, with each claim marked by how it was
established. It exists so that no one has to re-derive it, and so that a
control we call un-automatable is one we have actually checked rather than
one we assumed.

## 2. "Manual" is CIS's designation, not a statement that no API exists

CIS marks every recommendation **Automated** or **Manual**. For v7.0.0:

| CIS assessment status | Count |
|---|---|
| Automated | 143 |
| Manual | 17 |
| **Total** | **160** |

**Manual does not mean "no API exists."** It means CIS's own audit
procedure requires human judgment or their tooling does not check it. Two
of the 17 turn out to be readable through an API that CIS simply does not
document. Conversely, some controls CIS marks *Automated* are documented
only as portal clicks, and need an API path we work out ourselves.

So the useful question is not CIS's label. It is: **can an unattended
collector, authenticating app-only, read this state?**

## 3. The constraint that actually binds: app-only authentication

Our collectors run inside an AAP job with **no human present**. They use
Entra app registration client credentials. That rules out any API that
supports only *delegated* access — where a signed-in user's identity is
required.

This is a sharper constraint than "does an API exist", and it is the one
that decides automatability for us. Control 5.1.2.4 below is the worked
example: the API exists, and we still cannot use it.

## 4. Verified: genuinely not automatable

### 4.1 Self-service password reset — 5 controls

| Control | Title |
|---|---|
| 5.2.4.1 | Ensure 'Self service password reset enabled' is set to 'All' |
| 5.2.4.2 | Ensure that 2 methods are required for password reset |
| 5.2.4.3 | Ensure SSPR registration and authentication re-confirmation are configured |
| 5.2.4.4 | Ensure that users are notified on password resets |
| 5.2.4.5 | Ensure all admins are notified when other admins reset their password |

**Status: no read path exists, by API or PowerShell.** Microsoft's own
guidance states there is currently no method — API or PowerShell — to
manage SSPR settings through standard Graph endpoints; they are expected
under `/authentication/methods` eventually, but are not there today.

These settings live in the legacy SSPR policy surface, reachable only
through the Entra admin center UI.

**Consequence:** these 5 controls require operator attestation with a
screenshot. There is no collector to build.

### 4.2 Restricted access to the Entra admin center — 1 control

| Control | Title |
|---|---|
| 5.1.2.4 | Ensure access to the Entra admin center is restricted |

**Status: an API exists but cannot be used unattended.** Microsoft added
`GET /beta/admin/entra/uxSetting`, which returns `restrictNonAdminAccess`.
It **supports only delegated scenarios** — the signed-in user must hold
Global Administrator or Global Reader. App-only client credentials are not
supported.

This is the distinction that matters: *readable* but not *readable by us*,
given the unattended execution model the POC requires.

**Consequence:** attestation, unless we introduce a delegated-auth path
with a human sign-in — which would defeat scheduled assessment.

## 5. Verified: automatable despite CIS marking it Manual

| Control | Title | Path |
|---|---|---|
| 5.1.2.1 | Ensure 'Per-user MFA' is disabled | `GET /beta/users/{id}/authentication/requirements` → `perUserMfaState` |

`perUserMfaState` returns `disabled` / `enabled` / `enforced`. CIS marks
this Manual, but it is directly readable per user, app-only. **We should
collect it.** Note it is a `/beta` endpoint, which Microsoft documents as
subject to change and unsupported for production — record that as an
evidence caveat rather than pretending it is a v1.0 guarantee.

## 6. Not yet verified — do not quote these as limits

The remaining 10 Manual controls have **not** been individually checked
against the Graph surface. They are listed here so the gap is visible, not
so it can be cited as a finding.

| Control | Title | Likely path to check |
|---|---|---|
| 1.1.2 | Two emergency access accounts defined | Partly judgment — which accounts count as break-glass is a human decision, though CA-policy exclusions are readable |
| 1.3.8 | Sways cannot be shared externally | Admin-center org settings; `/beta/admin/*` may not expose Sway |
| 2.2.1 | Emergency access account activity is monitored | Alert-rule configuration; partly judgment |
| 2.4.3 | Defender for Cloud Apps enabled and configured | Defender/MCAS API exists; "configured appropriately" is judgment |
| 2.4.5 | 'AIR' remediation is enabled | Defender API / Exchange Online PowerShell |
| 5.1.2.5 | Option to remain signed in is hidden | Organization branding or directory settings |
| 5.1.2.6 | LinkedIn account connections disabled | Directory settings template |
| 5.1.3.2 | Restrict user access to My Groups features | Directory settings template |
| 5.1.3.3 | Owners can manage group membership requests in My Groups | Directory settings template |
| 8.4.1 | App permission policies are configured | Teams PowerShell (`Get-CsTeamsAppPermissionPolicy`) — likely automatable |

**Status: parked until the POC has a live tenant** (decision, 2026-08-14).
These cannot be settled from documentation — several hinge on whether the
endpoint accepts *application* permissions rather than only delegated
ones, and that is only established by calling it with app-only
credentials against a real tenant.

**POC action:** during Sprint 1, once tenant access and the app
registration exist, probe each of the 10 with app-only credentials and
record the result here. Until then they are counted as **unresolved**,
not as limits — the ceiling in §8 is stated as a range for exactly this
reason.

## 7. Controls CIS marks Automated but documents only as portal steps

Separately from the 17 Manual controls, **34 controls are marked Automated
while their Audit procedure gives nothing but portal clicks.** These are
automatable — CIS simply does not document how. Most are §5 Entra policy
objects (device registration, application management, consent workflow)
reachable through `/policies/*`.

For these we necessarily **deviate from the benchmark's documented audit
procedure**. That is legitimate, but it must be recorded: evidence that
traces CIS's own steps is stronger than evidence that reaches the same
conclusion another way. Each such control is flagged in the section
report's `evidence_strength`, as `6.1.1` already is.

A caution learned from building §8.3: where CIS *does* document a
procedure, follow it before assuming a shortcut. Three of the six controls
closed on 2026-08-25 behave differently from what their titles suggest —
one is a join across two APIs, one is compound across two PowerShell
endpoints, and one treats an empty list as compliant. Reading the title and
inferring the check would have produced plausible, wrong rules that unit
tests could not have caught, because the tests would assert the same wrong
behaviour. That is the [numbering defect](../../policies/benchmarks/cis/saas/m365_v7/COVERAGE.md)
in a different costume.

## 8. Current honest ceiling

| Category | Controls |
|---|---|
| Automatable — CIS documents an API/PowerShell path | 109 |
| Automatable — CIS documents portal steps only (we deviate) | 34 |
| **Verified not automatable** (SSPR ×5, Entra portal ×1) | **6** |
| Automatable despite Manual designation | 1 |
| **Unverified** — need a live-tenant check | 10 |
| **Total** | **160** |

So the ceiling is **at least 144 of 160 (90%)**, and **at most 154 (96%)**
depending on how the 10 unverified controls resolve. **Six controls are
confirmed to need operator attestation.**

Note this is *better* than the earlier "143 automatable / 17 manual" split,
because CIS's Manual designation was masking controls that are in fact
readable.

### 8.1 The 144 is now built (2026-08-25)

**The lower bound above is no longer a projection.** As of rego PR #66 and
compliance PR #458, the library evaluates **144 of 160**. Every control
this document classes as automatable has a rule and a collector call.

| Bucket | Controls | Meaning |
|---|---|---|
| Evaluated | **144** | a rule exists and a collector call feeds it |
| Requires attestation | 6 | §4 — verified to have no app-only read path |
| Unresolved | 10 | §6 — collectability unestablished |
| **Total** | **160** | |

Getting there required closing six controls that were, until 2026-08-25,
in **no category at all** — not evaluated, not attested, not listed as
unresolved, and therefore absent from the assessment entirely. The buckets
summed to 154. The §8 table above was correct throughout; the shipped
library did not match it.

That is the failure mode this document exists to prevent, so it is now
machine-checked: `scripts/check_cis_coverage.py` in the rego repo fails CI
if the buckets ever stop partitioning the 160, and the assessment publishes
its own `coverage_accounting` so a reader can check the sum unaided.

### 8.2 Built is not the same as verified

**Do not read 144 as "144 controls assessed."** It means the library *can*
assess 144. Whether each endpoint answers under **app-only** credentials —
the constraint of §3 — is established only by calling it against a live
tenant with app-only credentials.

That is the same gate holding the 10 unresolved controls in §6, and it
applies to the six most recently built ones for exactly the same reason.
Until the POC probe runs, any endpoint that refuses app-only access
produces "could not be evaluated", never a pass.

The honest statement for a customer or auditor is:

> The library implements 144 of the benchmark's 160 recommendations.
> Coverage achieved against a specific tenant is whatever that tenant's
> assessment reports, and is bounded by the permissions granted to the
> app registration.

### 8.3 The six closed on 2026-08-25

Each was implemented from the benchmark's own **Audit** procedure rather
than inferred from the control title. Three came out materially different
from what the title implies, which is why the procedure is recorded here:

| Control | Audit path implemented | Where the title misleads |
|---|---|---|
| 1.2.2 | `Get-EXOMailbox -RecipientTypeDetails SharedMailbox` joined to Graph `accountEnabled` | It is a **join across two APIs**, on the directory object id — not a single mailbox property |
| 1.3.3 | `Get-SharingPolicy` | CIS audits only the *default* policy; we check every policy, since a second enabled one shares calendars just as effectively |
| 2.4.1 | `Get-EmailTenantSettings` **and** `Get-ProtectionAlert` | **Compound.** The tenant toggle alone tags priority accounts; it does not watch them. Alert policies are required, and sit behind a second PowerShell endpoint (`Connect-IPPSSession`) |
| 5.1.6.1 | `/beta/legacy/policies` → `B2BManagementPolicy` | An **empty** allow-list is compliant (it permits nothing); an **absent** one is not. The `definition` field is a JSON *string*, not an object |
| 5.3.4 | `roleManagementPolicyAssignments` → `roleManagementPolicies/{id}/rules/Approval_EndUser_Assignment` | Requires `isApprovalRequired` **and** at least one approver — approval required of nobody gates nothing |
| 5.3.5 | as 5.3.4, against the Privileged Role Administrator role | as above |

The general lesson, and the reason §7 matters: **read the Audit procedure,
not the recommendation title.** Half of these would have been implemented
incorrectly from the title alone, and unit tests could not have caught it —
they would have asserted the same wrong behaviour.

## 9. How attestation should work

For controls with no collector path, the POC should not simply omit them —
an omitted control is indistinguishable from a passing one. The pattern
that preserves evidence quality:

1. The section's Rego emits a violation stating the control **could not be
   evaluated automatically** and requires attestation — the same
   fail-closed contract used everywhere else.
2. An operator records the observed setting plus a screenshot or export,
   dated and attributed.
3. The attestation is stored alongside the automated results with its
   source marked `attested`, never `measured`, so an auditor can tell them
   apart at a glance.

The distinction that must survive into the report: **we assessed this
automatically** versus **a human asserted this on a date**. Both are valid
evidence. Conflating them is not.

## 10. Verification status of this document

| Claim | How established |
|---|---|
| 143 Automated / 17 Manual | Parsed from the official CIS PDF; cross-checked against its summary table |
| Per-control audit tool | Parsed from each control's Audit procedure (`audit_feasibility.py`) |
| SSPR has no API | Microsoft documentation and Microsoft Q&A guidance |
| `/beta/admin/entra/uxSetting` is delegated-only | Microsoft documentation |
| `perUserMfaState` is readable | Microsoft Graph beta API reference |
| The 10 unverified controls | **Not established** — listed as open |
| §8.1 — the library evaluates 144 of 160 | `check_cis_coverage.py` against the benchmark enumeration; the assessment's own `coverage_accounting` |
| §8.3 — the six audit paths | Read from each control's Audit procedure in the v7.0.0 PDF, quoted into the implementing commit |
| §8.2 — app-only behaviour of the new endpoints | **Not established** — needs the live-tenant probe, same as §6 |

Nothing in §4, §5 or §8.3 rests on recall. Everything in §6 does, and is
marked accordingly — as does the app-only claim in §8.2, which is
deliberately *not* asserted.

---

## Revision history

| Version | Date | Change |
|---|---|---|
| v1.1 | 2026-08-25 | Added §8.1–§8.3. The 144-control lower bound of §8 is now built rather than projected, and six controls that were in no category at all have been closed. Separated "implemented" from "verified against a live tenant" throughout, and recorded the audit paths for the six. No claim in §1–§7 changed. |
| v1.0 | 2026-08-14 | Initial version. Established the app-only constraint as the binding one, verified the 6 attestation-only controls, and listed the 10 unresolved. |
