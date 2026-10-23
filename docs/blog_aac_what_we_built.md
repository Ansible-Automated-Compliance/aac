# What We Built: Turning the Automation You Already Own Into a Compliance Evidence Engine

**Version:** v1.2
**Date:** 2026-10-23
**Status:** Draft for publication. Every count below was taken from the repositories on this date.
**Authors:** Tim Coulter · Claude (Anthropic)

---

In March I started a repository with one Rego file in it. It checked whether a RHEL 9 host had its audit daemon configured the way CIS says it should. Seven months later that repository holds 729 policies across 976 Rego files, a second repository runs them against real infrastructure from Ansible Automation Platform, a third gives auditors and operators a place to see the results, and a fourth holds the demos. The whole thing has a name, Ansible Automated Compliance, and a short way of saying what it does: **gather facts once, judge them against many frameworks, and keep the verdicts as evidence.**

This post is about what we built, what turned out to matter, and what we deliberately did not build. It is written for people who run infrastructure under regulatory pressure and already own an automation platform. The code is open source and the links are at the end.

## The problem we were actually solving

Compliance in most enterprises is a point-in-time event. A few weeks before the audit, someone assembles screenshots, exports, and spreadsheets to show that controls were in place. The evidence is manual, it is stale by the time it is read, and it has to be rebuilt for every framework because the CIS assessor, the NERC auditor, and the ISO certifier each want their own pile.

Meanwhile the same enterprise already has an automation platform that talks to every host, every cloud account, and every network device it owns. It gathers facts about all of them as a matter of routine. The facts that prove a control is in place are, most of the time, facts the platform already has.

So the thesis was simple. Do not build another scanner. Use the automation platform to collect the facts once, hand them to a policy engine that knows what every framework requires, and write the result down in a database as an appended record that does not expire. Compliance stops being an event and becomes a by-product of operating the estate.

## The one mechanism everything rides on

Every feature in the platform is the same three steps wearing different clothes.

**Ansible gathers facts.** Playbooks collect the state of a RHEL host, a Windows server, a Microsoft 365 tenant, a Kubernetes cluster, a Terraform plan, or a smart meter head-end. One collection run produces one facts document.

**OPA evaluates them.** Open Policy Agent loads the policy library and answers the question "given these facts, which controls pass, which fail, and why." The same facts document is evaluated against every framework that applies to that asset. A RHEL 9 host gets CIS, the DISA STIG, NIST 800-53 and whatever regulatory overlay the business lives under, from one fact collection.

**PostgreSQL keeps the verdict.** Every evaluation lands in a results table with the asset, the framework, the control, the outcome, the reason, and the time. The evaluation path only appends; a verdict is never rewritten by a later run. The history is the audit record.

That is the whole architecture. The Grafana dashboards, the drift detection through Event-Driven Ansible, the CI/CD gates, the auditor reports and the customer portal are all either views onto that record and the tables derived from it, such as the technical-debt rollup and the inventory catalog, or triggers that cause another run to be written into it.

## What we built, layer by layer

**The policy library.** This is the content asset and the part most people find first. As of today it covers 42 CIS benchmark platforms, 19 DISA STIGs, and 48 framework modules across federal, financial, privacy, critical infrastructure, sovereignty and regional law, plus governance policies for AI systems, supply chain and FinOps, and enforcement policies for nine decision surfaces: Terraform, Kubernetes admission, CI/CD pipelines, Dockerfiles, git approvals, AAP job launches, Ansible content, repositories and software supply chain. This week all but two of those 729 policies gained a metadata block at the top of the file that states its class, framework, source authority and domains in a controlled vocabulary, so a consumer can ask the engine itself for "every security-class policy" instead of reading directory names. The last two, and the CI check that will refuse a new policy without a block, land with the next release. The library is Apache 2.0 and vendor-neutral. It does not know or care that Ansible collected the facts.

**The evidence engine.** The results schema carries provenance for every verdict. Exceptions are handled through policy too: a waivers file is evaluated by OPA, and a waived finding moves into metadata rather than disappearing, so an auditor can see what was excused and by whom. Reports can be exported in OSCAL assessment-results format. A technical-debt rollup prices open findings in hours so that an operations lead can rank remediation by effort instead of by alphabetical order.

**The decision surface.** Once the pattern of facts in, verdict out exists, it is tempting to apply it everywhere, and we did. The same OPA instances that judge host posture also gate Terraform plans before apply, admit or reject Kubernetes workloads, and decide whether an AAP job may launch. The most consequential of these is the newest. When we exposed the automation platform to an AI agent through the Model Context Protocol, the agent could reach 447 controller tools, among them delete, create-credential and change-settings operations. We put OPA in front of every tool call. The policy is default-deny, every decision can be persisted allow and deny alike and the deployment we run persists all of them, and the agent's own recommendation is treated as one more input the policy weighs, never as the verdict. We wrote that one up separately because it deserved its own post.

**The experience surfaces.** Grafana for operators, generated auditor-facing reports, and a multi-tenant customer portal built on FastAPI and React where a tenant can see posture, decide on remediation under a four-eyes rule, and prove what was done with signed policy bundles. The portal reads the customer's evidence database through a bridge and never takes raw facts out of the customer's environment.

**Distribution.** Four install paths, from a fresh platform to an existing one to a configuration-as-code import, and a single go/no-go verifier that refuses to call an install complete until the policy loader, the database, and the engines agree. On the ingestion side, scanner output can be loaded as evidence: OpenSCAP and CIS-CAT Pro results through an XCCDF and ARF parser, InSpec results through a separate ingester for its HDF format, so estates that already run those tools can bring their existing output along.

## The three rules that turned out to matter most

Looking back over seven months, three engineering decisions did more work than any feature.

**Fail closed, everywhere.** A framework that receives no facts reports non-compliant with the reason "could not be evaluated." It never reports a pass, and an empty result is never stored as green. This sounds obvious. It is also the single thing a generated policy library is most likely to get wrong, because the natural shape of a Rego rule is to be true when its conditions match and silently absent otherwise. We enforce the doctrine in three places: in the shape of the policies, in the loader that refuses to wire a framework with no entry point, and in the consumers and report generators that treat an empty evaluation as not evaluated rather than as a pass. The policy layer is not yet uniform. Seven older framework entry points still return an empty object when given no facts, and the layers above them catch it. Closing those seven in the policy itself is on the list. Last week a review found a benchmark that had quietly passed when a facts section was missing. It was fixed the same day, and the fix was a test that fails if it ever regresses.

**Evidence, not compliance.** The platform produces evidence of compliance. Compliance is a judgement a human assessor makes. This is NIST's own distinction between assessing and authorizing, and we took it literally, down to the naming of tables and reports. The tool never says "you are compliant." It says "here is what we observed, here is what the framework requires, here is the gap, here is when." That restraint is what makes the evidence worth something to the person who has to sign.

**Count it, do not quote it.** Every number in this post was produced by a command run against the repositories today. Documentation that quotes a count becomes wrong the week after it is written. We learned this by finding three different policy totals in three different documents and discovering that none of them was right. Now the badge in the README and the figure in a customer deck are re-counted from the repository whenever either is revised, and this post was the trigger for the latest recount.

## How it was built

The way the platform is built is part of what it is. The policies were drafted with an AI coding assistant working from the primary sources: the benchmark PDFs, the regulation text, the STIG XML. Every pull request is then reviewed by a second, independent AI reviewer before a human looks at it, and the two disagree often enough to be useful. Protected paths in the repositories, the workflows, the enforcement policies and the policy pin, require an explicit approval trailer on the commit, and a policy evaluated in CI checks for it. The project governs its own change process with the same engine it sells.

We also published our own defects. When an audit of the evidence corpus found results stored with incomplete provenance, the assessment went into the repository with the fixes, and the fixes changed how results were recorded without rewriting a single historical verdict. A compliance tool that cannot be honest about its own evidence has no business asking anyone else to be.

## What it is, and what it deliberately is not

It is not a Red Hat product and carries no support entitlement. The architecture it rides on, an automation platform calling a policy engine, is supported product. The policy content and the delivery tooling are an open-source project, in the way playbooks are content on Ansible.

It is a scanner first, and the broadest one you will run: the collections that manage a technology define its configurable settings, and AAC reads those settings for their current value over the technology's own management path, with no agent, then judges them. Nothing else reads that breadth of technologies through one program. It is not CIS-certified or SCAP-validated, and nothing in the library requires that; where a programme does require validated output, that tool's results land in the same evidence store beside AAC's own findings. For NIS2, DORA, the EU AI Act, digital sovereignty and supply-chain controls no certified tool exists at all, and the policy library is the engine.

It is not a product with fixed, pre-built components. There is no proprietary check set, agent or console you take as shipped: the collectors are Ansible content, the checks are Rego you can read and change, the engine, the database and the dashboards are the ones you already run, and every piece can be replaced.

It is not auto-remediation. Every remediation path is assessed first and gated by approval. Regulated operators want change control, not convergence, and the platform treats governed remediation as a feature rather than a limitation.

And it does not produce compliance. It produces the evidence from which a human can conclude compliance. We keep saying that because it is the point.

## Where to find it

- Policy library: https://github.com/ynotbhatc/rego_policy_libraries
- Orchestrator and install paths: https://github.com/ansible-automated-compliance/aac
- Demos and runbooks: https://github.com/ynotbhatc/aac-demos
- Policy catalog: https://ynotbhatc.github.io/rego_policy_libraries/

If you run an automation platform and an audit calendar, the facts you need are already flowing through the first. The rest is policy.

---

## Authorship

Drafted by **Tim Coulter** with **Claude (Anthropic, Claude Fable 5.1)** as co-author. Claude produced the counts from the repositories on the date above and drafted from the project's internal design documents. Tim edits and authorises every shipped-state claim.
