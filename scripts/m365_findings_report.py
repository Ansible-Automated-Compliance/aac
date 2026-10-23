#!/usr/bin/env python3
"""Interpreted, risk-ranked, mitigation-paired findings report for CIS M365.

This is the "decisioning layer" (F1 risk scoring + F2 mitigation guidance)
applied to the CIS Microsoft 365 Foundations Benchmark. It turns stored
assessment rows into a report a decision-maker can present: every finding
carries a DERIVED, EXPLAINABLE risk band (never "UNKNOWN") and a concrete
mitigation (where to fix it, what to do), ordered by risk rather than by
section.

Deterministic core (rows in → interpreted report out), mirroring
scripts/benchmark_concordance.py: no DB I/O here (the
m365_cis_findings_report.yml playbook owns that and runs it inside the
customer's own environment — assessment data never leaves the tenant).

Input (stdin), one JSON object:
  rows      compliance_results rows for ONE framework + tenant (latest per
            policy_name): each at least {"policy_name", "violations",
            "metadata", "compliance_percentage", "evaluation_timestamp"}
  catalog   the CIS M365 index recommendations list (control_id, section,
            section_name, assessment, levels) — from cis_m365_v7_index.json
  tenant    label for the report header

Output (stdout), one JSON object: {summary, findings[], by_band}, where each
finding carries control_id, title, section, risk{band,score,factors},
mitigation{where,action,method}, finding_type, detail.

The risk model is RULE-BASED and EXPLAINABLE on purpose: a score a customer
cannot interrogate is just a prettier "UNKNOWN". Every finding shows the
factors that produced its band.
"""
from __future__ import annotations

import json
import re
import sys

_CONTROL_ID = re.compile(r"CIS (?:L2 )?(?:M365 )?(\d+(?:\.\d+)*)")
_NOT_A_PASS = re.compile(r"\(this is not a pass\)", re.IGNORECASE)
_FAIL_CLOSED = re.compile(r"^FAIL-CLOSED\b", re.IGNORECASE)

# ── Risk model ────────────────────────────────────────────────────────
# Base weight by control domain (section prefix). Identity/admin/auth carry
# the most consequence; informational/UX settings the least.
_DOMAIN_BASE = [
    (("1.1", "5.1.1", "5.1.2", "5.1.6"), 4, "privileged-access / admin control"),
    (("5.2", "5.1.3", "5.1.4", "5.1.5"), 4, "authentication / identity governance"),
    (("2.", "6.5", "6.2"), 3, "threat protection / mail security"),
    (("3.", "6.1", "8.5", "7.2"), 3, "data protection / auditing"),
    (("1.3", "6.", "7.", "8.", "9."), 2, "service configuration"),
    (("1.2",), 2, "account / group hygiene"),
]
# Keyword elevators — a finding whose text implies one of these is raised.
_ELEVATORS = [
    (re.compile(r"global admin", re.I), 2, "affects global administrators"),
    (re.compile(r"\bMFA\b|multifactor|multi-factor", re.I), 2, "weakens multifactor authentication"),
    (re.compile(r"legacy auth|modern authentication|basic auth", re.I), 2, "permits legacy/basic authentication (bypasses CA/MFA)"),
    (re.compile(r"consent|consent-phish", re.I), 1, "enables user consent / consent-phishing exposure"),
    (re.compile(r"\bexternal\b|outside the organization|anonymous", re.I), 1, "exposes data/access externally"),
    (re.compile(r"audit", re.I), 1, "affects audit/evidence capture"),
    (re.compile(r"disconnect|tamper", re.I), 2, "affects a high-consequence control"),
    (re.compile(r"encrypt|bitlocker|tls", re.I), 1, "affects encryption/transport protection"),
]

_BANDS = [(8, "Critical"), (5, "High"), (3, "Medium"), (0, "Low")]

# ── Mitigation guidance (where to fix) keyed by section prefix ────────
# Directional CIS remediation: the admin surface + the action. Precise
# enough to act on; honest that exact steps live in the CIS benchmark.
_MITIGATION = [
    ("1.1", "Microsoft 365 admin center → Users / Roles", "adjust administrative role assignments and account configuration"),
    ("1.2", "Microsoft 365 admin center → Teams & groups", "restrict group creation / sharing to approved owners"),
    ("1.3", "Microsoft 365 admin center → Settings → Org settings", "disable the permissive service setting for this control"),
    ("2.", "Microsoft Defender portal → Policies & rules", "enable/strengthen the Safe Links / Safe Attachments / anti-phishing policy"),
    ("3.", "Microsoft Purview → Data lifecycle / DLP", "enable the data-protection or DLP policy for this control"),
    ("5.1.2", "Microsoft Entra admin center → Identity → Users → User settings", "restrict the user self-service capability to administrators"),
    ("5.1.3", "Microsoft Entra admin center → Identity → Groups → General", "restrict group self-service to administrators"),
    ("5.1.5", "Microsoft Entra admin center → Identity → Enterprise applications → Consent and permissions", "route app consent to an administrator"),
    ("5.1", "Microsoft Entra admin center → Identity → Users", "apply the identity restriction for this control"),
    ("5.2", "Microsoft Entra admin center → Protection → Authentication methods / Conditional Access", "enable the authentication-strength / MFA control"),
    ("5.3", "Microsoft Entra admin center → Identity Governance", "apply the access-review / PIM configuration"),
    ("6.", "Exchange admin center → Mail flow / Settings", "apply the Exchange Online configuration for this control"),
    ("7.", "SharePoint admin center → Policies / Sharing", "tighten the SharePoint/OneDrive sharing setting"),
    ("8.", "Teams admin center → Meetings / Messaging policies", "apply the Teams policy for this control"),
    ("9.", "Microsoft Fabric / Power Platform admin portal", "apply the tenant setting for this control"),
]


def _sort_key(cid: str):
    try:
        return tuple(int(p) for p in cid.split("."))
    except ValueError:
        return (9999,)


def _domain(cid: str):
    for prefixes, weight, label in _DOMAIN_BASE:
        if any(cid.startswith(p) for p in prefixes):
            return weight, label
    return 2, "service configuration"


def _mitigation(cid: str):
    best = None
    for prefix, where, action in _MITIGATION:
        if cid.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, where, action)
    if best:
        return {"where": best[1], "action": best[2], "method": "manual"}
    return {"where": "Microsoft 365 / Entra admin center", "action": "apply the CIS-recommended configuration", "method": "manual"}


def _band(score: int) -> str:
    for threshold, name in _BANDS:
        if score >= threshold:
            return name
    return "Low"


def _score_finding(cid: str, detail: str, is_level2: bool):
    base, domain_label = _domain(cid)
    factors = [f"base {base}: {domain_label}"]
    score = base
    for pat, bump, why in _ELEVATORS:
        if pat.search(detail):
            score += bump
            factors.append(f"+{bump}: {why}")
    if is_level2:
        factors.append("L2 defense-in-depth (not raised)")
    else:
        score += 1
        factors.append("+1: CIS Level 1 baseline")
    return score, factors


def build_report(payload: dict) -> dict:
    rows = payload.get("rows") or []
    catalog = {c["control_id"]: c for c in payload.get("catalog") or []}
    tenant = payload.get("tenant", "tenant")

    findings = []
    gaps = []
    for row in rows:
        section = str(row.get("policy_name", "")).rsplit(".", 1)[-1]
        for v in row.get("violations") or []:
            if not isinstance(v, str):
                continue
            m = _CONTROL_ID.search(v)
            cid = m.group(1) if m else "?"
            cat = catalog.get(cid, {})
            title = re.split(r"[:\-—]", v, maxsplit=1)[-1].strip() if ":" in v else v
            # Keep the full emitted message as the detail — it explains WHY.
            detail = re.sub(r"^CIS (?:L2 )?\d+(?:\.\d+)*:\s*", "", v).strip()
            is_gap = bool(_NOT_A_PASS.search(v) or _FAIL_CLOSED.match(v))
            levels = cat.get("levels") or []
            is_l2 = any("Level 2" in str(x) for x in levels)

            if is_gap:
                gaps.append({
                    "control_id": cid,
                    "section": cat.get("section", section),
                    "section_name": cat.get("section_name", ""),
                    "detail": detail,
                    "finding_type": "evidence_gap",
                })
                continue

            score, factors = _score_finding(cid, detail, is_l2)
            findings.append({
                "control_id": cid,
                "section": str(cat.get("section", section)),
                "section_name": cat.get("section_name", ""),
                "cis_assessment": cat.get("assessment", ""),
                "cis_level": "L2" if is_l2 else "L1",
                "finding_type": "assessed_failure",
                "detail": detail,
                "risk": {"band": _band(score), "score": score, "factors": factors},
                "mitigation": _mitigation(cid),
            })

    band_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    findings.sort(key=lambda f: (band_order[f["risk"]["band"]],
                                 -f["risk"]["score"], _sort_key(f["control_id"])))

    by_band = {b: 0 for b in band_order}
    for f in findings:
        by_band[f["risk"]["band"]] += 1

    # Aggregate compliance posture for the executive view, when the rows
    # carry pass/fail counts (they do when written by the assessment). Falls
    # back to a findings-only posture when counts are absent.
    passed = failed = evaluated = 0
    for row in rows:
        meta = row.get("metadata") or {}
        p = row.get("passed_controls")
        f_ = row.get("failed_controls")
        ev = meta.get("controls_evaluated")
        if p is not None:
            passed += int(p)
        if f_ is not None:
            failed += int(f_)
        if ev is not None:
            evaluated += int(ev)
    benchmark_total = len(catalog) or None
    scored_total = (passed + failed) or evaluated
    compliance_pct = round(passed * 100 / scored_total, 1) if scored_total else None

    # Posture: a plain-language verdict, not a score.
    total_findings = len(findings)
    crit_high = by_band["Critical"] + by_band["High"]
    if total_findings == 0:
        verdict = "No open control failures in scope — compliant for the evaluated controls."
    elif crit_high == 0:
        verdict = (f"{total_findings} control(s) failing, none critical or high — "
                   "a remediation backlog, not an active exposure.")
    else:
        verdict = (f"{crit_high} critical/high-risk control failure(s) require attention first, "
                   f"of {total_findings} total open findings.")

    return {
        "summary": {
            "benchmark": "CIS Microsoft 365 Foundations Benchmark v7.0.0",
            "tenant": tenant,
            "total_findings": total_findings,
            "by_band": by_band,
            "evidence_gaps": len(gaps),
            "verdict": verdict,
            "compliance_pct": compliance_pct,
            "controls_evaluated": evaluated or scored_total or None,
            "benchmark_total": benchmark_total,
        },
        "findings": findings,
        "evidence_gaps": gaps,
    }


def build_csv(payload: dict) -> str:
    """CSV export in the structure requested by the field: a per-CATEGORY
    summary (total / passed / failed / unable-to-assess) followed by a
    per-finding DETAIL section with ONE COLUMN PER FIELD (category, control,
    status, level, assessment, risk, basis, where, action, method, detail) so
    nothing has to be parsed out of a sentence downstream.

    Category = CIS M365 section. "Unable to assess" absorbs everything we
    could not confirm as a pass or a fail — controls not evaluated, facts
    not collected (evidence gaps), and attestation-required controls with no
    recorded attestation — so each category row balances:
    Total = Passed + Failed + Unable.
    """
    import csv
    import io

    rep = build_report(payload)
    catalog = payload.get("catalog") or []
    catalog_by_id = {str(c.get("control_id")): c for c in catalog}
    rows = payload.get("rows") or []

    # section number -> display name, and section number -> benchmark total
    sec_name = {}
    sec_total = {}
    for c in catalog:
        sec = str(c.get("section", ""))
        sec_name.setdefault(sec, c.get("section_name", f"Section {sec}"))
        sec_total[sec] = sec_total.get(sec, 0) + 1

    # passed/failed per section from the numeric section rows only (the
    # 'attestation' pseudo-row's failures are unattested -> unable, not failed)
    sec_pass = {s: 0 for s in sec_total}
    sec_fail = {s: 0 for s in sec_total}
    for row in rows:
        sec = str(row.get("policy_name", "")).rsplit(".", 1)[-1]
        if sec not in sec_total:
            continue
        sec_pass[sec] += int(row.get("passed_controls") or 0)
        sec_fail[sec] += int(row.get("failed_controls") or 0)

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["CIS Microsoft 365 Foundations Benchmark v7.0.0 — Results Export"])
    w.writerow([f"Tenant: {payload.get('tenant', '')}"])
    w.writerow([])
    w.writerow(["SUMMARY BY CATEGORY"])
    w.writerow(["Category", "Total Controls", "Passed", "Failed", "Unable to Assess"])
    tot = tp = tf = tu = 0
    for sec in sorted(sec_total, key=lambda s: _sort_key(s + ".0")):
        total = sec_total[sec]
        p = min(sec_pass.get(sec, 0), total)
        f = min(sec_fail.get(sec, 0), total - p)
        unable = max(total - p - f, 0)
        w.writerow([sec_name[sec], total, p, f, unable])
        tot += total; tp += p; tf += f; tu += unable
    w.writerow(["TOTAL", tot, tp, tf, tu])
    w.writerow([])
    w.writerow(["DETAIL"])
    # One column per field — nothing to parse downstream. Same vocabulary as
    # the generic findings workbook (docs/operations/FINDINGS_WORKBOOK_CONTRACT.md).
    w.writerow(["Category", "Control", "Status", "Profile level", "Benchmark assessment",
                "Risk", "Risk score", "Risk basis", "Where to fix", "Action", "Method", "Detail"])

    def _cat(cid):
        sec = cid.split(".")[0]
        return sec_name.get(sec, f"Section {sec}")

    for f in rep["findings"]:
        w.writerow([_cat(f["control_id"]), f["control_id"], "Failed", f.get("cis_level", ""),
                    f.get("cis_assessment", ""), f["risk"]["band"], f["risk"]["score"],
                    "; ".join(f["risk"]["factors"]), f["mitigation"]["where"],
                    f["mitigation"]["action"], f["mitigation"]["method"], f["detail"]])
    for g in rep["evidence_gaps"]:
        cat = catalog_by_id.get(g["control_id"], {})
        w.writerow([_cat(g["control_id"]), g["control_id"], "Unable to assess",
                    "L2" if any("Level 2" in str(x) for x in (cat.get("levels") or [])) else ("L1" if cat.get("levels") else ""),
                    cat.get("assessment", ""), "", "", "evidence gap — facts not collected or attestation not recorded",
                    "the assessment collector", "enable or fix fact collection for this area", "manual", g["detail"]])
    return out.getvalue()


def render_exec_html(rep: dict, *, sample: bool = False) -> str:
    """One-page executive view: posture, score, top risks, remediation
    outlook, coverage — not a list of every finding."""
    from html import escape as e
    s = rep["summary"]
    crit_high = [f for f in rep["findings"] if f["risk"]["band"] in ("Critical", "High")]
    top = crit_high[:5]
    pct = s.get("compliance_pct")
    pct_disp = f"{pct}%" if pct is not None else "—"
    pct_color = "#2e7d32" if (pct or 0) >= 90 else "#f9a825" if (pct or 0) >= 70 else "#c62828"
    cov = ""
    if s.get("controls_evaluated") and s.get("benchmark_total"):
        cov = (f"{s['controls_evaluated']} of {s['benchmark_total']} benchmark controls "
               f"evaluated this cycle.")
    top_rows = "".join(
        f'<tr><td><span class="b" style="background:{_BAND_COLOR[f["risk"]["band"]]}">'
        f'{f["risk"]["band"]}</span></td><td class="cid">CIS {e(f["control_id"])}</td>'
        f'<td>{e(f["detail"])}</td></tr>' for f in top) or \
        '<tr><td colspan="3">No critical or high-risk findings.</td></tr>'
    banner = ('<div class="sample">SAMPLE — synthetic data against real CIS M365 v7.0.0 '
              'control text. Not customer results.</div>') if sample else ""
    quick = s["by_band"]["Critical"] + s["by_band"]["High"]
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>M365 Compliance — Executive Summary — {e(s['tenant'])}</title><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:#fff;color:#1a1a2e}}
.hdr{{background:linear-gradient(135deg,#1a237e,#283593);color:#fff;padding:30px 48px}}
.hdr h1{{font-size:25px}} .hdr p{{opacity:.9;font-size:13px;margin-top:4px}}
.sample{{background:#fff3e0;color:#e65100;font-weight:600;padding:8px 48px;font-size:12px}}
.wrap{{max-width:940px;margin:0 auto;padding:30px 48px}}
.top{{display:grid;grid-template-columns:200px 1fr;gap:28px;align-items:center;margin-bottom:26px}}
.score{{text-align:center;background:#f7f8fc;border-radius:14px;padding:22px}}
.score .n{{font-size:52px;font-weight:800;color:{pct_color};line-height:1}}
.score .c{{font-size:12px;color:#666;margin-top:6px}}
.verdict{{font-size:19px;font-weight:600;line-height:1.4}}
.cov{{color:#666;font-size:13px;margin-top:10px}}
.bands{{display:flex;gap:10px;margin:8px 0 26px}}
.band{{flex:1;text-align:center;border-radius:9px;padding:14px 6px;color:#fff;font-weight:700}}
.band .bn{{font-size:26px}} .band .bl{{font-size:11px;opacity:.9;font-weight:600}}
h2{{color:#1a237e;font-size:16px;margin:24px 0 10px;border-bottom:2px solid #e8eaf6;padding-bottom:5px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}
td{{padding:9px 8px;border-bottom:1px solid #eee;vertical-align:top}}
.b{{color:#fff;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px}}
.cid{{font-weight:700;color:#1a237e;white-space:nowrap}}
.outlook{{background:#f1f8e9;border-left:4px solid #558b2f;padding:14px 18px;border-radius:6px;font-size:14px;margin-top:8px}}
.ft{{color:#999;font-size:11px;padding:22px 0 0;text-align:center}}
</style></head><body>
<div class="hdr"><h1>Microsoft 365 Compliance — Executive Summary</h1>
<p>CIS Microsoft 365 Foundations v7.0.0 · {e(s['tenant'])}</p></div>
{banner}
<div class="wrap">
<div class="top">
  <div class="score"><div class="n">{pct_disp}</div><div class="c">of evaluated controls passing</div></div>
  <div><div class="verdict">{e(s['verdict'])}</div><div class="cov">{e(cov)}</div></div>
</div>
<div class="bands">
  <div class="band" style="background:#b71c1c"><div class="bn">{s['by_band']['Critical']}</div><div class="bl">CRITICAL</div></div>
  <div class="band" style="background:#e65100"><div class="bn">{s['by_band']['High']}</div><div class="bl">HIGH</div></div>
  <div class="band" style="background:#f9a825"><div class="bn">{s['by_band']['Medium']}</div><div class="bl">MEDIUM</div></div>
  <div class="band" style="background:#2e7d32"><div class="bn">{s['by_band']['Low']}</div><div class="bl">LOW</div></div>
  <div class="band" style="background:#6a1b9a"><div class="bn">{s['evidence_gaps']}</div><div class="bl">EVIDENCE GAPS</div></div>
</div>
<h2>Top risks to address first</h2>
<table>{top_rows}</table>
<h2>Remediation outlook</h2>
<div class="outlook">{quick} critical/high-risk control(s) are the priority. Every open
finding has a defined remediation and is correctable through Microsoft 365 / Entra
admin-center configuration — these are governance and configuration changes, not
infrastructure projects. Full prioritized detail and step references are in the
accompanying findings report.</div>
<div class="ft">Generated by AAC from stored OPA evaluations · Co-authored by Claude (Anthropic) via Claude Code</div>
</div></body></html>"""


_BAND_COLOR = {"Critical": "#b71c1c", "High": "#e65100",
               "Medium": "#f9a825", "Low": "#2e7d32"}


def render_markdown(rep: dict, *, sample: bool = False) -> str:
    s = rep["summary"]
    L = []
    if sample:
        L += ["> **SAMPLE REPORT** — synthetic evaluation data against real CIS M365 v7.0.0",
              "> control text, to show report format. **Not customer results.**", ""]
    L += [f"# {s['benchmark']} — Prioritized Findings & Remediation", "",
          f"**Tenant:** {s['tenant']}", "",
          "## Posture", "", f"**{s['verdict']}**", "",
          "| Critical | High | Medium | Low | Evidence gaps |", "|--:|--:|--:|--:|--:|",
          f"| {s['by_band']['Critical']} | {s['by_band']['High']} | {s['by_band']['Medium']} | {s['by_band']['Low']} | {s['evidence_gaps']} |", "",
          "Findings are ordered by risk. Each carries a derived, explainable risk band",
          "and a concrete remediation — no finding is left unranked.", "",
          "## Findings (highest risk first)", ""]
    for f in rep["findings"]:
        r = f["risk"]
        L += [f"### [{r['band']}] CIS {f['control_id']} · {f['section_name']} · {f['cis_level']}",
              "", f"**Finding:** {f['detail']}", "",
              f"**Risk:** {r['band']} (score {r['score']}) — {'; '.join(r['factors'])}", "",
              f"**Remediation:** {f['mitigation']['action']}.  ",
              f"*Where:* {f['mitigation']['where']}  ·  *Method:* {f['mitigation']['method']}", ""]
    if rep["evidence_gaps"]:
        L += ["## Evidence gaps (could not be assessed — not failures, not passes)", ""]
        for g in rep["evidence_gaps"]:
            L.append(f"- **CIS {g['control_id']}** ({g['section_name']}): {g['detail']}")
        L.append("")
    L += ["---", "*Generated by AAC from stored OPA evaluations. Co-authored by Claude",
          "(Anthropic) via Claude Code — AI-authorship transparency.*"]
    return "\n".join(L) + "\n"


def render_html(rep: dict, *, sample: bool = False) -> str:
    from html import escape as e
    s = rep["summary"]
    cards = "".join(
        f'<div class="card" style="border-top:4px solid {_BAND_COLOR[b]}">'
        f'<div class="v" style="color:{_BAND_COLOR[b]}">{s["by_band"][b]}</div>'
        f'<div class="l">{b}</div></div>'
        for b in ("Critical", "High", "Medium", "Low"))
    cards += (f'<div class="card" style="border-top:4px solid #6a1b9a">'
              f'<div class="v" style="color:#6a1b9a">{s["evidence_gaps"]}</div>'
              f'<div class="l">Evidence gaps</div></div>')
    rows = ""
    for f in rep["findings"]:
        r = f["risk"]; c = _BAND_COLOR[r["band"]]
        rows += (f'<div class="finding">'
                 f'<div class="fh"><span class="badge" style="background:{c}">{r["band"]}</span>'
                 f'<span class="cid">CIS {e(f["control_id"])}</span>'
                 f'<span class="sec">{e(f["section_name"])} · {f["cis_level"]}</span></div>'
                 f'<div class="detail">{e(f["detail"])}</div>'
                 f'<div class="mit"><strong>Remediation:</strong> {e(f["mitigation"]["action"])}. '
                 f'<span class="where">{e(f["mitigation"]["where"])}</span></div>'
                 f'<div class="why">Risk basis: {e("; ".join(r["factors"]))}</div>'
                 f'</div>')
    gaps = ""
    if rep["evidence_gaps"]:
        items = "".join(f'<li><strong>CIS {e(g["control_id"])}</strong> ({e(g["section_name"])}): {e(g["detail"])}</li>'
                        for g in rep["evidence_gaps"])
        gaps = (f'<div class="gaps"><h2>Evidence gaps — could not be assessed '
                f'(not failures, not passes)</h2><ul>{items}</ul></div>')
    banner = ('<div class="sample">SAMPLE — synthetic data against real CIS M365 v7.0.0 '
              'control text, to show report format. Not customer results.</div>') if sample else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>M365 CIS Findings — {e(s['tenant'])}</title><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:#f0f2f5;color:#222}}
.hdr{{background:linear-gradient(135deg,#1a237e,#283593);color:#fff;padding:28px 40px}}
.hdr h1{{font-size:23px;margin-bottom:4px}} .hdr p{{opacity:.9;font-size:13px}}
.sample{{background:#fff3e0;color:#e65100;font-weight:600;padding:8px 40px;font-size:13px;border-bottom:1px solid #ffcc80}}
.wrap{{max-width:1000px;margin:0 auto;padding:26px}}
.verdict{{background:#e8eaf6;border-left:4px solid #283593;padding:14px 18px;border-radius:5px;font-size:15px;margin-bottom:20px}}
.cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:26px}}
.card{{background:#fff;border-radius:9px;padding:18px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.07)}}
.card .v{{font-size:30px;font-weight:700}} .card .l{{color:#666;font-size:12px;margin-top:3px}}
h2{{color:#1a237e;font-size:17px;margin:22px 0 12px}}
.finding{{background:#fff;border-radius:9px;padding:16px 18px;margin-bottom:12px;box-shadow:0 1px 5px rgba(0,0,0,.06)}}
.fh{{display:flex;align-items:center;gap:10px;margin-bottom:7px}}
.badge{{color:#fff;font-size:11px;font-weight:700;padding:2px 9px;border-radius:11px;letter-spacing:.3px}}
.cid{{font-weight:700;color:#1a237e}} .sec{{color:#888;font-size:12px}}
.detail{{font-size:14px;margin-bottom:8px}}
.mit{{font-size:13px;background:#f1f8e9;border-left:3px solid #558b2f;padding:7px 11px;border-radius:4px}}
.mit .where{{color:#33691e;font-style:italic}}
.why{{font-size:11px;color:#999;margin-top:6px}}
.gaps{{background:#f3e5f5;border-left:4px solid #6a1b9a;padding:12px 18px;border-radius:5px;margin-top:18px;font-size:13px}}
.gaps li{{margin:4px 0 4px 18px}}
.ft{{text-align:center;color:#888;font-size:11px;padding:20px}}
</style></head><body>
<div class="hdr"><h1>CIS Microsoft 365 v7.0.0 — Prioritized Findings &amp; Remediation</h1>
<p>Tenant: {e(s['tenant'])} · ordered by risk · every finding ranked and paired with a fix</p></div>
{banner}
<div class="wrap">
<div class="verdict"><strong>Posture:</strong> {e(s['verdict'])}</div>
<div class="cards">{cards}</div>
<h2>Findings — highest risk first</h2>
{rows}
{gaps}
<div class="ft">Generated by AAC from stored OPA evaluations · Co-authored by Claude (Anthropic) via Claude Code</div>
</div></body></html>"""


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--render", choices=["json", "md", "html", "exec-html", "csv"], default="json")
    ap.add_argument("--sample", action="store_true", help="mark output as SAMPLE")
    args = ap.parse_args()
    payload = json.load(sys.stdin)
    rep = build_report(payload)
    if args.render == "md":
        sys.stdout.write(render_markdown(rep, sample=args.sample))
    elif args.render == "html":
        sys.stdout.write(render_html(rep, sample=args.sample))
    elif args.render == "exec-html":
        sys.stdout.write(render_exec_html(rep, sample=args.sample))
    elif args.render == "csv":
        sys.stdout.write(build_csv(payload))
    else:
        json.dump(rep, sys.stdout, indent=1)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
