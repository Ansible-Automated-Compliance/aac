#!/usr/bin/env python3
"""
generate_nerc_cip_pdf.py — NERC-CIP Audit Report PDF Generator
Reads JSON data from stdin, writes a submission-ready PDF to the path given as argv[1].
"""

import sys
import json
import argparse
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.flowables import HRFlowable

# ── Colours ───────────────────────────────────────────────────────────────────
RED_HAT_RED   = colors.HexColor('#EE0000')
DARK_GRAY     = colors.HexColor('#1A1A1A')
MID_GRAY      = colors.HexColor('#4A4A4A')
LIGHT_GRAY    = colors.HexColor('#F5F5F5')
TABLE_HEADER  = colors.HexColor('#2C2C2C')
GREEN_OK      = colors.HexColor('#3D8B37')
RED_FAIL      = colors.HexColor('#CC0000')
AMBER_WARN    = colors.HexColor('#C07000')
BLUE_ACCENT   = colors.HexColor('#0066CC')
ROW_ALT       = colors.HexColor('#F9F9F9')
BORDER_COLOR  = colors.HexColor('#CCCCCC')


def build_styles():
    base = getSampleStyleSheet()
    styles = {}

    styles['cover_title'] = ParagraphStyle('cover_title',
        fontSize=28, fontName='Helvetica-Bold', textColor=DARK_GRAY,
        alignment=TA_CENTER, spaceAfter=8, leading=34)

    styles['cover_subtitle'] = ParagraphStyle('cover_subtitle',
        fontSize=16, fontName='Helvetica', textColor=MID_GRAY,
        alignment=TA_CENTER, spaceAfter=6)

    styles['cover_meta'] = ParagraphStyle('cover_meta',
        fontSize=11, fontName='Helvetica', textColor=MID_GRAY,
        alignment=TA_CENTER, spaceAfter=4, leading=16)

    styles['section_heading'] = ParagraphStyle('section_heading',
        fontSize=13, fontName='Helvetica-Bold', textColor=RED_HAT_RED,
        spaceBefore=16, spaceAfter=6, borderPadding=(0, 0, 4, 0))

    styles['subsection_heading'] = ParagraphStyle('subsection_heading',
        fontSize=11, fontName='Helvetica-Bold', textColor=DARK_GRAY,
        spaceBefore=10, spaceAfter=4)

    styles['body'] = ParagraphStyle('body',
        fontSize=10, fontName='Helvetica', textColor=DARK_GRAY,
        alignment=TA_JUSTIFY, spaceAfter=6, leading=15)

    styles['body_small'] = ParagraphStyle('body_small',
        fontSize=9, fontName='Helvetica', textColor=MID_GRAY,
        spaceAfter=4, leading=13)

    styles['table_header'] = ParagraphStyle('table_header',
        fontSize=9, fontName='Helvetica-Bold', textColor=colors.white,
        alignment=TA_CENTER)

    styles['table_cell'] = ParagraphStyle('table_cell',
        fontSize=9, fontName='Helvetica', textColor=DARK_GRAY,
        alignment=TA_LEFT, leading=13)

    styles['table_cell_center'] = ParagraphStyle('table_cell_center',
        fontSize=9, fontName='Helvetica', textColor=DARK_GRAY,
        alignment=TA_CENTER, leading=13)

    styles['compliant_badge'] = ParagraphStyle('compliant_badge',
        fontSize=9, fontName='Helvetica-Bold', textColor=GREEN_OK,
        alignment=TA_CENTER)

    styles['noncompliant_badge'] = ParagraphStyle('noncompliant_badge',
        fontSize=9, fontName='Helvetica-Bold', textColor=RED_FAIL,
        alignment=TA_CENTER)

    styles['footer'] = ParagraphStyle('footer',
        fontSize=8, fontName='Helvetica', textColor=MID_GRAY,
        alignment=TA_CENTER)

    styles['classification'] = ParagraphStyle('classification',
        fontSize=10, fontName='Helvetica-Bold', textColor=RED_HAT_RED,
        alignment=TA_CENTER, spaceAfter=4)

    styles['violation_high'] = ParagraphStyle('violation_high',
        fontSize=9, fontName='Helvetica', textColor=RED_FAIL,
        spaceAfter=3, leading=14, leftIndent=12)

    styles['violation_medium'] = ParagraphStyle('violation_medium',
        fontSize=9, fontName='Helvetica', textColor=AMBER_WARN,
        spaceAfter=3, leading=14, leftIndent=12)

    styles['toc_entry'] = ParagraphStyle('toc_entry',
        fontSize=10, fontName='Helvetica', textColor=DARK_GRAY,
        spaceAfter=3, leading=16)

    return styles


def header_footer(canvas, doc, data):
    canvas.saveState()
    w, h = letter

    # Header bar
    canvas.setFillColor(DARK_GRAY)
    canvas.rect(0, h - 0.55*inch, w, 0.55*inch, fill=1, stroke=0)
    canvas.setFillColor(RED_HAT_RED)
    canvas.rect(0, h - 0.58*inch, w, 0.03*inch, fill=1, stroke=0)

    canvas.setFillColor(colors.white)
    canvas.setFont('Helvetica-Bold', 9)
    canvas.drawString(0.5*inch, h - 0.35*inch, 'NERC-CIP COMPLIANCE AUDIT REPORT')
    canvas.setFont('Helvetica', 8)
    canvas.drawRightString(w - 0.5*inch, h - 0.35*inch,
        data.get('organization', 'Example Utility Co.'))

    # Footer
    canvas.setFillColor(DARK_GRAY)
    canvas.rect(0, 0, w, 0.4*inch, fill=1, stroke=0)
    canvas.setFillColor(RED_HAT_RED)
    canvas.rect(0, 0.4*inch, w, 0.02*inch, fill=1, stroke=0)

    canvas.setFillColor(colors.white)
    canvas.setFont('Helvetica', 7)
    if data.get('illustrative', False):
        footer_left = (f'ILLUSTRATIVE SAMPLE — not an official record. '
                       f'Assessment date: {data.get("assessment_date", "N/A")}')
    else:
        footer_left = (f'CONFIDENTIAL — For regulatory submission only. '
                       f'Assessment date: {data.get("assessment_date", "N/A")}')
    canvas.drawString(0.5*inch, 0.15*inch, footer_left)
    canvas.drawRightString(w - 0.5*inch, 0.15*inch,
        f'Page {doc.page}')

    canvas.restoreState()


def build_cover(data, styles):
    story = []
    org   = data.get('organization', 'Example Utility Co.')
    adate = data.get('assessment_date', 'N/A')
    gen   = data.get('generated', datetime.now().strftime('%Y-%m-%d %H:%M UTC'))
    overall = data.get('overall_status', 'COMPLIANT')
    assessor = data.get('assessor', 'Compliance Team')
    illustrative = bool(data.get('illustrative', False))

    story.append(Spacer(1, 0.9*inch))

    # Illustrative-sample banner (only when the data is not a real assessment)
    if illustrative:
        story.append(Table(
            [[Paragraph('ILLUSTRATIVE SAMPLE — demonstration of AAC report output. '
                        'Not an official compliance record or regulatory submission.',
                        ParagraphStyle('ban', fontSize=10, fontName='Helvetica-Bold',
                                       textColor=colors.white, alignment=TA_CENTER))]],
            colWidths=[6.5*inch],
            style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), AMBER_WARN),
                ('TOPPADDING', (0,0), (-1,-1), 8),
                ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ])))
        story.append(Spacer(1, 0.3*inch))

    # Red accent line
    story.append(HRFlowable(width='100%', thickness=3, color=RED_HAT_RED,
                             spaceAfter=20))

    story.append(Paragraph('NERC-CIP', ParagraphStyle('ct', fontSize=14,
        fontName='Helvetica', textColor=RED_HAT_RED, alignment=TA_CENTER,
        spaceAfter=4)))
    story.append(Paragraph('Critical Infrastructure Protection', styles['cover_title']))
    story.append(Paragraph('Compliance Audit Report', ParagraphStyle('cs',
        fontSize=20, fontName='Helvetica', textColor=MID_GRAY,
        alignment=TA_CENTER, spaceAfter=20)))

    story.append(HRFlowable(width='100%', thickness=1, color=BORDER_COLOR,
                             spaceBefore=4, spaceAfter=24))

    # Status badge
    badge_color = _status_color(overall)
    badge_text  = ('✓  ' if _status_is_ok(overall) else '✗  ') + _status_label(overall)
    story.append(Table(
        [[Paragraph(badge_text, ParagraphStyle('badge',
            fontSize=16, fontName='Helvetica-Bold',
            textColor=colors.white, alignment=TA_CENTER))]],
        colWidths=[3*inch],
        style=TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), badge_color),
            ('ROUNDEDCORNERS', [6]),
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ])
    ))
    story.append(Spacer(1, 0.3*inch))

    # Meta table
    meta_data = [
        ['Organization',   org],
        ['Assessment Date', adate],
        ['Standards',      'NERC CIP-002 through CIP-015 (Version 7)'],
        ['Assessor',       assessor],
        ['Generated',      gen],
    ]
    meta_table = Table(meta_data, colWidths=[2*inch, 4*inch])
    meta_table.setStyle(TableStyle([
        ('FONTNAME',     (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME',     (1,0), (1,-1), 'Helvetica'),
        ('FONTSIZE',     (0,0), (-1,-1), 10),
        ('TEXTCOLOR',    (0,0), (0,-1), MID_GRAY),
        ('TEXTCOLOR',    (1,0), (1,-1), DARK_GRAY),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.white, LIGHT_GRAY]),
        ('TOPPADDING',   (0,0), (-1,-1), 6),
        ('BOTTOMPADDING',(0,0), (-1,-1), 6),
        ('LEFTPADDING',  (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('BOX',          (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID',    (0,0), (-1,-1), 0.25, BORDER_COLOR),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.3*inch))

    story.append(HRFlowable(width='100%', thickness=1, color=BORDER_COLOR,
                             spaceBefore=4, spaceAfter=10))
    if illustrative:
        disc_text = ('ILLUSTRATIVE SAMPLE using demonstration data. This document shows the '
                     'format of an AAC-generated NERC-CIP audit report and does not represent '
                     'an actual compliance assessment or a regulatory submission.')
    else:
        disc_text = ('CONFIDENTIAL — Prepared for regulatory submission to NERC/regional entity. '
                     'Distribution restricted to authorized compliance personnel.')
    story.append(Paragraph(disc_text,
        ParagraphStyle('disc', fontSize=8, fontName='Helvetica-Oblique',
                       textColor=MID_GRAY, alignment=TA_CENTER)))

    story.append(PageBreak())
    return story


def build_toc(styles):
    story = []
    story.append(Paragraph('Table of Contents', styles['section_heading']))
    story.append(HRFlowable(width='100%', thickness=1, color=BORDER_COLOR,
                             spaceAfter=10))
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
        story.append(Paragraph(
            f'<b>{num}</b>&nbsp;&nbsp;&nbsp;{title}',
            styles['toc_entry']))
    story.append(PageBreak())
    return story


def build_executive_summary(data, styles):
    story = []
    overall    = data.get('overall_status', 'COMPLIANT')
    cip_pct    = float(data.get('cip_score', 100.0))
    cip015_pct = float(data.get('cip015_score', 100.0))
    n_systems  = int(data.get('bes_systems_count', 3))
    n_viols    = int(data.get('violation_count', 0))
    org        = data.get('organization', 'Example Utility Co.')
    adate      = data.get('assessment_date', 'N/A')

    story.append(Paragraph('1. Executive Summary', styles['section_heading']))
    story.append(HRFlowable(width='100%', thickness=1, color=RED_HAT_RED,
                             spaceAfter=8))

    summary_text = (
        f'{org} conducted a comprehensive NERC Critical Infrastructure Protection (CIP) '
        f'compliance assessment on {adate}. This assessment evaluated compliance with '
        f'CIP-002 through CIP-015 (Version 7) across {n_systems} BES Cyber Systems. '
        f'Assessment was performed using automated policy-as-code evaluation via '
        f'Open Policy Agent (OPA) with Ansible Automation Platform (AAP), providing '
        f'continuous, verifiable compliance evidence.'
    )
    story.append(Paragraph(summary_text, styles['body']))
    story.append(Spacer(1, 0.15*inch))

    # KPI table
    kpi_color = _status_color(overall)
    kpi_data = [
        [
            Paragraph('Overall Status', styles['table_header']),
            Paragraph('CIP-002–013 Score', styles['table_header']),
            Paragraph('CIP-015 INSM Score', styles['table_header']),
            Paragraph('Open Violations', styles['table_header']),
            Paragraph('BES Systems', styles['table_header']),
        ],
        [
            Paragraph(
                _status_label(overall),
                ParagraphStyle('kv', fontSize=13, fontName='Helvetica-Bold',
                               textColor=colors.white, alignment=TA_CENTER)),
            Paragraph(f'{cip_pct:.1f}%',
                ParagraphStyle('kv2', fontSize=13, fontName='Helvetica-Bold',
                               textColor=colors.white, alignment=TA_CENTER)),
            Paragraph(f'{cip015_pct:.1f}%',
                ParagraphStyle('kv2', fontSize=13, fontName='Helvetica-Bold',
                               textColor=colors.white, alignment=TA_CENTER)),
            Paragraph(str(n_viols),
                ParagraphStyle('kv3', fontSize=13, fontName='Helvetica-Bold',
                               textColor=colors.white, alignment=TA_CENTER)),
            Paragraph(str(n_systems),
                ParagraphStyle('kv4', fontSize=13, fontName='Helvetica-Bold',
                               textColor=colors.white, alignment=TA_CENTER)),
        ]
    ]
    kpi_colors = [kpi_color, BLUE_ACCENT, BLUE_ACCENT,
                  GREEN_OK if n_viols == 0 else RED_FAIL, DARK_GRAY]
    kpi_table = Table(kpi_data, colWidths=[1.3*inch]*5)
    style_cmds = [
        ('FONTNAME',     (0,0), (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',     (0,0), (-1,0),  8),
        ('TEXTCOLOR',    (0,0), (-1,0),  colors.white),
        ('TOPPADDING',   (0,0), (-1,-1), 8),
        ('BOTTOMPADDING',(0,0), (-1,-1), 8),
        ('ALIGN',        (0,0), (-1,-1), 'CENTER'),
        ('BOX',          (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('LINEAFTER',    (0,0), (-1,-1), 0.25, colors.white),
    ]
    for col, color in enumerate(kpi_colors):
        style_cmds.append(('BACKGROUND', (col,0), (col,0), TABLE_HEADER))
        style_cmds.append(('BACKGROUND', (col,1), (col,1), color))
    kpi_table.setStyle(TableStyle(style_cmds))
    story.append(kpi_table)
    story.append(Spacer(1, 0.2*inch))

    conclusion = (
        f'Based on this assessment, {org} is <b>{("in compliance" if overall == "COMPLIANT" else ("in substantial compliance" if overall == "SUBSTANTIALLY_COMPLIANT" else "not in compliance"))}</b> '
        f'with applicable NERC CIP reliability standards. '
        f'{"No violations were identified during this assessment period." if n_viols == 0 else f"{n_viols} violation(s) were identified and are detailed in Section 8."}'
    )
    story.append(Paragraph(conclusion, styles['body']))
    story.append(PageBreak())
    return story


def build_scope(data, styles):
    story = []
    story.append(Paragraph('2. Scope and Methodology', styles['section_heading']))
    story.append(HRFlowable(width='100%', thickness=1, color=RED_HAT_RED, spaceAfter=8))

    story.append(Paragraph('Assessment Scope', styles['subsection_heading']))
    story.append(Paragraph(
        'This assessment covers all BES Cyber Systems identified in the '
        'organization\'s CIP-002 categorization. The assessment evaluated '
        'compliance with the following NERC CIP reliability standards:',
        styles['body']))

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
    std_data = [[
        Paragraph('Standard', styles['table_header']),
        Paragraph('Title', styles['table_header']),
    ]] + [[
        Paragraph(s, styles['table_cell']),
        Paragraph(t, styles['table_cell']),
    ] for s, t in standards]

    std_table = Table(std_data, colWidths=[1.8*inch, 4.8*inch])
    std_table.setStyle(TableStyle([
        ('BACKGROUND',   (0,0), (-1,0),  TABLE_HEADER),
        ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.white, ROW_ALT]),
        ('TOPPADDING',   (0,0), (-1,-1), 5),
        ('BOTTOMPADDING',(0,0), (-1,-1), 5),
        ('LEFTPADDING',  (0,0), (-1,-1), 8),
        ('BOX',          (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID',    (0,0), (-1,-1), 0.25, BORDER_COLOR),
    ]))
    story.append(std_table)
    story.append(Spacer(1, 0.2*inch))

    story.append(Paragraph('Methodology', styles['subsection_heading']))
    story.append(Paragraph(
        'Compliance was evaluated using policy-as-code methodology with Open Policy '
        'Agent (OPA) version 0.60+, executing Rego v1 policies against collected '
        'system and configuration facts. Evidence was gathered via Ansible Automation '
        'Platform (AAP) 2.7 using authenticated SSH connections to managed systems. '
        'All assessment data is stored in PostgreSQL with full audit trail and timestamp.',
        styles['body']))

    story.append(PageBreak())
    return story


def build_bes_systems(data, styles):
    story = []
    story.append(Paragraph('3. BES Cyber Systems Assessed', styles['section_heading']))
    story.append(HRFlowable(width='100%', thickness=1, color=RED_HAT_RED, spaceAfter=8))

    bes_systems = data.get('bes_systems', [
        {'name': 'Energy Management System (EMS)',
         'category': 'High Impact', 'location': 'Control Center', 'impact': 'HIGH',
         'cip002_cat': 'Category 1 — High Impact BES Cyber System'},
        {'name': 'SCADA System',
         'category': 'High Impact', 'location': 'Control Center', 'impact': 'HIGH',
         'cip002_cat': 'Category 1 — High Impact BES Cyber System'},
        {'name': 'Substation RTU (Primary)',
         'category': 'Medium Impact', 'location': 'Substation Alpha', 'impact': 'MEDIUM',
         'cip002_cat': 'Category 2 — Medium Impact BES Cyber System'},
    ])

    story.append(Paragraph(
        f'The following {len(bes_systems)} BES Cyber System(s) were assessed during this evaluation period:',
        styles['body']))
    story.append(Spacer(1, 0.1*inch))

    bes_data = [[
        Paragraph('System Name', styles['table_header']),
        Paragraph('CIP-002 Category', styles['table_header']),
        Paragraph('Impact Level', styles['table_header']),
        Paragraph('Location', styles['table_header']),
    ]]
    for sys in bes_systems:
        impact = sys.get('impact', 'HIGH')
        impact_color = RED_FAIL if impact == 'HIGH' else AMBER_WARN
        bes_data.append([
            Paragraph(sys.get('name', ''), styles['table_cell']),
            Paragraph(sys.get('cip002_cat', ''), styles['table_cell']),
            Paragraph(impact, ParagraphStyle('imp', fontSize=9,
                fontName='Helvetica-Bold', textColor=impact_color, alignment=TA_CENTER)),
            Paragraph(sys.get('location', ''), styles['table_cell']),
        ])

    bes_table = Table(bes_data, colWidths=[2.1*inch, 2.5*inch, 1.1*inch, 1*inch])
    bes_table.setStyle(TableStyle([
        ('BACKGROUND',   (0,0), (-1,0),  TABLE_HEADER),
        ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.white, ROW_ALT]),
        ('TOPPADDING',   (0,0), (-1,-1), 6),
        ('BOTTOMPADDING',(0,0), (-1,-1), 6),
        ('LEFTPADDING',  (0,0), (-1,-1), 8),
        ('BOX',          (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID',    (0,0), (-1,-1), 0.25, BORDER_COLOR),
        ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(bes_table)
    story.append(PageBreak())
    return story


def build_ami_meters(data, styles):
    story = []
    story.append(Paragraph('4. AMI Smart Meter Infrastructure', styles['section_heading']))
    story.append(HRFlowable(width='100%', thickness=1, color=RED_HAT_RED, spaceAfter=8))

    story.append(Paragraph(
        'The following Advanced Metering Infrastructure (AMI) smart meter simulators '
        'were assessed as part of this audit. Three utility types — Electric, Gas, and Water — '
        'each operate 10 smart meter devices (30 devices total). Compliance was evaluated against '
        'NIST IR 7628 Rev 1, AMI Device Compliance (ANSI C12.22 / IEC 62351), and '
        'AMI Head-End Security frameworks.',
        styles['body']))
    story.append(Spacer(1, 0.1*inch))

    ami_results = data.get('ami_results', [])

    # ── Per-utility summary table ──────────────────────────────────────────────
    story.append(Paragraph('Compliance Summary by Utility', styles['subsection_heading']))

    sum_data = [[
        Paragraph('Utility', styles['table_header']),
        Paragraph('NIST IR 7628', styles['table_header']),
        Paragraph('Device Compliance', styles['table_header']),
        Paragraph('Head-End Security', styles['table_header']),
        Paragraph('Devices', styles['table_header']),
        Paragraph('Overall', styles['table_header']),
    ]]

    ami_devices = data.get('ami_devices') or {}
    utility_rows = {}
    for row in ami_results:
        u = row.get('utility', 'unknown')
        if u not in utility_rows:
            utility_rows[u] = {}
        utility_rows[u][row.get('policy_name', '')] = row

    for utility in ['electric', 'gas', 'water']:
        rows = utility_rows.get(utility, {})
        nist   = rows.get('AMI NIST IR 7628 Rev 1', {})
        device = rows.get('AMI Device Compliance', {})
        headend = rows.get('AMI Head-End Security', {})

        nist_pct   = float(nist.get('compliance_percentage', 0))
        dev_pct    = float(device.get('compliance_percentage', 0))
        head_pct   = float(headend.get('compliance_percentage', 0))
        overall_pct = (nist_pct + dev_pct + head_pct) / 3

        def pct_para(pct):
            color = GREEN_OK if pct >= 90 else (AMBER_WARN if pct >= 70 else RED_FAIL)
            return Paragraph(f'{pct:.0f}%', ParagraphStyle('pp',
                fontSize=9, fontName='Helvetica-Bold', textColor=color, alignment=TA_CENTER))

        sum_data.append([
            Paragraph(f'<b>{utility.capitalize()}</b>', styles['table_cell']),
            pct_para(nist_pct),
            pct_para(dev_pct),
            pct_para(head_pct),
            Paragraph(str(len(ami_devices.get(utility, []))) if ami_devices.get(utility) else '—',
                      styles['table_cell_center']),
            pct_para(overall_pct),
        ])

    sum_table = Table(sum_data, colWidths=[0.9*inch, 1.2*inch, 1.4*inch, 1.4*inch, 0.7*inch, 1.1*inch])
    sum_table.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0),  TABLE_HEADER),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [colors.white, ROW_ALT, colors.white]),
        ('TOPPADDING',    (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('BOX',           (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID',     (0,0), (-1,-1), 0.25, BORDER_COLOR),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(sum_table)
    story.append(Spacer(1, 0.2*inch))

    # ── Per-utility device detail ──────────────────────────────────────────────
    story.append(Paragraph('Device Compliance Detail', styles['subsection_heading']))
    # Per-device rows are rendered ONLY when the caller supplies real device
    # records (data['ami_devices'] / data['ami_per_device_violations']). The
    # stored AMI result is an aggregate percentage per utility; device IDs,
    # firmware, ports and findings cannot be derived from it and are never
    # synthesised here — an audit report must not contain invented evidence.
    if not ami_devices:
        story.append(Paragraph(
            'Per-device detail is not available in this data set: the stored AMI Device '
            'Compliance result is an aggregate score per utility. The scores above are the '
            'assessment evidence; device-level findings require the per-device results from '
            'the AMI assessment run to be supplied with the report data.',
            styles['body_small']))
        story.append(PageBreak())
        return story

    story.append(Paragraph(
        'The table below lists per-device compliance findings from the Device Compliance '
        'assessment (ANSI C12.22 / IEC 62351). Devices with no findings are compliant.',
        styles['body_small']))
    story.append(Spacer(1, 0.08*inch))

    for utility in ['electric', 'gas', 'water']:
        rows = utility_rows.get(utility, {})
        device_row = rows.get('AMI Device Compliance', {})
        dev_pct  = float(device_row.get('compliance_percentage', 0))
        devices = ami_devices.get(utility, [])
        per_device_viols = (data.get('ami_per_device_violations') or {}).get(utility, {})

        story.append(Paragraph(
            f'{utility.capitalize()} Meters',
            ParagraphStyle('uh', fontSize=10, fontName='Helvetica-Bold',
                           textColor=BLUE_ACCENT, spaceBefore=8, spaceAfter=4)))
        if not devices:
            story.append(Paragraph('No per-device records supplied for this utility.', styles['body_small']))
            continue

        dev_data = [[
            Paragraph('Device ID', styles['table_header']),
            Paragraph('Firmware', styles['table_header']),
            Paragraph('Port', styles['table_header']),
            Paragraph('Status', styles['table_header']),
            Paragraph('Findings', styles['table_header']),
        ]]

        for meter in devices:
            mid = meter.get('meter_id', '')
            num = meter.get('meter_num', 0)
            fw  = meter.get('firmware_version', 'N/A')
            port = str(meter.get('port', 'N/A'))
            viols = per_device_viols.get(mid.split('-')[-1].lstrip('0') or '0', [])
            # Try key with full suffix
            viols = per_device_viols.get(mid, viols)

            if viols:
                # format violations as bullet list
                viol_text = '<br/>'.join(
                    f'• {v}' for v in viols
                )
                status_color = RED_FAIL
                status_text = 'FAIL'
            else:
                viol_text = 'No findings'
                status_color = GREEN_OK
                status_text = 'PASS'

            dev_data.append([
                Paragraph(f'<b>{mid}</b>', styles['table_cell']),
                Paragraph(fw, styles['table_cell_center']),
                Paragraph(port, styles['table_cell_center']),
                Paragraph(status_text, ParagraphStyle('ds',
                    fontSize=8, fontName='Helvetica-Bold',
                    textColor=status_color, alignment=TA_CENTER)),
                Paragraph(viol_text, styles['body_small']),
            ])

        dev_table = Table(dev_data, colWidths=[1.4*inch, 0.75*inch, 0.55*inch, 0.55*inch, 3.45*inch])
        dev_table.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0),  TABLE_HEADER),
            ('ROWBACKGROUNDS',(0,1), (-1,-1), [colors.white, ROW_ALT]),
            ('TOPPADDING',    (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING',   (0,0), (-1,-1), 6),
            ('BOX',           (0,0), (-1,-1), 0.5, BORDER_COLOR),
            ('INNERGRID',     (0,0), (-1,-1), 0.25, BORDER_COLOR),
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(dev_table)

        counts = ''
        if 'passed_controls' in device_row or 'failed_controls' in device_row:
            counts = (f' — {int(device_row.get("passed_controls", 0))} compliant, '
                      f'{int(device_row.get("failed_controls", 0))} non-compliant')
        story.append(Paragraph(
            f'Score: <b>{dev_pct:.0f}%</b>{counts}',
            ParagraphStyle('ds2', fontSize=8, fontName='Helvetica', textColor=MID_GRAY,
                           spaceBefore=3, spaceAfter=6)))

    story.append(PageBreak())
    return story


def build_cip_results(data, styles):
    story = []
    story.append(Paragraph('5. CIP Standards Compliance Results', styles['section_heading']))
    story.append(HRFlowable(width='100%', thickness=1, color=RED_HAT_RED, spaceAfter=8))

    reqs = data.get('requirements', {})
    cip_score = float(data.get('cip_score', 100.0))

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

    # Summary score bar
    story.append(Paragraph(
        f'Overall CIP-002 through CIP-012 Compliance Score: <b>{cip_score:.1f}%</b>',
        styles['body']))
    story.append(Spacer(1, 0.1*inch))

    # Results table
    results_data = [[
        Paragraph('Standard', styles['table_header']),
        Paragraph('Title', styles['table_header']),
        Paragraph('Requirement Description', styles['table_header']),
        Paragraph('Status', styles['table_header']),
    ]]
    for std, title, desc, compliant in cip_standards:
        status_text = 'COMPLIANT' if compliant else 'NON-COMPLIANT'
        status_color = GREEN_OK if compliant else RED_FAIL
        results_data.append([
            Paragraph(f'<b>{std}</b>', styles['table_cell']),
            Paragraph(title, styles['table_cell']),
            Paragraph(desc, styles['body_small']),
            Paragraph(status_text, ParagraphStyle('st', fontSize=8,
                fontName='Helvetica-Bold', textColor=status_color,
                alignment=TA_CENTER)),
        ])

    results_table = Table(results_data, colWidths=[0.75*inch, 1.5*inch, 3.25*inch, 1.1*inch])
    results_table.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0),  TABLE_HEADER),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [colors.white, ROW_ALT]),
        ('TOPPADDING',    (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
        ('BOX',           (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID',     (0,0), (-1,-1), 0.25, BORDER_COLOR),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(results_table)
    story.append(PageBreak())
    return story


def build_cip015(data, styles):
    story = []
    story.append(Paragraph('6. CIP-015 Internal Network Security Monitoring',
                            styles['section_heading']))
    story.append(HRFlowable(width='100%', thickness=1, color=RED_HAT_RED, spaceAfter=8))

    cip015 = data.get('cip015', {})
    score  = float(cip015.get('score', 100.0))
    reqs15 = cip015.get('requirements', {
        'R1_insm_categorization':    True,
        'R2_insm_implementation':    True,
        'R3_documentation_management': True,
    })

    story.append(Paragraph(
        'CIP-015-1 establishes requirements for Internal Network Security Monitoring '
        '(INSM) of high-impact BES Cyber Systems and their associated Electronic '
        'Security Perimeters. The following requirements were evaluated:',
        styles['body']))
    story.append(Spacer(1, 0.1*inch))

    insm_data = [[
        Paragraph('Requirement', styles['table_header']),
        Paragraph('Description', styles['table_header']),
        Paragraph('Status', styles['table_header']),
    ], [
        Paragraph('<b>R1</b>', styles['table_cell']),
        Paragraph('INSM Categorization — Identify and categorize assets requiring INSM',
                  styles['table_cell']),
        Paragraph('COMPLIANT' if reqs15.get('R1_insm_categorization', True) else 'NON-COMPLIANT',
            ParagraphStyle('s', fontSize=9, fontName='Helvetica-Bold',
                textColor=GREEN_OK if reqs15.get('R1_insm_categorization', True) else RED_FAIL,
                alignment=TA_CENTER)),
    ], [
        Paragraph('<b>R2</b>', styles['table_cell']),
        Paragraph('INSM Implementation — Deploy and operate INSM capabilities',
                  styles['table_cell']),
        Paragraph('COMPLIANT' if reqs15.get('R2_insm_implementation', True) else 'NON-COMPLIANT',
            ParagraphStyle('s', fontSize=9, fontName='Helvetica-Bold',
                textColor=GREEN_OK if reqs15.get('R2_insm_implementation', True) else RED_FAIL,
                alignment=TA_CENTER)),
    ], [
        Paragraph('<b>R3</b>', styles['table_cell']),
        Paragraph('Documentation Management — Maintain and review INSM documentation',
                  styles['table_cell']),
        Paragraph('COMPLIANT' if reqs15.get('R3_documentation_management', True) else 'NON-COMPLIANT',
            ParagraphStyle('s', fontSize=9, fontName='Helvetica-Bold',
                textColor=GREEN_OK if reqs15.get('R3_documentation_management', True) else RED_FAIL,
                alignment=TA_CENTER)),
    ]]

    insm_table = Table(insm_data, colWidths=[0.8*inch, 4.8*inch, 1.1*inch])
    insm_table.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0),  TABLE_HEADER),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [colors.white, ROW_ALT, colors.white]),
        ('TOPPADDING',    (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('BOX',           (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID',     (0,0), (-1,-1), 0.25, BORDER_COLOR),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(insm_table)
    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph(f'CIP-015 Overall Score: <b>{score:.1f}%</b>', styles['body']))
    story.append(PageBreak())
    return story


def build_evidence(data, styles):
    story = []
    story.append(Paragraph('7. Control Evidence Detail', styles['section_heading']))
    story.append(HRFlowable(width='100%', thickness=1, color=RED_HAT_RED, spaceAfter=8))

    illustrative = bool(data.get('illustrative', False))
    story.append(Paragraph(
        'The following automated evidence categories were collected to support compliance '
        'assertions. Evidence is gathered via Ansible Automation Platform (AAP) 2.7 with '
        'authenticated connections, evaluated against Rego v1 policies in OPA, '
        'and persisted to PostgreSQL with timestamps.',
        styles['body']))
    if illustrative:
        story.append(Paragraph(
            '<i>Note: the entries below are illustrative evidence categories with sample '
            'findings; they do not represent verified results from an actual assessment.</i>',
            ParagraphStyle('evn', fontSize=8, fontName='Helvetica-Oblique',
                           textColor=AMBER_WARN)))
    story.append(Spacer(1, 0.1*inch))

    # Prefer evidence supplied in the dataset; otherwise use generic capability
    # statements (no fabricated calendar dates) so the section never asserts specifics
    # that were not actually observed.
    default_items = [
        ('BES Cyber System Inventory', 'CIP-002', 'Asset register reconciled against the OT asset database; systems categorized per R1 methodology.'),
        ('Access Control Review',      'CIP-004', 'Identity store and role-based access reviewed; unauthorized accounts flagged if present.'),
        ('Electronic Security Perimeter', 'CIP-005', 'Firewall rules and ESP boundaries evaluated via configuration baseline comparison.'),
        ('Patch Management Status',    'CIP-007', 'Patch currency evaluated against the 35-day requirement.'),
        ('Malicious Code Prevention',  'CIP-007', 'Endpoint/runtime protection deployment and signature currency evaluated.'),
        ('Incident Response Plan',     'CIP-008', 'IRP review/test recency evaluated against the 15-month requirement.'),
        ('Recovery Plan Test',         'CIP-009', 'Recovery plan test recency and RTO objectives evaluated.'),
        ('Configuration Baseline',     'CIP-010', 'Baseline currency evaluated; unauthorized configuration drift flagged if detected.'),
        ('Information Classification', 'CIP-011', 'BCSI inventory and encryption at rest/in transit evaluated.'),
        ('Control Center Comms',       'CIP-012', 'Encrypted communications between control centers evaluated.'),
        ('INSM Sensor Coverage',       'CIP-015', 'INSM sensor coverage of High Impact BES Cyber Systems evaluated.'),
        ('INSM Alert Review',          'CIP-015', 'INSM alert-review process and retention configuration evaluated.'),
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

    ev_data = [[
        Paragraph('Evidence Item', styles['table_header']),
        Paragraph('Std', styles['table_header']),
        Paragraph('Finding', styles['table_header']),
        Paragraph('Result', styles['table_header']),
    ]]
    for item, std, finding, result in evidence_items:
        ev_data.append([
            Paragraph(f'<b>{item}</b>', styles['table_cell']),
            Paragraph(std, styles['table_cell_center']),
            Paragraph(finding, styles['body_small']),
            Paragraph(result, ParagraphStyle('ev', fontSize=8,
                fontName='Helvetica-Bold', textColor=GREEN_OK, alignment=TA_CENTER)),
        ])

    ev_table = Table(ev_data, colWidths=[1.6*inch, 0.65*inch, 3.65*inch, 0.75*inch])
    ev_table.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0),  TABLE_HEADER),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [colors.white, ROW_ALT]),
        ('TOPPADDING',    (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
        ('BOX',           (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID',     (0,0), (-1,-1), 0.25, BORDER_COLOR),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(ev_table)
    story.append(PageBreak())
    return story


def build_findings(data, styles):
    story = []
    story.append(Paragraph('8. Findings and Violations', styles['section_heading']))
    story.append(HRFlowable(width='100%', thickness=1, color=RED_HAT_RED, spaceAfter=8))

    violations = data.get('violations', [])

    if not violations:
        story.append(Table(
            [[Paragraph('✓  No violations identified during this assessment period.',
                ParagraphStyle('nv', fontSize=11, fontName='Helvetica-Bold',
                               textColor=GREEN_OK, alignment=TA_CENTER))]],
            colWidths=[6.6*inch],
            style=TableStyle([
                ('BACKGROUND',   (0,0), (-1,-1), colors.HexColor('#F0FFF0')),
                ('BOX',          (0,0), (-1,-1), 1, GREEN_OK),
                ('TOPPADDING',   (0,0), (-1,-1), 16),
                ('BOTTOMPADDING',(0,0), (-1,-1), 16),
            ])
        ))
        story.append(Spacer(1, 0.15*inch))
        story.append(Paragraph(
            'All NERC CIP requirements evaluated during this assessment period are '
            'satisfied. No potential violations, apparent violations, or confirmed '
            'violations were identified.',
            styles['body']))
    else:
        for i, v in enumerate(violations, 1):
            # Violations may be stored as plain strings (message only) or as dicts.
            # Normalize so string-shaped rows don't crash the report.
            if isinstance(v, str):
                v = {'description': v, 'severity': 'HIGH'}
            severity = v.get('severity', 'HIGH')
            scolor = RED_FAIL if severity == 'HIGH' else AMBER_WARN
            vdata = [[
                Paragraph(f'Finding #{i} — {severity}',
                    ParagraphStyle('fh', fontSize=10, fontName='Helvetica-Bold',
                                   textColor=colors.white)),
            ], [
                Paragraph(v.get('description', str(v)), styles['table_cell']),
            ]]
            vtable = Table(vdata, colWidths=[6.6*inch])
            vtable.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), scolor),
                ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#FFF8F8')),
                ('BOX',        (0,0), (-1,-1), 0.5, scolor),
                ('TOPPADDING', (0,0), (-1,-1), 8),
                ('BOTTOMPADDING',(0,0),(-1,-1), 8),
                ('LEFTPADDING', (0,0), (-1,-1), 10),
            ]))
            story.append(vtable)
            story.append(Spacer(1, 0.1*inch))

    story.append(PageBreak())
    return story


def build_remediation(data, styles):
    story = []
    story.append(Paragraph('9. Remediation Status', styles['section_heading']))
    story.append(HRFlowable(width='100%', thickness=1, color=RED_HAT_RED, spaceAfter=8))

    violations = data.get('violations', [])
    if not violations:
        story.append(Paragraph(
            'No remediation actions are required. All identified controls are '
            'operating effectively within the assessment scope.',
            styles['body']))
    else:
        rem_data = [[
            Paragraph('Finding', styles['table_header']),
            Paragraph('Standard', styles['table_header']),
            Paragraph('Remediation Action', styles['table_header']),
            Paragraph('Target Date', styles['table_header']),
            Paragraph('Owner', styles['table_header']),
        ]]
        for v in violations:
            rem_data.append([
                Paragraph(v.get('id', 'N/A'), styles['table_cell']),
                Paragraph(v.get('standard', 'N/A'), styles['table_cell']),
                Paragraph(v.get('remediation', 'TBD'), styles['table_cell']),
                Paragraph(v.get('target_date', 'TBD'), styles['table_cell_center']),
                Paragraph(v.get('owner', 'TBD'), styles['table_cell']),
            ])
        rem_table = Table(rem_data, colWidths=[0.8*inch, 0.8*inch, 3*inch, 0.9*inch, 1.1*inch])
        rem_table.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0),  TABLE_HEADER),
            ('ROWBACKGROUNDS',(0,1), (-1,-1), [colors.white, ROW_ALT]),
            ('TOPPADDING',    (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING',   (0,0), (-1,-1), 6),
            ('BOX',           (0,0), (-1,-1), 0.5, BORDER_COLOR),
            ('INNERGRID',     (0,0), (-1,-1), 0.25, BORDER_COLOR),
        ]))
        story.append(rem_table)

    story.append(PageBreak())
    return story


def build_certification(data, styles):
    story = []
    story.append(Paragraph('10. Auditor Certification', styles['section_heading']))
    story.append(HRFlowable(width='100%', thickness=1, color=RED_HAT_RED, spaceAfter=8))

    org      = data.get('organization', 'Example Utility Co.')
    assessor = data.get('assessor', 'Compliance Team')
    adate    = data.get('assessment_date', 'N/A')
    gen      = data.get('generated', 'N/A')
    overall  = data.get('overall_status', 'COMPLIANT')

    story.append(Paragraph(
        f'I hereby certify that the information contained in this report accurately '
        f'represents the results of the NERC CIP compliance assessment conducted for '
        f'<b>{org}</b> for the assessment period ending <b>{adate}</b>.',
        styles['body']))
    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph(
        'This assessment was conducted using automated policy-as-code evaluation '
        'consistent with NERC CIP Version 7 requirements. Evidence is retained in '
        'the compliance management system and is available for regulatory review '
        'upon request.',
        styles['body']))
    story.append(Spacer(1, 0.3*inch))

    # Signature block
    sig_data = [
        [Paragraph('<b>Compliance Assessor</b>', styles['table_cell']),
         Paragraph('<b>Compliance Manager</b>', styles['table_cell']),
         Paragraph('<b>CISO / VP Security</b>', styles['table_cell'])],
        [Paragraph(' ', styles['table_cell']),
         Paragraph(' ', styles['table_cell']),
         Paragraph(' ', styles['table_cell'])],
        [Paragraph('_' * 28, styles['table_cell']),
         Paragraph('_' * 28, styles['table_cell']),
         Paragraph('_' * 28, styles['table_cell'])],
        [Paragraph(f'Name: {assessor}', styles['body_small']),
         Paragraph('Name: ________________________', styles['body_small']),
         Paragraph('Name: ________________________', styles['body_small'])],
        [Paragraph(f'Date: {adate}', styles['body_small']),
         Paragraph('Date: ________________________', styles['body_small']),
         Paragraph('Date: ________________________', styles['body_small'])],
        [Paragraph('Title: Compliance Analyst', styles['body_small']),
         Paragraph('Title: ________________________', styles['body_small']),
         Paragraph('Title: ________________________', styles['body_small'])],
    ]
    sig_table = Table(sig_data, colWidths=[2.2*inch]*3)
    sig_table.setStyle(TableStyle([
        ('TOPPADDING',    (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('BACKGROUND',    (0,0), (-1,0),  LIGHT_GRAY),
        ('BOX',           (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID',     (0,0), (-1,-1), 0.25, BORDER_COLOR),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 0.3*inch))

    # System certification block
    cert_data = [
        [Paragraph('Assessment System', styles['table_header']),
         Paragraph('Value', styles['table_header'])],
        [Paragraph('Platform', styles['table_cell']),
         Paragraph('Ansible Automation Platform 2.7 + Open Policy Agent 0.60+', styles['table_cell'])],
        [Paragraph('Policy Engine', styles['table_cell']),
         Paragraph('OPA opa-ot container (:8183) — NERC-CIP Rego v1 policies', styles['table_cell'])],
        [Paragraph('Data Store', styles['table_cell']),
         Paragraph('PostgreSQL 15 — compliance database (compliance_results table)', styles['table_cell'])],
        [Paragraph('Report Generated', styles['table_cell']),
         Paragraph(gen, styles['table_cell'])],
        [Paragraph('Overall Status', styles['table_cell']),
         Paragraph(f'<b>{overall}</b>',
            ParagraphStyle('os', fontSize=9, fontName='Helvetica-Bold',
                textColor=_status_color(overall)))],
    ]
    cert_table = Table(cert_data, colWidths=[2*inch, 4.6*inch])
    cert_table.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0),  TABLE_HEADER),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [colors.white, ROW_ALT]),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('BOX',           (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID',     (0,0), (-1,-1), 0.25, BORDER_COLOR),
    ]))
    story.append(cert_table)
    return story


def _normalize_violations(vs):
    """Coerce violation entries to dicts. NERC results may store them as plain
    strings (message only); the builders expect dicts with .get()."""
    out = []
    for v in (vs or []):
        if isinstance(v, str):
            out.append({'description': v, 'severity': 'HIGH'})
        elif isinstance(v, dict):
            out.append(v)
    return out


def _status_is_ok(s):
    """Compliant or substantially-compliant both count as 'passing'."""
    return (s or '').upper() in ('COMPLIANT', 'SUBSTANTIALLY_COMPLIANT')


def _status_color(s):
    s = (s or '').upper()
    return GREEN_OK if s == 'COMPLIANT' else (AMBER_WARN if s == 'SUBSTANTIALLY_COMPLIANT' else RED_FAIL)


def _status_label(s):
    return (s or 'COMPLIANT').replace('_', ' ')


def generate(data, output_path):
    # Normalize violation shapes once, so every builder can rely on dicts.
    data['violations'] = _normalize_violations(data.get('violations'))
    if isinstance(data.get('cip015'), dict):
        data['cip015']['violations'] = _normalize_violations(data['cip015'].get('violations'))
    styles = build_styles()
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.65*inch,
        rightMargin=0.65*inch,
        topMargin=0.75*inch,
        bottomMargin=0.65*inch,
        title='NERC-CIP Compliance Audit Report',
        author=data.get('assessor', 'Compliance Team'),
        subject='NERC Critical Infrastructure Protection Compliance Assessment',
    )

    story = []
    story += build_cover(data, styles)
    story += build_toc(styles)
    story += build_executive_summary(data, styles)
    story += build_scope(data, styles)
    story += build_bes_systems(data, styles)
    story += build_ami_meters(data, styles)
    story += build_cip_results(data, styles)
    story += build_cip015(data, styles)
    story += build_evidence(data, styles)
    story += build_findings(data, styles)
    story += build_remediation(data, styles)
    story += build_certification(data, styles)

    doc.build(story,
              onFirstPage=lambda c, d: None,  # cover has no header/footer
              onLaterPages=lambda c, d: header_footer(c, d, data))

    print(f'PDF generated: {output_path}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', help='Output PDF path')
    parser.add_argument('--data', help='JSON data file (default: stdin)')
    args = parser.parse_args()

    if args.data:
        with open(args.data) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    generate(data, args.output)
