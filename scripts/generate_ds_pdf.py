#!/usr/bin/env python3
"""
generate_ds_pdf.py — Digital Sovereignty Audit Report PDF Generator
Reads JSON data from --data <file>, writes a submission-ready PDF to argv[1].
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

# ── Colours ────────────────────────────────────────────────────────────────────
RED_HAT_RED   = colors.HexColor('#EE0000')
DARK_GRAY     = colors.HexColor('#1A1A1A')
MID_GRAY      = colors.HexColor('#4A4A4A')
LIGHT_GRAY    = colors.HexColor('#F5F5F5')
TABLE_HEADER  = colors.HexColor('#2C2C2C')
GREEN_OK      = colors.HexColor('#3D8B37')
RED_FAIL      = colors.HexColor('#CC0000')
AMBER_WARN    = colors.HexColor('#C07000')
BLUE_ACCENT   = colors.HexColor('#0066CC')
PURPLE_DS     = colors.HexColor('#6B2FA0')
ROW_ALT       = colors.HexColor('#F9F9F9')
BORDER_COLOR  = colors.HexColor('#CCCCCC')

LEVEL_COLORS = {
    'SOVEREIGN':           colors.HexColor('#3D8B37'),
    'HIGH_ASSURANCE':      colors.HexColor('#0066CC'),
    'MODERATE_ASSURANCE':  colors.HexColor('#C07000'),
    'LIMITED_ASSURANCE':   colors.HexColor('#E05800'),
    'NON_SOVEREIGN':       colors.HexColor('#CC0000'),
}

LEVEL_LABELS = {
    'SOVEREIGN':           'SOVEREIGN',
    'HIGH_ASSURANCE':      'HIGH ASSURANCE',
    'MODERATE_ASSURANCE':  'MODERATE ASSURANCE',
    'LIMITED_ASSURANCE':   'LIMITED ASSURANCE',
    'NON_SOVEREIGN':       'NON-SOVEREIGN',
}

# Framework applicability per domain
FRAMEWORK_MAP = {
    'data_residency':                  ['ENISA', 'GAIA-X', 'BSI C5', 'IRAP'],
    'cryptographic_sovereignty':       ['ENISA', 'FedRAMP High', 'BSI C5', 'NCSC', 'IRAP'],
    'infrastructure_sovereignty':      ['GAIA-X', 'FedRAMP High', 'BSI C5', 'IRAP'],
    'software_sovereignty':            ['GAIA-X', 'ENISA', 'BSI C5'],
    'operational_sovereignty':         ['FedRAMP High', 'BSI C5', 'NCSC', 'IRAP'],
    'network_sovereignty':             ['FedRAMP High', 'NCSC', 'IRAP'],
    'ai_sovereignty':                  ['ENISA', 'GAIA-X'],
    'breach_notification_sovereignty': ['ENISA', 'NCSC', 'FedRAMP High'],
    'geopolitical_sovereignty':        ['GAIA-X', 'BSI C5', 'IRAP'],
}

ALL_FRAMEWORKS = ['ENISA', 'GAIA-X', 'FedRAMP High', 'BSI C5', 'NCSC', 'IRAP']


def build_styles():
    styles = {}

    styles['cover_title'] = ParagraphStyle('cover_title',
        fontSize=26, fontName='Helvetica-Bold', textColor=DARK_GRAY,
        alignment=TA_CENTER, spaceAfter=8, leading=32)

    styles['cover_subtitle'] = ParagraphStyle('cover_subtitle',
        fontSize=15, fontName='Helvetica', textColor=MID_GRAY,
        alignment=TA_CENTER, spaceAfter=6)

    styles['cover_meta'] = ParagraphStyle('cover_meta',
        fontSize=11, fontName='Helvetica', textColor=MID_GRAY,
        alignment=TA_CENTER, spaceAfter=4, leading=16)

    styles['cover_level'] = ParagraphStyle('cover_level',
        fontSize=22, fontName='Helvetica-Bold', textColor=colors.white,
        alignment=TA_CENTER, spaceAfter=4, leading=28)

    styles['section_heading'] = ParagraphStyle('section_heading',
        fontSize=13, fontName='Helvetica-Bold', textColor=PURPLE_DS,
        spaceBefore=16, spaceAfter=6)

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

    styles['violation_critical'] = ParagraphStyle('violation_critical',
        fontSize=9, fontName='Helvetica', textColor=RED_FAIL,
        spaceAfter=3, leading=14, leftIndent=12)

    styles['violation_high'] = ParagraphStyle('violation_high',
        fontSize=9, fontName='Helvetica', textColor=colors.HexColor('#E05800'),
        spaceAfter=3, leading=14, leftIndent=12)

    styles['violation_medium'] = ParagraphStyle('violation_medium',
        fontSize=9, fontName='Helvetica', textColor=AMBER_WARN,
        spaceAfter=3, leading=14, leftIndent=12)

    return styles


def header_footer(canvas, doc, data):
    canvas.saveState()
    w, h = letter

    # Header bar
    canvas.setFillColor(DARK_GRAY)
    canvas.rect(0, h - 0.55*inch, w, 0.55*inch, fill=1, stroke=0)
    canvas.setFillColor(PURPLE_DS)
    canvas.rect(0, h - 0.58*inch, w, 0.03*inch, fill=1, stroke=0)

    canvas.setFillColor(colors.white)
    canvas.setFont('Helvetica-Bold', 9)
    canvas.drawString(0.5*inch, h - 0.35*inch, 'DIGITAL SOVEREIGNTY ASSESSMENT REPORT')

    canvas.setFont('Helvetica', 8)
    canvas.drawRightString(w - 0.5*inch, h - 0.35*inch,
        f"CONFIDENTIAL — {data.get('organization', '')} — {data.get('assessment_date', '')}")

    # Footer
    canvas.setFillColor(LIGHT_GRAY)
    canvas.rect(0, 0, w, 0.45*inch, fill=1, stroke=0)
    canvas.setStrokeColor(BORDER_COLOR)
    canvas.line(0, 0.45*inch, w, 0.45*inch)

    canvas.setFillColor(MID_GRAY)
    canvas.setFont('Helvetica', 7)
    canvas.drawString(0.5*inch, 0.17*inch,
        'Generated by Ansible Automated Compliance (AAC) — Policy-as-Code via Open Policy Agent (OPA)')
    canvas.drawRightString(w - 0.5*inch, 0.17*inch, f'Page {doc.page}')

    canvas.restoreState()


def cover_page(data, styles):
    elements = []
    level = data.get('sovereignty_level', 'NON_SOVEREIGN')
    level_color = LEVEL_COLORS.get(level, RED_FAIL)
    level_label = LEVEL_LABELS.get(level, level)
    score = int(data.get('sovereignty_score', 0))

    elements.append(Spacer(1, 1.2*inch))

    # Title
    elements.append(Paragraph('Digital Sovereignty', styles['cover_title']))
    elements.append(Paragraph('Assessment Report', styles['cover_title']))
    elements.append(Spacer(1, 0.15*inch))
    elements.append(HRFlowable(width='80%', thickness=2, color=PURPLE_DS, spaceAfter=0.2*inch))

    # Org and date
    elements.append(Paragraph(f"<b>Organization:</b> {data.get('organization', 'N/A')}", styles['cover_meta']))
    elements.append(Paragraph(f"<b>Assessment Date:</b> {data.get('assessment_date', 'N/A')}", styles['cover_meta']))
    elements.append(Paragraph(f"<b>Generated:</b> {data.get('generated', 'N/A')}", styles['cover_meta']))
    elements.append(Spacer(1, 0.35*inch))

    # Sovereignty level badge
    badge_data = [[Paragraph(level_label, styles['cover_level'])]]
    badge = Table(badge_data, colWidths=[4.5*inch])
    badge.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), level_color),
        ('ROUNDEDCORNERS', [8]),
        ('TOPPADDING',    (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(Table([[badge]], colWidths=[7.5*inch]))
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph(f'Sovereignty Score: <b>{score}%</b>', styles['cover_meta']))
    elements.append(Spacer(1, 0.35*inch))

    # Applicable frameworks
    elements.append(Paragraph('<b>Applicable Frameworks:</b>', styles['cover_meta']))
    elements.append(Paragraph('ENISA Cloud Security · GAIA-X Federation · FedRAMP High · BSI C5 · NCSC · IRAP Protected',
        styles['cover_meta']))
    elements.append(Spacer(1, 0.4*inch))

    elements.append(HRFlowable(width='80%', thickness=1, color=BORDER_COLOR))
    elements.append(Spacer(1, 0.15*inch))
    elements.append(Paragraph(
        'This report is CONFIDENTIAL and intended solely for use by authorized compliance '
        'personnel and designated regulators. Distribution outside the organization requires '
        'written authorization from the Chief Information Security Officer.',
        styles['body_small']))

    elements.append(PageBreak())
    return elements


def exec_summary(data, styles):
    elements = []
    elements.append(Paragraph('Executive Summary', styles['section_heading']))

    level = data.get('sovereignty_level', 'NON_SOVEREIGN')
    level_color = LEVEL_COLORS.get(level, RED_FAIL)
    level_label = LEVEL_LABELS.get(level, level)
    score = int(data.get('sovereignty_score', 0))
    domains_assessed = int(data.get('domains_assessed', 0))
    domains_passing  = int(data.get('domains_passing', 0))
    viols = data.get('violation_summary', {})
    total_v    = int(viols.get('total', 0))
    critical_v = int(viols.get('critical', 0))
    high_v     = int(viols.get('high', 0))

    # Summary paragraph
    level_prose = {
        'SOVEREIGN':          'fully sovereign — all assessed domains meet all applicable framework requirements with no critical or high-severity findings.',
        'HIGH_ASSURANCE':     'at high assurance — the organization meets nearly all sovereignty requirements with only minor findings.',
        'MODERATE_ASSURANCE': 'at moderate assurance — most sovereignty requirements are met; high-severity findings require remediation.',
        'LIMITED_ASSURANCE':  'at limited assurance — significant sovereignty gaps exist that must be addressed before regulatory submission.',
        'NON_SOVEREIGN':      'NON-SOVEREIGN — critical sovereignty gaps exist. Regulatory approval cannot be granted in the current posture.',
    }
    prose = level_prose.get(level, 'in an undetermined sovereignty posture.')
    elements.append(Paragraph(
        f"As of {data.get('assessment_date', 'the assessment date')}, <b>{data.get('organization', 'the organization')}</b> "
        f"is assessed as <b>{prose}</b>",
        styles['body']))
    elements.append(Spacer(1, 0.1*inch))

    # KPI table
    kpi_rows = [
        [Paragraph('Metric', styles['table_header']),
         Paragraph('Value', styles['table_header'])],
        [Paragraph('Sovereignty Level', styles['table_cell']),
         Paragraph(f'<b>{level_label}</b>', styles['table_cell_center'])],
        [Paragraph('Overall Score', styles['table_cell']),
         Paragraph(f'<b>{score}%</b>', styles['table_cell_center'])],
        [Paragraph('Domains Assessed', styles['table_cell']),
         Paragraph(str(domains_assessed), styles['table_cell_center'])],
        [Paragraph('Domains Passing', styles['table_cell']),
         Paragraph(f'{domains_passing} / {domains_assessed}', styles['table_cell_center'])],
        [Paragraph('Total Violations', styles['table_cell']),
         Paragraph(str(total_v), styles['table_cell_center'])],
        [Paragraph('Critical Violations', styles['table_cell']),
         Paragraph(str(critical_v), styles['table_cell_center'])],
        [Paragraph('High Violations', styles['table_cell']),
         Paragraph(str(high_v), styles['table_cell_center'])],
    ]
    kpi_table = Table(kpi_rows, colWidths=[3.5*inch, 3*inch])
    ts = [
        ('BACKGROUND',    (0, 0), (-1, 0),  TABLE_HEADER),
        ('BACKGROUND',    (0, 1), (-1, 1),  LIGHT_GRAY),
        ('BACKGROUND',    (0, 2), (-1, 2),  level_color),
        ('TEXTCOLOR',     (0, 2), (-1, 2),  colors.white),
        ('FONTNAME',      (0, 2), (-1, 2),  'Helvetica-Bold'),
        ('ROWBACKGROUNDS',(0, 3), (-1, -1), [colors.white, ROW_ALT]),
        ('GRID',          (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
    ]
    if critical_v > 0:
        # Highlight critical row red
        for i, row in enumerate(kpi_rows):
            if 'Critical' in (row[0].text if hasattr(row[0], 'text') else ''):
                ts.append(('TEXTCOLOR', (1, i), (1, i), RED_FAIL))
    kpi_table.setStyle(TableStyle(ts))
    elements.append(kpi_table)
    elements.append(Spacer(1, 0.2*inch))

    # Applicable frameworks note
    elements.append(Paragraph('<b>Applicable Regulatory Frameworks</b>', styles['subsection_heading']))
    fw_desc = {
        'ENISA':        'ENISA Cloud Security Framework — European Union Agency for Cybersecurity guidelines for cloud sovereignty.',
        'GAIA-X':       'GAIA-X Federation — European cloud data infrastructure sovereignty and interoperability standards.',
        'FedRAMP High': 'FedRAMP High Baseline — US Federal Risk and Authorization Management Program cloud requirements.',
        'BSI C5':       'BSI C5 — German Federal Office for Information Security cloud compliance catalogue.',
        'NCSC':         'NCSC Cloud Security Principles — UK National Cyber Security Centre guidance.',
        'IRAP Protected': 'IRAP Protected — Australian Government Information Security Registered Assessors Program.',
    }
    fw_rows = [[Paragraph('Framework', styles['table_header']),
                Paragraph('Description', styles['table_header'])]]
    for fw, desc in fw_desc.items():
        fw_rows.append([Paragraph(fw, styles['table_cell']),
                        Paragraph(desc, styles['table_cell'])])
    fw_table = Table(fw_rows, colWidths=[1.5*inch, 5*inch])
    fw_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), TABLE_HEADER),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ('GRID',          (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
    ]))
    elements.append(fw_table)
    elements.append(PageBreak())
    return elements


def domain_scorecard(data, styles):
    elements = []
    elements.append(Paragraph('Domain Scorecard', styles['section_heading']))
    elements.append(Paragraph(
        'The following table shows compliance results for each sovereignty domain evaluated '
        'in this assessment. A domain is COMPLIANT when all controls within it pass.',
        styles['body']))
    elements.append(Spacer(1, 0.1*inch))

    domains = data.get('domains', {})

    header = [
        Paragraph('Domain', styles['table_header']),
        Paragraph('Status', styles['table_header']),
        Paragraph('Controls', styles['table_header']),
        Paragraph('Passing', styles['table_header']),
        Paragraph('Violations', styles['table_header']),
        Paragraph('Score', styles['table_header']),
    ]
    rows = [header]

    total_controls = 0
    total_passing  = 0
    total_violations = 0

    for domain_key, domain_data in domains.items():
        label    = domain_data.get('label', domain_key)
        compliant = domain_data.get('compliant', False)
        tc       = int(domain_data.get('total_controls', 0))
        pc       = int(domain_data.get('passing_controls', 0))
        viols    = domain_data.get('violations', [])
        vc       = len(viols)
        score    = int((pc / max(tc, 1)) * 100)

        total_controls   += tc
        total_passing    += pc
        total_violations += vc

        status_para = Paragraph('✓ PASS' if compliant else '✗ FAIL',
            styles['compliant_badge'] if compliant else styles['noncompliant_badge'])

        rows.append([
            Paragraph(label, styles['table_cell']),
            status_para,
            Paragraph(str(tc), styles['table_cell_center']),
            Paragraph(str(pc), styles['table_cell_center']),
            Paragraph(str(vc), styles['table_cell_center']),
            Paragraph(f'{score}%', styles['table_cell_center']),
        ])

    # Totals row
    overall_score = int((total_passing / max(total_controls, 1)) * 100)
    rows.append([
        Paragraph('<b>TOTAL</b>', styles['table_cell']),
        Paragraph('', styles['table_cell']),
        Paragraph(f'<b>{total_controls}</b>', styles['table_cell_center']),
        Paragraph(f'<b>{total_passing}</b>', styles['table_cell_center']),
        Paragraph(f'<b>{total_violations}</b>', styles['table_cell_center']),
        Paragraph(f'<b>{overall_score}%</b>', styles['table_cell_center']),
    ])

    col_widths = [2.4*inch, 0.9*inch, 0.8*inch, 0.8*inch, 0.9*inch, 0.7*inch]
    table = Table(rows, colWidths=col_widths, repeatRows=1)

    ts = [
        ('BACKGROUND',    (0, 0),  (-1, 0),           TABLE_HEADER),
        ('BACKGROUND',    (0, -1), (-1, -1),           LIGHT_GRAY),
        ('FONTNAME',      (0, -1), (-1, -1),           'Helvetica-Bold'),
        ('ROWBACKGROUNDS',(0, 1),  (-1, -2),           [colors.white, ROW_ALT]),
        ('GRID',          (0, 0),  (-1, -1),           0.5, BORDER_COLOR),
        ('VALIGN',        (0, 0),  (-1, -1),           'MIDDLE'),
        ('TOPPADDING',    (0, 0),  (-1, -1),           5),
        ('BOTTOMPADDING', (0, 0),  (-1, -1),           5),
        ('LEFTPADDING',   (0, 0),  (-1, -1),           8),
    ]
    # Colour failing domain rows
    for i, (dk, dd) in enumerate(domains.items(), start=1):
        if not dd.get('compliant', False):
            ts.append(('BACKGROUND', (0, i), (0, i), colors.HexColor('#FFF0F0')))
    table.setStyle(TableStyle(ts))
    elements.append(table)
    elements.append(PageBreak())
    return elements


def framework_mapping(data, styles):
    elements = []
    elements.append(Paragraph('Framework Applicability Matrix', styles['section_heading']))
    elements.append(Paragraph(
        'This matrix shows which regulatory frameworks are affected by violations in each domain. '
        'A domain with violations implicates all frameworks listed for that domain.',
        styles['body']))
    elements.append(Spacer(1, 0.1*inch))

    domains = data.get('domains', {})

    # Build header row
    fw_abbrev = ['ENISA', 'GAIA-X', 'FedRAMP\nHigh', 'BSI C5', 'NCSC', 'IRAP']
    header = [Paragraph('Domain', styles['table_header'])]
    for fw in fw_abbrev:
        header.append(Paragraph(fw, styles['table_header']))
    rows = [header]

    for domain_key, domain_data in domains.items():
        label    = domain_data.get('label', domain_key)
        has_viols = len(domain_data.get('violations', [])) > 0
        applies_to = FRAMEWORK_MAP.get(domain_key, [])

        row = [Paragraph(label, styles['table_cell'])]
        for fw in ['ENISA', 'GAIA-X', 'FedRAMP High', 'BSI C5', 'NCSC', 'IRAP']:
            if fw not in applies_to:
                cell = Paragraph('—', styles['table_cell_center'])
            elif has_viols:
                cell = Paragraph('⚠', styles['noncompliant_badge'])
            else:
                cell = Paragraph('✓', styles['compliant_badge'])
            row.append(cell)
        rows.append(row)

    col_widths = [2.2*inch] + [0.87*inch] * 6
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0),  (-1, 0),  TABLE_HEADER),
        ('ROWBACKGROUNDS',(0, 1),  (-1, -1), [colors.white, ROW_ALT]),
        ('GRID',          (0, 0),  (-1, -1), 0.5, BORDER_COLOR),
        ('VALIGN',        (0, 0),  (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0),  (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0),  (-1, -1), 5),
        ('LEFTPADDING',   (0, 0),  (-1, -1), 8),
        ('ALIGN',         (1, 0),  (-1, -1), 'CENTER'),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.15*inch))

    # Legend
    legend_data = [[
        Paragraph('✓ = Compliant', styles['body_small']),
        Paragraph('⚠ = Violations present', styles['body_small']),
        Paragraph('— = Framework does not apply to this domain', styles['body_small']),
    ]]
    legend = Table(legend_data, colWidths=[1.8*inch, 2.0*inch, 3.5*inch])
    legend.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    elements.append(legend)
    elements.append(PageBreak())
    return elements


def violation_detail(data, styles):
    elements = []
    elements.append(Paragraph('Violation Detail', styles['section_heading']))

    domains = data.get('domains', {})
    all_violations = []
    for domain_key, domain_data in domains.items():
        for v in domain_data.get('violations', []):
            all_violations.append({**v, '_domain': domain_data.get('label', domain_key),
                                   '_domain_key': domain_key})

    if not all_violations:
        elements.append(Paragraph(
            'No violations were found. All assessed domains are compliant.',
            styles['body']))
        elements.append(PageBreak())
        return elements

    elements.append(Paragraph(
        f'The following {len(all_violations)} violation(s) were identified during this assessment. '
        'Violations are grouped by sovereignty domain and ordered by severity.',
        styles['body']))

    sev_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    sev_colors_map = {
        'critical': RED_FAIL,
        'high':     colors.HexColor('#E05800'),
        'medium':   AMBER_WARN,
        'low':      MID_GRAY,
    }

    for domain_key, domain_data in domains.items():
        viols = domain_data.get('violations', [])
        if not viols:
            continue

        label = domain_data.get('label', domain_key)
        fw_applies = FRAMEWORK_MAP.get(domain_key, [])

        elements.append(Paragraph(label, styles['subsection_heading']))
        elements.append(Paragraph(
            f'<i>Affected frameworks: {", ".join(fw_applies)}</i>',
            styles['body_small']))

        sorted_viols = sorted(viols, key=lambda v: sev_order.get(v.get('severity', 'low'), 3))

        viol_rows = [[
            Paragraph('Severity', styles['table_header']),
            Paragraph('Control ID', styles['table_header']),
            Paragraph('Finding', styles['table_header']),
            Paragraph('Remediation', styles['table_header']),
        ]]
        for v in sorted_viols:
            sev     = v.get('severity', 'medium').upper()
            ctrl_id = v.get('control_id', v.get('id', '—'))
            msg     = v.get('message', str(v))
            remed   = v.get('remediation', v.get('fix', '—'))
            sev_col = sev_colors_map.get(v.get('severity', 'medium'), MID_GRAY)

            sev_cell = Paragraph(f'<b>{sev}</b>', ParagraphStyle('sev',
                fontSize=9, fontName='Helvetica-Bold', textColor=sev_col,
                alignment=TA_CENTER))
            viol_rows.append([
                sev_cell,
                Paragraph(str(ctrl_id), styles['table_cell']),
                Paragraph(str(msg), styles['table_cell']),
                Paragraph(str(remed), styles['table_cell']),
            ])

        v_table = Table(viol_rows, colWidths=[0.85*inch, 1.1*inch, 2.6*inch, 2.0*inch],
                        repeatRows=1)
        v_table.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  TABLE_HEADER),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, ROW_ALT]),
            ('GRID',          (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ]))
        elements.append(KeepTogether([v_table, Spacer(1, 0.15*inch)]))

    elements.append(PageBreak())
    return elements


def certification_page(data, styles):
    elements = []
    elements.append(Paragraph('Assessment Certification', styles['section_heading']))
    elements.append(Spacer(1, 0.1*inch))

    elements.append(Paragraph(
        f'This Digital Sovereignty Assessment Report for <b>{data.get("organization", "the organization")}</b> '
        f'was produced on <b>{data.get("assessment_date", "N/A")}</b> using Ansible Automated Compliance (AAC), '
        f'an automated policy-as-code compliance platform powered by Open Policy Agent (OPA) and '
        f'Ansible Automation Platform (AAP).',
        styles['body']))

    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph('<b>Assessment Methodology</b>', styles['subsection_heading']))
    elements.append(Paragraph(
        'Sovereignty posture was evaluated by submitting organizational configuration data against '
        'Rego v1 policy rules loaded into a purpose-specific OPA instance. Each policy domain '
        'independently evaluates the input and returns a set of violations. Results are '
        'automatically stored in a compliance database with full audit trail.',
        styles['body']))

    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph('<b>Sovereignty Level Classification</b>', styles['subsection_heading']))

    level_rows = [
        [Paragraph('Level', styles['table_header']),
         Paragraph('Criteria', styles['table_header'])],
        [Paragraph('SOVEREIGN', ParagraphStyle('sl', fontSize=9, fontName='Helvetica-Bold',
             textColor=LEVEL_COLORS['SOVEREIGN'], alignment=TA_CENTER)),
         Paragraph('All domains pass. No critical or high-severity violations.', styles['table_cell'])],
        [Paragraph('HIGH ASSURANCE', ParagraphStyle('sl', fontSize=9, fontName='Helvetica-Bold',
             textColor=LEVEL_COLORS['HIGH_ASSURANCE'], alignment=TA_CENTER)),
         Paragraph('Score ≥ 85%. No critical violations. ≤ 2 high-severity violations.', styles['table_cell'])],
        [Paragraph('MODERATE ASSURANCE', ParagraphStyle('sl', fontSize=9, fontName='Helvetica-Bold',
             textColor=LEVEL_COLORS['MODERATE_ASSURANCE'], alignment=TA_CENTER)),
         Paragraph('Score ≥ 70%. No critical violations. High-severity violations present.', styles['table_cell'])],
        [Paragraph('LIMITED ASSURANCE', ParagraphStyle('sl', fontSize=9, fontName='Helvetica-Bold',
             textColor=LEVEL_COLORS['LIMITED_ASSURANCE'], alignment=TA_CENTER)),
         Paragraph('Score ≥ 50%. No critical violations.', styles['table_cell'])],
        [Paragraph('NON-SOVEREIGN', ParagraphStyle('sl', fontSize=9, fontName='Helvetica-Bold',
             textColor=LEVEL_COLORS['NON_SOVEREIGN'], alignment=TA_CENTER)),
         Paragraph('Critical violations present, or score < 50%.', styles['table_cell'])],
    ]
    level_table = Table(level_rows, colWidths=[1.8*inch, 5.2*inch])
    level_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  TABLE_HEADER),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ('GRID',          (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
    ]))
    elements.append(level_table)
    elements.append(Spacer(1, 0.3*inch))

    elements.append(HRFlowable(width='100%', thickness=1, color=BORDER_COLOR))
    elements.append(Spacer(1, 0.15*inch))
    elements.append(Paragraph(
        'This report was generated automatically. All findings are based on the configuration '
        'data submitted at the time of assessment and reflect the organization\'s sovereignty '
        'posture at that point in time. This document does not constitute legal advice.',
        styles['body_small']))

    return elements


def generate_pdf(output_path, data):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=0.85*inch,
        bottomMargin=0.65*inch,
        title=f"Digital Sovereignty Assessment — {data.get('organization', '')}",
        author='Ansible Automated Compliance (AAC)',
        subject='Digital Sovereignty Assessment Report',
    )

    styles = build_styles()
    hf = lambda canvas, doc: header_footer(canvas, doc, data)

    story = []
    story += cover_page(data, styles)
    story += exec_summary(data, styles)
    story += domain_scorecard(data, styles)
    story += framework_mapping(data, styles)
    story += violation_detail(data, styles)
    story += certification_page(data, styles)

    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    print(f'PDF written to {output_path}')


def main():
    parser = argparse.ArgumentParser(description='Generate Digital Sovereignty Assessment PDF')
    parser.add_argument('output', help='Output PDF path')
    parser.add_argument('--data', required=True, help='JSON data file path')
    args = parser.parse_args()

    with open(args.data) as f:
        data = json.load(f)

    generate_pdf(args.output, data)


if __name__ == '__main__':
    main()
