"""
maintenance_pdf.py — Genera el FO-SGSI-20 pre-llenado como PDF (ReportLab).
Formato: Acciones Preventivas, Correctivas y de Mejora.
"""

import io
import os
from datetime import date as _date

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, HRFlowable, Image, KeepTogether
)
from reportlab.lib.colors import HexColor, white, black, Color

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE = os.path.dirname(__file__)
_LOGO = os.path.join(_BASE, 'static', 'images', 'responsiva_image1.jpg')

# ── Paleta ────────────────────────────────────────────────────────────────────
NAVY      = HexColor('#233C6E')
BLUE      = HexColor('#089ACF')
GRAY_HDR  = HexColor('#F2F2F2')
GRAY_MED  = HexColor('#BFBFBF')
GRAY_TXT  = HexColor('#A5A5A5')
BORDER    = HexColor('#C0C0C0')

MONTHS_ES = {
    1:'Enero', 2:'Febrero', 3:'Marzo', 4:'Abril',
    5:'Mayo', 6:'Junio', 7:'Julio', 8:'Agosto',
    9:'Septiembre', 10:'Octubre', 11:'Noviembre', 12:'Diciembre',
}

NC_SOURCE_MAP = {
    'quejas':        'Quejas y reclamos recurrentes de los usuarios',
    'auditoria':     'Informes de Auditoría Interna o Externa',
    'direccion':     'Resultados de la Revisión por la Dirección',
    'satisfaccion':  'Resultados de las Mediciones de Satisfacción',
    'indicadores':   'Mediciones de Indicadores',
    'autoevaluacion':'Resultados de Autoevaluación',
    'riesgos':       'Gestión de Riesgos',
    'otro':          'Otro',
}

# ── Estilos ───────────────────────────────────────────────────────────────────
def _st():
    return {
        'title': ParagraphStyle('title',
            fontName='Helvetica-Bold', fontSize=13, textColor=black,
            alignment=TA_CENTER, spaceAfter=4),
        'h1': ParagraphStyle('h1',
            fontName='Helvetica-Bold', fontSize=11, textColor=NAVY,
            spaceBefore=8, spaceAfter=2),
        'label': ParagraphStyle('label',
            fontName='Helvetica-Bold', fontSize=9, textColor=black,
            alignment=TA_LEFT),
        'label_c': ParagraphStyle('label_c',
            fontName='Helvetica-Bold', fontSize=9, textColor=black,
            alignment=TA_CENTER),
        'value': ParagraphStyle('value',
            fontName='Helvetica', fontSize=9.5, textColor=black,
            alignment=TA_LEFT),
        'hint': ParagraphStyle('hint',
            fontName='Helvetica-Oblique', fontSize=8, textColor=GRAY_TXT,
            alignment=TA_LEFT),
        'small': ParagraphStyle('small',
            fontName='Helvetica', fontSize=8, textColor=HexColor('#555555'),
            alignment=TA_LEFT),
        'chk_yes': ParagraphStyle('chk_yes',
            fontName='Helvetica-Bold', fontSize=10, textColor=NAVY,
            alignment=TA_CENTER),
        'chk_no': ParagraphStyle('chk_no',
            fontName='Helvetica', fontSize=10, textColor=GRAY_TXT,
            alignment=TA_CENTER),
        'footer': ParagraphStyle('footer',
            fontName='Helvetica', fontSize=7, textColor=HexColor('#888888'),
            alignment=TA_CENTER),
        'white_label': ParagraphStyle('white_label',
            fontName='Helvetica-Bold', fontSize=9, textColor=white,
            alignment=TA_LEFT),
        'white_label_c': ParagraphStyle('white_label_c',
            fontName='Helvetica-Bold', fontSize=9, textColor=white,
            alignment=TA_CENTER),
    }

CELL_PAD = [('LEFTPADDING',(0,0),(-1,-1),4),
            ('RIGHTPADDING',(0,0),(-1,-1),4),
            ('TOPPADDING',(0,0),(-1,-1),3),
            ('BOTTOMPADDING',(0,0),(-1,-1),3),
            ('GRID',(0,0),(-1,-1),.4,BORDER)]


def _val(text, st_key, styles, empty='—'):
    t = (text or '').strip() or empty
    return Paragraph(t, styles[st_key])


def _checked(yes: bool, styles):
    return Paragraph('☑' if yes else '☐', styles['chk_yes'] if yes else styles['chk_no'])


# ── Footer ────────────────────────────────────────────────────────────────────
def _draw_footer(canvas, doc):
    canvas.saveState()
    pw, _ = LETTER
    y = doc.bottomMargin - 10 * mm
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(.4)
    canvas.line(doc.leftMargin, y + 5*mm, pw - doc.rightMargin, y + 5*mm)
    canvas.setFont('Helvetica', 6.5)
    canvas.setFillColor(HexColor('#888888'))
    canvas.drawCentredString(pw/2, y+1.5*mm,
        'Intermall Laguna, Calz José Vasconcelos 1955, Residencial Tecnológico, 27272 Torreón, Coah. · www.remoteteamsolutions.com')
    canvas.drawRightString(pw - doc.rightMargin, y+1.5*mm, f'Página {canvas.getPageNumber()}')
    canvas.restoreRect = None
    canvas.restoreState()


# ── Secciones del documento ───────────────────────────────────────────────────

def _header_table(st, usable_w):
    """Logo + título + metadatos del formato."""
    logo = Image(_LOGO, width=5*cm, height=1.7*cm)

    title = [
        Paragraph('Formato de Acciones Preventivas,\nCorrectivas y de Mejora', st['title']),
    ]

    meta = Table([
        [Paragraph('ID: FO-SGSI-20', st['label']), Paragraph('Tipo: Interno', st['label']), Paragraph('Versión: 01', st['label'])],
    ], colWidths=[usable_w*0.35, usable_w*0.35, usable_w*0.3])
    meta.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),GRAY_HDR),
        ('GRID',(0,0),(-1,-1),.4,BORDER),
        *CELL_PAD,
    ]))

    tbl = Table([
        [logo, title],
        [Spacer(1,2), meta],
    ], colWidths=[5.5*cm, usable_w - 5.5*cm])
    tbl.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),0),
        ('RIGHTPADDING',(0,0),(-1,-1),0),
        ('TOPPADDING',(0,0),(-1,-1),0),
        ('BOTTOMPADDING',(0,0),(-1,-1),3),
        ('SPAN',(0,0),(0,1)),
    ]))
    return tbl


def _info_general(record, st, usable_w):
    """Tabla 2 — Información General de la Acción."""
    reported_date = record.reported_date
    date_str = f"{reported_date.day} de {MONTHS_ES[reported_date.month]} de {reported_date.year}" if reported_date else '—'

    type_labels = {'preventivo':'Preventiva','correctivo':'Correctiva','mejora':'De Mejora'}
    mtype = record.maintenance_type

    # Asset info for description
    asset = record.asset
    asset_info = f"{asset.name} | {asset.asset_tag}"
    if asset.model:      asset_info += f" | Modelo: {asset.model}"
    if asset.serial_number: asset_info += f" | S/N: {asset.serial_number}"

    # Employee if assigned
    emp = asset.current_assignment
    emp_str = record.reported_by or '—'
    if emp:
        emp_str = f"{emp.employee.name} — {emp.employee.department or 'IT'}"
        if record.reported_by:
            emp_str += f" | Reportado por: {record.reported_by}"

    cw = [usable_w*.18, usable_w*.30, usable_w*.17, usable_w*.17, usable_w*.18]

    rows = [
        # Row 0 — Header
        [Paragraph('Fecha:', st['label']),
         Paragraph('Nombre y Cargo:', st['label']),
         Paragraph('Consecutivo de la Acción:', st['label']), '', ''],
        # Row 1 — Values
        [Paragraph(date_str, st['value']),
         Paragraph(emp_str, st['value']),
         Paragraph(record.ticket_folio or '—', st['value']), '', ''],
        # Row 2–4 — Proceso + Tipo
        [Paragraph('Proceso:', st['label']),
         Paragraph(record.process_name or '—', st['value']),
         Paragraph('Tipo de Acción', st['label_c']),
         Paragraph('Preventiva', st['label']),
         _checked(mtype=='preventivo', st)],
        [Paragraph('Responsable:', st['label']),
         Paragraph(record.process_responsible or '—', st['value']),
         Paragraph('Tipo de Acción', st['label_c']),
         Paragraph('Correctiva', st['label']),
         _checked(mtype=='correctivo', st)],
        [Paragraph('', st['value']),
         Paragraph('', st['value']),
         Paragraph('Tipo de Acción', st['label_c']),
         Paragraph('De Mejora', st['label']),
         _checked(mtype=='mejora', st)],
        # Row 5 — Fuente NC header
        [Paragraph('Fuente de la No Conformidad:', st['label']), '', '', '', ''],
        # Row 6 — Fuente value
        [Paragraph(NC_SOURCE_MAP.get(record.nc_source, record.nc_source or '—'), st['value']),
         '', '', '', ''],
        # Row 7 — Descripción header
        [Paragraph('Descripción de la no conformidad real o potencial / Activo:', st['label']),
         '', '', '', ''],
        # Row 8 — Descripción value + asset info
        [Paragraph(f"{record.description or '—'}\n\n[Activo: {asset_info}]", st['value']),
         '', '', '', ''],
    ]

    row_h = [None]*9
    row_h[8] = 3*cm
    tbl = Table(rows, colWidths=cw, rowHeights=row_h)
    tbl.setStyle(TableStyle([
        *CELL_PAD,
        ('GRID',(0,0),(-1,-1),.4,BORDER),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('BACKGROUND',(0,0),(-1,0),GRAY_HDR),
        ('SPAN',(2,0),(4,0)), ('SPAN',(2,1),(4,1)),
        ('BACKGROUND',(0,0),(1,0),GRAY_HDR),
        ('BACKGROUND',(2,2),(3,4),GRAY_HDR),
        ('SPAN',(0,5),(4,5)), ('BACKGROUND',(0,5),(4,5),GRAY_HDR),
        ('SPAN',(0,6),(4,6)),
        ('SPAN',(0,7),(4,7)), ('BACKGROUND',(0,7),(4,7),GRAY_HDR),
        ('SPAN',(0,8),(4,8)),
    ]))
    return tbl


def _causa_raiz(record, st, usable_w):
    """Tabla 3 — Análisis de Causa Raíz y Plan de Acción."""
    cw2 = [usable_w/2, usable_w/2]
    cw4 = [usable_w*.22, usable_w*.22, usable_w*.28, usable_w*.28]

    plan_rows = [
        [Paragraph('Tareas o acciones', st['label']),
         Paragraph('Responsable', st['label']),
         Paragraph('Fecha límite', st['label_c']), '']
    ]
    plan_list = record.action_plan_list or []
    if plan_list:
        for row in plan_list:
            plan_rows.append([
                Paragraph(row.get('task',''), st['value']),
                Paragraph(row.get('responsible',''), st['value']),
                Paragraph(row.get('deadline',''), st['value']), '',
            ])
    else:
        for _ in range(3):
            plan_rows.append(['','','',''])

    rows = [
        # Header método / participantes
        [Paragraph('Método de análisis:', st['label']),
         Paragraph('Participantes:', st['label'])],
        [Paragraph(record.analysis_method or '—', st['value']),
         Paragraph(record.participants or '—', st['value'])],
        # Desarrollo
        [Paragraph('Desarrollo del análisis causa raíz:', st['label']), ''],
        [Paragraph(record.root_cause_analysis or '—', st['value']), ''],
        # Causa raíz
        [Paragraph('Causa raíz identificada:', st['label']), ''],
        [Paragraph(record.root_cause or '—', st['value']), ''],
        # Corrección
        [Paragraph('Descripción de la corrección realizada o a realizar:', st['label']), ''],
        [Paragraph(record.correction_desc or '—', st['value']), ''],
    ]

    rh_main = [None, None, None, 1.5*cm, None, 1*cm, None, 1.5*cm]
    tbl_main = Table(rows, colWidths=cw2, rowHeights=rh_main)
    style_cmds = [
        *CELL_PAD,
        ('GRID',(0,0),(-1,-1),.4,BORDER),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('BACKGROUND',(0,0),(-1,0),GRAY_HDR),
        ('SPAN',(0,2),(1,2)), ('BACKGROUND',(0,2),(1,2),GRAY_HDR),
        ('SPAN',(0,3),(1,3)),
        ('SPAN',(0,4),(1,4)), ('BACKGROUND',(0,4),(1,4),GRAY_HDR),
        ('SPAN',(0,5),(1,5)),
        ('SPAN',(0,6),(1,6)), ('BACKGROUND',(0,6),(1,6),GRAY_HDR),
        ('SPAN',(0,7),(1,7)),
    ]
    tbl_main.setStyle(TableStyle(style_cmds))

    # Plan table
    plan_header = [
        [Paragraph('Plan de Acción:', st['label']), '', '', ''],
    ]
    full_plan = plan_header + plan_rows
    tbl_plan = Table(full_plan, colWidths=[usable_w*.45, usable_w*.2, usable_w*.2, usable_w*.15])

    pc = [
        *CELL_PAD,
        ('GRID',(0,0),(-1,-1),.4,BORDER),
        ('SPAN',(0,0),(3,0)), ('BACKGROUND',(0,0),(3,0),GRAY_HDR),
        ('BACKGROUND',(0,1),(3,1),GRAY_HDR),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
    ]
    tbl_plan.setStyle(TableStyle(pc))

    # Fecha cierre propuesta
    pcd = record.proposed_close_date
    pcd_str = f"{pcd.day} de {MONTHS_ES[pcd.month]} de {pcd.year}" if pcd else '—'
    tbl_close = Table(
        [[Paragraph('Fecha de cierre propuesta:', st['label']),
          Paragraph(pcd_str, st['value'])]],
        colWidths=[usable_w*.4, usable_w*.6]
    )
    tbl_close.setStyle(TableStyle([
        *CELL_PAD, ('GRID',(0,0),(-1,-1),.4,BORDER),
        ('BACKGROUND',(0,0),(0,0),GRAY_HDR),
    ]))

    return [tbl_main, Spacer(1,3), tbl_plan, Spacer(1,3), tbl_close]


def _seguimiento(record, st, usable_w):
    """Tabla 4 + 5 — Seguimiento y Eficacia."""
    cw = [usable_w/2, usable_w/2]

    eff = record.effectiveness_ok
    eff_si  = '☑ Sí' if eff is True  else '☐ Sí'
    eff_no  = '☑ No' if eff is False else '☐ No'

    rows = [
        [Paragraph('Responsable del Seguimiento:', st['label']),
         Paragraph('Responsable del Cierre:', st['label'])],
        [Paragraph(record.followup_responsible or '—', st['value']),
         Paragraph(record.close_responsible or '—', st['value'])],
        [Paragraph('Evaluación de la Eficacia:', st['label']), ''],
        [Paragraph('¿Se eliminó la causa raíz?', st['label']),
         Paragraph(f'{eff_si}     {eff_no}', st['value'])],
        [Paragraph('Justificación:', st['label']), ''],
        [Paragraph(record.effectiveness_notes or '—', st['value']), ''],
        [Paragraph('Fecha de cierre final:', st['label']),
         Paragraph(record.actual_close_date.strftime('%d/%m/%Y') if record.actual_close_date else '___/___/______', st['value'])],
    ]

    rh_seg = [None, None, None, None, None, 1*cm, None]
    tbl = Table(rows, colWidths=cw, rowHeights=rh_seg)
    tbl.setStyle(TableStyle([
        *CELL_PAD,
        ('GRID',(0,0),(-1,-1),.4,BORDER),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('BACKGROUND',(0,0),(-1,0),GRAY_HDR),
        ('SPAN',(0,2),(1,2)), ('BACKGROUND',(0,2),(1,2),GRAY_HDR),
        ('SPAN',(0,4),(1,4)), ('BACKGROUND',(0,4),(1,4),GRAY_HDR),
        ('SPAN',(0,5),(1,5)),
        ('BACKGROUND',(0,6),(0,6),GRAY_HDR),
    ]))
    return tbl


def _firmas(record, st, usable_w):
    """Tabla 6 — Área de firmas."""
    sep = 0.3*cm
    cw  = [(usable_w - sep)/2, sep, (usable_w - sep)/2]
    rows = [[
        Paragraph(
            f"Nombre y firma del responsable de cerrar la acción<br/>"
            f"<b>{record.close_responsible or '_' * 30}</b><br/><br/>"
            f"Fecha (dd/mm/aaaa): ___/___/______",
            st['small']),
        '',
        Paragraph(
            f"Nombre y firma del responsable de la acción<br/>"
            f"<b>{record.followup_responsible or '_' * 30}</b><br/><br/>"
            f"Fecha (dd/mm/aaaa): ___/___/______",
            st['small']),
    ]]
    tbl = Table(rows, colWidths=cw)
    tbl.setStyle(TableStyle([
        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),40),
        ('BOTTOMPADDING',(0,0),(-1,-1),10),
        ('BOX',(0,0),(0,0),.6,BORDER),
        ('BOX',(2,0),(2,0),.6,BORDER),
        ('VALIGN',(0,0),(-1,-1),'BOTTOM'),
    ]))
    return tbl


# ── Función principal ─────────────────────────────────────────────────────────

def generate_fo_sgsi20(record) -> io.BytesIO:
    """
    Genera el FO-SGSI-20 pre-llenado con los datos del ticket de mantenimiento.

    Parameters
    ----------
    record : instancia del modelo Maintenance

    Returns
    -------
    io.BytesIO con el PDF listo para send_file()
    """
    buf    = io.BytesIO()
    margin = 1.3 * cm
    foot_h = 12 * mm

    page_w, page_h = LETTER
    usable_w = page_w - 2 * margin

    main_frame = Frame(
        margin, margin + foot_h,
        usable_w, page_h - 2 * margin - foot_h,
        id='main', leftPadding=0, rightPadding=0,
        topPadding=0, bottomPadding=0,
    )

    doc = BaseDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin + foot_h,
        title='FO-SGSI-20 Acciones Preventivas, Correctivas y de Mejora',
        author='Remote Team Solutions',
        subject=f'Mantenimiento {record.ticket_folio}',
        creator='RTS Intranet',
    )
    doc.addPageTemplates([PageTemplate(id='fo', frames=[main_frame], onPage=_draw_footer)])

    st    = _st()
    story = []

    # ① Encabezado del formato
    story.append(_header_table(st, usable_w))
    story.append(Spacer(1, 4))

    # ② Información General
    story.append(Paragraph('1. Información General de la Acción', st['h1']))
    story.append(_info_general(record, st, usable_w))
    story.append(Spacer(1, 6))

    # ③ Causa Raíz y Plan de Acción
    story.append(Paragraph('2. Identificación de la causa raíz y plan de acción', st['h1']))
    for el in _causa_raiz(record, st, usable_w):
        story.append(el)
    story.append(Spacer(1, 6))

    # ④ Seguimiento y Eficacia
    story.append(Paragraph('3. Seguimiento, verificación y cierre de las acciones', st['h1']))
    story.append(_seguimiento(record, st, usable_w))
    story.append(Spacer(1, 6))

    # ⑤ Firmas
    story.append(Paragraph('4. Área de Firmas', st['h1']))
    story.append(_firmas(record, st, usable_w))

    doc.build(story)
    buf.seek(0)
    return buf
