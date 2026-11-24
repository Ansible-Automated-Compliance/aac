# CIS Microsoft 365 Foundations Benchmark v7.0.0 — Findings Workbook

**Framework:** cis_m365_v7  
**Subjects:** tenant.example  
**Generated:** 2026-10-13T12:00:00+00:00  
**Contract:** v1.0

> 3 critical/high-risk failure(s) need attention first, of 3 open. 1 regressed since the previous run.

## Summary

| Item | Value |
|---|---|
| Contract version | 1.0 |
| Framework | cis_m365_v7 |
| Benchmark | CIS Microsoft 365 Foundations Benchmark v7.0.0 |
| Subjects | tenant.example |
| Generated | 2026-10-13T12:00:00+00:00 |
| Latest run | tenant.example: 2026-10-12T09:00:03+00:00 |
| Previous run | tenant.example: 2026-09-15T10:00:02+00:00 |
| Policy SHA | (not recorded) |
| Verdict | 3 critical/high-risk failure(s) need attention first, of 3 open. 1 regressed since the previous run. |
| Controls in benchmark | 11 |
| Controls evaluated | 6 |
| Passed | 2 |
| Failed (open) | 3 |
| Waived | 1 |
| Unassessable | 5 |
|   unassessable: attestation_required | 1 |
|   unassessable: benchmark_manual | 2 |
|   unassessable: collector_not_built | 1 |
|   unassessable: facts_not_collected | 1 |
| Open by risk: Critical | 1 |
| Open by risk: High | 2 |
| Open by risk: Medium | 0 |
| Open by risk: Low | 0 |
| Open by owner: Identity team | 1 |
| Open by owner: M365 platform team | 1 |
| Open by owner: Messaging team lead | 1 |
| Sampled evidence (findings) | 1 |
| Delta: new | 2 |
| Delta: fixed | 1 |
| Delta: regressed | 1 |
| Delta: still open | 1 |
| Decisions on file | 3 |
| Decisions expiring | 0 |
| Decisions expired | 0 |
| Decisions unmatched | 1 |
| Decisions with issues | 2 |
| Open findings undecided | 1 |

## Findings (4)

| Finding ID | Control | Title | Category | Subject | Effective risk | Owner | Decision | Decision status | Delta | Age (days) | Where to fix | Action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 55edb7693f | 1.1.3 | only 1 global admin designated; fewer than two risks lockout | M365 admin center | tenant.example | Critical | M365 platform team | remediate | active | regressed | 42 | Microsoft 365 admin center -> Users / Roles | adjust administrative role assignments and account configuration |
| 886185661f | 6.5.1 | modern authentication for Exchange Online is not enabled; legacy authentication bypasses MFA | Exchange admin center | tenant.example | High | Messaging team lead | accept | active | still open | 42 | Exchange admin center -> Mail flow / Settings | apply the Exchange Online configuration for this control |
| def0c4713b | 5.1.2.2 | users can register applications; any user can consent-phish other users | Entra admin center | tenant.example | High | Identity team |  | undecided | new | 1 | Microsoft Entra admin center -> Identity -> Users -> User settings | restrict the user self-service capability to administrators |
| 098cc943cb | 6.1.2 | mailbox auditing disabled for 3 mailboxes | Exchange admin center | tenant.example | Medium | Messaging team | accept | expiring | new | 1 | Exchange admin center -> Mail flow / Settings | apply the Exchange Online configuration for this control |

## Unassessable (5)

| Control | Title | Section | Category | Profile level | Benchmark assessment | Subject | Reason | Who acts | Owner | Detail | Evidence row |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5.2.4.1 |  | 5 | Entra admin center | L1 | Manual | tenant.example | attestation_required | customer | Identity team | CIS 5.2.4.1: requires attestation -- no automated procedure (this is not a pass) | 10 |
| 1.3.3 |  | 1 | M365 admin center | L2 | Manual | * | benchmark_manual | customer | M365 platform team | benchmark classifies this control as Manual |  |
| 7.2.1 |  | 7 | SharePoint admin center | L2 | Manual | * | benchmark_manual | customer | Security operations | benchmark classifies this control as Manual |  |
| 9.1.1 |  | 9 | Fabric | L1 | Automated | * | collector_not_built | vendor | Security operations | no collector path yet (vendor backlog) |  |
| 2.1.1 |  | 2 | Microsoft 365 Defender | L2 | Automated | tenant.example | facts_not_collected | vendor | Security operations | CIS 2.1.1: Defender policy facts were not collected (this is not a pass) | 8 |

## Decisions (3)

| Control | Subject | Decision | Owner | Justification | Approver | Approved | Expires | Status | Days to expiry | Matched findings | Issues | Ticket |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 6.5.1 | * | accept | Messaging team lead | Legacy scanners need basic authentication until the Q1 replacement | Jane Doe | 2026-10-01 | 2026-12-30 | active | 78 | 886185661f | expiry missing — defaulted to approved + 90 days (2026-12-30) | CHG-0001 |
| 1.1.3 | tenant.example | remediate | M365 platform team |  | security-team | 2026-10-05 |  | active |  | 55edb7693f | approver is not a named person |  |
| 9.1.1 | * | accept | Data platform team | Superseded exception | Ann Lee | 2026-07-01 | 2026-09-30 | unmatched | -13 |  |  |  |

## Delta (5)

| Change | Finding ID | Control | Title | Subject | Effective risk | First seen | Previous run | Latest run |
|---|---|---|---|---|---|---|---|---|
| regressed | 55edb7693f | 1.1.3 | only 1 global admin designated; fewer than two risks lockout | tenant.example | Critical | 2026-09-01T10:00:02+00:00 | 2026-09-15T10:00:02+00:00 | 2026-10-12T09:00:03+00:00 |
| new | def0c4713b | 5.1.2.2 | users can register applications; any user can consent-phish other users | tenant.example | High | 2026-10-12T09:00:03+00:00 | 2026-09-15T10:00:02+00:00 | 2026-10-12T09:00:03+00:00 |
| new | 098cc943cb | 6.1.2 | mailbox auditing disabled for 3 mailboxes | tenant.example | Medium | 2026-10-12T09:00:03+00:00 | 2026-09-15T10:00:02+00:00 | 2026-10-12T09:00:03+00:00 |
| fixed | c56218b77f | 5.2.3.6 |  | tenant.example |  | 2026-09-01T10:00:02+00:00 | 2026-09-15T10:00:02+00:00 | 2026-10-12T09:00:03+00:00 |
| still open | 886185661f | 6.5.1 | modern authentication for Exchange Online is not enabled; legacy authentication bypasses MFA | tenant.example | High | 2026-09-01T10:00:02+00:00 | 2026-09-15T10:00:02+00:00 | 2026-10-12T09:00:03+00:00 |

## Passed (2)

| Control | Title | Section | Category | Subject | Sampled | Evidence strength | Evidence row |
|---|---|---|---|---|---|---|---|
| 1.1.1 |  | 1 | M365 admin center | tenant.example |  |  | 7 |
| 5.2.3.6 |  | 5 | Entra admin center | tenant.example |  |  | 8 |

---

Generated by AAC from stored OPA evaluations. Evidence is never edited; decisions live in the decisions file; this workbook is the join of the two. Co-authored by Claude (Anthropic) via Claude Code.
