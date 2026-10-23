# AAC — Components & Traffic Flow

**Version:** v1.0
**Date:** 2026-08-03
**Purpose:** presentation reference — what AAC is made of, and how data moves through it.
**Grounding:** the deployed reference environment (AAP 2.7 on CRC/OpenShift), verified 2026-08-01.
**Authors:** Tim Coulter; Claude (Anthropic).

---

## 1. Components

| # | Component | Role | Where it runs |
|---|---|---|---|
| 1 | **Ansible Automation Platform 2.7** | Collects facts, orchestrates every assessment, schedules recurring runs | OpenShift, ns `aap-operator` |
| 2 | **OPA — security** | CIS benchmarks, NIST, STIGs | ns `aac`, svc `opa-security:8181` |
| 3 | **OPA — compliance** | ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, sovereignty, governance | ns `aac`, svc `opa-compliance:8181` |
| 4 | **OPA — OT** | NERC-CIP, AMI / NIST IR 7628, IEC 62443 | ns `aac`, svc `opa-ot:8181` |
| 5 | **Rego policy library** | 510 policy files across 50+ frameworks — the decision logic | git submodule, loaded into 2–4 |
| 6 | **PostgreSQL** | `compliance_results` (scored history), `compliance_certifications` (signed evidence) | ns `aac`, svc `compliance-db:5432` |
| 7 | **Grafana** | Posture dashboards, trends, drift panels | ns `aac`, svc `grafana:3000` |
| 8 | **CAA signing** | cosign ECDSA-P256 — evidence an auditor can verify offline | inside the AAP job |
| 9 | **MCP server** | Governed API surface for AI agents | podman on the RHEL host, `:8004` |

**Three OPAs, one engine.** The split is by domain for blast radius and clarity — all three
listen on **8181** and are addressed by *service name*, not port.

**Optional, not load-bearing:** Grafana is presentation only. It reads the database over SQL, so
any BI tool substitutes without touching assessment, storage, or policy.

---

## 2. How compliance is evaluated — **state**, not activity

AAC answers one question: **is the system in a compliant state right now, and can I prove it?**

It does not watch logs, tail events, or infer from activity. It reads the system's actual
configuration, expresses it as data, and evaluates that data against policy.

### The three-step model

```
   1. OBSERVE            2. EVALUATE                3. RECORD
   ─────────────         ───────────                ─────────
   Ansible reads the     OPA evaluates the          Result stored with
   system's real         facts against Rego         score, violations,
   configuration    ──►  policy. Pure function ──►  timestamp, evidence
   → a JSON document     of (facts, policy).        → PostgreSQL
```

### 1 — Observe: state becomes data

Ansible gathers configuration into a JSON document — roughly 180 KB per system. Mounts, sysctls,
PAM, SSH config, audit rules, installed packages, users, cloud/cluster settings.

**Read-only.** Nothing is changed on the target. There is no agent to install.

### 2 — Evaluate: policy is a pure function of that data

A control is a statement about the facts. In Rego:

```rego
violation contains msg if {
    not input.filesystem.tmp_nodev
    msg := "CIS 1.1.6: /tmp must be mounted with nodev — currently mounted without it"
}
```

Three properties follow, and they are the whole argument:

| Property | Why it matters |
|---|---|
| **Deterministic** | The same facts and the same policy always give the same answer. A result can be replayed and reproduced months later — which is why the record stores an `input_hash` and the policy library commit |
| **Explainable** | A failure names the control and the specific reason. Auditors read the violation message, not the source |
| **Portable** | The policy doesn't care how the facts were gathered — host, cloud API, Kubernetes, or a SaaS tenant |

### 3 — Record: the answer becomes evidence

Each evaluation is stored as a row: per-control pass/fail, a score, the violations as structured
JSON, a timestamp, and a back-reference to the source object. Optionally cosign-signed so an
auditor can verify it offline.

### One observation, many frameworks

The same facts answer many questions, because frameworks overlap heavily on the underlying state:

```
                            ┌─► CIS RHEL 9      "is /tmp nodev?"
   one fact document  ──────┼─► NIST 800-53     "CM-6 baseline config"
   (state of a host)        ├─► ISO 27001       "A.8.9 configuration mgmt"
                            └─► NERC-CIP        "CIP-010 baseline"
```

Collect once, evaluate many. Adding a framework means adding policy, **not** re-instrumenting the
estate.

### Why state-based rather than activity-based

| | Activity-based (logs/events) | **State-based (AAC)** |
|---|---|---|
| Answers | "what happened?" | **"what *is* true?"** |
| Missed a change? | You lose it | Still visible — state persists |
| Auditor question *"is it compliant now?"* | Inferred | **Answered directly** |
| Baseline comparison | Hard | Native — it's just two states |

The last row is the one that matters for CIP-010 and change management: comparing two states is
trivial, and that is what makes drift detection fall out of the same machinery (§5).

---

## 3. Traffic flow — assessment (the main path)

```
   Managed estate
   RHEL · Windows · cloud · OT · OpenShift
            │
            │  ① collect facts (Ansible, read-only)
            ▼
   ┌─────────────────┐
   │       AAP       │
   └────────┬────────┘
            │  ② POST facts (~180 KB/system)
            ▼
   ┌─────────────────┐
   │   OPA  ×3       │   evaluates 510 Rego policies
   └────────┬────────┘
            │  ③ structured report: per-control results, score, violations
            ▼
   ┌─────────────────┐
   │   PostgreSQL    │   durable, timestamped, queryable
   └────────┬────────┘
            │
      ┌─────┴──────┬───────────────┐
      ▼            ▼               ▼
  ④ Grafana   ⑤ PDF/DOCX      ⑥ CAA signed
    dashboards   auditor report    certification
```

| Step | What makes it matter |
|---|---|
| ① | **Read-only.** Assessment never changes the system being assessed |
| ② | Facts are the contract — the policy doesn't care how they were gathered |
| ③ | Decision logic lives in Rego, not in playbooks |
| ④–⑥ | **The record outlives the scan.** This is the difference between a scan and an audit |

---

## 4. Traffic flow — enforcement (Policy as Code)

The same engine, applied to automation rather than the estate.

```
   git push ──① EDA webhook──┐
                             ▼
   job launch ──② MCP/AAP──► OPA ──► {"allowed": bool, "violations": [...]}
                             ▲                    │
   playbook run ──③ pre-task─┘         allow ─────┴───── deny → blocked + logged
```

| # | Enforcement point | Catches |
|---|---|---|
| ① | **git check-in** | A bad change before it merges |
| ② | **job launch** | Who may run what, where, and when |
| ③ | **runtime pre-flight** | Content that slipped past the gates |

Plus a **post-hoc audit sweep** for anything that bypassed all three.

---

## 5. Traffic flow — drift (CIP-010 pattern)

```
  capture baseline ──► (unauthorised change) ──► detect drift ──► remediate ──► re-verify
         │                                            │                            │
         └──────────────► PostgreSQL ◄────────────────┴────────────────────────────┘
                    every turn of the loop is a historical row
```

A deviation with no matching change ticket is tagged **`UNAUDITED`** — that is CIP-010 R1.2,
automated.

---

## 6. Endpoint reference

| Service | In-cluster | External route |
|---|---|---|
| AAP | `aap.aap-operator.svc.cluster.local` | `aap-aap-operator.apps.<cluster-domain>` |
| OPA security | `opa-security.aac.svc.cluster.local:8181` | `opa-security-aac.apps.<cluster-domain>` |
| OPA compliance | `opa-compliance.aac.svc.cluster.local:8181` | `opa-compliance-aac.apps.<cluster-domain>` |
| OPA OT | `opa-ot.aac.svc.cluster.local:8181` | `opa-ot-aac.apps.<cluster-domain>` |
| PostgreSQL | `compliance-db.aac.svc.cluster.local:5432` | — |
| Grafana | `grafana.aac.svc.cluster.local:3000` | `grafana-aac.apps.<cluster-domain>` |
| MCP | — | host `:8004` (endpoint `/mcp`) |

---

## 7. Three lines worth saying out loud

- **Read-only by default.** Assessment never touches what it measures; remediation is a separate,
  explicit, recorded act.
- **The policy is the product.** 510 Rego files across 50+ frameworks. Red Hat ships the engine;
  the library is what turns it into compliance.
- **History is the differentiator.** A scan tells you today. AAC tells you what changed, when, who
  approved it, and proves it to an auditor months later.
