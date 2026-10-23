# AAC Install Methods — Support Matrix and Lifecycle

**Version:** v1.0 · **Date:** 2026-08-31
**Authors:** Tim Coulter; Claude (Anthropic)

The single honest statement of which install paths exist, what tier each sits at, and what has
actually been tested. This document exists because four install docs previously claimed four
different AAP versions and nothing stated what had been exercised (handover audit v1.1 §4).

## Tiers

- **Supported** — the paths we stand behind; changes go through review and the install-config
  hygiene gate; regressions are defects.
- **Demo/field** — works and is exercised, but exists for demo environments; not a customer
  install path.
- **Unsupported (lab example)** — maintainer lab tooling, kept in the aac-demos repository (`demos/lab-crc/`), outside this repository and its hygiene scan; no
  expectations attached.
- **Absorbed** — the name remains as a pointer; the content lives inside a supported path.

## The matrix

| Method | Tier | Target | AAP | Execution evidence (as of 2026-08-31) |
|---|---|---|---|---|
| [`standard/`](standard/README.md) | **Supported** (canonical) | Any, profile-driven (`lab`/`rhpds`/`customer`) | 2.6+ (2.7 reference) | Preflight + verify gates executed and fail-closed behavior proven 2026-08-31; install stages still converging (see README status) |
| [`standard/` EC2 provisioning](standard/PROVISION_EC2.md) | Supported (path into standard) | Fresh EC2/bare metal | 2.6 bundle | **Never executed on the current lab** — chain exists (fresh_install_00–06), phase 06 GO/NO-GO gate well-designed; treat as unvalidated until a full exercise |
| [`existing-aap/`](existing-aap/README.md) | **Supported** | AAP already running | 2.6+ | Lab-exercised informally; the reference lab itself is an existing-AAP-style deployment |
| [`existing-aap/extended/`](existing-aap/extended/README.adoc) | Supported (variant) | Existing AAP + quadlets/EE build | 2.5.5+ | Authored 2026-08; bootstrap playbook untested on current lab |
| [`config-as-code/`](config-as-code/README.md) | **Supported** | Git + AAP API | 2.6+ | The RHPDS CaC files are applied by the provisioning flow |
| [`rhpds/`](rhpds/README.md) | **Demo/field** | RHPDS OpenShift clusters | 2.6/2.7 | Exercised across multiple cluster provisionings; per-cluster by nature |
| [`openshift-local/`](openshift-local/README.md) | **Demo/field** (evaluation) | One RHEL 9 host: AAP 2.7 and Automation Orchestrator in OpenShift Local, from shipped manifests; AAC via `existing-aap/extended/` afterwards | 2.7 | Authored 2026-10-22; manifests and values taken from the maintainers' AAP 2.7 (`stable-2.7`, CSV `aap-operator.v2.7.0`) and Orchestrator (`stable`, CSV `automation-orchestrator-operator.v2026.8`) installs; not yet walked end to end by a customer team |
| `from-scratch/` | **Absorbed** → `standard/PROVISION_EC2.md` | — | — | Name kept as a pointer only |
| aac-demos `demos/lab-crc/mac-aap/` | **Unsupported** | Maintainer laptop CRC | 2.7 | Heavily exercised (it is the maintainer's daily lab) — but that is not a support statement |

## Lifecycle policy

- A method enters **Supported** only with: a walkthrough-verified README, preflight/verify gate
  coverage, and at least one recorded end-to-end exercise.
- A Supported method that loses its maintainer or fails its exercise two releases running is
  demoted with a deprecation note in the chooser, kept one release, then absorbed or removed.
- The lab example in aac-demos carries no lifecycle at all — it may change or vanish without notice.
- This matrix is updated in the same PR as any change to install-method structure; the chooser
  (`install/README.md`) links here and lists only non-absorbed methods.
