#!/usr/bin/env python3
"""
generate_nerc_cip_docx.py — NERC-CIP Audit Report Google Docs–compatible DOCX generator
Reads the same JSON data file as the PDF generator; writes a .docx suitable for
upload to Google Drive (File → Open with Google Docs).
"""

import sys
import json
import argparse
from datetime import datetime

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# ── Colour palette ─────────────────────────────────────────────────────────────
RED       = RGBColor(0xEE, 0x00, 0x00)   # Red Hat red
DARK      = RGBColor(0x1A, 0x1A, 0x1A)
MID       = RGBColor(0x4A, 0x4A, 0x4A)
GREEN     = RGBColor(0x2E, 0x7D, 0x32)
ORANGE    = RGBColor(0xC0, 0x70, 0x00)
RED_FAIL  = RGBColor(0xCC, 0x00, 0x00)
BLUE      = RGBColor(0x00, 0x66, 0xCC)
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
HDRBACK   = RGBColor(0x2C, 0x2C, 0x2C)
ROWALT    = RGBColor(0xF5, 0xF5, 0xF5)


# ── XML helpers ────────────────────────────────────────────────────────────────

def set_cell_bg(cell, hex_color: str):
    """Set table cell background colour (hex without #)."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def set_row_bg(row, hex_color: str):
    for cell in row.cells:
        set_cell_bg(cell, hex_color)


def cell_para(cell, text, bold=False, color=None, align=WD_ALIGN_PARAGRAPH.LEFT,
              font_size=10, italic=False):
    """Clear a cell and write a single paragraph with given style."""
    cell.paragraphs[0].clear()
    p = cell.paragraphs[0]
    p.alignment = align
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(font_size)
    if color:
        run.font.color.rgb = color
    else:
        run.font.color.rgb = DARK
    return p


def add_section_heading(doc, number, title, level=1):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(f'{number}. {title}')
    run.bold = True
    run.font.size = Pt(14 if level == 1 else 11)
    run.font.color.rgb = RED
    return p


def add_subsection(doc, title):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(11)
    run.font.color.rgb = DARK
    return p


def add_body(doc, text, italic=False, color=None):
    p = doc.add_paragraph(style='Normal')
    p.paragraph_format.space_after = Pt(5)
    run = p.add_run(text)
    run.font.size = Pt(10)
    run.italic = italic
    run.font.color.rgb = color or DARK
    return p


def add_hr(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    pPr = p._p.get_or_add_pPr()
    pb = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '6')
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), 'CCCCCC')
    pb.append(bottom)
    pPr.append(pb)
    return p


def set_col_widths(table, widths_inches):
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            if i < len(widths_inches):
                cell.width = Inches(widths_inches[i])


def header_row(table, labels, widths=None):
    """Style the first row of a table as a dark header."""
    row = table.rows[0]
    set_row_bg(row, '2C2C2C')
    for i, label in enumerate(labels):
        cell_para(row.cells[i], label, bold=True, color=WHITE,
                  align=WD_ALIGN_PARAGRAPH.CENTER, font_size=9)
    if widths:
        set_col_widths(table, widths)


# ── Page setup ─────────────────────────────────────────────────────────────────

def page_setup(doc):
    section = doc.sections[0]
    section.page_width  = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin    = Inches(0.85)
    section.bottom_margin = Inches(0.75)
    section.left_margin   = Inches(0.9)
    section.right_margin  = Inches(0.9)


# ── Cover ──────────────────────────────────────────────────────────────────────

def build_cover(doc, data):
    org     = data.get('organization', 'Example Utility Co.')
    adate   = data.get('assessment_date', 'N/A')
    gen     = data.get('generated', datetime.now().strftime('%Y-%m-%d %H:%M UTC'))
    overall = data.get('overall_status', 'COMPLIANT')
    assessor = data.get('assessor', 'Compliance Team')
    illustrative = bool(data.get('illustrative', False))

    for _ in range(3):
        doc.add_paragraph()

    # Illustrative-sample banner (only when the data is not a real assessment)
    if illustrative:
        b = doc.add_table(rows=1, cols=1)
        b.alignment = WD_TABLE_ALIGNMENT.CENTER
        set_cell_bg(b.cell(0, 0), 'C07000')
        cell_para(b.cell(0, 0),
                  'ILLUSTRATIVE SAMPLE — demonstration of AAC report output. '
                  'Not an official compliance record or regulatory submission.',
                  bold=True, color=WHITE, align=WD_ALIGN_PARAGRAPH.CENTER, font_size=10)
        b.cell(0, 0).width = Inches(6.5)
        doc.add_paragraph()

    # Title block
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run('NERC-CIP')
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = RED

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run('Critical Infrastructure Protection')
    run.bold = True
    run.font.size = Pt(26)
    run.font.color.rgb = DARK

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run('Compliance Audit Report')
    run.font.size = Pt(18)
    run.font.color.rgb = MID

    doc.add_paragraph()
    add_hr(doc)

    # Status badge (table with colored cell)
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    badge_hex = _status_hex(overall)
    badge_text = ('✓  ' if _status_is_ok(overall) else '✗  ') + _status_label(overall)
    set_cell_bg(t.cell(0, 0), badge_hex)
    c = cell_para(t.cell(0, 0), badge_text, bold=True, color=WHITE,
                  align=WD_ALIGN_PARAGRAPH.CENTER, font_size=16)
    t.cell(0, 0).width = Inches(3)
    doc.add_paragraph()

    # Meta table
    meta = [
        ('Organization',  org),
        ('Assessment Date', adate),
        ('Standards',     'NERC CIP-002 through CIP-015 (Version 7)'),
        ('Assessor',      assessor),
        ('Generated',     gen),
    ]
    t2 = doc.add_table(rows=len(meta), cols=2)
    t2.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (k, v) in enumerate(meta):
        bg = 'FFFFFF' if i % 2 == 0 else 'F5F5F5'
        set_row_bg(t2.rows[i], bg)
        cell_para(t2.cell(i, 0), k, bold=True, color=MID, font_size=10)
        cell_para(t2.cell(i, 1), v, font_size=10)
    set_col_widths(t2, [2.0, 4.5])

    doc.add_paragraph()
    add_hr(doc)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if illustrative:
        disc = ('ILLUSTRATIVE SAMPLE using demonstration data. This document shows the '
                'format of an AAC-generated NERC-CIP audit report and does not represent '
                'an actual compliance assessment or a regulatory submission.')
    else:
        disc = ('CONFIDENTIAL — Prepared for regulatory submission to NERC/regional entity. '
                'Distribution restricted to authorized compliance personnel.')
    run = p.add_run(disc)
    run.italic = True
    run.font.size = Pt(8)
    run.font.color.rgb = MID

    doc.add_page_break()


# ── Table of Contents ──────────────────────────────────────────────────────────

def build_toc(doc):
    add_section_heading(doc, '', 'Table of Contents')
    add_hr(doc)
    toc = [
        ('1.', 'Executive Summary'),
        ('2.', 'Scope and Methodology'),
        ('3.', 'BES Cyber Systems Assessed'),
        ('4.', 'AMI Smart Meter Infrastructure'),
        ('5.', 'CIP Standards Compliance Results'),
        ('6.', 'CIP-015 Internal Network Security Monitoring'),
        ('7.', 'Control Evidence Detail'),
        ('8.', 'Findings and Violations'),
        ('9.', 'Remediation Status'),
        ('10.', 'Auditor Certification'),
    ]
    for num, title in toc:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent = Inches(0.2)
        r = p.add_run(f'{num}    {title}')
        r.font.size = Pt(10)
        r.font.color.rgb = DARK
    doc.add_page_break()


# ── Executive Summary ──────────────────────────────────────────────────────────

def build_executive_summary(doc, data):
    overall    = data.get('overall_status', 'COMPLIANT')
    cip_pct    = float(data.get('cip_score', 100.0))
    cip015_pct = float(data.get('cip015_score', 100.0))
    n_systems  = int(data.get('bes_systems_count', 3))
    n_viols    = int(data.get('violation_count', 0))
    org        = data.get('organization', 'Example Utility Co.')
    adate      = data.get('assessment_date', 'N/A')

    add_section_heading(doc, '1', 'Executive Summary')
    add_hr(doc)
    add_body(doc,
        f'{org} conducted a comprehensive NERC Critical Infrastructure Protection (CIP) '
        f'compliance assessment on {adate}. This assessment evaluated compliance with '
        f'CIP-002 through CIP-015 (Version 7) across {n_systems} BES Cyber Systems. '
        f'Assessment was performed using automated policy-as-code evaluation via '
        f'Open Policy Agent (OPA) with Ansible Automation Platform (AAP).')

    # KPI table
    kpi_labels = ['Overall Status', 'CIP-002–013 Score', 'CIP-015 INSM Score',
                  'Open Violations', 'BES Systems']
    kpi_values = [
        (_status_label(overall), _status_hex(overall)),
        (f'{cip_pct:.1f}%', '0066CC'),
        (f'{cip015_pct:.1f}%', '0066CC'),
        (str(n_viols), '2E7D32' if n_viols == 0 else 'CC0000'),
        (str(n_systems), '2C2C2C'),
    ]

    t = doc.add_table(rows=2, cols=5)
    set_row_bg(t.rows[0], '2C2C2C')
    for i, label in enumerate(kpi_labels):
        cell_para(t.cell(0, i), label, bold=True, color=WHITE,
                  align=WD_ALIGN_PARAGRAPH.CENTER, font_size=9)
    for i, (val, hex_c) in enumerate(kpi_values):
        set_cell_bg(t.cell(1, i), hex_c)
        cell_para(t.cell(1, i), val, bold=True, color=WHITE,
                  align=WD_ALIGN_PARAGRAPH.CENTER, font_size=13)
    set_col_widths(t, [1.3] * 5)
    doc.add_paragraph()

    conclusion = (
        f'Based on this assessment, {org} is '
        f'{("in compliance" if overall == "COMPLIANT" else ("in substantial compliance" if overall == "SUBSTANTIALLY_COMPLIANT" else "not in compliance"))} '
        f'with applicable NERC CIP reliability standards. '
        + ('No violations were identified during this assessment period.'
           if n_viols == 0 else
           f'{n_viols} violation(s) were identified and are detailed in Section 8.')
    )
    add_body(doc, conclusion)
    doc.add_page_break()


# ── Scope ──────────────────────────────────────────────────────────────────────

def build_scope(doc):
    add_section_heading(doc, '2', 'Scope and Methodology')
    add_hr(doc)
    add_subsection(doc, 'Assessment Scope')
    add_body(doc,
        "This assessment covers all BES Cyber Systems identified in the organization's "
        "CIP-002 categorization, evaluated against the following NERC CIP reliability standards:")

    standards = [
        ('CIP-002-5.1a', 'BES Cyber System Categorization'),
        ('CIP-003-8',    'Security Management Controls'),
        ('CIP-004-6',    'Personnel and Training'),
        ('CIP-005-6',    'Electronic Security Perimeters'),
        ('CIP-006-6',    'Physical Security of BES Cyber Systems'),
        ('CIP-007-6',    'Systems Security Management'),
        ('CIP-008-6',    'Incident Reporting and Response Planning'),
        ('CIP-009-6',    'Recovery Plans for BES Cyber Systems'),
        ('CIP-010-4',    'Configuration Change Management and Vulnerability Management'),
        ('CIP-011-3',    'Information Protection'),
        ('CIP-012-1',    'Communications between Control Centers'),
        ('CIP-013-2',    'Supply Chain Risk Management'),
        ('CIP-014-3',    'Physical Security (Transmission Stations)'),
        ('CIP-015-1',    'Internal Network Security Monitoring (INSM)'),
    ]
    t = doc.add_table(rows=len(standards) + 1, cols=2)
    header_row(t, ['Standard', 'Title'], widths=[1.8, 4.7])
    for i, (std, title) in enumerate(standards):
        bg = 'FFFFFF' if i % 2 == 0 else 'F5F5F5'
        set_row_bg(t.rows[i + 1], bg)
        cell_para(t.cell(i + 1, 0), std, bold=True, font_size=9)
        cell_para(t.cell(i + 1, 1), title, font_size=9)

    doc.add_paragraph()
    add_subsection(doc, 'Methodology')
    add_body(doc,
        'Compliance was evaluated using policy-as-code methodology with Open Policy Agent '
        '(OPA) version 0.60+, executing Rego v1 policies against collected system and '
        'configuration facts. Evidence was gathered via Ansible Automation Platform (AAP) 2.7 '
        'using authenticated connections to managed systems. All assessment data is stored in '
        'PostgreSQL with full audit trail and timestamp.')
    doc.add_page_break()


# ── BES Systems ────────────────────────────────────────────────────────────────

def build_bes_systems(doc, data):
    bes_systems = data.get('bes_systems', [])
    add_section_heading(doc, '3', 'BES Cyber Systems Assessed')
    add_hr(doc)
    add_body(doc,
        f'The following {len(bes_systems)} BES Cyber System(s) were assessed during this evaluation period:')

    t = doc.add_table(rows=len(bes_systems) + 1, cols=4)
    header_row(t, ['System Name', 'CIP-002 Category', 'Impact Level', 'Location'],
               widths=[2.1, 2.5, 1.1, 0.8])
    for i, sys in enumerate(bes_systems):
        bg = 'FFFFFF' if i % 2 == 0 else 'F5F5F5'
        set_row_bg(t.rows[i + 1], bg)
        impact = sys.get('impact', 'HIGH')
        impact_color = RED_FAIL if impact == 'HIGH' else ORANGE
        cell_para(t.cell(i + 1, 0), sys.get('name', ''), font_size=9)
        cell_para(t.cell(i + 1, 1), sys.get('cip002_cat', ''), font_size=9)
        cell_para(t.cell(i + 1, 2), impact, bold=True, color=impact_color,
                  align=WD_ALIGN_PARAGRAPH.CENTER, font_size=9)
        cell_para(t.cell(i + 1, 3), sys.get('location', ''), font_size=9)
    doc.add_page_break()


# ── AMI Smart Meters ───────────────────────────────────────────────────────────

def build_ami_meters(doc, data):
    add_section_heading(doc, '4', 'AMI Smart Meter Infrastructure')
    add_hr(doc)
    add_body(doc,
        'The following Advanced Metering Infrastructure (AMI) smart meter simulators were '
        'assessed as part of this audit. Three utility types — Electric, Gas, and Water — '
        'each operate 10 smart meter devices (30 devices total). Compliance was evaluated '
        'against NIST IR 7628 Rev 1, AMI Device Compliance (ANSI C12.22 / IEC 62351), '
        'and AMI Head-End Security frameworks.')

    add_subsection(doc, 'Compliance Summary by Utility')

    ami_results = data.get('ami_results', [])
    utility_rows = {}
    for row in ami_results:
        u = row.get('utility', 'unknown')
        if u not in utility_rows:
            utility_rows[u] = {}
        utility_rows[u][row.get('policy_name', '')] = row

    ami_devices = data.get('ami_devices') or {}
    per_device_viols = data.get('ami_per_device_violations') or {}

    t = doc.add_table(rows=4, cols=6)
    header_row(t, ['Utility', 'NIST IR 7628', 'Device Compliance', 'Head-End Security',
                   'Devices', 'Avg Score'], widths=[0.9, 1.2, 1.4, 1.4, 0.7, 0.95])
    for ri, utility in enumerate(['electric', 'gas', 'water']):
        rows = utility_rows.get(utility, {})
        n_devices = len(ami_devices.get(utility, []))
        nist   = float(rows.get('AMI NIST IR 7628 Rev 1', {}).get('compliance_percentage', 0))
        device = float(rows.get('AMI Device Compliance', {}).get('compliance_percentage', 0))
        headend = float(rows.get('AMI Head-End Security', {}).get('compliance_percentage', 0))
        avg = (nist + device + headend) / 3

        def pct_color(v):
            return GREEN if v >= 90 else (ORANGE if v >= 70 else RED_FAIL)

        bg = 'FFFFFF' if ri % 2 == 0 else 'F5F5F5'
        set_row_bg(t.rows[ri + 1], bg)
        cell_para(t.cell(ri + 1, 0), utility.capitalize(), bold=True, font_size=9)
        for ci, (val, col) in enumerate([(nist, pct_color(nist)),
                                          (device, pct_color(device)),
                                          (headend, pct_color(headend)),
                                          (n_devices, DARK),
                                          (avg, pct_color(avg))]):
            text = f'{val:.0f}%' if ci != 3 else (str(n_devices) if n_devices else '—')
            cell_para(t.cell(ri + 1, ci + 1), text, bold=(ci != 3), color=col,
                      align=WD_ALIGN_PARAGRAPH.CENTER, font_size=9)

    doc.add_paragraph()
    add_subsection(doc, 'Device Compliance Detail')
    # Per-device rows are rendered ONLY when the caller supplies real device
    # records (data['ami_devices'] / data['ami_per_device_violations']). The
    # stored AMI result is an aggregate percentage per utility; device IDs,
    # firmware, ports and findings cannot be derived from it and are never
    # synthesised here — an audit report must not contain invented evidence.
    if not ami_devices:
        add_body(doc,
            'Per-device detail is not available in this data set: the stored AMI Device '
            'Compliance result is an aggregate score per utility. The scores above are the '
            'assessment evidence; device-level findings require the per-device results from '
            'the AMI assessment run to be supplied with the report data.',
            italic=True, color=MID)
        doc.add_page_break()
        return

    add_body(doc,
        'Per-device findings from the Device Compliance assessment (ANSI C12.22 / IEC 62351). '
        'Devices with no findings are compliant.',
        italic=True)

    for utility in ['electric', 'gas', 'water']:
        rows = utility_rows.get(utility, {})
        dev_row = rows.get('AMI Device Compliance', {})
        dev_pct  = float(dev_row.get('compliance_percentage', 0))
        devices = ami_devices.get(utility, [])
        util_viols = per_device_viols.get(utility, {})
        counts = ''
        if 'passed_controls' in dev_row or 'failed_controls' in dev_row:
            counts = (f'  ({int(dev_row.get("passed_controls", 0))} compliant, '
                      f'{int(dev_row.get("failed_controls", 0))} non-compliant)')

        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(3)
        run = p.add_run(f'{utility.capitalize()} Meters  —  Score: {dev_pct:.0f}%{counts}')
        run.bold = True
        run.font.size = Pt(10)
        run.font.color.rgb = BLUE

        if not devices:
            add_body(doc, 'No per-device records supplied for this utility.', italic=True, color=MID)
            continue

        t = doc.add_table(rows=len(devices) + 1, cols=5)
        header_row(t, ['Device ID', 'Firmware', 'Port', 'Status', 'Findings'],
                   widths=[1.4, 0.75, 0.55, 0.6, 3.2])

        for i, meter in enumerate(devices):
            mid  = meter.get('meter_id', '')
            fw   = meter.get('firmware_version', 'N/A')
            port = str(meter.get('port', 'N/A'))
            viols = util_viols.get(mid, [])
            has_viols = bool(viols)
            status_text = 'FAIL' if has_viols else 'PASS'
            status_color = RED_FAIL if has_viols else GREEN
            finding_text = ' | '.join(viols) if viols else 'No findings'

            bg = 'FFF8F8' if has_viols else ('FFFFFF' if i % 2 == 0 else 'F5F5F5')
            set_row_bg(t.rows[i + 1], bg)
            cell_para(t.cell(i + 1, 0), mid, bold=True, font_size=9)
            cell_para(t.cell(i + 1, 1), fw, font_size=9, align=WD_ALIGN_PARAGRAPH.CENTER)
            cell_para(t.cell(i + 1, 2), port, font_size=9, align=WD_ALIGN_PARAGRAPH.CENTER)
            cell_para(t.cell(i + 1, 3), status_text, bold=True, color=status_color,
                      align=WD_ALIGN_PARAGRAPH.CENTER, font_size=9)
            cell_para(t.cell(i + 1, 4), finding_text, font_size=8,
                      color=RED_FAIL if has_viols else MID)

        doc.add_paragraph()

    doc.add_page_break()


# ── CIP Results ────────────────────────────────────────────────────────────────

def build_cip_results(doc, data):
    reqs = data.get('requirements', {})
    cip_score = float(data.get('cip_score', 100.0))

    add_section_heading(doc, '5', 'CIP Standards Compliance Results')
    add_hr(doc)

    p = doc.add_paragraph()
    r = p.add_run(f'Overall CIP-002 through CIP-012 Compliance Score: ')
    r.font.size = Pt(10)
    r2 = p.add_run(f'{cip_score:.1f}%')
    r2.bold = True
    r2.font.size = Pt(10)
    r2.font.color.rgb = GREEN if cip_score >= 90 else RED_FAIL

    cip_standards = [
        ('CIP-002', 'BES Cyber System Categorization',
         'Identification and categorization of BES Cyber Systems',
         reqs.get('CIP_002_categorization', True)),
        ('CIP-003', 'Security Management Controls',
         'Minimum security management controls to protect BES Cyber Systems',
         reqs.get('CIP_003_security_management', True)),
        ('CIP-004', 'Personnel and Training',
         'Personnel risk assessment, training, and access management',
         reqs.get('CIP_004_personnel_training', True)),
        ('CIP-005', 'Electronic Security Perimeters',
         'Define and protect the Electronic Security Perimeter(s)',
         reqs.get('CIP_005_electronic_security', True)),
        ('CIP-006', 'Physical Security',
         'Physical security controls for BES Cyber Systems',
         reqs.get('CIP_006_physical_security', True)),
        ('CIP-007', 'Systems Security Management',
         'Ports and services, patch management, malicious code prevention',
         reqs.get('CIP_007_systems_security', True)),
        ('CIP-008', 'Incident Reporting and Response',
         'Incident response and reporting to E-ISAC',
         reqs.get('CIP_008_incident_response', True)),
        ('CIP-009', 'Recovery Plans',
         'Recovery plans, plan testing, and lessons learned',
         reqs.get('CIP_009_recovery_plans', True)),
        ('CIP-010', 'Configuration Change Management',
         'Configuration baseline, change management, vulnerability assessment',
         reqs.get('CIP_010_configuration_management', True)),
        ('CIP-011', 'Information Protection',
         'BES Cyber System Information protection and storage/transit encryption',
         reqs.get('CIP_011_information_protection', True)),
        ('CIP-012', 'Communications Protection',
         'Protection of communications between control centers',
         reqs.get('CIP_012_communications_protection', True)),
    ]

    t = doc.add_table(rows=len(cip_standards) + 1, cols=4)
    header_row(t, ['Standard', 'Title', 'Requirement Description', 'Status'],
               widths=[0.75, 1.5, 3.5, 0.85])
    for i, (std, title, desc, compliant) in enumerate(cip_standards):
        bg = 'FFFFFF' if i % 2 == 0 else 'F5F5F5'
        set_row_bg(t.rows[i + 1], bg)
        cell_para(t.cell(i + 1, 0), std, bold=True, font_size=9)
        cell_para(t.cell(i + 1, 1), title, font_size=9)
        cell_para(t.cell(i + 1, 2), desc, font_size=8, color=MID)
        status_text = 'COMPLIANT' if compliant else 'NON-COMPLIANT'
        cell_para(t.cell(i + 1, 3), status_text, bold=True,
                  color=GREEN if compliant else RED_FAIL,
                  align=WD_ALIGN_PARAGRAPH.CENTER, font_size=8)
    doc.add_page_break()


# ── CIP-015 ────────────────────────────────────────────────────────────────────

def build_cip015(doc, data):
    cip015 = data.get('cip015', {})
    score  = float(cip015.get('score', 100.0))
    reqs15 = cip015.get('requirements', {
        'R1_insm_categorization': True,
        'R2_insm_implementation': True,
        'R3_documentation_management': True,
    })

    add_section_heading(doc, '6', 'CIP-015 Internal Network Security Monitoring')
    add_hr(doc)
    add_body(doc,
        'CIP-015-1 establishes requirements for Internal Network Security Monitoring (INSM) '
        'of high-impact BES Cyber Systems and their associated Electronic Security Perimeters.')

    reqs_list = [
        ('R1', 'INSM Categorization',
         'Identify and categorize assets requiring INSM',
         reqs15.get('R1_insm_categorization', True)),
        ('R2', 'INSM Implementation',
         'Deploy and operate INSM capabilities',
         reqs15.get('R2_insm_implementation', True)),
        ('R3', 'Documentation Management',
         'Maintain and review INSM documentation',
         reqs15.get('R3_documentation_management', True)),
    ]

    t = doc.add_table(rows=len(reqs_list) + 1, cols=3)
    header_row(t, ['Requirement', 'Description', 'Status'],
               widths=[0.8, 5.0, 0.85])
    for i, (req, title, desc, compliant) in enumerate(reqs_list):
        bg = 'FFFFFF' if i % 2 == 0 else 'F5F5F5'
        set_row_bg(t.rows[i + 1], bg)
        cell_para(t.cell(i + 1, 0), req, bold=True, font_size=10)
        cell_para(t.cell(i + 1, 1), f'{title} — {desc}', font_size=9)
        status_text = 'COMPLIANT' if compliant else 'NON-COMPLIANT'
        cell_para(t.cell(i + 1, 2), status_text, bold=True,
                  color=GREEN if compliant else RED_FAIL,
                  align=WD_ALIGN_PARAGRAPH.CENTER, font_size=9)

    doc.add_paragraph()
    p = doc.add_paragraph()
    r = p.add_run(f'CIP-015 Overall Score: ')
    r.font.size = Pt(10)
    r2 = p.add_run(f'{score:.1f}%')
    r2.bold = True
    r2.font.size = Pt(10)
    r2.font.color.rgb = GREEN if score >= 90 else RED_FAIL
    doc.add_page_break()


# ── Evidence ───────────────────────────────────────────────────────────────────

def build_evidence(doc, data):
    illustrative = bool(data.get('illustrative', False))
    add_section_heading(doc, '7', 'Control Evidence Detail')
    add_hr(doc)
    add_body(doc,
        'The following automated evidence categories were collected to support compliance '
        'assertions. Evidence is gathered via AAP 2.7 with authenticated connections, '
        'evaluated against Rego v1 policies in OPA, and persisted to PostgreSQL with timestamps.')
    if illustrative:
        add_body(doc,
            'Note: the entries below are illustrative evidence categories with sample '
            'findings; they do not represent verified results from an actual assessment.',
            italic=True, color=ORANGE)

    # Prefer evidence supplied in the dataset; otherwise use generic capability
    # statements (no fabricated calendar dates) so the section never asserts specifics
    # that were not actually observed.
    default_items = [
        ('BES Cyber System Inventory', 'CIP-002', 'Asset register reconciled against the OT asset database; systems categorized per R1 methodology.'),
        ('Access Control Review',       'CIP-004', 'Identity store and role-based access reviewed; unauthorized accounts flagged if present.'),
        ('Electronic Security Perimeter','CIP-005', 'Firewall rules and ESP boundaries evaluated via configuration baseline comparison.'),
        ('Patch Management Status',     'CIP-007', 'Patch currency evaluated against the 35-day requirement.'),
        ('Malicious Code Prevention',   'CIP-007', 'Endpoint/runtime protection deployment and signature currency evaluated.'),
        ('Incident Response Plan',      'CIP-008', 'IRP review/test recency evaluated against the 15-month requirement.'),
        ('Recovery Plan Test',          'CIP-009', 'Recovery plan test recency and RTO objectives evaluated.'),
        ('Configuration Baseline',      'CIP-010', 'Baseline currency evaluated; unauthorized configuration drift flagged if detected.'),
        ('Information Classification',  'CIP-011', 'BCSI inventory and encryption at rest/in transit evaluated.'),
        ('Control Center Comms',        'CIP-012', 'Encrypted communications between control centers evaluated.'),
        ('INSM Sensor Coverage',        'CIP-015', 'INSM sensor coverage of High Impact BES Cyber Systems evaluated.'),
        ('INSM Alert Review',           'CIP-015', 'INSM alert-review process and retention configuration evaluated.'),
    ]
    supplied = data.get('evidence_items')
    if supplied:
        evidence_items = [(i.get('item', ''), i.get('standard', ''),
                           i.get('finding', ''), i.get('result', 'EVALUATED'))
                          for i in supplied]
    else:
        result_label = 'SAMPLE' if illustrative else 'EVALUATED'
        evidence_items = [(item, std, finding, result_label)
                          for item, std, finding in default_items]

    t = doc.add_table(rows=len(evidence_items) + 1, cols=4)
    header_row(t, ['Evidence Item', 'Std', 'Finding', 'Result'],
               widths=[1.6, 0.6, 3.75, 0.65])
    for i, (item, std, finding, result) in enumerate(evidence_items):
        bg = 'FFFFFF' if i % 2 == 0 else 'F5F5F5'
        set_row_bg(t.rows[i + 1], bg)
        cell_para(t.cell(i + 1, 0), item, bold=True, font_size=9)
        cell_para(t.cell(i + 1, 1), std, align=WD_ALIGN_PARAGRAPH.CENTER, font_size=9)
        cell_para(t.cell(i + 1, 2), finding, font_size=8, color=MID)
        cell_para(t.cell(i + 1, 3), result, bold=True, color=GREEN,
                  align=WD_ALIGN_PARAGRAPH.CENTER, font_size=8)
    doc.add_page_break()


# ── Findings ───────────────────────────────────────────────────────────────────

def build_findings(doc, data):
    violations = data.get('violations', [])
    add_section_heading(doc, '8', 'Findings and Violations')
    add_hr(doc)

    if not violations:
        t = doc.add_table(rows=1, cols=1)
        set_cell_bg(t.cell(0, 0), 'F0FFF0')
        cell_para(t.cell(0, 0),
                  '✓  No violations identified during this assessment period.',
                  bold=True, color=GREEN, align=WD_ALIGN_PARAGRAPH.CENTER, font_size=11)
        doc.add_paragraph()
        add_body(doc,
            'All NERC CIP requirements evaluated during this assessment period are satisfied. '
            'No potential violations, apparent violations, or confirmed violations were identified.')
    else:
        for i, v in enumerate(violations, 1):
            severity = v.get('severity', 'HIGH')
            hex_c = 'CC0000' if severity == 'HIGH' else 'C07000'
            t = doc.add_table(rows=2, cols=1)
            set_cell_bg(t.cell(0, 0), hex_c)
            cell_para(t.cell(0, 0), f'Finding #{i} — {severity}',
                      bold=True, color=WHITE, font_size=10)
            set_cell_bg(t.cell(1, 0), 'FFF8F8')
            cell_para(t.cell(1, 0), v.get('description', str(v)), font_size=9)
            doc.add_paragraph()

    doc.add_page_break()


# ── Remediation ────────────────────────────────────────────────────────────────

def build_remediation(doc, data):
    violations = data.get('violations', [])
    add_section_heading(doc, '9', 'Remediation Status')
    add_hr(doc)

    if not violations:
        add_body(doc,
            'No remediation actions are required. All identified controls are operating '
            'effectively within the assessment scope.')
    else:
        t = doc.add_table(rows=len(violations) + 1, cols=5)
        header_row(t, ['Finding', 'Standard', 'Remediation Action', 'Target Date', 'Owner'],
                   widths=[0.8, 0.8, 3.1, 0.9, 1.0])
        for i, v in enumerate(violations):
            bg = 'FFFFFF' if i % 2 == 0 else 'F5F5F5'
            set_row_bg(t.rows[i + 1], bg)
            cell_para(t.cell(i + 1, 0), v.get('id', 'N/A'), font_size=9)
            cell_para(t.cell(i + 1, 1), v.get('standard', 'N/A'), font_size=9)
            cell_para(t.cell(i + 1, 2), v.get('remediation', 'TBD'), font_size=9)
            cell_para(t.cell(i + 1, 3), v.get('target_date', 'TBD'),
                      align=WD_ALIGN_PARAGRAPH.CENTER, font_size=9)
            cell_para(t.cell(i + 1, 4), v.get('owner', 'TBD'), font_size=9)

    doc.add_page_break()


# ── Certification ──────────────────────────────────────────────────────────────

def build_certification(doc, data):
    org      = data.get('organization', 'Example Utility Co.')
    assessor = data.get('assessor', 'Compliance Team')
    adate    = data.get('assessment_date', 'N/A')
    gen      = data.get('generated', 'N/A')
    overall  = data.get('overall_status', 'COMPLIANT')

    add_section_heading(doc, '10', 'Auditor Certification')
    add_hr(doc)

    add_body(doc,
        f'I hereby certify that the information contained in this report accurately '
        f'represents the results of the NERC CIP compliance assessment conducted for '
        f'{org} for the assessment period ending {adate}.')
    add_body(doc,
        'This assessment was conducted using automated policy-as-code evaluation '
        'consistent with NERC CIP Version 7 requirements. Evidence is retained in '
        'the compliance management system and is available for regulatory review upon request.')

    doc.add_paragraph()

    # Signature block
    sig_roles = ['Compliance Assessor', 'Compliance Manager', 'CISO / VP Security']
    t = doc.add_table(rows=5, cols=3)
    set_row_bg(t.rows[0], 'F5F5F5')
    for i, role in enumerate(sig_roles):
        cell_para(t.cell(0, i), role, bold=True, font_size=10)
    for row_i in range(1, 5):
        for col_i in range(3):
            if row_i == 1:
                cell_para(t.cell(row_i, col_i), ' ', font_size=14)  # space for signature
            elif row_i == 2:
                cell_para(t.cell(row_i, col_i), '_' * 32, font_size=10)
            elif row_i == 3:
                names = [f'Name: {assessor}', 'Name: ________________________', 'Name: ________________________']
                cell_para(t.cell(row_i, col_i), names[col_i], font_size=9, color=MID)
            else:
                dates = [f'Date: {adate}', 'Date: ________________________', 'Date: ________________________']
                cell_para(t.cell(row_i, col_i), dates[col_i], font_size=9, color=MID)
    set_col_widths(t, [2.2, 2.2, 2.2])

    doc.add_paragraph()

    # System cert table
    cert = [
        ('Platform',       'Ansible Automation Platform 2.7 + Open Policy Agent 0.60+'),
        ('Policy Engine',  'OPA opa-ot container (:8183) — NERC-CIP Rego v1 policies'),
        ('Data Store',     'PostgreSQL 15 — compliance database (compliance_results table)'),
        ('Report Generated', gen),
        ('Overall Status', overall),
    ]
    t2 = doc.add_table(rows=len(cert) + 1, cols=2)
    header_row(t2, ['Assessment System', 'Value'], widths=[2.0, 4.6])
    for i, (k, v) in enumerate(cert):
        bg = 'FFFFFF' if i % 2 == 0 else 'F5F5F5'
        set_row_bg(t2.rows[i + 1], bg)
        cell_para(t2.cell(i + 1, 0), k, font_size=9)
        vcolor = _status_rgb(overall) if k == 'Overall Status' else DARK
        cell_para(t2.cell(i + 1, 1), _status_label(v) if k == 'Overall Status' else v,
                  bold=(k == 'Overall Status'), color=vcolor, font_size=9)


# ── Main ───────────────────────────────────────────────────────────────────────

def _normalize_violations(vs):
    out = []
    for v in (vs or []):
        if isinstance(v, str):
            out.append({'description': v, 'severity': 'HIGH'})
        elif isinstance(v, dict):
            out.append(v)
    return out


def _status_is_ok(s):
    return (s or '').upper() in ('COMPLIANT', 'SUBSTANTIALLY_COMPLIANT')


def _status_label(s):
    return (s or 'COMPLIANT').replace('_', ' ')


def _status_hex(s):
    s = (s or '').upper()
    return '2E7D32' if s == 'COMPLIANT' else ('C07000' if s == 'SUBSTANTIALLY_COMPLIANT' else 'CC0000')


def _status_rgb(s):
    s = (s or '').upper()
    return GREEN if s == 'COMPLIANT' else (ORANGE if s == 'SUBSTANTIALLY_COMPLIANT' else RED_FAIL)


def generate(data, output_path):
    data['violations'] = _normalize_violations(data.get('violations'))
    if isinstance(data.get('cip015'), dict):
        data['cip015']['violations'] = _normalize_violations(data['cip015'].get('violations'))
    doc = Document()
    page_setup(doc)

    # Default normal style
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(10)

    build_cover(doc, data)
    build_toc(doc)
    build_executive_summary(doc, data)
    build_scope(doc)
    build_bes_systems(doc, data)
    build_ami_meters(doc, data)
    build_cip_results(doc, data)
    build_cip015(doc, data)
    build_evidence(doc, data)
    build_findings(doc, data)
    build_remediation(doc, data)
    build_certification(doc, data)

    doc.save(output_path)
    print(f'DOCX generated: {output_path}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', help='Output .docx path')
    parser.add_argument('--data', help='JSON data file (default: stdin)')
    args = parser.parse_args()

    if args.data:
        with open(args.data) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    generate(data, args.output)
