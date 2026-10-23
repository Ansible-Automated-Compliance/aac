# ADR-003: Policy / Benchmark Version Lifecycle — Manifest-Driven Versioning

**Status:** Proposed (draft for review)
**Version:** v0.2
**Date:** 2026-10-08 (v0.1 2026-09-15)
**Deciders:** Tim Coulter (architect / maintainer)
**Authors:** Tim Coulter; Claude (Anthropic) — co-author
**Supersedes / relates to:** ADR-002 (Policy Engine — OPA)

---

## 1. Context

AAC evaluates infrastructure against published benchmarks and frameworks (CIS, NIST,
STIG, ISO 27001, NERC-CIP, …). **These sources are revised on their own cadence** — CIS
M365 Foundations went v3.1.0 → v7.0.0; CIS RHEL 9 will eventually get a v3; STIGs
release quarterly. Each revision can change the control set, so a score under one
version is not comparable to a score under another.

Today versioning is **ad-hoc**. The CIS M365 work is the worked example of the cost:

- The v7 bundle was published as a **new package** (`cis_m365_v7`) beside the old
  `cis_m365` — the right instinct, but nothing enforced or wired it.
- The **old `cis_m365` bundle was left in the tree**. Because it lives under
  `benchmarks/cis/**`, the loader loads it into opa-security right next to v7. It has
  no `.main` aggregator, so querying it returns `{}`. A customer POC did exactly that and
  hit an "empty report / a rule is undefined" failure.
- Routing the new version required a **hand-chase across four places** — the assessment
  role default, the loader, `opa_framework_map`, and every doc/runbook — and each was
  found wrong or stale in a separate review round.
- History was stored version-explicit (`framework='cis_m365_v7'`), which was correct,
  but by accident of that one collection rather than by policy.

The failure modes were all **structural**, not content bugs: the v7 rego itself passes
144/144 tests. The problem is that a version bump has no single control point, and a
retired version has no defined end-of-life, so it lingers as a landmine.

## 2. Decision drivers

1. **One-edit bumps.** Introducing a new benchmark version must be a single, obvious
   change — not a sweep across role, loader, map, and docs.
2. **No landmines.** A superseded version must not silently keep loading and answering
   queries with `{}`.
3. **Version-explicit history.** New versions must be trackable as their own series; scores
   must not silently mix incomparable control sets.
4. **Customer / auditor pinning.** Auditors frequently mandate a specific benchmark
   version; an assessment must be able to target a named version.
5. **Discoverability.** A contributor must be able to see, in one place, which versions
   of a framework exist and which is current.

## 3. Options considered

**Option A — Ad-hoc suffixed packages (status quo).** Each version is its own package
(`cis_m365_v7`); routing and retirement handled by hand per framework.
*Rejected:* this is what produced the M365 landmine and the four-place hand-chase. No
single control point, no retirement discipline.

**Option B — Single stable package name, version as data.** Keep one package
(`cis_m365`), carry `benchmark_version` as a field, update content in place.
*Rejected:* in-place mutation destroys the old version (can't run v7 and v8 side by
side for a pinned customer), makes history incomparable, and offers no clean migration
window. This is essentially what the original unversioned `cis_m365` did, and it broke
the moment the control semantics changed.

**Option C — Manifest-driven parallel packages with enforced retirement (chosen).**
Versions remain explicit, parallel packages; a small per-framework **manifest** is the
single source of truth for which versions exist, which is default, and each version's
lifecycle status; the loader, assessment role, framework map, and a CI guard all resolve
from it. See §4.

## 4. Decision

Adopt **manifest-driven versioning** with five elements.

### 4.1 Version is always explicit in package and directory

Every benchmark that can revision uses a versioned package and directory —
`benchmarks/cis/saas/m365_v7/`, package `cis_m365_v7.*`. No bare unversioned names for
revisionable content. (`cis_rhel9` is the current exception and migrates to
`cis_rhel9_v2` under §6.)

### 4.2 A per-framework version manifest is the single source of truth

A small file next to the policies declares available versions, the default, each
version's lifecycle status, and the OPA bucket. It travels with the rego library
(a submodule bump carries the version change):

```yaml
# policies/benchmarks/cis/saas/m365/versions.yml
framework: cis_m365
bucket: security                 # intrinsic to the framework; feeds opa_framework_map
default: v7                      # what an unpinned assessment runs; must name the one version whose status is `default`
versions:
  v7:
    package: cis_m365_v7
    dir: benchmarks/cis/saas/m365_v7
    status: default              # default | supported | deprecated | removed — exactly one `default`
    benchmark_version: "7.0.0"
  cis_m365:                       # the pre-v7 bundle
    package: cis_m365
    dir: benchmarks/cis/saas/m365
    status: removed              # not loaded; leaves the tree
    benchmark_version: "3.1.0"
```

**Lifecycle statuses:** `default` (the one unpinned runs pick — exactly one per
framework), `supported` (loadable, pinnable), `deprecated` (still loaded and pinnable,
emits a warning, scheduled for removal), `removed` (not loaded, deleted from the tree).

### 4.3 Four consumers resolve from the manifest

- **Assessment role** — `m365_opa_package` and the bucket come from `default` + `bucket`
  (removes today's hardcoded role default).
- **Loader** (`load_opa_policies.yml`) — loads only `supported` / `deprecated` / `default`
  versions; a `removed` version is never loaded.
- **`opa_framework_map`** — generated from each manifest's `bucket`, closing the current
  gap where `cis_m365_v7` is absent from the map.
- **CI guard** — see §4.5.

### 4.4 History stays version-explicit

Results persist the versioned framework string (`framework='cis_m365_v7'`). A new version
is a new series; trends never silently mix control sets. A `benchmark_version` survey
variable lets a customer pin a specific version, defaulting to the manifest `default`.

### 4.5 Retirement discipline + a CI guard

The recurring landmine — a superseded bundle that still loads and returns `{}` — is
closed by a CI check:

> For every version the manifest marks loadable (`default` / `supported` / `deprecated`),
> `opa eval 'data.<package>.main.compliance_report'` on empty input must return a
> **populated object**, not `{}` or `undefined`.

A `removed` version must not exist in the tree (or the guard fails). This single check
would have caught the dead `cis_m365` bundle before it reached the customer.

## 5. Consequences

**Positive**
- A version bump is: add the new bundle dir + flip `default` + mark the prior version
  `supported`/`deprecated`. One file, one submodule bump.
- Retired versions cannot linger as `{}`-returning landmines.
- `opa_framework_map` stops drifting out of sync with the loaded policy set.
- Customer version pinning and version-explicit per-version history fall out for free.

**Costs / migrations**
- A one-time migration to add `versions.yml` to each revisionable framework and rename
  `cis_rhel9` → `cis_rhel9_v2` (with a compatibility window).
- The loader, assessment roles, and framework-map generation must be reworked to read the
  manifest. This is done incrementally, one framework at a time — the manifest is additive,
  so un-migrated frameworks keep working unchanged.
- Manifests live in the rego library but are consumed by the compliance repo through the
  submodule; a bump is a coordinated two-repo change (already the norm for policy updates).

## 6. Rollout

1. **This ADR** — agree the scheme.
2. **M365 as the reference implementation** — it is already in flight, and its cleanup
   (remove the retired `cis_m365` bundle, repoint/rename `full_cis_assessment.yml`, fix
   the customer install guide, add the manifest + the four consumers + the CI guard) *is* the
   pilot. One framework, proven end-to-end.
3. **Backfill** the remaining frameworks onto manifests over time; `cis_rhel9` →
   `cis_rhel9_v2` happens in this phase.

## 7. References

- ADR-002 (Policy Engine — OPA): the three-bucket loading model this builds on.
- The M365 subsystem audit of 2026-09-15 (the audit that motivated this; a customer-facing
  artifact held outside the repo): the retired-bundle landmine, the framework-map gap, and the
  four-place hand-chase.
- `ansible/playbooks/load_opa_policies.yml`: the `benchmarks/cis/** → opa-security` routing
  that a manifest `bucket` field formalizes.
- Rego library rule #5 ("`default rule := false` is required; an undefined field collapses
  the report to `{}`"): why the CI guard checks a populated `.main` on empty input.
