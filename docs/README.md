# AAC Documentation

This directory holds all AAC docs organized by purpose. Pick the section that matches what you're trying to do.

| Section | When to use it |
|---|---|
| **[install/](install/)** | Standing up AAC from scratch on a host or in OpenShift (CRC / RHPDS) |
| **[integration/](integration/)** | Wiring AAP, OPA, EDA, and Private Automation Hub together; calling OPA from AAP playbooks |
| **[architecture/](architecture/)** | Understanding the system design; ADRs; how the pieces fit |
| **[frameworks/](frameworks/)** | Framework-specific coverage and runbooks (CIS, STIG, NIST, NERC-CIP, Digital Sovereignty, Sentinel, AMI) |
| **[operations/](operations/)** | Day-2 ops: audit evidence collection, compliance reporting, OPA scaling, workflow setup |
| **[reference/](reference/)** | Quick references, cheat sheets, FAQ, capabilities catalog, requirements |
| **[strategy/](strategy/)** | Strategic / customer-facing material: certification roadmap, hybrid architecture, consulting playbooks |

The long-form catalog (`DOCUMENTATION_INDEX.md`) was retired 2026-09-01 — 67 of its links were dead (handover audit). This README is the docs landing page; CI now verifies every internal link (`scripts/check_doc_links.py`).

---

## Most-asked-for docs

| If you want to… | Read |
|---|---|
| Install AAC on a fresh RHEL host | [install/COMPLETE_INSTALLATION_GUIDE.md](install/COMPLETE_INSTALLATION_GUIDE.md) |
| Install AAC on RHPDS | [install/RHPDS_MANUAL_INSTALL_GUIDE.md](install/RHPDS_MANUAL_INSTALL_GUIDE.md) |
| Run AAC locally on macOS via OpenShift Local | [aac-demos `demos/lab-crc/mac-aap/README.md`](https://github.com/ynotbhatc/aac-demos/tree/main/demos/lab-crc/mac-aap) (unsupported lab example) |
| Understand the OPA + AAP integration | [integration/AAP_OPA_INTEGRATION_GUIDE.md](integration/AAP_OPA_INTEGRATION_GUIDE.md) + [architecture/AAP_OPA_INTEGRATION_ARCHITECTURE.md](architecture/AAP_OPA_INTEGRATION_ARCHITECTURE.md) |
| Look up a CRA control | [../policies/frameworks/compliance/cra/COVERAGE.md](../policies/frameworks/compliance/cra/COVERAGE.md) (in the rego_policy_libraries submodule) |
| Get a quick cheat sheet | [reference/AAP_62_CHEAT_SHEET.md](reference/AAP_62_CHEAT_SHEET.md) or [reference/AAP_OPA_QUICK_REFERENCE.md](reference/AAP_OPA_QUICK_REFERENCE.md) |
| Read the FAQ | [reference/FAQ.md](reference/FAQ.md) |
| Understand AAC's enterprise architecture | [architecture/ENTERPRISE_ARCHITECTURE.md](architecture/ENTERPRISE_ARCHITECTURE.md) |
| See the auditor-facing certifiable-audit-artifact spec | [strategy/AAC_CERTIFIABLE_AUDIT_ARTIFACT_SPEC.md](strategy/AAC_CERTIFIABLE_AUDIT_ARTIFACT_SPEC.md) |
| Understand how compliance evidence is collected + stored | [operations/AUDIT_EVIDENCE_COLLECTION.md](operations/AUDIT_EVIDENCE_COLLECTION.md) |
| Find which framework satisfies which regulatory mapping | [frameworks/REGULATORY_MAPPING.md](frameworks/REGULATORY_MAPPING.md) |

## Cross-cutting

- **README.md** at the repo root is the entry point for the whole project (architecture overview, demo links, deployment paths).
- **CLAUDE.md** at the repo root is the codebase guide for AI assistants and contributors — it describes conventions, AAP credential IDs, OPA routing, vault structure, and the topology-agnostic playbook pattern.
- **CHANGELOG.md** tracks releases; see `[2.7.0]` for the CRA / contract-expansion / mac-aap / topology-refactor wave that introduced this directory structure.

## How docs are organized

Each subdirectory holds a single category. There's no hierarchy below the first level — every doc has exactly one home. If a doc could plausibly live in two categories, it goes where the *primary audience* would look for it: e.g. `EDA_OPA_INTEGRATION.md` is integration (integration team) not architecture (design team), even though it explains how EDA fits.

Older docs whose content is fully superseded by newer ones get a `(superseded by ...)` note in their first paragraph and may eventually move to an `archive/` subdirectory. This directory does not currently have an `archive/`; if it grows one, entries there get flagged in this README.
