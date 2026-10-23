#!/usr/bin/env python3
"""Build the colour-coded AAC Technical Debt Heatmap (DOCX + styled HTML->PDF).

Palette matches the prior house style extracted from aac_technical_debt_budget.docx:
  1C2B3A navy header   1A5C8A steel subhead   FDF2E0 amber fill   FAD7D7 red fill
  C0392B red accent    F39C12 amber accent    27AE60 green accent
"""
import os, html

NAVY, STEEL = "1C2B3A", "1A5C8A"
RED_FILL, AMBER_FILL, GREEN_FILL, BLUE_FILL = "FAD7D7", "FDF2E0", "E3F5E9", "E8F0F7"
RED, AMBER, GREEN, GREY = "C0392B", "F39C12", "27AE60", "6B7785"
WHITE = "FFFFFF"

# ---- data (from AAP job 1900 / compliance DB, 2026-08-04) -------------------
HOSTS = [
    # host, items, hours, last_assessed, tier  (tier drives colour)
    ("localhost",      116, 1926.0, "2026-08-04", "ok"),
    ("unknown",         92,  435.0, "2026-04-22", "crit"),
    ("676354893a37",    64,  130.0, "2026-04-20", "crit"),
    ("0d6785656747",    64,  130.0, "2026-04-20", "crit"),
    ("7b698240fb47",    64,  130.0, "2026-04-20", "crit"),
    ("aap-controller",   2,    2.0, "2026-06-30", "warn"),
    ("aap-postgres",     2,    2.0, "2026-06-30", "warn"),
]
HEAT = [
    # framework, domain, items, hours, cost, tier
    ("Digital Sovereignty", "sovereignty",             115, 1992.0, 448200, "crit"),
    ("CIS RHEL 9",          "compliance",              153,  330.0,  64350, "warn"),
    ("NERC-CIP",            "critical_infrastructure",   8,  120.0,  34200, "warn"),
    ("CIS RHEL 9",          "security",                 91,  168.5,  29488, "warn"),
    ("AMI / NIST IR 7628",  "critical_infrastructure",   7,   60.0,  17100, "info"),
    ("NCSC CAF",            "security",                 11,   66.0,  11550, "info"),
    ("NCSC CAF",            "compliance",                2,    8.0,   1560, "ok"),
    ("CIS RHEL 9",          "operational",              17,   10.5,   1313, "ok"),
]
SEV = [
    ("CRITICAL",  49,  644.0, 23.4, "crit"),
    ("HIGH",     301, 1794.5, 65.1, "warn"),
    ("MEDIUM",    46,  312.5, 11.3, "info"),
    ("LOW",        8,    4.0,  0.1, "ok"),
]
RATES = [
    ("critical_infrastructure", 285, "OT / ICS / SCADA specialist", "crit"),
    ("sovereignty",             225, "Privacy / legal engineer",    "warn"),
    ("compliance",              195, "GRC specialist",              "warn"),
    ("security",                175, "General security engineer",   "info"),
    ("technology_lifecycle",    150, "IT asset management",         "info"),
    ("operational",             125, "SysAdmin / DevOps",           "ok"),
]
FILL = {"crit": RED_FILL, "warn": AMBER_FILL, "info": BLUE_FILL, "ok": GREEN_FILL, None: None}
ACCENT = {"crit": RED, "warn": AMBER, "info": STEEL, "ok": GREEN}
LEGEND = [("crit", "Critical", "Immediate attention / severely stale"),
          ("warn", "High", "Significant exposure / stale"),
          ("info", "Medium", "Monitor"),
          ("ok", "Low / current", "Acceptable or freshly assessed")]

# ============================== DOCX =========================================
def build_docx(path):
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    def shade(cell, hexcolor):
        if not hexcolor: return
        el = OxmlElement("w:shd"); el.set(qn("w:val"), "clear")
        el.set(qn("w:color"), "auto"); el.set(qn("w:fill"), hexcolor)
        cell._tc.get_or_add_tcPr().append(el)

    def put(cell, text, bold=False, color=None, size=9, align=None):
        cell.text = ""
        p = cell.paragraphs[0]
        if align: p.alignment = align
        r = p.add_run(str(text)); r.bold = bold; r.font.size = Pt(size)
        if color: r.font.color.rgb = RGBColor.from_string(color)

    def table(doc, headers, rows, widths=None):
        t = doc.add_table(rows=1, cols=len(headers)); t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, h in enumerate(headers):
            put(t.rows[0].cells[i], h, bold=True, color=WHITE, size=9)
            shade(t.rows[0].cells[i], NAVY)
        for row in rows:
            cells = t.add_row().cells
            tier = row[-1]
            for i, v in enumerate(row[:-1]):
                right = isinstance(v, (int, float)) and i > 0
                put(cells[i], v, size=9,
                    align=WD_ALIGN_PARAGRAPH.RIGHT if right else None,
                    color=ACCENT.get(tier) if i == 0 else None,
                    bold=(i == 0))
                shade(cells[i], FILL.get(tier))
        if widths:
            for r_ in t.rows:
                for i, w in enumerate(widths): r_.cells[i].width = Inches(w)
        doc.add_paragraph()
        return t

    doc = Document()
    st = doc.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(10)

    h = doc.add_heading("AAC Technical Debt Heatmap", 0)
    for r in h.runs: r.font.color.rgb = RGBColor.from_string(NAVY)

    meta = doc.add_paragraph()
    meta.add_run("Version: ").bold = True; meta.add_run("v2.0    ")
    meta.add_run("Report date: ").bold = True; meta.add_run("2026-08-04    ")
    meta.add_run("Environment: ").bold = True; meta.add_run(os.environ.get("AAC_ENV_LABEL", "<environment>"))
    p = doc.add_paragraph(); p.add_run("Authors: ").bold = True
    p.add_run("Tim Coulter; Claude (Anthropic)")
    p = doc.add_paragraph(); p.add_run("Source: ").bold = True
    p.add_run("AAP job 1900 (template 142) — technical_debt_items where status = 'open'")

    # Legend
    doc.add_heading("Colour key", level=2)
    lt = doc.add_table(rows=1, cols=3); lt.style = "Table Grid"
    for i, hh in enumerate(("Band", "Level", "Meaning")):
        put(lt.rows[0].cells[i], hh, bold=True, color=WHITE); shade(lt.rows[0].cells[i], NAVY)
    for tier, label, meaning in LEGEND:
        c = lt.add_row().cells
        put(c[0], "        ", bold=True); shade(c[0], FILL[tier])
        put(c[1], label, bold=True, color=ACCENT[tier]); put(c[2], meaning)
    doc.add_paragraph()

    doc.add_heading("1. Scope and freshness — read first", level=1)
    doc.add_paragraph(
        "Only one of seven hosts is currently assessed. The rest carry data between five weeks "
        "and 3.5 months old, and three are ephemeral container-ID hostnames that may no longer "
        "exist. The portfolio total is the sum of each host's most recent assessment — it is NOT "
        "a statement of present-day posture.")
    table(doc, ["Host", "Open items", "Effort (h)", "Last assessed", "Freshness"],
          [[h_, i, f"{hr:,.1f}", d, {"ok": "Current", "warn": "5 weeks stale",
                                     "crit": "3+ months stale"}[t], t] for h_, i, hr, d, t in HOSTS],
          widths=[1.6, 1.0, 1.0, 1.3, 1.5])
    doc.add_paragraph(
        "Two tables measure different populations. This report uses technical_debt_items filtered "
        "to status = 'open' — the same source the Grafana Technical Debt Heatmap queries — so the "
        "document and the dashboard agree. Totals from technical_debt_summary will differ and are "
        "not comparable.")

    doc.add_heading("2. Headline — the debt score rose because measurement improved", level=1)
    t = doc.add_table(rows=1, cols=4); t.style = "Table Grid"
    for i, hh in enumerate(("Metric", "2026-07-28", "2026-08-04", "Change")):
        put(t.rows[0].cells[i], hh, bold=True, color=WHITE); shade(t.rows[0].cells[i], NAVY)
    for m, a, b, c, tier in [("Debt items", "8", "11", "+3", "info"),
                             ("Effort hours", "96.0", "148.0", "+52.0", "warn"),
                             ("Debt score", "67.50", "115.50", "+48.00", "crit")]:
        cc = t.add_row().cells
        put(cc[0], m, bold=True); put(cc[1], a); put(cc[2], b)
        put(cc[3], c, bold=True, color=ACCENT[tier])
        for x in cc: shade(x, FILL[tier])
    doc.add_paragraph()
    p = doc.add_paragraph()
    r = p.add_run("This increase is a measurement improvement, not a posture regression. ")
    r.bold = True; r.font.color.rgb = RGBColor.from_string(GREEN)
    p.add_run("Nothing on the host got worse. On 2026-08-04 three classes of false compliance were "
              "corrected in the policy library:")
    for txt in [
        "Every registered CIS framework key returned an empty result ({}) through the Generic "
        "Framework Assessment path; assessments recorded empty rows while reporting success.",
        "CIS Amazon Linux 2023 imported a package prefix that did not exist, so it reported 100% "
        "compliant on any input, including no input at all.",
        "Seven benchmarks failed open on missing facts, reporting 69–99% compliance for "
        "assessments that evaluated nothing."]:
        doc.add_paragraph(txt, style="List Bullet")
    p = doc.add_paragraph()
    p.add_run("Those paths now fail closed. Debt that was previously invisible is now counted, so "
              "the score rose. ")
    r = p.add_run("A falling debt score achieved by not measuring is worse than a rising one that "
                  "is honest."); r.bold = True
    p.add_run(" Expect a further one-time rise as the remaining six hosts are re-assessed.")

    doc.add_heading("3. Portfolio totals (open items)", level=1)
    t = doc.add_table(rows=1, cols=2); t.style = "Table Grid"
    put(t.rows[0].cells[0], "Measure", bold=True, color=WHITE); shade(t.rows[0].cells[0], NAVY)
    put(t.rows[0].cells[1], "Value", bold=True, color=WHITE); shade(t.rows[0].cells[1], NAVY)
    for k, v, tier in [("Open debt items", "404", "warn"), ("Remediation effort", "2,755.0 hours", "warn"),
                       ("Estimated cost", "$607,760", "crit"), ("Blended rate", "$220.60 / hour", "info")]:
        c = t.add_row().cells
        put(c[0], k, bold=True); put(c[1], v, bold=True, color=ACCENT[tier])
        for x in c: shade(x, FILL[tier])
    doc.add_paragraph()
    doc.add_paragraph("Cost is computed per item from remediation_rates via the standard LATERAL "
                      "JOIN on debt_category — no rate is hardcoded.")

    doc.add_heading("4. Heatmap — framework x domain", level=1)
    table(doc, ["Framework", "Domain", "Items", "Hours", "Cost (USD)"],
          [[f, d, i, f"{hr:,.1f}", f"${c:,}", t] for f, d, i, hr, c, t in HEAT] +
          [["TOTAL", "", 404, "2,755.0", "$607,760", "crit"]],
          widths=[1.7, 1.7, 0.7, 0.9, 1.2])
    doc.add_paragraph("Digital Sovereignty is 74% of total exposure on 28% of the items — a scope "
                      "decision, not an accumulation of small fixes. CIS RHEL 9 is the volume "
                      "driver (65% of findings, 18% of cost, ~1.95 h each) and the best automation "
                      "candidate. OT work costs roughly 2.3x equivalent operational effort.")

    doc.add_heading("5. Severity distribution", level=1)
    table(doc, ["Severity", "Items", "Hours", "Share of effort"],
          [[s, i, f"{hr:,.1f}", f"{sh}%", t] for s, i, hr, sh, t in SEV],
          widths=[1.4, 1.0, 1.1, 1.4])
    doc.add_paragraph("CRITICAL averages 13.1 hours per item against HIGH's 6.0 — the critical "
                      "tier is not just more urgent, it is individually more expensive to close.")

    doc.add_heading("6. Rate card", level=1)
    table(doc, ["Domain", "Rate (USD/h)", "Rationale"],
          [[d, f"${r_}", why, t] for d, r_, why, t in RATES], widths=[2.0, 1.1, 3.0])

    doc.add_heading("7. Budget comparison — no data", level=1)
    p = doc.add_paragraph()
    r = p.add_run("remediation_budgets contains 0 rows. ")
    r.bold = True; r.font.color.rgb = RGBColor.from_string(RED)
    p.add_run("The OT/IT budget-separation capability exists in schema and the domain groupings "
              "are defined, but no budget figures have been loaded. Budget-versus-debt analysis is "
              "therefore unavailable in this report rather than estimated.")

    doc.add_heading("8. Recommended sequence", level=1)
    for n, (txt, tier) in enumerate([
        ("Re-assess the six stale hosts. Until they are re-run against the corrected policy "
         "library the figures above understate real debt — the same false-compliance defects that "
         "hid 52 hours on localhost were active during those assessments. Highest-value next "
         "action; it changes every number in this report.", "crit"),
        ("Retire the ephemeral hostnames. 0d6785656747, 676354893a37 and 7b698240fb47 are "
         "container IDs. If those workloads are gone, their 192 hours are phantom debt inflating "
         "the total.", "warn"),
        ("Take a scope decision on Digital Sovereignty. At $448,200 it is 74% of exposure and "
         "warrants an explicit in-scope / deferred call.", "warn"),
        ("Automate the CIS RHEL 9 tier. 261 items at ~1.95 hours each is the best candidate for "
         "bulk remediation via existing Ansible roles.", "info"),
        ("Load remediation_budgets so funding gaps can be reported rather than inferred.", "ok")], 1):
        p = doc.add_paragraph(style="List Number")
        r = p.add_run(txt.split(".")[0] + ". "); r.bold = True
        r.font.color.rgb = RGBColor.from_string(ACCENT[tier])
        p.add_run(txt.split(".", 1)[1].strip())

    doc.add_heading("Document control", level=1)
    for k, v in [("Version", "v2.0 (adds colour-coded criticality banding; v1.0 was monochrome)"),
                 ("Date", "2026-08-04"),
                 ("Environment", os.environ.get("AAC_ENV_LABEL", "<environment>")),
                 ("Source job", "AAP job 1900 (template 142)"),
                 ("Data scope", "technical_debt_items where status = 'open'"),
                 ("Authors", "Tim Coulter; Claude (Anthropic)")]:
        p = doc.add_paragraph(); p.add_run(f"{k}: ").bold = True; p.add_run(v)
    p = doc.add_paragraph()
    r = p.add_run("Figures reflect the lab environment and are illustrative of method, not a "
                  "customer posture statement."); r.italic = True
    r.font.color.rgb = RGBColor.from_string(GREY)
    doc.save(path)
    print("  DOCX ->", path)

# ============================== HTML / PDF ===================================
def build_html(path):
    def row(cells, tier, bold_first=True):
        f = FILL.get(tier); a = ACCENT.get(tier, "000000")
        tds = []
        for i, c in enumerate(cells):
            style = f"background:#{f};" if f else ""
            if i == 0 and bold_first: style += f"font-weight:700;color:#{a};"
            elif i > 0: style += "text-align:right;"
            tds.append(f'<td style="{style}">{html.escape(str(c))}</td>')
        return "<tr>" + "".join(tds) + "</tr>"

    def tbl(headers, rows):
        h_ = "".join(f"<th>{html.escape(x)}</th>" for x in headers)
        return f"<table><thead><tr>{h_}</tr></thead><tbody>{''.join(rows)}</tbody></table>"

    legend = "".join(
        f'<span class="chip"><span class="sw" style="background:#{FILL[t]};'
        f'border-color:#{ACCENT[t]}"></span><b style="color:#{ACCENT[t]}">{l}</b> — {m}</span>'
        for t, l, m in LEGEND)

    hosts = "".join(row([h_, i, f"{hr:,.1f}", d,
                         {"ok": "Current", "warn": "5 weeks stale", "crit": "3+ months stale"}[t]], t)
                    for h_, i, hr, d, t in HOSTS)
    heat = "".join(row([f, d, i, f"{hr:,.1f}", f"${c:,}"], t) for f, d, i, hr, c, t in HEAT)
    heat += row(["TOTAL", "", 404, "2,755.0", "$607,760"], "crit")
    sev = "".join(row([s, i, f"{hr:,.1f}", f"{sh}%"], t) for s, i, hr, sh, t in SEV)
    rates = "".join(row([d, f"${r_}", why], t, bold_first=True) for d, r_, why, t in RATES)
    head = "".join(row([m, a, b, c], t) for m, a, b, c, t in
                   [("Debt items", "8", "11", "+3", "info"),
                    ("Effort hours", "96.0", "148.0", "+52.0", "warn"),
                    ("Debt score", "67.50", "115.50", "+48.00", "crit")])
    totals = "".join(row([k, v], t) for k, v, t in
                     [("Open debt items", "404", "warn"), ("Remediation effort", "2,755.0 hours", "warn"),
                      ("Estimated cost", "$607,760", "crit"), ("Blended rate", "$220.60 / hour", "info")])

    # Never name the maintainer lab in a generated, auditor-facing document.
    env_label = os.environ.get("AAC_ENV_LABEL", "<environment>")
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>AAC Technical Debt Heatmap v2.0</title><style>
@page {{ size:A4; margin:16mm 14mm; }}
body {{ font-family:-apple-system,"Helvetica Neue",Arial,sans-serif; font-size:10pt; color:#1a1a1a; line-height:1.45; }}
h1 {{ color:#{NAVY}; border-bottom:4px solid #{NAVY}; padding-bottom:6px; font-size:22pt; margin-bottom:4px; }}
h2 {{ color:#{NAVY}; font-size:13.5pt; margin-top:22px; border-bottom:1px solid #dde3ea; padding-bottom:3px; }}
table {{ border-collapse:collapse; width:100%; margin:10px 0 14px; font-size:9pt; page-break-inside:avoid; }}
th {{ background:#{NAVY}; color:#fff; text-align:left; padding:6px 8px; font-weight:600; }}
td {{ border-bottom:1px solid #e6e6e6; padding:5px 8px; }}
.meta {{ background:#f6f8fa; border-left:4px solid #{STEEL}; padding:9px 12px; font-size:9pt; margin:10px 0 16px; }}
.chip {{ display:inline-block; margin:0 14px 6px 0; font-size:8.5pt; }}
.sw {{ display:inline-block; width:22px; height:11px; border:1.5px solid; border-radius:2px; vertical-align:-1px; margin-right:5px; }}
.callout {{ background:#{GREEN_FILL}; border-left:4px solid #{GREEN}; padding:10px 13px; margin:12px 0; }}
.warnbox {{ background:#{RED_FILL}; border-left:4px solid #{RED}; padding:10px 13px; margin:12px 0; }}
ol li {{ margin-bottom:7px; }} code {{ background:#f2f4f6; padding:1px 4px; border-radius:3px; font-size:8.5pt; }}
.foot {{ color:#{GREY}; font-style:italic; font-size:8.5pt; margin-top:18px; }}
</style></head><body>
<h1>AAC Technical Debt Heatmap</h1>
<div class="meta"><b>Version:</b> v2.0 &nbsp;|&nbsp; <b>Report date:</b> 2026-08-04 &nbsp;|&nbsp;
<b>Environment:</b> {env_label}<br>
<b>Source:</b> AAP job 1900 (template 142) — <code>technical_debt_items</code> where <code>status = 'open'</code><br>
<b>Authors:</b> Tim Coulter; Claude (Anthropic)</div>
<h2>Colour key</h2><div>{legend}</div>
<h2>1. Scope and freshness — read first</h2>
<p><b>Only one of seven hosts is currently assessed.</b> The rest carry data between five weeks and
3.5 months old, and three are ephemeral container-ID hostnames that may no longer exist. The
portfolio total is the sum of each host's most recent assessment — it is <b>not</b> a statement of
present-day posture.</p>
{tbl(["Host","Open items","Effort (h)","Last assessed","Freshness"], [hosts])}
<p>Two tables measure different populations. This report uses <code>technical_debt_items</code>
filtered to <code>status='open'</code> — the same source the Grafana <i>Technical Debt Heatmap</i>
queries — so document and dashboard agree. Totals from <code>technical_debt_summary</code> differ
and are not comparable.</p>
<h2>2. Headline — the debt score rose because measurement improved</h2>
{tbl(["Metric","2026-07-28","2026-08-04","Change"], [head])}
<div class="callout"><b style="color:#{GREEN}">This increase is a measurement improvement, not a
posture regression.</b> Nothing on the host got worse. On 2026-08-04 three classes of false
compliance were corrected in the policy library:
<ul><li>Every registered CIS framework key returned an empty result (<code>{{}}</code>) through the
Generic Framework Assessment path; assessments recorded empty rows while reporting success.</li>
<li>CIS Amazon Linux 2023 imported a package prefix that did not exist, so it reported <b>100%
compliant on any input</b>, including no input at all.</li>
<li>Seven benchmarks failed <b>open</b> on missing facts, reporting 69–99% compliance for
assessments that evaluated nothing.</li></ul>
Those paths now fail closed. Debt that was previously invisible is now counted, so the score rose.
<b>A falling debt score achieved by not measuring is worse than a rising one that is honest.</b>
Expect a further one-time rise as the remaining six hosts are re-assessed.</div>
<h2>3. Portfolio totals (open items)</h2>
{tbl(["Measure","Value"], [totals])}
<p>Cost is computed per item from <code>remediation_rates</code> via the standard <code>LATERAL
JOIN</code> on <code>debt_category</code> — no rate is hardcoded.</p>
<h2>4. Heatmap — framework &times; domain</h2>
{tbl(["Framework","Domain","Items","Hours","Cost (USD)"], [heat])}
<p><b>Digital Sovereignty is 74% of total exposure</b> on 28% of the items — a scope decision, not
an accumulation of small fixes. <b>CIS RHEL 9 is the volume driver</b> (65% of findings, 18% of
cost, ~1.95 h each) and the best automation candidate. <b>OT carries a rate premium</b> — NERC-CIP
and AMI are 15 items / 180 h but cost $51,300, more than the 91-item CIS security tier.</p>
<h2>5. Severity distribution</h2>
{tbl(["Severity","Items","Hours","Share of effort"], [sev])}
<p>CRITICAL averages 13.1 hours per item against HIGH's 6.0 — the critical tier is not just more
urgent, it is individually more expensive to close.</p>
<h2>6. Rate card</h2>
{tbl(["Domain","Rate (USD/h)","Rationale"], [rates])}
<h2>7. Budget comparison — no data</h2>
<div class="warnbox"><b style="color:#{RED}">remediation_budgets contains 0 rows.</b> The OT/IT
budget-separation capability exists in schema and the domain groupings are defined, but no budget
figures have been loaded. Budget-versus-debt analysis is unavailable in this report rather than
estimated.</div>
<h2>8. Recommended sequence</h2><ol>
<li><b style="color:#{RED}">Re-assess the six stale hosts.</b> Until they are re-run against the
corrected policy library the figures above understate real debt — the same false-compliance defects
that hid 52 hours on <code>localhost</code> were active during those assessments. Highest-value
next action; it changes every number in this report.</li>
<li><b style="color:#{AMBER}">Retire the ephemeral hostnames.</b> Three entries are container IDs.
If those workloads are gone, their 192 hours are phantom debt inflating the total.</li>
<li><b style="color:#{AMBER}">Take a scope decision on Digital Sovereignty.</b> At $448,200 it is
74% of exposure and warrants an explicit in-scope / deferred call.</li>
<li><b style="color:#{STEEL}">Automate the CIS RHEL 9 tier.</b> 261 items at ~1.95 hours each is
the best candidate for bulk remediation via existing Ansible roles.</li>
<li><b style="color:#{GREEN}">Load remediation_budgets</b> so funding gaps can be reported rather
than inferred.</li></ol>
<h2>Document control</h2>
<table><tbody>
<tr><td><b>Version</b></td><td>v2.0 — adds colour-coded criticality banding (v1.0 was monochrome)</td></tr>
<tr><td><b>Source job</b></td><td>AAP job 1900 (template 142)</td></tr>
<tr><td><b>Data scope</b></td><td><code>technical_debt_items</code> where <code>status = 'open'</code></td></tr>
<tr><td><b>Authors</b></td><td>Tim Coulter; Claude (Anthropic)</td></tr>
</tbody></table>
<p class="foot">Figures reflect the lab environment and are illustrative of method, not a customer
posture statement.</p>
</body></html>"""
    open(path, "w", encoding="utf-8").write(doc)
    print("  HTML ->", path)

if __name__ == "__main__":
    out = os.path.expanduser("~/Downloads")
    build_docx(f"{out}/aac_technical_debt_heatmap-v2.0.docx")
    build_html("/tmp/aac_technical_debt_heatmap.html")
