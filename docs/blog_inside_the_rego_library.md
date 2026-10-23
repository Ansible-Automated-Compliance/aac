# Inside the Rego Library: How 13,758 Compliance Checks Are Built, Counted and Kept Honest

**Version:** v1.0
**Date:** 2026-10-12
**Status:** Draft for publication. Every count below was taken from the repository at tag v2.3.4 on this date, with the command that produces it.
**Authors:** Tim Coulter · Claude (Anthropic)

*The opinions in this post are mine and my co-author's. They are not Red Hat's.*

---

Seven months ago the library was one file that checked an audit daemon. Today it is 740 Rego policy files holding 13,758 control-level checks across 54 tracked standards, and a CI job recomputes that number on every merge and fails the build if the README disagrees with it. I believe it is the largest open library of executable compliance policy that anyone can verify. This post is not about the size. It is about how the thing is built, what the policies actually look like inside, and the two places where it embarrassed us this year and what we changed.

If you write policy as code, run OPA, or sit on the receiving end of audits, the details below are the ones that matter.

## One contract for every framework

Every framework in the library, whether it is CIS RHEL 9 or the Monetary Authority of Singapore's technology risk guidelines, answers the same question at the same address:

```
data.<framework>.main.compliance_report
```

The report is a structured object: `compliant`, `compliance_percentage`, `total_controls`, `passed_controls`, `failed_controls`, a `violations` list where every entry carries the control number and what was wrong, and whatever the framework adds. A dashboard, a CI gate or an orchestrator evaluates one framework by name without learning its internal layout. That uniformity is the single most useful property the library has, and it was the hardest to keep as the library grew past a hundred directories.

Three rules hold the contract together, and all three came from production failures rather than design sessions.

**Default to false.** In Rego a rule that never fires is not `false`, it is `undefined`. An `undefined` member inside an object literal makes the whole object undefined, and OPA then returns `{}` at the endpoint. An orchestrator that stored whatever OPA returned wrote an empty result and marked the job green. So every boolean in a report is sourced through a defaulted helper, and the contract forbids a report that can collapse.

**Fail closed.** A framework given no facts must report non-compliant with an explicit reason, never a silent pass. The idiom that does it in Rego is deliberately ugly:

```rego
violations contains msg if {
    _applicable
    not _in.audit.completed == true
    msg := "CCPA §7120(a): no cybersecurity audit completed — ..."
}
```

`not x == true` fires when the field is false and also when the field is absent. `x == false` alone would let a missing field pass. Forty-two framework files use the pattern today, and the 2.3.4 release added a measured guard stamp to every module saying whether fail-closed is enforced by the module itself, by the orchestrator above it, or by nothing. More on that list below.

**One entrypoint, one metadata block.** Every package carries an OPA `# METADATA` annotation above the package line with a controlled vocabulary: class (which policy engine instance it belongs in), framework, source authority, domains, and since 2.3.4 a coverage stamp. `opa inspect -a -f json .` returns all of it as data, and a script fails the build when a block is missing or uses a word outside the vocabulary. Consumers classify policies without parsing directory names.

## Two shapes of policy

Open the library and you find two kinds of policy that look nothing alike, and the difference is the most important thing to understand about compliance as code.

**Fact-driven policies parse the system.** The CIS and STIG benchmarks, about 2,100 checks, read raw configuration that an automation platform collected and decide from it. The SSH module takes the output of `sshd -T`, splits it into a key-value map, ignores comments and blank lines, and then asks the questions the benchmark asks:

```rego
sshd_config := {lower(key): value |
    some line in split(input.ssh.sshd_config_raw, "\n")
    trimmed := trim_space(line)
    not startswith(trimmed, "#")
    trimmed != ""
    parts := regex.split(`\s+`, trimmed)
    count(parts) >= 2
    key := parts[0]
    value := parts[1]
}
```

Across the CIS tree there are about 1,300 parse operations of this kind. The rule knows nothing about intent. It knows what the daemon said its effective configuration was, and whether that string matches what the benchmark requires.

**Attestation-driven policies evaluate declarations.** The regulatory frameworks, about 5,300 checks and roughly two thirds of the library, mostly look like this instead:

```rego
# Access rights are reviewed regularly
access_rights_reviewed if {
    input.access_controls.periodic_reviews.enabled == true
    input.access_controls.periodic_reviews.frequency_days <= 90
    input.access_controls.periodic_reviews.documented == true
}
```

That is SOC 2. The standard says access rights are reviewed "regularly". The rule says 90 days, says the review must be documented, and says someone must declare that it is enabled. Where the first shape parses reality, the second shape evaluates a claim about reality. There are about 5,600 `== true` comparisons in the framework tree and about 1,000 numeric thresholds. The library does not hide this. The converters documentation states it plainly: two thirds of the checks are attestation tables, which is why they convert to any questionnaire or GRC format with a script rather than a compiler.

My opinion: this is the honest state of regulatory compliance and most tools pretend otherwise. A control that says "appropriate" or "periodically" cannot be read off a host. What a policy engine can do is pin the interpretation to a number, pin the claim to a named field with a date and a declarant, and refuse to pass when the claim is absent. That is still a large improvement over a spreadsheet, and I will say more about where it stops in the next post.

## The embarrassment, part one: a perfect score on one section

In October a colleague preparing for a customer engagement found that the Linux assessment playbooks in the companion orchestrator were sending OPA almost nothing. The RHEL 9 playbook shipped the operating system facts and none of the 59 input sections the policy modules read. The modules, finding no SSH, PAM or auditd data, raised no violations. The playbook computed a score of 338 minus zero over 338. The host scored 100 percent for weeks.

Nothing in Rego was wrong. Every rule was correct for the input it received. The defect was that the policy had no way to say "I was not given the facts to decide this", and the orchestrator had no way to ask. The fix was in the library, and it is now the pattern for every benchmark:

```rego
section_inputs := {
    "section_4_1_auditd": ["auditd"],
    "section_5_2_ssh":    ["ssh"],
    "section_5_4_5_5_pam": ["pam"],
    ...
}

section_assessed(name) if { some k in section_inputs[name]; input[k] }

not_assessed_sections := sort([name |
    some name, _ in section_inputs
    not section_assessed(name)
])

assessment_coverage_percentage := round((assessed_sections * 100) / count(section_inputs))
```

A section whose required input is missing now produces a violation that reads `NOT ASSESSED: section_5_2_ssh — required input not collected: ssh`, counts as failed in the score, and appears in the report as a coverage percentage. The orchestrator stores OPA's numbers and no longer computes its own. A host with one section collected scores a few percent, with a list of what was not looked at. That is what a customer should see.

## The embarrassment, part two: the library audits itself

The 2.3.4 release did something I would recommend to anyone maintaining a policy library of any size. A generator wrote a smoke test for every module that had none, 554 files, and each test asserts only what the module was proven to do on empty input: it evaluates without error, its report is an object, the report is not compliant, and the violations are non-empty. The suite went from 1,954 tests to 3,375.

The generator could not write that test for every module, and the ones it could not are the interesting ones. Published in the repository, by name: 60 modules whose report is undefined on empty input (the collapse to `{}` the contract forbids), 18 modules that report compliant on empty input with no orchestrator guarding them, and 2 whose report says compliant while the module itself emits violations. Those are open defects and they are listed in the repository rather than in a private tracker.

My co-author's view, which I share: a policy library that publishes its own fail-open list is more trustworthy than one with a clean README, because the second kind has simply not looked. Every count in this post comes from a script in the repository, and the comparison document that backs the "largest" claim also says what we do not claim. The closed commercial libraries, measured as per-setting checks, are probably larger. They publish no auditable count, so neither side can prove it, and we do not try.

## What else is in the tree

**A control spine.** The `crosswalk/` directory joins the standards onto a shared NIST SP 800-53 substrate: a map from STIG rule identifiers to 800-53 controls for 15 platforms, and a correlation module that turns any STIG finding list into per-control satisfied or gap status. A gap wins over a pass, and a control that was never assessed is never reported as passed. The point is to assess a control once and report it against every standard that inherits it.

**Converters.** Rego is already the native language of a dozen engines, so the biggest reach comes from packaging rather than translation. Shipping today: WebAssembly bundles with 92 entrypoints, OCI bundles on GitHub's container registry (unsigned today; signing is the next step), Gatekeeper constraint templates, Kubewarden policies, a Conftest layout for infrastructure-as-code gates, and policy sets for Terraform Cloud, Spacelift and env0. The interchange tier exports 143 OSCAL catalogs plus component definitions and assessment results, and emits SARIF and OCSF from the same compliance reports with the same control identifiers. Per-engine generators, SCAP, InSpec, Wazuh, Kyverno CEL, Azure Policy, AWS Config, Steampipe, Sentinel, Sigma and Prowler, are planned and their contract is written.

**A standards registry.** Every tracked standard has a row recording the edition the policies were written against, how often the upstream revises it and where to watch, with a monthly sweep, so a reader can see that CIS RHEL 9 is at v2.0.0 and that the Malaysian central bank's technology risk policy is the September 2026 edition before trusting a result.

**Honest coverage notes.** Where a benchmark is partially covered, the module header says so. The Google Kubernetes Engine benchmark is explicitly partial. The RHEL 9 policy modules reference 224 distinct CIS control identifiers against a benchmark of 338; a single rule can cover more than one control, so that is a floor, and the number we quote is the measured one, not the aspirational one.

## How to use it in a minute

Pull the bundle, evaluate your facts, fail the job on non-compliance:

```bash
opa eval -b bundle.tar.gz -i facts.json 'data.cis_rhel9.main.compliance_report'
```

Conftest users point it at the enforcement gates, which expose `deny`, `violation` and `warn`. The integration document in the repository has the GitHub Actions job, and it runs in the library's own CI on every merge so that it cannot go stale quietly.

## What I think this adds up to

The library is not valuable because it is large. It is valuable because every one of its checks is a small, versioned, testable statement of what a standard requires, written in a language that a dozen engines run unchanged, with a contract that refuses to pass when it has not been given the facts. The size is a consequence of a working method: read the standard, write the check, write the test, count it with a parser, publish the count and the gaps together.

If you maintain compliance evidence for infrastructure and you have ever assembled it by hand the month before an audit, I would like to talk. Message me here on LinkedIn, or open an issue on the repository. Tell me which standard hurts the most and I will tell you honestly how much of it the library can decide from facts and how much it will ask you to declare.

## Where to find it

- Policy library: https://github.com/ynotbhatc/rego_policy_libraries
- How the size was measured, against every public library we could find: https://github.com/ynotbhatc/rego_policy_libraries/blob/main/docs/COMPARISON.md
- Use it in CI: https://github.com/ynotbhatc/rego_policy_libraries/blob/main/docs/INTEGRATIONS.md
- Policy catalog: https://ynotbhatc.github.io/rego_policy_libraries/
- Orchestrator that feeds it facts from Ansible Automation Platform: https://github.com/ansible-automated-compliance/aac

---

## Authorship

Drafted by **Tim Coulter** with **Claude (Anthropic, Claude Fable 5.1)** as co-author. Claude produced every count from the repository at v2.3.4 on the date above and drafted from the library's own documentation and source. Tim edits and authorises every shipped-state claim. The opinions are ours, not Red Hat's.
