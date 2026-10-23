# ComplyTime Business Evaluation

## What Is ComplyTime?

[ComplyTime](https://github.com/complytime/complyctl) is a CNCF-aligned open source project that provides a `complyctl` CLI for generating compliance documentation (OSCAL artifacts, assessment plans, compliance reports) from structured control definitions. It focuses on the **document generation** and **OSCAL output** side of compliance — what auditors receive after an assessment.

## What Does AAC Do Differently?

AAC focuses on **continuous automated assessment** — collecting live facts from infrastructure, evaluating them against Rego policies in OPA, storing results in PostgreSQL, and visualising trends in Grafana. Where ComplyTime answers "did you document your controls correctly?", AAC answers "are your controls actually enforced right now across 100% of your estate?"

| Capability | ComplyTime (`complyctl`) | AAC |
|-----------|--------------------------|-----|
| OSCAL document generation | Yes (native) | Planned Q3 2026 |
| Live infrastructure assessment | No | Yes — AAP + OPA |
| Continuous monitoring / EDA | No | Yes — ansible-rulebook activations |
| 50+ framework coverage | Partial (FedRAMP/NIST focus) | Yes |
| Historical trend tracking | No | Yes — PostgreSQL JSONB |
| Executive dashboards | No | Yes — 6 Grafana dashboards |
| Drift detection + auto-remediation | No | Yes — Golden Image workflow |
| Cost-of-non-compliance scoring | No | Yes — Technical Debt framework |

## Integration Opportunity

AAC and ComplyTime are complementary, not competing. The integration picture:

```
Live Infrastructure
       │
       ▼
  AAP (fact collection)
       │
       ▼
  OPA (policy evaluation) ──► PostgreSQL (history)
       │                              │
       ▼                              ▼
  AAC compliance report ──► complyctl (OSCAL export)
                                      │
                                      ▼
                             FedRAMP / DoD submission package
```

AAC becomes the **orchestration and analytics layer** above `complyctl`:
- AAC runs the live assessment and stores structured results
- `complyctl` converts those results into OSCAL-formatted artifacts for regulatory submissions
- The auditor receives both a Grafana dashboard (live posture) and an OSCAL package (point-in-time evidence)

## Evaluation Status

| Item | Status |
|------|--------|
| ComplyTime repo reviewed | Done |
| OSCAL output format mapped to AAC PostgreSQL schema | In progress |
| `complyctl` integration playbook | Not started |
| OSCAL Assessment Results export | Planned Q3 2026 |
| FedRAMP High submission package | Planned Q3 2026 |

## Next Steps

1. Map AAC's `compliance_results` table columns to OSCAL Assessment Results fields
2. Write an Ansible role that calls `complyctl generate` using PostgreSQL-sourced control data
3. Add `AAC_Export_OSCAL` job template to the existing template library
4. Test end-to-end against a FedRAMP Moderate control baseline

---

*Last updated: 2026-04-30*
