"""
responsiva_pdf.py — Carta de Resguardo en PDF (no editable)
Genera el documento usando ReportLab Platypus (puro Python, sin dependencias del sistema).
"""

import io
import os
from datetime import date as _date

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image, KeepTogether
)
from reportlab.lib.colors import HexColor, white, black

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE = os.path.dirname(__file__)
_LOGO = os.path.join(_BASE, 'static', 'images', 'responsiva_image1.jpg')

# ── Paleta ───────────────────────────────────────────────────────────────────
NAVY     = HexColor('#1F3864')
NAVY_LT  = HexColor('#D9E1F2')
GRAY_ROW = HexColor('#F2F4F8')
GRAY_TXT = HexColor('#555555')
BORDER   = HexColor('#C9D0DC')

# ── Textos ────────────────────────────────────────────────────────────────────
_MONTHS_ES = {
    1:'Enero', 2:'Febrero', 3:'Marzo', 4:'Abril',
    5:'Mayo', 6:'Junio', 7:'Julio', 8:'Agosto',
    9:'Septiembre', 10:'Octubre', 11:'Noviembre', 12:'Diciembre',
}

_TYPE_LABELS = {
    'laptop':'Laptop', 'desktop':'Desktop / PC', 'monitor':'Monitor',
    'tablet':'Tablet', 'headset':'Headset', 'teclado':'Teclado',
    'mouse':'Mouse', 'impresora':'Impresora', 'camara':'Cámara', 'otro':'Otro',
}

_BODY_TEXT = (
    "El equipo anteriormente descrito le fue asignado al trabajador para el eficiente "
    "desarrollo de su trabajo de acuerdo a lo establecido en la fracción III del Artículo 132 "
    "de la Ley Federal del Trabajo, mismo equipo que se encuentra en perfecto estado funcional, "
    "por lo que el Trabajador se compromete a conservarlo en buen estado y a que en el supuesto "
    "caso de que el equipo sufriese algún desperfecto, percance o avería será el único responsable "
    "de pagar el importe de la reparación, y todo lo que esto implica, y/o el reemplazo del equipo. "
    "Lo anterior será de acuerdo con las políticas previamente establecidas por la empresa aplicables "
    "al caso concreto y apegándose a la fracción VI del artículo 134 de la Ley Federal del Trabajo, "
    "no siendo responsable por el deterioro que origine el uso normal de dicho equipo, ni del "
    "ocasionado por caso fortuito, fuerza mayor, por causa de mala calidad o defectos de fabricación. "
    "Asimismo, en caso de robo o extravío, el trabajador está obligado a dar aviso de inmediato."
)


# ── Estilos ───────────────────────────────────────────────────────────────────
def _styles():
    return {
        'doc_title': ParagraphStyle('doc_title',
            fontName='Helvetica-Bold', fontSize=20, textColor=NAVY,
            alignment=TA_RIGHT, leading=24, spaceAfter=0),
        'date': ParagraphStyle('date',
            fontName='Helvetica', fontSize=9.5, textColor=HexColor('#333333'),
            alignment=TA_RIGHT, spaceBefore=8, spaceAfter=4),
        'body': ParagraphStyle('body',
            fontName='Helvetica', fontSize=9, leading=14,
            alignment=TA_JUSTIFY, spaceBefore=10, spaceAfter=10,
            textColor=HexColor('#222222')),
        'cell':   ParagraphStyle('cell',   fontName='Helvetica',      fontSize=8.5, leading=12, alignment=TA_LEFT),
        'cell_c': ParagraphStyle('cell_c', fontName='Helvetica',      fontSize=8.5, leading=12, alignment=TA_CENTER),
        'cell_r': ParagraphStyle('cell_r', fontName='Helvetica',      fontSize=8.5, leading=12, alignment=TA_RIGHT),
        'cell_hdr': ParagraphStyle('cell_hdr', fontName='Helvetica-Bold', fontSize=8.5, leading=12,
                                   alignment=TA_CENTER, textColor=white),
        'total_label': ParagraphStyle('total_label', fontName='Helvetica-Bold', fontSize=9,
                                      leading=12, alignment=TA_RIGHT, textColor=NAVY),
        'total_val': ParagraphStyle('total_val', fontName='Helvetica-Bold', fontSize=10,
                                    leading=13, alignment=TA_RIGHT, textColor=white),
        'sig_name': ParagraphStyle('sig_name', fontName='Helvetica-Bold', fontSize=9,
                                   leading=12, alignment=TA_CENTER, textColor=NAVY),
        'sig_role': ParagraphStyle('sig_role', fontName='Helvetica', fontSize=7.5,
                                   leading=11, alignment=TA_CENTER, textColor=GRAY_TXT),
    }


# ── Footer fijo en cada página ────────────────────────────────────────────────
def _draw_footer(canvas, doc):
    """Dibuja el pie de página fijo: línea, texto legal, número de página."""
    canvas.saveState()

    page_w, _ = LETTER
    lm = doc.leftMargin
    rm = doc.rightMargin
    content_w = page_w - lm - rm
    footer_y  = doc.bottomMargin - 10 * mm   # posición Y fija

    # Línea divisora
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(lm, footer_y + 6 * mm, page_w - rm, footer_y + 6 * mm)

    # Copyright — año dinámico
    year = _date.today().year
    canvas.setFont('Helvetica', 6.5)
    canvas.setFillColor(HexColor('#888888'))
    copyright_text = (
        f'Remote Team Solutions  |  Internal Copyright © {year}. All Rights Reserved.'
    )
    canvas.drawCentredString(page_w / 2, footer_y + 2 * mm, copyright_text)

    # Número de página
    page_num = canvas.getPageNumber()
    canvas.drawRightString(
        page_w - rm, footer_y + 2 * mm,
        f'Página {page_num}'
    )

    canvas.restoreState()


# ── Header: logo + título ─────────────────────────────────────────────────────
def _build_header(styles, usable_w):
    logo = Image(_LOGO, width=5.2 * cm, height=1.8 * cm)
    logo.hAlign = 'LEFT'

    title_cell = [Paragraph('CARTA DE RESGUARDO', styles['doc_title'])]

    tbl = Table(
        [[logo, title_cell]],
        colWidths=[5.8 * cm, usable_w - 5.8 * cm],
        hAlign='LEFT',
    )
    tbl.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
    ]))
    return tbl


# ── Tabla de equipos ──────────────────────────────────────────────────────────
def _build_equipment_table(assets: list, styles, usable_w: float):
    col_ratios = [0.13, 0.15, 0.24, 0.27, 0.21]
    col_widths = [usable_w * r for r in col_ratios]

    hdrs = ['EQUIPO', 'MARCA', 'TIPO / MODELO', 'NÚMERO DE SERIE', 'COSTO UNITARIO']
    data = [[Paragraph(h, styles['cell_hdr']) for h in hdrs]]

    total = 0.0
    for i, asset in enumerate(assets):
        equipo    = _TYPE_LABELS.get(asset.asset_type or '', asset.asset_type or 'Equipo')
        marca     = (asset.brand.name if getattr(asset, 'brand_id', None) and asset.brand
                     else getattr(asset, 'manufacturer', None) or '—')
        modelo    = asset.model or '—'
        serie     = asset.serial_number or '—'
        costo     = asset.purchase_cost or 0.0
        total    += costo
        costo_str = f'${costo:,.2f} MXN' if costo else '—'

        data.append([
            Paragraph(equipo,    styles['cell']),
            Paragraph(marca,     styles['cell']),
            Paragraph(modelo,    styles['cell']),
            Paragraph(serie,     styles['cell_c']),
            Paragraph(costo_str, styles['cell_r']),
        ])

    total_str = f'${total:,.2f} MXN'
    data.append([
        Paragraph('COSTO TOTAL DEL SETUP', styles['total_label']),
        '', '', '',
        Paragraph(total_str, styles['total_val']),
    ])

    n = len(data)

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        # Global
        ('FONTNAME',      (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 0), (-1, -1), 8.5),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 5),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        # Header
        ('BACKGROUND',    (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0), white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
        ('GRID',          (0, 0), (-1, n - 2), 0.4, BORDER),
        # Alternating rows
        ('ROWBACKGROUNDS',(0, 1), (-1, n - 2), [GRAY_ROW, colors.white]),
        # Total row
        ('SPAN',          (0, n-1), (3, n-1)),
        ('BACKGROUND',    (0, n-1), (3, n-1), NAVY_LT),
        ('BACKGROUND',    (4, n-1), (4, n-1), NAVY),
        ('FONTNAME',      (0, n-1), (-1, n-1), 'Helvetica-Bold'),
        ('GRID',          (0, n-1), (-1, n-1), 0.4, BORDER),
        ('ALIGN',         (0, n-1), (3, n-1), 'RIGHT'),
        ('ALIGN',         (4, n-1), (4, n-1), 'RIGHT'),
        ('TOPPADDING',    (0, n-1), (-1, n-1), 7),
        ('BOTTOMPADDING', (0, n-1), (-1, n-1), 7),
    ]))
    return tbl


# ── Firmas ────────────────────────────────────────────────────────────────────
def _build_signatures(employee_name: str, styles, usable_w: float):
    hr = HRFlowable(width='75%', thickness=1, color=black, hAlign='CENTER')

    def col(name, roles):
        block = [Spacer(1, 1.8 * cm), hr,
                 Spacer(1, 3), Paragraph(name, styles['sig_name'])]
        for r in roles:
            block.append(Paragraph(r, styles['sig_role']))
        return block

    left  = col(employee_name.upper(),
                ['TRABAJADOR A QUIEN EL EQUIPO LE FUE ASIGNADO', 'Y RESPONSABLE DEL MISMO'])
    right = col('PEDRO ANTONIO BARBOGLIO MURRA', ['DIRECCIÓN GENERAL'])

    sig_tbl = Table([[left, right]],
                    colWidths=[usable_w / 2, usable_w / 2])
    sig_tbl.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
    ]))
    return sig_tbl


# ── Función principal ─────────────────────────────────────────────────────────
def generate_responsiva_pdf(employee, assets: list, assign_date=None) -> io.BytesIO:
    """
    Genera la Carta de Resguardo como PDF no editable.

    Parameters
    ----------
    employee    : instancia del modelo Employee
    assets      : lista de instancias del modelo Asset
    assign_date : datetime.date — por defecto hoy

    Returns
    -------
    io.BytesIO con el contenido PDF listo para send_file()
    """
    if assign_date is None:
        assign_date = _date.today()

    # Guardia: fecha inválida (ej. año < 2000 por error de parseo en BD)
    if hasattr(assign_date, 'year') and assign_date.year < 2000:
        assign_date = _date.today()

    buf    = io.BytesIO()
    margin = 2.3 * cm
    foot_h = 14 * mm   # altura reservada para el pie de página

    page_w, page_h = LETTER
    usable_w = page_w - 2 * margin

    # Frame principal: deja espacio abajo para el footer fijo
    main_frame = Frame(
        margin, margin + foot_h,
        usable_w, page_h - 2 * margin - foot_h,
        id='main', leftPadding=0, rightPadding=0,
        topPadding=0, bottomPadding=0,
    )

    doc = BaseDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin + foot_h,
        title='Carta de Resguardo',
        author='Remote Team Solutions',
        subject=f'Resguardo — {employee.name}',
        creator='RTS Intranet',
    )

    doc.addPageTemplates([
        PageTemplate(id='carta', frames=[main_frame], onPage=_draw_footer)
    ])

    st = _styles()

    date_str = (f"Torreón, Coahuila, a {assign_date.day} de "
                f"{_MONTHS_ES[assign_date.month]} de {assign_date.year}")

    # Altura útil del frame (para calcular el spacer de empuje)
    frame_h = page_h - 2 * margin - foot_h

    # Estimación de alturas del contenido para empujar firmas al final
    # (valores aproximados en puntos)
    est_header  = 2.2 * cm
    est_divider = 0.5 * cm
    est_date    = 0.8 * cm
    est_table   = (len(assets) + 2) * 0.7 * cm + 1.2 * cm  # hdr + rows + total
    est_body    = 5.5 * cm   # texto legal (~7 líneas a 14pt)
    est_sigs    = 4.5 * cm   # espacio firmas + líneas + nombres

    used   = est_header + est_divider + est_date + est_table + est_body + est_sigs
    spacer = max(frame_h - used, 0.8 * cm)   # mínimo 0.8 cm aunque haya muchos activos

    story = []

    # 1. Header
    story.append(_build_header(st, usable_w))

    # 2. Línea navy
    story.append(HRFlowable(width='100%', thickness=2.5, color=NAVY,
                             spaceBefore=2, spaceAfter=2))

    # 3. Fecha
    story.append(Paragraph(date_str, st['date']))

    # 4. Tabla de equipos
    story.append(Spacer(1, 4))
    story.append(_build_equipment_table(assets, st, usable_w))

    # 5. Texto legal
    story.append(Paragraph(_BODY_TEXT, st['body']))

    # 6. Empujador → firmas hasta el fondo
    story.append(Spacer(1, spacer))

    # 7. Firmas (agrupadas para no partirlas entre páginas)
    story.append(KeepTogether(_build_signatures(employee.name, st, usable_w)))

    doc.build(story)
    buf.seek(0)
    return buf
