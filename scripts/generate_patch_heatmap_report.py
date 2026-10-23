#!/usr/bin/env python3
"""
generate_patch_heatmap_report.py — build the Patch Exposure Heat Map report.

Reads the JSON export produced from the compliance DB (patch_heatmap_latest,
patch_unpatched_systems, patch_risk_scores, patch_risk_parameters) and emits:

  - Markdown  (canonical, into docs/)
  - DOCX      (pandoc + the AAC house reference doc)
  - PDF       (styled HTML + Chrome headless, per the house CSS)

Usage:
  generate_patch_heatmap_report.py <heatmap.json> <outdir> [version]

Document conventions (CLAUDE.md section 7): version near the top, Claude
(Anthropic) as co-author; the two Markdown copies plus versioned DOCX in
~/Downloads and the styled PDF are the maintainers' publishing step.
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

VALLEY_MEANING = {
    "coverage": "Never assessed — we do not know whether a fix exists.",
    "currency": "A fix exists and we are still inside the regulatory window.",
    "exposure": "A fix EXISTS and the regulatory deadline has passed.",
    "support":  "No fix will EVER exist. This risk never decays.",
}


def band(risk):
    """Peak-risk band. Words, not block characters — solid blocks render as
    heavy black boxes in the PDF and fight the table for attention."""
    if risk >= 100: return f"{risk:.0f} · SEVERE"
    if risk >= 75:  return f"{risk:.0f} · HIGH"
    if risk >= 50:  return f"{risk:.0f} · ELEVATED"
    if risk >= 25:  return f"{risk:.0f} · MODERATE"
    return f"{risk:.0f} · LOW"


def md_table(headers, rows, align=None):
    align = align or ["---"] * len(headers)
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(align) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def build(d, version):
    t, e = d["totals"], d["estate"]
    today = date.today().isoformat()
    sim = t.get("simulated")

    L = []
    A = L.append

    A(f"# AAC Patch Exposure Heat Map")
    A("")
    A(f"**Version:** v{version}  ")
    A(f"**Generated:** {d['generated_at']}  ")
    A(f"**Estate:** {e['hosts']} hosts · {e['products']} catalogued products · "
      f"{e['packages']:,} installed package records  ")
    A(f"**Inventory age:** {d['inventory_age_h']} hours  ")
    A(f"**Source:** `patch_risk_scores` / `patch_heatmap_latest`, AAC compliance database")
    A("")
    A("---")
    A("")

    # ---------------------------------------------------------------- provenance
    A("## Data provenance — read this first")
    A("")
    if sim:
        A("This report mixes **measured** and **fixture** data. The distinction is not "
          "cosmetic and it must survive any reuse of these figures.")
        A("")
        A(md_table(
            ["Element", "Status"],
            [["Hosts, components, installed versions", "**Measured** — observed by fact collection"],
             ["Which systems are affected", "**Measured** — matched against observed inventory"],
             ["Risk formula and parameters", "**Real** — documented, table-driven, auditable"],
             ["SLA clocks", "**Real** — CISA BOD 22-01, NERC CIP-007-6, PCI DSS v4.0, FedRAMP"],
             ["Support / end-of-life status", "**Measured** — resolved from vendor lifecycle data"],
             ["CVE records and vendor fix dates", "**FIXTURE** — synthetic `CVE-2026-9xxxx` ids, `source='demo_seed'`"]],
            [":---", ":---"]))
        A("")
        A("> **The vulnerabilities in this report are not real.** They carry synthetic "
          "identifiers that correspond to no published advisory. Real CVE identifiers were "
          "deliberately not used: attaching invented severities and fix dates to a genuine "
          "CVE id would put false security information into a database people make decisions "
          "from, and it would outlive this demonstration indistinguishable from measured data.")
        A("")
        A("> **The estate is real.** Every host, component and version below was observed on "
          "live infrastructure. What this report demonstrates is the *scoring and aggregation "
          "model operating on a real estate* — not a real exposure position.")
    else:
        A("All inputs to this report are measured. No fixture data is present.")
    A("")
    A("---")
    A("")

    # ---------------------------------------------------------------- exec summary
    A("## 1. Executive summary")
    A("")
    A(f"**{t['hosts']} of {e['hosts']} hosts carry at least one unpatched component.** "
      f"Across them, {t['findings']:,} host×component findings resolve from {t['cves']} "
      f"distinct vulnerabilities.")
    A("")
    A(md_table(
        ["Measure", "Count", "What it means"],
        [["Unpatched hosts", t["hosts"], "Systems with at least one affected component"],
         ["Findings", f"{t['findings']:,}", "Host × component pairs needing action"],
         ["Actively exploited (KEV)", t["kev"], "Being exploited in the wild **now**"],
         ["**SLA breached**", f"**{t['breached']}**", "**A fix exists and the regulatory deadline has passed**"],
         ["SLA at risk", t["at_risk"], "Inside the window, but approaching the deadline"],
         ["SLA attained", t["attained"], "Inside the regulatory window"],
         ["No fix available", t["no_fix"], "No vendor remediation exists — see §5"],
         ["Risk tier 3", t["tier3"], "Highest ceremony: deepest backup, full approval"],
         ["Aggregate risk", f"{t['risk_total']:,}", "Sum of all finding risk scores"]],
        [":---", "---:", ":---"]))
    A("")
    A(f"**The single most important number is {t['breached']}.** Those are findings where the "
      "vendor has already shipped a fix and the regulatory clock has run out. They are not a "
      "capability problem or a knowledge problem — the fix exists and is obtainable. They are "
      "the findings hardest to defend to an auditor.")
    A("")

    # ---------------------------------------------------------------- heat map
    A("---")
    A("")
    A("## 2. The heat map")
    A("")
    A("Patch exposure folds into the **existing** technical-debt categories rather than "
      "creating a new one. One cell, one owner, one budget line — a separate \"patching\" "
      "category would create a second queue competing with the first for the same engineers.")
    A("")
    rows = []
    for c in d["heatmap"]:
        rows.append([
            f"**{c['debt_category']}**",
            c["valley_type"],
            c["hosts"],
            c["findings"],
            c["kev_findings"],
            c["sla_breached"],
            f"{c['effort_hours']:.0f}h",
            f"${c['cost_usd']:,.0f}",
            f"{c['risk_total']:,.0f}",
            band(float(c["risk_max"])),
        ])
    A(md_table(
        ["Category", "Valley", "Hosts", "Findings", "KEV", "Breached", "Effort", "Cost", "Risk", "Peak"],
        rows,
        [":---", ":---", "---:", "---:", "---:", "---:", "---:", "---:", "---:", ":---"]))
    A("")
    A("### Why two axes")
    A("")
    A("The heat map has always been a **cost** surface: hours × rate, driven by compliance "
      "violations. Patch exposure adds something cost cannot express. A KEV vulnerability is "
      "being exploited right now; the question is not *what does it cost to fix* but "
      "**what does it cost not to fix**. Both columns are shown because they answer different "
      "questions and neither substitutes for the other.")
    A("")
    A("### The four valley types")
    A("")
    A(md_table(["Valley", "Meaning"],
               [[f"`{k}`", v] for k, v in VALLEY_MEANING.items()],
               [":---", ":---"]))
    A("")
    A("`exposure` is the band that matters most: the fix is available and the deadline has "
      "passed. `support` is the band people underestimate — see §5.")
    A("")

    # ---------------------------------------------------------------- risk model
    A("---")
    A("")
    A("## 3. How risk is scored")
    A("")
    A("```")
    A("risk = severity_weight  ×  kev_multiplier  ×  age_factor  ×  breadth_factor")
    A("```")
    A("")
    A("Every factor is stored alongside the score, so any number in this report can be "
      "explained rather than asserted. An auditor asking *\"why is this 124.5\"* is shown the "
      "four factors and the parameter rows that produced them.")
    A("")
    A("**The age factor is measured from when the FIX became available — not from when the "
      "vulnerability was published.** The clock starts when action became possible. A "
      "vulnerability disclosed three years ago whose fix shipped last week represents one "
      "week of exposure, not three years. This also makes stale backlog grow louder over time, "
      "which is the behaviour we want.")
    A("")
    A("### Parameters")
    A("")
    groups = {}
    for p in d["params"]:
        groups.setdefault(p["param_group"], []).append(p)
    for g, ps in groups.items():
        A(f"**`{g}`**")
        A("")
        A(md_table(["Key", "Value", "Rationale", "Source"],
                   [[f"`{p['param_key']}`", p["param_value"], p["rationale"] or "", f"*{p['source'] or ''}*"] for p in ps],
                   [":---", "---:", ":---", ":---"]))
        A("")
    A("### The SLA clocks are real regulatory deadlines")
    A("")
    A("They are not internal targets. Missing them is a compliance finding, not a preference:")
    A("")
    A(md_table(["Clock", "Deadline", "Instrument"],
               [["KEV (actively exploited)", "14 days", "CISA **BOD 22-01** — CVEs published 2021+"],
                ["Critical / high", "1 month", "**PCI DSS v4.0 §6.3.3**"],
                ["High (BES cyber systems)", "35 + 35 days", "**NERC CIP-007-6 R2.2 / R2.3** — evaluate, then apply or mitigate"],
                ["Moderate / low", "90 / 180 days", "**FedRAMP** continuous monitoring"]],
               [":---", "---:", ":---"]))
    A("")
    A("### Risk tiers drive procedure depth")
    A("")
    A("Tier is a **policy decision, not a fixed procedure** — it determines backup depth, "
      "assurance depth and approval ceremony for each change.")
    A("")
    A(md_table(["Tier", "Findings", "Implication"],
               [["**3**", t["tier3"], "Deepest backup, full approval ceremony, highest assurance"],
                ["2", t["tier2"], "Elevated handling"],
                ["1", t["tier1"], "Standard change"],
                ["0", t["tier0"], "Routine"]],
               [":---", "---:", ":---"]))
    A("")

    # ---------------------------------------------------------------- unpatched
    A("---")
    A("")
    A("## 4. Unpatched systems")
    A("")
    A(f"The systems carrying exposure, ranked by aggregate risk. This is the operational "
      f"work list — every row is a real host observed on the estate.")
    A("")
    rows = []
    for u in d["unpatched"]:
        rows.append([
            f"`{u['hostname']}`",
            u["findings"],
            u["kev_findings"],
            u["sla_breached"],
            f"{float(u['risk_total']):,.0f}",
            f"{float(u['risk_max']):.1f}",
            u["max_tier"],
            u["categories"],
        ])
    A(md_table(
        ["Host", "Findings", "KEV", "Breached", "Total risk", "Peak", "Tier", "Categories"],
        rows,
        [":---", "---:", "---:", "---:", "---:", "---:", "---:", ":---"]))
    A("")
    if len(d["unpatched"]) >= 20:
        A(f"*Showing the top 20 by risk. {t['hosts']} hosts carry exposure in total.*")
        A("")
    A("**Ranking by aggregate risk rather than finding count is deliberate.** A host with one "
      "actively-exploited critical vulnerability is a more urgent problem than a host with "
      "twenty low-severity findings inside their regulatory window. Counting findings inverts "
      "that priority.")
    A("")

    # ---------------------------------------------------------------- top cves
    A("---")
    A("")
    A("## 5. Highest-risk vulnerabilities")
    A("")
    rows = []
    for c in sorted(d["top_cves"], key=lambda x: -float(x["risk"])):
        dsf = c["days_since_fix"]
        rows.append([
            f"`{c['cve_id']}`",
            c["product"],
            c["severity"],
            "**YES**" if c["kev"] else "no",
            c["hosts"],
            f"{dsf}d" if dsf is not None else "—",
            f"{c['sla_days']}d",
            f"`{c['sla_state']}`",
            f"{float(c['risk']):.1f}",
            c["tier"],
        ])
    A(md_table(
        ["CVE", "Component", "Severity", "KEV", "Hosts", "Since fix", "SLA", "State", "Risk", "Tier"],
        rows,
        [":---", ":---", ":---", ":---", "---:", "---:", "---:", ":---", "---:", "---:"]))
    A("")

    # ---------------------------------------------------------------- no fix
    if d.get("nofix"):
        A("---")
        A("")
        A("## 6. Components where no fix will ever exist")
        A("")
        A("These findings sit in the **`support`** valley and fold into "
          "**`technology_lifecycle`**, not `security`. The distinction is the most consequential "
          "one in this report.")
        A("")
        A(md_table(["Component", "Hosts", "Peak risk"],
                   [[f"`{n['product']}`", n["hosts"], f"{float(n['risk']):.1f}"] for n in d["nofix"]],
                   [":---", "---:", "---:"]))
        A("")
        A("**\"No fix\" on a supported product is a data gap** — the fix may ship tomorrow. "
          "**\"No fix\" past end-of-support is a permanent fact.** Its exposure risk never "
          "decays, because no patch cycle will ever retire it. Only replacement will.")
        A("")
        A("> **Unsupported technology converts remediation debt into REPLACEMENT debt.** "
          "That is a different budget line, a different timescale, and a different "
          "conversation with the business.")
        A("")
        A("Under **NERC CIP-007-6 R2.3**, a *dated mitigation plan* is the only lawful path "
          "when no patch is available. This makes technology lifecycle a compliance "
          "requirement rather than hygiene. The relevant controls are **NIST 800-53 SA-22** "
          "(Unsupported System Components) and **CIS Controls v8 Safeguard 2.2**.")
        A("")

    # ---------------------------------------------------------------- limits
    A("---")
    A("")
    A("## 7. What this report does not tell you")
    A("")
    A("Stated plainly, because a heat map that hides its own limits is worse than no heat map.")
    A("")
    A(md_table(["Not covered", "Consequence"],
               [["**Exploitability in context**",
                 "Risk is scored on severity, exploitation status, age and breadth — **not** on "
                 "whether mitigating controls are in force on each host. Red Hat's guidance is to "
                 "rank on exploitability in context; SELinux and ASLR often make vulnerable code "
                 "impractical to exploit. AAC holds that evidence in `compliance_results` but it is "
                 "not yet wired into this score. **Some findings here are almost certainly ranked "
                 "too high.**"],
                ["Effort estimates", "A uniform 30 minutes per host × component. Not calibrated "
                 "against actual remediation runs, so cost figures are indicative only."],
                ["Asset criticality", "All hosts are weighted equally. A lab host and a production "
                 "database score the same for identical findings."],
                ["Risk tiering policy", "Tiers are threshold-derived, not policy-derived. Stage 6 "
                 "OPA tiering is not built."],
                ["Closure verification", "This is an exposure snapshot. It does not assert anything "
                 "has been remediated."]],
               [":---", ":---"]))
    A("")

    # ---------------------------------------------------------------- actions
    A("---")
    A("")
    A("## 8. Recommended sequence")
    A("")
    A(f"1. **The {t['kev']} actively-exploited findings first**, regardless of severity band. "
      "KEV means exploitation is happening now, not that it is theoretically possible.")
    A(f"2. **Then the {t['breached']} SLA-breached findings.** A fix exists and the deadline has "
      "passed; these are the least defensible findings in an audit.")
    A(f"3. **Then the {t['tier3']} tier-3 findings** through the full change ceremony — deepest "
      "backup, full approval, highest assurance.")
    A("4. **Separately, and on a different budget line: the no-fix components in §6.** These do "
      "not belong in the patch queue at all. They need a dated mitigation plan and a "
      "replacement decision.")
    A("")
    A("---")
    A("")
    A("## Method")
    A("")
    A("Generated from the AAC compliance database by "
      "`ansible/playbooks/simulate_patch_lifecycle.yml`, which scores "
      "`patch_worklist` into `patch_risk_scores` and aggregates into "
      "`patch_heatmap_cells`. The work list itself is produced by "
      "`ansible/playbooks/identify_affected_components.yml`, which matches CVE records "
      "against the observed product catalog.")
    A("")
    A("Implements `docs/patch_remediation_lifecycle.md` §5 (heat-map aggregation) and "
      "Stage 6 (risk tiering).")
    A("")
    A("---")
    A("")
    A("## Authorship")
    A("")
    A("Prepared by **Tim Coulter** with **Claude (Anthropic, Claude Opus 5)** as co-author.")
    A("")
    return "\n".join(L)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    data = json.load(open(sys.argv[1]))
    outdir = Path(sys.argv[2]); outdir.mkdir(parents=True, exist_ok=True)
    version = sys.argv[3] if len(sys.argv) > 3 else "1.0"

    md = build(data, version)
    stem = "AAC_Patch_Exposure_Heat_Map"
    md_path = outdir / f"{stem}.md"
    md_path.write_text(md)
    print(f"markdown  {md_path}  ({len(md.splitlines())} lines)")

    dl = Path.home() / "Downloads"
    today = date.today().isoformat()
    for p in [dl / f"{stem}.md", dl / f"{stem}-{today}.md"]:
        p.write_text(md); print(f"markdown  {p}")

    ref = dl / "AAC_Document_Template.docx"
    for name in [f"{stem}-v{version}.docx", f"{stem}-v{version}-{today}.docx"]:
        cmd = ["pandoc", str(md_path), "-o", str(dl / name)]
        if ref.exists():
            cmd += [f"--reference-doc={ref}"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(("docx      " if r.returncode == 0 else "DOCX FAIL ") + str(dl / name) + (r.stderr[:200] if r.returncode else ""))

    # PDF: styled HTML + Chrome headless (no LaTeX, no LibreOffice)
    css = dl / "aac_house.css"
    html_path = outdir / f"{stem}.html"
    cmd = ["pandoc", str(md_path), "-s", "--metadata", f"title={stem.replace('_',' ')}",
           "-o", str(html_path)]
    if css.exists():
        cmd += [f"--css={css}", "--embed-resources", "--standalone"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("HTML FAIL", r.stderr[:300]); return
    print(f"html      {html_path}")

    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    pdf = dl / f"{stem}-v{version}.pdf"
    if pdf.exists():
        pdf.unlink()          # so a failed render cannot leave a stale file looking fresh
    # Chrome needs an ABSOLUTE file:// URL — a relative path silently renders
    # its "site can't be reached" error page into a perfectly valid PDF.
    r = subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", html_path.resolve().as_uri()],
                       capture_output=True, text=True, timeout=120)
    if pdf.exists():
        print(f"pdf       {pdf}  ({pdf.stat().st_size:,} bytes)")
        import shutil
        dated = dl / f"{stem}-v{version}-{today}.pdf"
        shutil.copy(pdf, dated); print(f"pdf       {dated}")
    else:
        print("PDF FAIL", r.stderr[:300])


if __name__ == "__main__":
    main()
