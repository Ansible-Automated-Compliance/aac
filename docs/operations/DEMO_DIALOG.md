> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx3, AAP-2.5/2.6x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAC Demo Dialog — Presenter Script

**Version:** 1.0
**Date:** 2026-03-26
**Audience:** CISO, VP Security, Compliance Officers, VP IT Operations
**Duration:** 30–45 minutes (full) | 15 minutes (executive summary only)

> **How to use this script:**
> Speaker lines are in plain text. Stage directions are in *italics*.
> `[Screen]` notes tell you what to have visible. Pause markers indicate natural breath points.
> Key talking points are in **bold**.

---

## Opening (2 minutes)

*Open with the AAP dashboard at https://AAP_HOST. Have the Job Templates list visible.*

---

Good morning. Let me show you something that most compliance teams don't realize is possible.

Every organization I talk to has the same two problems. First: compliance assessments happen once or twice a year — a consultant shows up, spends three weeks collecting spreadsheets, and hands you a report that's already out of date. Second: your automation runs constantly, but nothing is checking whether that automation itself follows policy. A developer merges a playbook that touches every production server. A Terraform plan opens port 22 to the world. An AI agent remediates a production system at 2am with no approval. By the time you find out, the change is live.

What you're going to see today is a single platform that solves both problems — **continuous compliance assessment** and **policy enforcement across your entire automation stack**.

This is Ansible Automated Compliance. We call it AAC. It runs on Ansible Automation Platform, Open Policy Agent, and PostgreSQL. Let me show you what it does.

---

## PART ONE: Policy Enforcement (10 minutes)

*Navigate to Job Templates in the AAP UI.*

### Setup — The Problem

I want to start with the enforcement story, because this is where we differentiate from every other compliance tool on the market.

Most organizations use HashiCorp Sentinel. Sentinel is a fine product. But Sentinel governs **Terraform plans only**. If your shop uses Ansible — and most shops that use Terraform also use Ansible — Sentinel sees nothing. That's half your automation, completely ungoverned.

I'm going to show you five enforcement points across your automation stack. HashiCorp Sentinel covers two of them. AAC covers all five.

---

### Act 1 — Ansible Enforcement: Git Check-in Gate

*Run Template 33 — "Sentinel — Validate Ansible Playbook (Bad)".*

Here's a playbook a developer just pushed to GitHub. Let me show you what our git webhook catches.

*[Wait for job to complete. Point to the violations output.]*

Four violations. **SENTINEL-ANS-001:** The play has no name — makes log tracing nearly impossible. **SENTINEL-ANS-002:** `hosts: all` in a production playbook. That means this runs on every managed host in your inventory — your databases, your load balancers, everything. **SENTINEL-ANS-003:** There's a hardcoded database password in the vars section. That's a secret in source control. **SENTINEL-ANS-004:** No task tags, which means you can't do a targeted rollback if something goes wrong.

OPA evaluated this in milliseconds and returned DENY. In production, this sets the GitHub commit status to FAILURE. The PR cannot merge.

**The developer doesn't get to break production today.**

---

### Act 2 — Ansible Enforcement: Runtime Pre-flight Gate

*Run Template 34 — "Sentinel - Demo: Runtime Pre-flight Block".*

Now let's say the developer is clever. They bypassed the webhook — pushed directly to main. They've already created a job template in AAP and they're trying to run it right now.

*[Point to the job failing immediately.]*

Watch what happens. The job fails at line one. Why? Because this playbook includes our sentinel pre-flight check as its very first `pre_task`. Before a single task runs — before touching a single server — it calls OPA. OPA says DENY. The job stops.

**Zero infrastructure changes. Zero blast radius.**

And the beauty of this pattern is that including the pre-flight is one line of YAML. Any playbook in your organization can be protected this way.

---

### Act 3 — Ansible Enforcement: Continuous Audit Sweep

*Run Template 35 — "Sentinel - Audit: Scan All Playbooks".*

Third enforcement point. Both gates can be bypassed in theory — maybe the webhook was down for a week, maybe someone has admin privileges. How do you find violations that slipped through?

*[Wait for job output. Point to the compliance table.]*

This job scans every playbook in the repository, evaluates each one against OPA, and writes the results to PostgreSQL. Look at the output — you can see which playbooks are ALLOW and which are DENY, with the specific violation codes. The job deliberately fails so it shows red in AAP, which triggers a notification.

**This runs on a schedule. Your compliance posture is never more than 24 hours stale.**

HashiCorp Sentinel has no equivalent to this. It has no concept of auditing what's already in your repository.

---

### Act 4 — Terraform Enforcement

*Run Template 46 — "Sentinel — TF Bad (Denied)".*

Now for Terraform — this is the one capability HashiCorp Sentinel also has. I want to show you that AAC does it just as well.

*[Wait for the job to output the violations.]*

Three violations. An EC2 instance and an RDS instance are both missing required tags — Owner, CostCenter, Environment. Without these, your finance team can't track cloud costs, and your security team can't identify who owns a resource during an incident. And there's an SSH port 22 rule open to the entire internet on the web security group. OPA denies this plan. It never reaches `terraform apply`.

*Optionally run Template 47 — "Sentinel — TF Good (Approved + Apply)".*

Now watch the compliant plan.

*[Point to the ALLOW result and terraform apply output.]*

OPA evaluates the plan, finds no violations, returns ALLOW, and AAP proceeds with `terraform apply`. A t3.micro spins up, we verify it, then destroy it. The entire enforcement-to-apply loop is automated and auditable.

---

### Act 5 — AI Controls Enforcement

*Run Template 36 — "Sentinel - Demo: AI Controls Enforcement".*

Last enforcement point — and this one is forward-looking. As AI agents become part of your automation estate, you need governance over what they're allowed to do. No other tool has this.

*[Walk through the four scenario outputs as they appear.]*

Scenario one: an AI agent requests to run a compliance audit. Read-only operation. OPA evaluates it — **ALLOW**. No human needed. It runs.

Scenario two: an AI agent wants to remediate a high-severity vulnerability on a production server. No approval ticket attached. OPA says **PENDING_APPROVAL**. The action is blocked. A notification goes to the CISO's queue.

Scenario three: same remediation request, but this time it includes an approved CISO ticket. OPA says **ALLOW_WITH_LOGGING**. The action proceeds, but every detail is written to PostgreSQL — what the AI did, when, under whose authorization.

Scenario four: an AI system that hasn't been authorized in our registry tries to deploy infrastructure. **DENY**. Blocked at the policy layer before a single API call is made.

**You govern AI the same way you govern humans and code — with OPA policies evaluated before any action executes.**

---

*Pause. Let the enforcement story land.*

So that's five enforcement points. HashiCorp Sentinel covers two of them. AAC covers all five. And everything you just saw — every ALLOW and DENY decision — is stored in PostgreSQL with a timestamp. That's your audit trail.

---

## PART TWO: Continuous Compliance Assessment (10 minutes)

*Navigate to Job Templates. Have the NERC-CIP and AMI templates visible.*

Policy enforcement catches what's wrong at deploy time. Now let me show you the other side of the platform — **continuous assessment of what's already running**.

---

### NERC-CIP Critical Infrastructure Compliance

*Run Template 26 — "AAC - NERC CIP Compliance Report".*

This organization operates bulk electric systems — this is a NERC-regulated utility. Every year they submit a compliance report to their regional reliability entity. Historically that report takes three weeks and a consulting engagement. Let me show you what that looks like with AAC.

*[Wait for the job output. Walk through the results summary.]*

CIP-002 through CIP-015 — all fourteen Critical Infrastructure Protection standards evaluated automatically. Facts were collected from the BES Cyber Systems and evaluated by OPA in the `opa-ot` container, our operational technology policy engine. Results go directly into PostgreSQL.

Look at the output. 11 requirements passing. CIP-015 Internal Network Security Monitoring — 100% compliant across all three requirements. The overall status is COMPLIANT.

**This ran in under 30 seconds.** The same assessment that used to take three weeks.

---

### AMI Smart Meter Compliance

*Navigate to and run Template 29 — "AMI - Full Compliance Audit and Store".*

Now let me show you the Advanced Metering Infrastructure component. This utility operates smart meters for electric, gas, and water customers — 30 devices across three utility types.

*[Wait for the job output.]*

Three frameworks evaluated simultaneously. NIST IR 7628 Rev 1 — the federal smart grid security standard. AMI Device Compliance, which maps to ANSI C12.22 and IEC 62351. And AMI Head-End Security. Each evaluated per utility type.

*[Point to the per-utility scores.]*

Head-End Security is at 90% across all three utilities — strong. NIST IR 7628 is at 83%. Device Compliance is where we have work to do — 40%, meaning 6 of the 10 devices in each utility fleet are non-compliant.

Let me show you exactly which devices and exactly why.

---

### The Audit Report

*Open ~/Downloads/nerc_cip_audit_report_2026-03-26.pdf.*

*[Display the cover page.]*

This is the PDF audit report that was generated from the data we just stored. This is what goes to the regulator.

*[Flip to Section 4: AMI Smart Meter Infrastructure.]*

Look at Section 4. Every device in the fleet. For the electric utility — SM-electric-0001 through SM-electric-0004 are clean. SM-electric-0005: expired device certificate, marked CRITICAL. SM-electric-0006 and 0007: key rotation overdue, last rotated more than 90 days ago. SM-electric-0008: firmware version 2.1.0, below the minimum required 3.2.1. SM-electric-0009: prohibited encryption algorithms in use and mutual authentication disabled. SM-electric-0010: physical tamper detected — that's a CRITICAL finding requiring immediate investigation — and secure boot is not enabled.

The same findings repeat for gas and water, because these are fleet-wide issues, not isolated to one utility.

*[Flip to Section 5: CIP Standards Compliance Results.]*

Section 5 is the NERC-CIP results table. Every standard from CIP-002 to CIP-012, pass or fail, with the full description. This is the evidence table an auditor walks through.

*[Flip to Section 6: CIP-015 INSM.]*

CIP-015, Internal Network Security Monitoring — three requirements, all passing.

*[Flip to Section 10: Auditor Certification.]*

And the final section is the certification and signature block — ready for the compliance officer to sign and submit.

**This report was generated in under a minute from live data in PostgreSQL. No spreadsheets. No consultants. No three-week engagement.**

---

## PART THREE: The Nightly Workflow (3 minutes)

*Navigate to Workflow Templates, show Workflow 99.*

The real power of this platform is that none of what you just saw requires human initiation.

*[Open Workflow 99 — "NERC/AMI - Nightly Audit + Report". Show the workflow graph.]*

Every night at 3:00 AM UTC, this workflow kicks off automatically. The NERC-CIP assessment and the AMI compliance assessment run in parallel. When both complete, the remediation report job runs, queries the new results from PostgreSQL, and produces a prioritized list of open items — CRITICAL first, then HIGH, then MEDIUM.

*[Point to the schedule.]*

The compliance team wakes up every morning to a fresh status. If something has drifted since yesterday — a certificate expired, a patch fell behind, a configuration changed — it shows up in the report. Not during the next quarterly audit. **Today.**

The audit trail in PostgreSQL goes back to the first day you installed AAC. Every assessment, every score, every violation — immutable, timestamped, queryable. When a regulator asks "show me your compliance posture on this date," you run a SQL query.

---

## PART FOUR: Grafana Dashboards (3 minutes)

*Open Grafana at http://AAP_HOST:3000. Login: admin / $GRAFANA_PASSWORD.*

*[Navigate to the AMI Compliance Dashboard.]*

The dashboards pull directly from PostgreSQL in real time. Your CISO can bookmark this page. It shows compliance trends over time, per-framework scores, open violation counts.

*[Point to the per-utility breakdown if available.]*

When Device Compliance drops to 40% because six meters have certificate issues, **it shows up here as a red panel at 3am**. The on-call team doesn't have to wait for a monthly report. The evidence is live.

---

## Closing (2 minutes)

*Return to the AAP Job Templates list.*

---

Let me leave you with two things. AAC runs on infrastructure you already own: Ansible Automation Platform, which you're already paying for.

**338 CIS controls** — that's our RHEL 9 coverage, 100%. And that same policy-as-code approach scales to CIS benchmarks for Windows, Ubuntu, Kubernetes, AWS, Azure, Oracle, and 15 other platforms. NERC-CIP. NIST. ISO 27001. SOC 2. PCI-DSS. SOX. FISMA. One platform, complete coverage — because regulators require 100%, not the 20% that a traditional IT automation tool covers.

**Zero spreadsheets** — every piece of evidence you just saw is automatically collected, evaluated, stored, and reportable. The PDF you saw gets generated from live data. When your auditor arrives, you hand them a login to Grafana and a PDF. The three-week consulting engagement is replaced by a job template.

That's AAC. Policy enforcement from commit to production, continuous compliance assessment, and audit-ready evidence — all automated, all on Ansible Automation Platform.

What questions do you have?

---

## Common Questions & Answers

**Q: How long does installation take?**
> A: For a greenfield deployment on an existing AAP 2.6 environment, the install script takes about 45 minutes. It provisions the OPA containers, loads the policy library, sets up PostgreSQL, creates all 50+ job templates, and configures the nightly schedules. Day one you have a running system.

**Q: Can we customize the policies?**
> A: Yes, and that's a key part of the value proposition. The policies are Rego files in a Git repository. Your compliance team edits them, commits, and the next policy load job picks them up. No compiled code, no vendor tickets. You can add organization-specific rules in the `policies/corporate/` directory — password policies, approved regions, required tags. We've had customers add 900+ custom policies. Once you have that depth of policy, switching to any other tool becomes economically impossible.

**Q: What about remediation — does AAC fix things automatically?**
> A: Deliberately, AAC is read-only by default. We assess. We report. We enforce at the gate. Auto-remediation is available — we have playbooks for it — but the default posture is that a human approves remediation before it runs. You saw that in the AI Controls demo: even an AI request to remediate requires a CISO ticket. The reason is practical: auto-remediating a production BES Cyber System without human sign-off would itself be a NERC-CIP violation.

**Q: What's the difference between this and Ansible's built-in compliance modules?**
> A: Ansible collects facts and runs playbooks. It has no native policy decision engine — if you want to say "this configuration violates CIP-007," you write that logic in Jinja2 inside the playbook. That logic lives in automation code, not in a policy file. AAC separates the concerns: Ansible collects evidence, OPA decides whether that evidence is compliant, PostgreSQL records the history. The separation means your compliance team can change policy without touching automation code, and your security team can audit every policy change in Git.

**Q: We already use Qualys / Tenable. Why replace it?**
> A: You don't have to replace it — AAC can ingest Qualys and Tenable scan data alongside its own assessments. But the observation we hear from customers is that Qualys tells you about vulnerabilities, not about regulatory compliance controls. A NERC-CIP auditor isn't asking about CVEs — they're asking "do you have a documented access control review process, and can you show me it ran last month?" AAC answers that question. Qualys doesn't.

**Q: How does this handle Windows and cloud infrastructure?**
> A: Windows assessment uses WinRM rather than SSH. We have CIS Benchmarks for Windows Server 2016, 2019, and 2022, with the same modular Rego policy structure as Linux. For cloud, we have CIS Foundations benchmarks for AWS, Azure, and GCP — those assess the control plane configuration rather than individual instances. All results flow into the same PostgreSQL database and appear in the same Grafana dashboards.

**Q: What does NERC-CIP 015 actually require and how does AAC address it?**
> A: CIP-015 is the Internal Network Security Monitoring standard — it requires utilities to deploy IDS/IPS sensors inside their Electronic Security Perimeters, not just at the boundary. Three requirements: categorize which assets need INSM coverage, implement the monitoring, and maintain the documentation. AAC evaluates all three via OPA. The evidence we collect — sensor deployment records, coverage reports, alert review logs — maps directly to the R1, R2, and R3 requirements you saw in the PDF. During an audit, you can show the assessor the specific evidence collected for each requirement.

---

## Quick Reference — Screen States by Section

| Section | What to have open |
|---------|------------------|
| Opening | AAP Job Templates list |
| Act 1 — Git Gate | Template 33 running / output |
| Act 1 — Runtime | Template 34 running / output |
| Act 1 — Audit Sweep | Template 35 running / output |
| Act 2 — Terraform Bad | Template 46 running / output |
| Act 2 — Terraform Good | Template 47 running / output |
| Act 3 — AI Controls | Template 36 running / output |
| NERC-CIP | Template 26 running / output |
| AMI | Template 29 running / output |
| PDF Report | `~/Downloads/nerc_cip_audit_report_2026-03-26.pdf` |
| Nightly Workflow | Workflow 99 — visual editor |
| Grafana | http://AAP_HOST:3000 — AMI Dashboard |

---

## Executive Summary Version (15 minutes)

For a C-suite audience with limited time, run only:

1. **Opening** — the two problems (1 min)
2. **Act 1, Step 1** — Ansible git gate DENY (2 min) — "HashiCorp Sentinel can't do this"
3. **Act 2, Bad Terraform** — shows overlap with Sentinel (2 min) — "we do what Sentinel does too"
4. **NERC-CIP job** — 30-second assessment (2 min)
5. **PDF Report** — open it, flip to the AMI section and the CIP results table (3 min)
6. **Grafana** — show the dashboard (2 min)
7. **Closing** — three numbers (2 min)

Skip the runtime pre-flight, audit sweep, AI controls, and workflow sections. Those are for a technical audience.

---

*End of presenter script.*
