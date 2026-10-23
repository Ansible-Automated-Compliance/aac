#!/usr/bin/env python3
"""F4 — the findings workbook: one generic, actionable report for ANY framework.

Composes the decisioning layer over stored evidence into the work product a
control owner can act on and a manager can read:

  Summary        posture, counts, run provenance, delta headline
  Findings       one row per (control, subject) failure — identity, risk,
                 remediation, owner, decision, delta, age, evidence pointer
  Unassessable   controls the run could NOT confirm, split by cause
  Decisions      the business decisions file joined to live findings,
                 with expiry status (active / expiring / expired / unmatched)
  Delta          new / fixed / regressed / still open vs the previous run
  Passed         controls that passed, when the evidence records them

Three things are kept separate on purpose:
  evidence   compliance_results — append-only, never edited (input `rows`)
  decisions  a small reviewed file per framework/tenant — owner, decision,
             justification, approver, expiry (input `decisions`)
  report     this workbook — the JOIN of the two, regenerated every run
So a decision survives the next run, and no report is ever hand-edited.

Framework-agnostic by construction: identity comes from the same extractor
the findings layer uses (scripts/findings_extract.py); risk from
scripts/risk_score.py with a per-framework data config; remediation from
scripts/mitigation.py with a per-framework catalog. Nothing here knows about
Microsoft 365 except through those data files.

Deterministic core (rows in → workbook out); no database I/O here — the
compliance_findings_workbook.yml playbook owns that and runs inside the
customer's own environment, so assessment data never leaves it. Standard
library only: the .xlsx writer is a minimal SpreadsheetML emitter, so no
extra package is needed in the execution environment.

Input (stdin), one JSON object:
  framework           framework key (required)
  rows                compliance_results rows for the framework inside the
                      lookback window (ALL subjects, ALL runs in window):
                      {id, hostname, framework, policy_name, policy_version,
                       passed_controls, failed_controls, total_controls,
                       violations, metadata, evaluation_timestamp,
                       policy_sha?, project_sha?}
  catalog             optional control catalog: a list, or an object with a
                      "recommendations"/"catalog" list, of
                      {control_id, title?, section?, section_name?,
                       levels?|level?, assessment?|cis_assessment?}
  coverage            optional benchmark coverage buckets
                      {evaluated[], requires_attestation[], unresolved[],
                       not_implemented[]}
  risk_config         ansible/vars/risk/<framework>.yml content
  mitigation_catalog  ansible/vars/mitigation/<framework>.yml content
  decisions           ansible/vars/decisions/<framework>.yml content
  benchmark           optional {name, version}
  run_gap_minutes     rows closer than this on one subject = one run (30)
  expiring_days       decisions/waivers expiring within N days flagged (30)
  now                 ISO timestamp for age math (tests); default: now

Output: `--out-dir DIR --basename NAME` writes NAME.xlsx, NAME.html, NAME.md,
NAME.json and one NAME-<sheet>.csv per sheet, and prints a manifest.
`--emit-waivers` prints accepted decisions as OPA waiver entries (JSON), so
the decisions file is the single source of accepted deviations.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import pathlib
import re
import sys
import zipfile
from datetime import datetime, timedelta, timezone

CONTRACT_VERSION = "1.0"

_HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_fx = _load("findings_extract")
_rs = _load("risk_score")
_mi = _load("mitigation")

# ── Column contract (v1.0) ───────────────────────────────────────────────────
# Every sheet's columns, in order. Renderers (xlsx, csv, html, md) all read
# from here, and docs/operations/FINDINGS_WORKBOOK_CONTRACT.md is generated from
# it (--print-contract) so the published contract cannot drift from the code.

FINDINGS_COLUMNS = [
    ("finding_id", "Finding ID", "Stable short key for the (framework, control, subject) identity. Survives re-runs; join on it."),
    ("identity", "Identity", "framework|control|subject — the identity the findings layer uses."),
    ("framework", "Framework", "Framework key as stored in the evidence."),
    ("control_id", "Control", "Control number with any framework prefix removed (e.g. 6.5.1)."),
    ("control_raw", "Control (as emitted)", "Control id exactly as the policy emitted it."),
    ("title", "Title", "Catalog title when the catalog has one; otherwise the leading clause of the finding."),
    ("section", "Section", "Section/category number from the catalog or the stored row."),
    ("category", "Category", "Section/category name (e.g. Exchange admin center)."),
    ("level", "Profile level", "Benchmark profile level (L1/L2) from the catalog, when known."),
    ("assessment", "Benchmark assessment", "Automated or Manual, as the benchmark classifies the control."),
    ("subject", "Subject", "The system or tenant the finding is on."),
    ("status", "Status", "open or waived (a waived finding is still listed)."),
    ("risk_band", "Risk", "Derived risk band: Critical / High / Medium / Low."),
    ("risk_score", "Risk score", "Numeric score behind the band."),
    ("risk_basis", "Risk basis", "The factors that produced the score — the score is explainable."),
    ("risk_override", "Risk override", "Customer override from the decisions file, when set."),
    ("effective_risk", "Effective risk", "Override when present, otherwise the derived band. Sort on this."),
    ("blast_radius", "Blast radius", "Number of subjects failing this control in the latest runs."),
    ("sampled", "Sampled", "yes when the evidence was taken from a sample, not the full population."),
    ("evidence_strength", "Evidence strength", "The policy's own note on how strong the evidence is."),
    ("where", "Where to fix", "Admin surface where the control is set."),
    ("action", "Action", "What to change."),
    ("method", "Method", "manual / automated / governed."),
    ("owner", "Owner", "From the decisions file: per-finding decision, else default owner by section."),
    ("decision", "Decision", "remediate / accept / review, from the decisions file; blank = undecided."),
    ("justification", "Justification", "Business justification recorded with an accept decision."),
    ("approver", "Approver", "Named person who approved the decision."),
    ("expires", "Expires", "Expiry of an accepted deviation (renewal date)."),
    ("decision_status", "Decision status", "active / expiring / expired / undecided."),
    ("ticket", "Ticket", "Change or tracking reference from the decisions file."),
    ("delta", "Delta", "new / still open / regressed / first run, relative to the previous run."),
    ("first_seen", "First seen", "First run in the window that reported this finding."),
    ("last_seen", "Last seen", "Latest run that reported it."),
    ("times_seen", "Times seen", "Runs in the window that reported it."),
    ("age_days", "Age (days)", "Days since first seen."),
    ("detail", "Detail", "The finding text exactly as the policy emitted it."),
    ("evidence_id", "Evidence row", "compliance_results.id of the row this finding came from."),
    ("evidence_at", "Evidence timestamp", "evaluation_timestamp of that row."),
    ("policy_sha", "Policy SHA", "Policy library commit that produced the row, when recorded."),
]

UNASSESSABLE_COLUMNS = [
    ("control_id", "Control", "Control number."),
    ("title", "Title", "Catalog title, when known."),
    ("section", "Section", "Section number."),
    ("category", "Category", "Section name."),
    ("level", "Profile level", "L1/L2 when known."),
    ("assessment", "Benchmark assessment", "Automated or Manual per the benchmark."),
    ("subject", "Subject", "System or tenant, or * when the gap is benchmark-wide."),
    ("reason", "Reason", "benchmark_manual / attestation_required / collector_not_built / facts_not_collected / not_evaluated."),
    ("who_acts", "Who acts", "customer (manual review / attestation) or vendor (collector backlog)."),
    ("owner", "Owner", "Default owner by section from the decisions file."),
    ("detail", "Detail", "The gap text as emitted, or the coverage note."),
    ("evidence_id", "Evidence row", "compliance_results.id when the gap came from a stored row."),
]

DECISIONS_COLUMNS = [
    ("control_id", "Control", "Control the decision applies to."),
    ("subject", "Subject", "Subject the decision applies to, or *."),
    ("decision", "Decision", "remediate / accept / review."),
    ("owner", "Owner", "Business owner."),
    ("justification", "Justification", "Why the deviation is kept (accept) or the plan (remediate)."),
    ("approver", "Approver", "Named person."),
    ("approved", "Approved", "Date approved."),
    ("expires", "Expires", "Renewal date for an accepted deviation."),
    ("status", "Status", "active / expiring / expired / unmatched (no open finding)."),
    ("days_to_expiry", "Days to expiry", "Negative when expired."),
    ("matched_findings", "Matched findings", "Open findings this decision applies to."),
    ("issues", "Issues", "Validation notes: missing expiry (defaulted), approver not a person, unknown band."),
    ("ticket", "Ticket", "Change reference."),
]

DELTA_COLUMNS = [
    ("change", "Change", "new / fixed / regressed / still open."),
    ("finding_id", "Finding ID", "Stable key."),
    ("control_id", "Control", "Control number."),
    ("title", "Title", "Catalog title when known."),
    ("subject", "Subject", "System or tenant."),
    ("effective_risk", "Effective risk", "Band for open items; blank for fixed."),
    ("first_seen", "First seen", "First run in the window."),
    ("previous_run", "Previous run", "Timestamp of the run compared against."),
    ("latest_run", "Latest run", "Timestamp of the latest run."),
]

PASSED_COLUMNS = [
    ("control_id", "Control", "Control number."),
    ("title", "Title", "Catalog title when known."),
    ("section", "Section", "Section number."),
    ("category", "Category", "Section name."),
    ("subject", "Subject", "System or tenant."),
    ("sampled", "Sampled", "yes when the pass rests on a sample."),
    ("evidence_strength", "Evidence strength", "The policy's note on the evidence, when any."),
    ("evidence_id", "Evidence row", "compliance_results.id."),
]

SHEETS = [
    ("Summary", None),
    ("Findings", FINDINGS_COLUMNS),
    ("Unassessable", UNASSESSABLE_COLUMNS),
    ("Decisions", DECISIONS_COLUMNS),
    ("Delta", DELTA_COLUMNS),
    ("Passed", PASSED_COLUMNS),
]

BANDS = ("Critical", "High", "Medium", "Low")
_BAND_ORDER = {b: i for i, b in enumerate(BANDS)}
_PREFIX = re.compile(r"^(?:CIS (?:L2 )?(?:M365 )?)")
_NOT_A_PASS = re.compile(r"\(this is not a pass\)", re.IGNORECASE)
_GAP_REASONS = [
    (re.compile(r"attestation", re.I), "attestation_required", "customer"),
    (re.compile(r"collectability is unresolved|not yet evaluated|no collector", re.I), "collector_not_built", "vendor"),
    (re.compile(r"not collected|unavailable|FAIL-CLOSED|could not be read|not readable", re.I), "facts_not_collected", "vendor"),
]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _parse_ts(ts):
    if ts is None or ts == "":
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    s = str(ts).replace("Z", "+00:00")
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_date(d):
    if not d:
        return None
    dt = _parse_ts(str(d)[:10] if len(str(d)) >= 10 else str(d))
    return dt.date() if dt else None


def _iso(dt):
    return dt.isoformat(timespec="seconds") if dt else ""


def _bare(cid: str) -> str:
    return _PREFIX.sub("", cid or "").strip()


def _sort_key(cid: str):
    nums = re.findall(r"\d+", cid or "")
    return tuple(int(n) for n in nums) if nums else (9999,)


def _finding_key(framework: str, control: str, subject: str) -> str:
    return hashlib.sha1(f"{framework}|{control}|{subject}".encode()).hexdigest()[:10]


def _normalize_catalog(cat) -> dict:
    """→ {bare_control_id: {title, section, section_name, level, assessment}}"""
    if isinstance(cat, dict):
        cat = cat.get("recommendations") or cat.get("catalog") or []
    out = {}
    for c in cat or []:
        cid = _bare(str(c.get("control_id") or c.get("id") or ""))
        if not cid:
            continue
        levels = c.get("levels") or ([c["level"]] if c.get("level") else [])
        lv = ""
        if any("2" in str(x) for x in levels):
            lv = "L2"
        elif levels:
            lv = "L1"
        out[cid] = {
            "title": c.get("title") or "",
            "keywords": ", ".join(c.get("title_keywords") or []),
            "section": str(c.get("section") or cid.split(".")[0]),
            "section_name": c.get("section_name") or "",
            "level": lv,
            "assessment": c.get("assessment") or c.get("cis_assessment") or "",
        }
    return out


def _cluster_runs(rows: list[dict], gap_minutes: int) -> dict:
    """→ {subject: [run, ...]} oldest→newest; run = {start, end, rows}.
    Rows on one subject closer than the gap belong to one assessment run
    (section-per-row stores write several rows milliseconds apart)."""
    by_subject: dict[str, list] = {}
    for r in rows:
        subj = (r.get("hostname") or "").strip()
        ts = _parse_ts(r.get("evaluation_timestamp"))
        if not subj or ts is None or _fx._invalid_subject(subj):
            continue
        by_subject.setdefault(subj, []).append((ts, r))
    runs = {}
    gap = timedelta(minutes=gap_minutes)
    for subj, items in by_subject.items():
        items.sort(key=lambda x: (x[0], x[1].get("id") or 0))
        cur = None
        out = []
        for ts, r in items:
            if cur is None or ts - cur["end"] > gap:
                cur = {"start": ts, "end": ts, "rows": []}
                out.append(cur)
            cur["end"] = ts
            cur["rows"].append(r)
        runs[subj] = out
    return runs


def _gap_reason(text: str):
    for pat, reason, who in _GAP_REASONS:
        if pat.search(text or ""):
            return reason, who
    return "facts_not_collected", "vendor"


def _extract_run(run: dict, framework: str, subject: str) -> dict:
    """One run → {failures:{bare_cid: f}, gaps:{bare_cid: g}, waived:{...},
    evaluated:set|None, strength:{cid: note}}"""
    failures, gaps, waived = {}, {}, {}
    evaluated = None
    strength = {}
    for r in run["rows"]:
        meta = r.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except ValueError:
                meta = {}
        ev = meta.get("evaluated_control_ids")
        if isinstance(ev, list):
            evaluated = (evaluated or set()) | {_bare(str(x)) for x in ev}
        es = meta.get("evidence_strength") or {}
        if isinstance(es, dict):
            for k, v in es.items():
                strength[_bare(str(k))] = str(v)
        viols = r.get("violations") or []
        if isinstance(viols, str):
            try:
                viols = json.loads(viols)
            except ValueError:
                viols = [viols]
        # Some writers persisted a wrapper object {"violations": [...]} rather
        # than a bare array (same normalisation as scripts/sarif_mapper.py);
        # iterating the dict would emit its keys as bogus findings.
        if isinstance(viols, dict):
            viols = viols.get("violations", []) or []
        for v in viols:
            if isinstance(v, dict):
                raw, ftype, sev, title, refs = _fx._finding_from_dict(v)
                detail = title
            else:
                raw, ftype = _fx._control_from_message(str(v))
                sev, refs = None, {}
                detail = str(v)
                if _NOT_A_PASS.search(detail):
                    ftype = "evidence_gap"
            cid = _bare(raw)
            if ftype == "evidence_gap":
                m = re.search(r"(?:CIS (?:L2 )?(?:M365 )?)?(\d+(?:\.\d+)+)", detail)
                if cid.startswith("EVIDENCE-GAP") and m:
                    cid = m.group(1)
                reason, who = _gap_reason(detail)
                gaps.setdefault(cid, {"control_raw": raw, "detail": detail, "reason": reason,
                                      "who_acts": who, "evidence_id": r.get("id"),
                                      "evidence_at": _iso(_parse_ts(r.get("evaluation_timestamp"))),
                                      "section_hint": str(meta.get("section") or "")})
            else:
                failures.setdefault(cid, {"control_raw": raw, "detail": detail, "severity": sev,
                                          "refs": refs, "evidence_id": r.get("id"),
                                          "evidence_at": _iso(_parse_ts(r.get("evaluation_timestamp"))),
                                          "policy_sha": r.get("policy_sha") or "",
                                          "section_hint": str(meta.get("section") or ""),
                                          "category_hint": str(meta.get("section_name") or "")})
        for w in meta.get("waivers_applied") or []:
            v = w.get("violation") if isinstance(w, dict) else w
            entry = w.get("waiver", {}) if isinstance(w, dict) else {}
            raw, _ = _fx._control_from_message(str(v)) if not isinstance(v, dict) \
                else (_fx._finding_from_dict(v)[0], "violation")
            cid = _bare(raw)
            waived.setdefault(cid, {"control_raw": raw, "detail": str(v), "waiver": entry,
                                    "evidence_id": r.get("id"),
                                    "evidence_at": _iso(_parse_ts(r.get("evaluation_timestamp"))),
                                    "policy_sha": r.get("policy_sha") or "",
                                    "section_hint": str(meta.get("section") or ""),
                                    "category_hint": str(meta.get("section_name") or "")})
    return {"failures": failures, "gaps": gaps, "waived": waived,
            "evaluated": evaluated, "strength": strength}


# ── Decisions ───────────────────────────────────────────────────────────────

_ALIAS = re.compile(r"^(team|group|dl|list|distro|security|secops|ops|it|admin|admins|noreply|no-reply)[-_.@]", re.I)


def _looks_like_person(approver: str) -> bool:
    a = (approver or "").strip()
    if not a:
        return False
    if _ALIAS.match(a):
        return False
    if "@" in a:
        local = a.split("@", 1)[0]
        return bool(re.search(r"[A-Za-z]", local)) and not _ALIAS.match(local + "@")
    return len(a.split()) >= 2


def _prefix_match(control: str, table: dict):
    best = None
    for prefix, value in (table or {}).items():
        if prefix == "_default":
            continue
        p = str(prefix)
        if (control == p or control.startswith(p + ".")) and (best is None or len(p) > len(best[0])):
            best = (p, value)
    return best[1] if best else (table or {}).get("_default", "")


def _load_decisions(decisions: dict, today, expiring_days: int) -> dict:
    """Normalize and validate the decisions file.
    → {entries:[...], default_owners:{}, cycle:int}"""
    d = decisions or {}
    cycle = int(d.get("review_cycle_days") or 90)
    entries = []
    for i, e in enumerate(d.get("decisions") or []):
        issues = []
        control = _bare(str(e.get("control_id") or ""))
        subject = str(e.get("subject") or "*")
        decision = str(e.get("decision") or "").strip().lower()
        if decision not in ("remediate", "accept", "review"):
            issues.append(f"unknown decision '{decision or '(blank)'}' (use remediate / accept / review)")
        approver = str(e.get("approver") or "")
        if not _looks_like_person(approver):
            issues.append("approver is not a named person")
        approved = _parse_date(e.get("approved"))
        expires = _parse_date(e.get("expires"))
        if decision == "accept" and expires is None:
            base = approved or today
            expires = base + timedelta(days=cycle)
            issues.append(f"expiry missing — defaulted to approved + {cycle} days ({expires.isoformat()})")
        override = str(e.get("risk_override") or "").strip().title()
        if override and override not in BANDS:
            issues.append(f"risk_override '{e.get('risk_override')}' is not one of {', '.join(BANDS)}")
            override = ""
        status = "active"
        days = None
        if expires is not None:
            days = (expires - today).days
            if days < 0:
                status = "expired"
            elif days <= expiring_days:
                status = "expiring"
        if not control:
            issues.append("control_id missing")
        entries.append({
            "index": i, "control_id": control, "subject": subject, "decision": decision,
            "owner": str(e.get("owner") or ""), "justification": str(e.get("justification") or ""),
            "approver": approver, "approved": approved.isoformat() if approved else "",
            "expires": expires.isoformat() if expires else "", "status": status,
            "days_to_expiry": days, "risk_override": override,
            "ticket": str(e.get("ticket") or ""), "issues": issues, "matched": [],
        })
    return {"entries": entries, "default_owners": d.get("default_owners") or {}, "cycle": cycle}


def _match_decision(entries: list, control: str, subject: str):
    """Most specific decision for a finding: exact subject beats '*'."""
    exact = [e for e in entries if e["control_id"] == control and e["subject"] == subject]
    star = [e for e in entries if e["control_id"] == control and e["subject"] == "*"]
    pick = (exact or star)
    return pick[-1] if pick else None


# ── Build ───────────────────────────────────────────────────────────────────

def build(payload: dict) -> dict:
    framework = str(payload.get("framework") or "").strip()
    if not framework:
        raise SystemExit("framework is required")
    now = _parse_ts(payload.get("now")) or datetime.now(timezone.utc)
    today = now.date()
    gap_min = int(payload.get("run_gap_minutes") or 30)
    expiring_days = int(payload.get("expiring_days") or 30)
    catalog = _normalize_catalog(payload.get("catalog"))
    coverage = payload.get("coverage") or {}
    cov = {k: {_bare(str(x)) for x in (coverage.get(k) or [])}
           for k in ("evaluated", "requires_attestation", "unresolved", "not_implemented")}
    risk_config = payload.get("risk_config") or {}
    mit_catalog = payload.get("mitigation_catalog") or {}
    decisions = _load_decisions(payload.get("decisions") or {}, today, expiring_days)
    bench = payload.get("benchmark") or {}

    rows = [r for r in payload.get("rows") or [] if (r.get("framework") or framework) == framework]
    runs_by_subject = _cluster_runs(rows, gap_min)
    subjects = sorted(runs_by_subject)

    # Per subject: extract every run; keep latest + previous + history
    extracted = {s: [_extract_run(run, framework, s) for run in runs] for s, runs in runs_by_subject.items()}

    # Blast radius: subjects failing each control in their latest run
    radius: dict[str, int] = {}
    for s in subjects:
        latest = extracted[s][-1]
        for cid in list(latest["failures"]) + list(latest["waived"]):
            radius[cid] = radius.get(cid, 0) + 1

    def _cat(cid, hint_sec="", hint_name=""):
        c = catalog.get(cid, {})
        return {
            "title": c.get("title", ""),
            "keywords": c.get("keywords", ""),
            "section": c.get("section") or hint_sec or (cid.split(".")[0] if "." in cid else ""),
            "category": c.get("section_name") or hint_name,
            "level": c.get("level", ""),
            "assessment": c.get("assessment", ""),
        }

    findings, unassessable, delta, passed = [], [], [], []
    provenance = {"latest_runs": {}, "previous_runs": {}, "policy_shas": set(), "project_shas": set()}
    totals = {"failed": 0, "waived": 0, "gaps": 0, "passed": 0, "evaluated": 0, "new": 0,
              "fixed": 0, "regressed": 0, "still_open": 0, "sampled": 0}
    by_band = {b: 0 for b in BANDS}
    by_owner: dict[str, int] = {}

    for s in subjects:
        hist = extracted[s]
        runs = runs_by_subject[s]
        latest, prev = hist[-1], (hist[-2] if len(hist) > 1 else None)
        latest_ts, prev_ts = runs[-1]["end"], (runs[-2]["end"] if len(runs) > 1 else None)
        provenance["latest_runs"][s] = _iso(latest_ts)
        provenance["previous_runs"][s] = _iso(prev_ts)
        for r in runs[-1]["rows"]:
            if r.get("policy_sha"):
                provenance["policy_shas"].add(str(r["policy_sha"]))
            if r.get("project_sha"):
                provenance["project_shas"].add(str(r["project_sha"]))
        prev_open = set(prev["failures"]) | set(prev["waived"]) if prev else set()
        earlier_open = set()
        for h in hist[:-2]:
            earlier_open |= set(h["failures"]) | set(h["waived"])

        def _evaluated_in(run_x, cid):
            """True when a run verifiably evaluated the control: it is not an
            evidence gap there, and when the run lists its evaluated ids the
            control is among them. Unknown lists (frameworks that do not
            record them) count as evaluated — that is the findings layer's
            verified-by-rescan rule."""
            if cid in run_x["gaps"]:
                return False
            return run_x["evaluated"] is None or cid in run_x["evaluated"]

        def _first_seen(cid):
            n = 0
            first = None
            for run, h in zip(runs, hist):
                if cid in h["failures"] or cid in h["waived"]:
                    n += 1
                    if first is None:
                        first = run["end"]
            return first, n

        open_items = [(cid, f, "open") for cid, f in latest["failures"].items()] + \
                     [(cid, w, "waived") for cid, w in latest["waived"].items()]
        for cid, f, status in open_items:
            c = _cat(cid, f.get("section_hint", ""), f.get("category_hint", ""))
            first, n = _first_seen(cid)
            if prev is None:
                change = "first run"
            elif cid in prev_open:
                change = "still open"
            elif cid in earlier_open:
                # A regression needs a verified pass in between: the previous
                # run must have evaluated the control and reported it clean.
                change = "regressed" if _evaluated_in(prev, cid) else "still open"
            else:
                change = "new"
            risk = _rs.score_finding({"control_id": cid, "severity": f.get("severity"),
                                      "title": f["detail"], "blast_radius": radius.get(cid, 1)}, risk_config)
            mit = _mi.mitigate({"control_id": cid, "finding_type": "violation"}, mit_catalog)
            dec = _match_decision(decisions["entries"], cid, s)
            fid = _finding_key(framework, cid, s)
            if dec:
                dec["matched"].append(fid)
            owner = (dec or {}).get("owner") or _prefix_match(cid, decisions["default_owners"])
            override = (dec or {}).get("risk_override") or ""
            if status == "waived" and not dec:
                w = f.get("waiver") or {}
                dec = {"decision": "accept", "justification": w.get("reason", ""),
                       "approver": w.get("approver", ""), "expires": w.get("expires", ""),
                       "status": "active", "ticket": ""}
                exp = _parse_date(w.get("expires"))
                if exp:
                    d_ = (exp - today).days
                    dec["status"] = "expired" if d_ < 0 else ("expiring" if d_ <= expiring_days else "active")
                    if d_ < 0:
                        # An expired waiver no longer excepts anything: the
                        # finding is open again and counts as a failure.
                        status = "open"
            strength = latest["strength"].get(cid, "")
            sampled = "yes" if "sampl" in strength.lower() else ""
            if sampled:
                totals["sampled"] += 1
            eff = override or risk["band"]
            row = {
                "finding_id": fid, "identity": f"{framework}|{cid}|{s}", "framework": framework,
                "control_id": cid, "control_raw": f.get("control_raw", cid),
                "title": c["title"] or re.split(r"[:—]", f["detail"], maxsplit=1)[-1].strip()[:120],
                "section": c["section"], "category": c["category"], "level": c["level"],
                "assessment": c["assessment"], "subject": s, "status": status,
                "risk_band": risk["band"], "risk_score": risk["score"],
                "risk_basis": "; ".join(risk["factors"]), "risk_override": override,
                "effective_risk": eff, "blast_radius": radius.get(cid, 1),
                "sampled": sampled, "evidence_strength": strength,
                "where": mit["where"], "action": mit["action"], "method": mit["method"],
                "owner": owner, "decision": (dec or {}).get("decision", ""),
                "justification": (dec or {}).get("justification", ""),
                "approver": (dec or {}).get("approver", ""), "expires": (dec or {}).get("expires", ""),
                "decision_status": (dec or {}).get("status", "") if dec else "undecided",
                "ticket": (dec or {}).get("ticket", ""), "delta": change,
                "first_seen": _iso(first), "last_seen": _iso(latest_ts), "times_seen": n,
                "age_days": (now - first).days if first else "",
                "detail": f["detail"], "evidence_id": f.get("evidence_id", ""),
                "evidence_at": f.get("evidence_at", ""), "policy_sha": f.get("policy_sha", ""),
            }
            findings.append(row)
            totals["failed" if status == "open" else "waived"] += 1
            if status == "open":
                by_band[eff] = by_band.get(eff, 0) + 1
                by_owner[owner or "(unassigned)"] = by_owner.get(owner or "(unassigned)", 0) + 1
            if change in ("new", "regressed", "still open"):
                totals[change.replace(" ", "_")] += 1
            if change != "first run":
                delta.append({"change": change, "finding_id": fid, "control_id": cid, "title": row["title"],
                              "subject": s, "effective_risk": eff, "first_seen": row["first_seen"],
                              "previous_run": _iso(prev_ts), "latest_run": _iso(latest_ts)})
        if prev is not None:
            gone = prev_open - set(latest["failures"]) - set(latest["waived"])
            # Fixed only when the latest run verifiably evaluated the control
            # and reported it clean; a gap or an unevaluated control is not a
            # closure and is already listed under Unassessable.
            for cid in sorted((cid for cid in gone if _evaluated_in(latest, cid)), key=_sort_key):
                c = _cat(cid)
                first, _ = _first_seen(cid)
                totals["fixed"] += 1
                delta.append({"change": "fixed", "finding_id": _finding_key(framework, cid, s),
                              "control_id": cid, "title": c["title"] or c["keywords"], "subject": s, "effective_risk": "",
                              "first_seen": _iso(first), "previous_run": _iso(prev_ts), "latest_run": _iso(latest_ts)})

        # Gaps from the stored rows, classified by cause
        for cid, g in latest["gaps"].items():
            c = _cat(cid, g.get("section_hint", ""))
            reason, who = g["reason"], g["who_acts"]
            if cid in cov["requires_attestation"]:
                reason, who = "attestation_required", "customer"
            elif cid in cov["unresolved"] or cid in cov["not_implemented"]:
                reason, who = "collector_not_built", "vendor"
            elif c["assessment"].lower() == "manual" and reason != "facts_not_collected":
                reason, who = "benchmark_manual", "customer"
            unassessable.append({"control_id": cid, "title": c["title"] or c["keywords"], "section": c["section"],
                                 "category": c["category"], "level": c["level"], "assessment": c["assessment"],
                                 "subject": s, "reason": reason, "who_acts": who,
                                 "owner": _prefix_match(cid, decisions["default_owners"]),
                                 "detail": g["detail"], "evidence_id": g.get("evidence_id", "")})
            totals["gaps"] += 1

        # Passed = evaluated − failed − waived − gaps, when the evidence lists evaluated ids
        if latest["evaluated"] is not None:
            totals["evaluated"] += len(latest["evaluated"])
            for cid in sorted(latest["evaluated"] - set(latest["failures"]) - set(latest["waived"]) - set(latest["gaps"]), key=_sort_key):
                c = _cat(cid)
                strength = latest["strength"].get(cid, "")
                passed.append({"control_id": cid, "title": c["title"] or c["keywords"], "section": c["section"],
                               "category": c["category"], "subject": s,
                               "sampled": "yes" if "sampl" in strength.lower() else "",
                               "evidence_strength": strength,
                               "evidence_id": next((r.get("id") for r in runs[-1]["rows"]
                                                    if cid in {_bare(str(x)) for x in ((r.get("metadata") or {}).get("evaluated_control_ids") or [])}), "")})
                totals["passed"] += 1

    # Catalog controls no run touched: per subject, rolled up to one "*" row
    # when no subject touched the control at all (so a control one host
    # evaluates and another omits still shows the omission for that host).
    if catalog:
        def _reason_for(cid, c):
            if cid in cov["requires_attestation"]:
                return "attestation_required", "customer", "benchmark control requires attestation; none recorded"
            if cid in cov["unresolved"] or cid in cov["not_implemented"]:
                return "collector_not_built", "vendor", "no collector path yet (vendor backlog)"
            if c["assessment"].lower() == "manual":
                return "benchmark_manual", "customer", "benchmark classifies this control as Manual"
            if cov["evaluated"] and cid not in cov["evaluated"]:
                return "not_evaluated", "vendor", "no policy evaluates this control yet"
            return "not_evaluated", "vendor", "not present in any stored run in the window"

        touched_by = {}
        for s in subjects:
            latest = extracted[s][-1]
            touched_by[s] = set(latest["failures"]) | set(latest["waived"]) | set(latest["gaps"]) | (latest["evaluated"] or set())
        for cid in sorted(catalog, key=_sort_key):
            c = _cat(cid)
            missing = [s for s in subjects if cid not in touched_by[s]]
            if subjects and not missing:
                continue
            targets = ["*"] if (not subjects or len(missing) == len(subjects)) else missing
            reason, who, note = _reason_for(cid, c)
            for subj in targets:
                unassessable.append({"control_id": cid, "title": c["title"] or c["keywords"], "section": c["section"],
                                     "category": c["category"], "level": c["level"], "assessment": c["assessment"],
                                     "subject": subj, "reason": reason, "who_acts": who,
                                     "owner": _prefix_match(cid, decisions["default_owners"]),
                                     "detail": note, "evidence_id": ""})
                totals["gaps"] += 1

    findings.sort(key=lambda r: (_BAND_ORDER.get(r["effective_risk"], 9), -int(r["risk_score"] or 0),
                                 _sort_key(r["control_id"]), r["subject"]))
    unassessable.sort(key=lambda r: (r["reason"], _sort_key(r["control_id"]), r["subject"]))
    order = {"regressed": 0, "new": 1, "fixed": 2, "still open": 3}
    delta.sort(key=lambda r: (order[r["change"]], _BAND_ORDER.get(r["effective_risk"], 9), _sort_key(r["control_id"]), r["subject"]))
    passed.sort(key=lambda r: (_sort_key(r["control_id"]), r["subject"]))

    dec_rows = []
    for e in decisions["entries"]:
        status = e["status"] if e["matched"] else "unmatched"
        dec_rows.append({"control_id": e["control_id"], "subject": e["subject"], "decision": e["decision"],
                         "owner": e["owner"], "justification": e["justification"], "approver": e["approver"],
                         "approved": e["approved"], "expires": e["expires"], "status": status,
                         "days_to_expiry": e["days_to_expiry"] if e["days_to_expiry"] is not None else "",
                         "matched_findings": ", ".join(e["matched"]), "issues": "; ".join(e["issues"]),
                         "ticket": e["ticket"]})
    gap_reasons: dict[str, int] = {}
    for u in unassessable:
        gap_reasons[u["reason"]] = gap_reasons.get(u["reason"], 0) + 1
    expiring = [r for r in dec_rows if r["status"] in ("expiring", "expired")] + \
               [f for f in findings if f["decision_status"] in ("expiring", "expired")]
    open_count = totals["failed"]
    crit_high = by_band.get("Critical", 0) + by_band.get("High", 0)
    if open_count == 0:
        verdict = "No open control failures in the evaluated scope."
    elif crit_high == 0:
        verdict = f"{open_count} open control failure(s), none critical or high — a remediation backlog, not an active exposure."
    else:
        verdict = f"{crit_high} critical/high-risk failure(s) need attention first, of {open_count} open."
    if totals["regressed"]:
        verdict += f" {totals['regressed']} regressed since the previous run."

    summary = {
        "contract_version": CONTRACT_VERSION,
        "framework": framework,
        "benchmark": bench.get("name") or framework,
        "benchmark_version": bench.get("version") or "",
        "subjects": subjects,
        "subject_count": len(subjects),
        "generated_at": _iso(now),
        "latest_runs": provenance["latest_runs"],
        "previous_runs": provenance["previous_runs"],
        "policy_shas": sorted(provenance["policy_shas"]),
        "project_shas": sorted(provenance["project_shas"]),
        "benchmark_total": len(catalog) or None,
        "controls_evaluated": totals["evaluated"] or None,
        "passed": totals["passed"],
        "failed": totals["failed"],
        "waived": totals["waived"],
        "unassessable": totals["gaps"],
        "unassessable_by_reason": gap_reasons,
        "by_band": by_band,
        "by_owner": by_owner,
        "sampled": totals["sampled"],
        "delta": {"new": totals["new"], "fixed": totals["fixed"], "regressed": totals["regressed"],
                  "still_open": totals["still_open"]},
        "decisions": {"total": len(dec_rows),
                      "unmatched": sum(1 for r in dec_rows if r["status"] == "unmatched"),
                      "expiring": sum(1 for r in dec_rows if r["status"] == "expiring"),
                      "expired": sum(1 for r in dec_rows if r["status"] == "expired"),
                      "with_issues": sum(1 for r in dec_rows if r["issues"])},
        "undecided": sum(1 for f in findings if f["decision_status"] == "undecided"),
        "verdict": verdict,
    }
    return {"summary": summary, "findings": findings, "unassessable": unassessable,
            "decisions": dec_rows, "delta": delta, "passed": passed}


def emit_waivers(decisions: dict, framework: str, now=None) -> list:
    """Accepted decisions → OPA waiver entries (ansible/vars/waivers.yml shape),
    so an accepted deviation is also honoured at evidence time. Uses the same
    normalisation as the workbook, so an accept whose expiry was defaulted
    to approved + review cycle exports WITH that date (an entry without an
    expiry never matches in OPA, which would silently un-honour it)."""
    today = (_parse_ts(now) or datetime.now(timezone.utc)).date()
    norm = _load_decisions(decisions or {}, today, 0)
    out = []
    for e in norm["entries"]:
        if e["decision"] != "accept" or not e["control_id"]:
            continue
        cid = e["control_id"]
        # OPA matches control_id as a substring of the violation text. A bare
        # dotted id ("1.1") would also match 1.1.3 and 11.1, so anchor dotted
        # ids on both sides the way the message families write them:
        # "CIS 1.1: …" / "CIS L2 1.1: …" → " 1.1:".
        if re.fullmatch(r"\d+(?:\.\d+)*", cid):
            cid = f" {cid}:"
        out.append({"host": e["subject"], "framework": framework, "control_id": cid,
                    "reason": e["justification"], "approver": e["approver"],
                    "expires": e["expires"]})
    return out


# ── Renderers ───────────────────────────────────────────────────────────────

def _summary_rows(s: dict) -> list:
    rows = [
        ("Contract version", s["contract_version"]),
        ("Framework", s["framework"]),
        ("Benchmark", f"{s['benchmark']} {s['benchmark_version']}".strip()),
        ("Subjects", ", ".join(s["subjects"]) or "(none)"),
        ("Generated", s["generated_at"]),
        ("Latest run", "; ".join(f"{k}: {v}" for k, v in s["latest_runs"].items())),
        ("Previous run", "; ".join(f"{k}: {v or '(none)'}" for k, v in s["previous_runs"].items())),
        ("Policy SHA", ", ".join(s["policy_shas"]) or "(not recorded)"),
        ("Verdict", s["verdict"]),
        ("Controls in benchmark", s["benchmark_total"] if s["benchmark_total"] is not None else "(no catalog)"),
        ("Controls evaluated", s["controls_evaluated"] if s["controls_evaluated"] is not None else "(not recorded)"),
        ("Passed", s["passed"]),
        ("Failed (open)", s["failed"]),
        ("Waived", s["waived"]),
        ("Unassessable", s["unassessable"]),
    ]
    for k, v in sorted(s["unassessable_by_reason"].items()):
        rows.append((f"  unassessable: {k}", v))
    for b in BANDS:
        rows.append((f"Open by risk: {b}", s["by_band"].get(b, 0)))
    for k, v in sorted(s["by_owner"].items()):
        rows.append((f"Open by owner: {k}", v))
    rows += [
        ("Sampled evidence (findings)", s["sampled"]),
        ("Delta: new", s["delta"]["new"]),
        ("Delta: fixed", s["delta"]["fixed"]),
        ("Delta: regressed", s["delta"]["regressed"]),
        ("Delta: still open", s["delta"]["still_open"]),
        ("Decisions on file", s["decisions"]["total"]),
        ("Decisions expiring", s["decisions"]["expiring"]),
        ("Decisions expired", s["decisions"]["expired"]),
        ("Decisions unmatched", s["decisions"]["unmatched"]),
        ("Decisions with issues", s["decisions"]["with_issues"]),
        ("Open findings undecided", s["undecided"]),
    ]
    return rows


def _sheet_data(rep: dict):
    """→ [(sheet_name, header_labels, rows_as_lists)]"""
    out = [("Summary", ["Item", "Value"], [[k, v] for k, v in _summary_rows(rep["summary"])])]
    for name, cols in SHEETS[1:]:
        key = name.lower()
        out.append((name, [lbl for _, lbl, _ in cols],
                    [[r.get(k, "") for k, _, _ in cols] for r in rep[key]]))
    return out


_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def _cell_safe(v):
    """Neutralise spreadsheet formula injection: evidence text comes from
    policy messages and, through them, from the assessed systems. A value
    that starts with a formula lead character is prefixed with a single quote
    so Excel/LibreOffice treat it as text. Numbers are left alone."""
    if isinstance(v, str) and v and (v[0] in _FORMULA_LEAD or v.lstrip()[:1] in ("=", "+", "@")):
        return "'" + v
    return v


def _xml(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _sheet_xml(header: list, rows: list) -> str:
    widths = [min(max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h)), 60) + 2
              for i, h in enumerate(header)]
    cols = "".join(f'<col min="{i+1}" max="{i+1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths))
    body = []

    def cell(ref, v, style=0):
        v = _cell_safe(v)
        if v is None or v == "":
            return ""
        if isinstance(v, bool):
            return f'<c r="{ref}" t="inlineStr"{f" s={chr(34)}{style}{chr(34)}" if style else ""}><is><t>{_xml(v)}</t></is></c>'
        if isinstance(v, (int, float)):
            return f'<c r="{ref}"{f" s={chr(34)}{style}{chr(34)}" if style else ""}><v>{v}</v></c>'
        return f'<c r="{ref}" t="inlineStr"{f" s={chr(34)}{style}{chr(34)}" if style else ""}><is><t xml:space="preserve">{_xml(v)}</t></is></c>'

    body.append('<row r="1">' + "".join(cell(f"{_col_letter(i+1)}1", h, 1) for i, h in enumerate(header)) + "</row>")
    for ri, r in enumerate(rows, start=2):
        body.append(f'<row r="{ri}">' + "".join(cell(f"{_col_letter(i+1)}{ri}", v) for i, v in enumerate(r)) + "</row>")
    last = f"{_col_letter(len(header))}{len(rows)+1}"
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            f'<cols>{cols}</cols><sheetData>{"".join(body)}</sheetData>'
            f'<autoFilter ref="A1:{last}"/></worksheet>')


def write_xlsx(rep: dict, path: pathlib.Path) -> None:
    sheets = _sheet_data(rep)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    parts = {}
    for i, (name, header, rows) in enumerate(sheets, start=1):
        ct.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        wb.append(f'<sheet name="{_xml(name[:31])}" sheetId="{i}" r:id="rId{i}"/>')
        rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
        parts[f"xl/worksheets/sheet{i}.xml"] = _sheet_xml(header, rows)
    n = len(sheets)
    rels.append(f'<Relationship Id="rId{n+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
    ct.append("</Types>")
    wb.append("</sheets></workbook>")
    rels.append("</Relationships>")
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
              '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
              '</styleSheet>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                 '</Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", "".join(wb))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        z.writestr("xl/styles.xml", styles)
        for name, xml in parts.items():
            z.writestr(name, xml)


def sheet_csv(rep: dict, sheet: str) -> str:
    for name, header, rows in _sheet_data(rep):
        if name == sheet:
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(header)
            w.writerows([[_cell_safe(v) for v in r] for r in rows])
            return out.getvalue()
    raise KeyError(sheet)


def render_markdown(rep: dict) -> str:
    s = rep["summary"]
    L = [f"# {s['benchmark']} {s['benchmark_version']} — Findings Workbook".rstrip(), "",
         f"**Framework:** {s['framework']}  ", f"**Subjects:** {', '.join(s['subjects']) or '(none)'}  ",
         f"**Generated:** {s['generated_at']}  ", f"**Contract:** v{s['contract_version']}", "",
         f"> {s['verdict']}", "", "## Summary", "", "| Item | Value |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in _summary_rows(s)]
    for name, cols in SHEETS[1:]:
        rows = rep[name.lower()]
        L += ["", f"## {name} ({len(rows)})", ""]
        if not rows:
            L.append("_none_")
            continue
        keys = [k for k, _, _ in cols]
        labels = [l for _, l, _ in cols]
        if name == "Findings":
            keep = ["finding_id", "control_id", "title", "category", "subject", "effective_risk", "owner",
                    "decision", "decision_status", "delta", "age_days", "where", "action"]
            idx = [keys.index(k) for k in keep]
            keys, labels = keep, [labels[i] for i in idx]
        L.append("| " + " | ".join(labels) + " |")
        L.append("|" + "---|" * len(labels))
        for r in rows:
            L.append("| " + " | ".join(str(r.get(k, "")).replace("|", "\\|").replace("\n", " ") for k in keys) + " |")
    L += ["", "---", "", "Generated by AAC from stored OPA evaluations. Evidence is never edited; "
          "decisions live in the decisions file; this workbook is the join of the two. "
          "Co-authored by Claude (Anthropic) via Claude Code."]
    return "\n".join(L) + "\n"


_CSS = """body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;margin:24px;color:#222}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px;border-bottom:1px solid #ddd}
.meta{color:#555;font-size:13px}.verdict{background:#f3f6fa;border-left:4px solid #2a5db0;padding:10px 14px;margin:14px 0}
table{border-collapse:collapse;font-size:12.5px;width:100%}th,td{border:1px solid #e3e3e3;padding:4px 7px;text-align:left;vertical-align:top}
th{background:#f7f7f7;position:sticky;top:0}.Critical{color:#b00020;font-weight:600}.High{color:#d2691e;font-weight:600}
.Medium{color:#8a6d00}.Low{color:#2e7d32}.regressed{color:#b00020;font-weight:600}.new{color:#d2691e}.fixed{color:#2e7d32}
.ft{margin-top:30px;color:#777;font-size:12px}"""


def render_html(rep: dict) -> str:
    s = rep["summary"]
    H = [f"<!doctype html><html><head><meta charset='utf-8'><title>{_xml(s['benchmark'])} findings workbook</title>",
         f"<style>{_CSS}</style></head><body>",
         f"<h1>{_xml(s['benchmark'])} {_xml(s['benchmark_version'])} — Findings Workbook</h1>",
         f"<div class='meta'>Framework {_xml(s['framework'])} · Subjects: {_xml(', '.join(s['subjects']) or '(none)')} · "
         f"Generated {_xml(s['generated_at'])} · Contract v{s['contract_version']}</div>",
         f"<div class='verdict'>{_xml(s['verdict'])}</div>", "<h2>Summary</h2><table>"]
    H += [f"<tr><th>{_xml(k)}</th><td>{_xml(v)}</td></tr>" for k, v in _summary_rows(s)]
    H.append("</table>")
    for name, cols in SHEETS[1:]:
        rows = rep[name.lower()]
        H.append(f"<h2>{name} ({len(rows)})</h2>")
        if not rows:
            H.append("<p><em>none</em></p>")
            continue
        keys = [k for k, _, _ in cols]
        labels = [l for _, l, _ in cols]
        if name == "Findings":
            keep = ["finding_id", "control_id", "title", "category", "level", "subject", "effective_risk",
                    "risk_basis", "owner", "decision", "decision_status", "expires", "delta", "age_days",
                    "where", "action", "sampled", "detail"]
            idx = [keys.index(k) for k in keep]
            keys, labels = keep, [labels[i] for i in idx]
        H.append("<table><tr>" + "".join(f"<th>{_xml(l)}</th>" for l in labels) + "</tr>")
        for r in rows:
            cells = []
            for k in keys:
                v = r.get(k, "")
                cls = str(v) if k in ("effective_risk", "risk_band", "change", "delta") else ""
                cells.append(f"<td class='{_xml(cls.replace(' ', '-'))}'>{_xml(v)}</td>")
            H.append("<tr>" + "".join(cells) + "</tr>")
        H.append("</table>")
    H.append("<div class='ft'>Generated by AAC from stored OPA evaluations · evidence is never edited; decisions "
             "live in the decisions file; this workbook is their join · Co-authored by Claude (Anthropic) via Claude Code</div>")
    H.append("</body></html>")
    return "\n".join(H)


def print_contract() -> str:
    L = [f"Contract version {CONTRACT_VERSION}", ""]
    for name, cols in SHEETS:
        L += [f"## {name}", ""]
        if cols is None:
            L += ["| Column | Meaning |", "|---|---|", "| Item | Summary item name |",
                  "| Value | Its value for this run |", ""]
            continue
        L += ["| Column | Key | Meaning |", "|---|---|---|"]
        L += [f"| {lbl} | `{key}` | {desc} |" for key, lbl, desc in cols]
        L.append("")
    return "\n".join(L)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", help="write NAME.xlsx/.html/.md/.json and NAME-<sheet>.csv here")
    ap.add_argument("--basename", default="findings_workbook")
    ap.add_argument("--render", choices=["json", "md", "html"], default="json",
                    help="stdout render when --out-dir is not given")
    ap.add_argument("--emit-waivers", action="store_true",
                    help="print accepted decisions as OPA waiver entries (JSON) and exit")
    ap.add_argument("--print-contract", action="store_true", help="print the column contract (Markdown)")
    args = ap.parse_args()
    if args.print_contract:
        sys.stdout.write(print_contract())
        return
    payload = json.load(sys.stdin)
    if args.emit_waivers:
        json.dump({"waiver_entries": emit_waivers(payload.get("decisions") or {}, payload.get("framework", ""),
                                                  payload.get("now"))},
                  sys.stdout, indent=1)
        sys.stdout.write("\n")
        return
    rep = build(payload)
    if args.out_dir:
        out = pathlib.Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        base = args.basename
        files = {}
        write_xlsx(rep, out / f"{base}.xlsx")
        files["xlsx"] = str(out / f"{base}.xlsx")
        (out / f"{base}.html").write_text(render_html(rep), encoding="utf-8")
        files["html"] = str(out / f"{base}.html")
        (out / f"{base}.md").write_text(render_markdown(rep), encoding="utf-8")
        files["md"] = str(out / f"{base}.md")
        (out / f"{base}.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
        files["json"] = str(out / f"{base}.json")
        for name, _ in SHEETS:
            p = out / f"{base}-{name.lower()}.csv"
            p.write_text(sheet_csv(rep, name), encoding="utf-8")
            files[f"csv_{name.lower()}"] = str(p)
        json.dump({"files": files, "summary": rep["summary"]}, sys.stdout, indent=1, default=str)
        sys.stdout.write("\n")
    elif args.render == "md":
        sys.stdout.write(render_markdown(rep))
    elif args.render == "html":
        sys.stdout.write(render_html(rep))
    else:
        json.dump(rep, sys.stdout, indent=1, default=str)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
