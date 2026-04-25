"""
offboarding_pdf.py — Acta de Entrega-Recepción de Equipo (Offboarding)
Incluye depreciación SAT (Art. 40 LISR) y sección de responsabilidad por daños.
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

# ── Paleta (verde oscuro / gris para distinguir de la Carta Responsiva) ───────
DARK    = HexColor('#1A3C34')      # verde oscuro corporativo
DARK_LT = HexColor('#D4E8E1')
WARN    = HexColor('#C0392B')      # rojo para daños
WARN_LT = HexColor('#FDECEA')
GRAY_ROW= HexColor('#F4F6F8')
GRAY_TXT= HexColor('#555555')
BORDER  = HexColor('#C9D0DC')
NAVY    = HexColor('#1F3864')

# ── Depreciación (SAT Art. 40 LISR) ──────────────────────────────────────────
# Tasas anuales máximas de deducción para activos tecnológicos
_DEPR_RATES = {
    'laptop':    0.30,   # 30 % — equipo de cómputo
    'desktop':   0.30,
    'tablet':    0.30,
    'monitor':   0.20,   # 20 % — mobiliario/equipo de oficina
    'headset':   0.25,
    'teclado':   0.25,
    'mouse':     0.25,
    'impresora': 0.25,
    'camara':    0.25,
    'otro':      0.25,
}

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

OFFBOARDING_REASONS = [
    ('renuncia',      'Renuncia voluntaria'),
    ('terminacion',   'Terminación de contrato'),
    ('jubilacion',    'Jubilación'),
    ('fincontrato',   'Fin de contrato temporal'),
    ('otro',          'Otro'),
]


def calc_depreciation(purchase_cost: float, purchase_date, asset_type: str,
                      as_of: _date = None) -> dict:
    """
    Calcula la depreciación en línea recta (SAT Art. 40 LISR).

    Returns dict:
        rate          tasa anual (ej. 0.30)
        years         años de uso (float)
        depr_pct      porcentaje depreciado acumulado (0-100)
        depr_amount   monto depreciado acumulado
        current_value valor actual (libro) — mínimo $0
        fully_depr    True si ya está totalmente depreciado
    """
    today = as_of or _date.today()
    rate  = _DEPR_RATES.get(asset_type or '', 0.25)
    cost  = purchase_cost or 0.0

    if not purchase_date or cost <= 0:
        return {
            'rate': rate, 'years': 0.0, 'depr_pct': 0.0,
            'depr_amount': 0.0, 'current_value': cost,
            'fully_depr': False,
        }

    years     = (today - purchase_date).days / 365.25
    depr_pct  = min(rate * years * 100, 100.0)
    depr_amt  = cost * min(rate * years, 1.0)
    curr_val  = max(0.0, cost - depr_amt)

    return {
        'rate':          rate,
        'years':         round(years, 2),
        'depr_pct':      round(depr_pct, 1),
        'depr_amount':   round(depr_amt, 2),
        'current_value': round(curr_val, 2),
        'fully_depr':    depr_pct >= 100.0,
    }


# ── Estilos ───────────────────────────────────────────────────────────────────
def _styles():
    return {
        'doc_title': ParagraphStyle('ob_title',
            fontName='Helvetica-Bold', fontSize=17, textColor=DARK,
            alignment=TA_RIGHT, leading=22, spaceAfter=0),
        'subtitle': ParagraphStyle('ob_subtitle',
            fontName='Helvetica', fontSize=9, textColor=HexColor('#444444'),
            alignment=TA_RIGHT, spaceBefore=2, spaceAfter=0),
        'date': ParagraphStyle('ob_date',
            fontName='Helvetica', fontSize=9.5, textColor=HexColor('#333333'),
            alignment=TA_RIGHT, spaceBefore=8, spaceAfter=4),
        'section': ParagraphStyle('ob_section',
            fontName='Helvetica-Bold', fontSize=9, textColor=DARK,
            spaceBefore=8, spaceAfter=4),
        'body': ParagraphStyle('ob_body',
            fontName='Helvetica', fontSize=8.5, leading=13,
            alignment=TA_JUSTIFY, spaceBefore=6, spaceAfter=6,
            textColor=HexColor('#222222')),
        'cell':    ParagraphStyle('ob_cell',   fontName='Helvetica',      fontSize=7.5, leading=10, alignment=TA_LEFT),
        'cell_c':  ParagraphStyle('ob_cell_c', fontName='Helvetica',      fontSize=7.5, leading=10, alignment=TA_CENTER),
        'cell_r':  ParagraphStyle('ob_cell_r', fontName='Helvetica',      fontSize=7.5, leading=10, alignment=TA_RIGHT),
        'cell_hdr':ParagraphStyle('ob_cell_hdr', fontName='Helvetica-Bold', fontSize=7.5, leading=10,
                                  alignment=TA_CENTER, textColor=white),
        'cell_hdr_sm':ParagraphStyle('ob_cell_hdr_sm', fontName='Helvetica-Bold', fontSize=6.5, leading=9,
                                     alignment=TA_CENTER, textColor=white),
        'dmg':     ParagraphStyle('ob_dmg',    fontName='Helvetica-Bold', fontSize=7.5,
                                  leading=10, alignment=TA_CENTER, textColor=WARN),
        'ok':      ParagraphStyle('ob_ok',     fontName='Helvetica-Bold', fontSize=7.5,
                                  leading=10, alignment=TA_CENTER, textColor=HexColor('#198754')),
        'total_lbl': ParagraphStyle('ob_tlbl', fontName='Helvetica-Bold', fontSize=8,
                                    leading=11, alignment=TA_RIGHT, textColor=DARK),
        'total_val': ParagraphStyle('ob_tval', fontName='Helvetica-Bold', fontSize=9,
                                    leading=12, alignment=TA_RIGHT, textColor=white),
        'warn_val': ParagraphStyle('ob_wval',  fontName='Helvetica-Bold', fontSize=9,
                                   leading=12, alignment=TA_RIGHT, textColor=white),
        'sig_name': ParagraphStyle('ob_sname', fontName='Helvetica-Bold', fontSize=8.5,
                                   leading=12, alignment=TA_CENTER, textColor=DARK),
        'sig_role': ParagraphStyle('ob_srole', fontName='Helvetica', fontSize=7,
                                   leading=10, alignment=TA_CENTER, textColor=GRAY_TXT),
        'emp_info': ParagraphStyle('ob_emp',   fontName='Helvetica', fontSize=9,
                                   leading=13, textColor=HexColor('#222222')),
        'emp_bold': ParagraphStyle('ob_empb',  fontName='Helvetica-Bold', fontSize=9,
                                   leading=13, textColor=DARK),
    }


# ── Footer ────────────────────────────────────────────────────────────────────
def _draw_footer(canvas, doc):
    canvas.saveState()
    page_w, _ = LETTER
    lm, rm    = doc.leftMargin, doc.rightMargin
    footer_y  = doc.bottomMargin - 10 * mm

    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(lm, footer_y + 6 * mm, page_w - rm, footer_y + 6 * mm)

    year = _date.today().year
    canvas.setFont('Helvetica', 6.5)
    canvas.setFillColor(HexColor('#888888'))
    canvas.drawCentredString(
        page_w / 2, footer_y + 2 * mm,
        f'Remote Team Solutions  |  Internal Copyright © {year}. All Rights Reserved.'
    )
    canvas.drawRightString(page_w - rm, footer_y + 2 * mm,
                           f'Página {canvas.getPageNumber()}')
    canvas.restoreState()


# ── Header ────────────────────────────────────────────────────────────────────
def _build_header(styles, usable_w):
    if os.path.exists(_LOGO):
        logo = Image(_LOGO, width=5.2 * cm, height=1.8 * cm)
        logo.hAlign = 'LEFT'
    else:
        logo = Paragraph('', styles['cell'])

    title_block = [
        Paragraph('ACTA DE ENTREGA-RECEPCIÓN DE EQUIPO', styles['doc_title']),
        Paragraph('Offboarding / Baja de Colaborador', styles['subtitle']),
    ]
    tbl = Table([[logo, title_block]],
                colWidths=[5.8 * cm, usable_w - 5.8 * cm])
    tbl.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
    ]))
    return tbl


# ── Info del empleado ─────────────────────────────────────────────────────────
def _build_emp_info(employee, offboarding_date, reason_label, styles, usable_w):
    rows = [
        [Paragraph('COLABORADOR:', styles['emp_bold']),
         Paragraph(employee.name.upper(), styles['emp_info']),
         Paragraph('ID:', styles['emp_bold']),
         Paragraph(employee.employee_id, styles['emp_info'])],
        [Paragraph('DEPARTAMENTO:', styles['emp_bold']),
         Paragraph(employee.department or '—', styles['emp_info']),
         Paragraph('FECHA DE BAJA:', styles['emp_bold']),
         Paragraph(offboarding_date.strftime('%d/%m/%Y'), styles['emp_info'])],
        [Paragraph('MOTIVO:', styles['emp_bold']),
         Paragraph(reason_label, styles['emp_info']),
         '', ''],
    ]
    cw = [usable_w * 0.18, usable_w * 0.32, usable_w * 0.18, usable_w * 0.32]
    tbl = Table(rows, colWidths=cw)
    tbl.setStyle(TableStyle([
        ('FONTNAME',      (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 0), (-1, -1), 9),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND',    (0, 0), (-1, -1), DARK_LT),
        ('GRID',          (0, 0), (-1, -1), 0.4, BORDER),
        ('SPAN',          (1, 2), (3, 2)),   # motivo spans 3 cols
    ]))
    return tbl


# ── Tabla de activos con depreciación ─────────────────────────────────────────
def _build_asset_table(asset_entries: list, styles, usable_w: float):
    """
    asset_entries: list of dicts:
        asset        Asset model instance
        condition    'bueno' | 'dano'
        damage_notes str (descripción del daño)
        depr         dict from calc_depreciation()
    """
    hdrs = [
        'EQUIPO / MODELO', 'NO. SERIE', 'COSTO\nORIGINAL',
        'AÑOS\nUSO', 'DEPREC.\nACUM.', 'VALOR\nACTUAL', 'CONDICIÓN',
    ]
    cw = [
        usable_w * 0.26,   # equipo
        usable_w * 0.13,   # serie
        usable_w * 0.11,   # costo orig
        usable_w * 0.07,   # años
        usable_w * 0.09,   # deprec %
        usable_w * 0.11,   # valor actual
        usable_w * 0.23,   # condición
    ]

    data = [[Paragraph(h, styles['cell_hdr_sm']) for h in hdrs]]

    total_orig    = 0.0
    total_current = 0.0
    total_damage  = 0.0

    for entry in asset_entries:
        asset  = entry['asset']
        depr   = entry['depr']
        cond   = entry['condition']
        dnotes = entry['damage_notes'] or ''

        equipo  = _TYPE_LABELS.get(asset.asset_type or '', 'Equipo')
        marca   = (asset.brand.name if getattr(asset, 'brand_id', None) and asset.brand
                   else getattr(asset, 'manufacturer', None) or '')
        modelo  = asset.model or ''
        nombre  = asset.name or equipo
        line1   = nombre
        line2   = f'{marca} {modelo}'.strip() if (marca or modelo) else ''
        eq_text = line1 + (f'<br/><font size="6" color="#777777">{line2}</font>' if line2 else '')

        cost    = asset.purchase_cost or 0.0
        curr    = depr['current_value']
        total_orig    += cost
        total_current += curr

        cond_style = styles['dmg'] if cond == 'dano' else styles['ok']
        cond_text  = 'CON DAÑO' if cond == 'dano' else 'BUEN ESTADO'
        if cond == 'dano' and dnotes:
            cond_text += f'<br/><font size="6" color="#C0392B">{dnotes[:60]}</font>'
            total_damage += curr

        data.append([
            Paragraph(eq_text,                         styles['cell']),
            Paragraph(asset.serial_number or '—',      styles['cell_c']),
            Paragraph(f'${cost:,.2f}' if cost else '—', styles['cell_r']),
            Paragraph(f'{depr["years"]:.1f}',          styles['cell_c']),
            Paragraph(f'{depr["depr_pct"]:.0f}%',      styles['cell_c']),
            Paragraph(f'${curr:,.2f}' if cost else '—', styles['cell_r']),
            Paragraph(cond_text,                       cond_style),
        ])

    n = len(data)

    # ── Fila totales originales / actuales
    data.append([
        Paragraph('TOTALES', styles['total_lbl']),
        '', '',
        '',
        '',
        Paragraph(f'${total_current:,.2f}', styles['total_val']),
        Paragraph(f'Original: ${total_orig:,.2f}', styles['cell_r']),
    ])

    # ── Fila responsabilidad por daños (solo si hay daños)
    if total_damage > 0:
        data.append([
            Paragraph('RESPONSABILIDAD POR DAÑOS', styles['total_lbl']),
            '', '', '', '',
            Paragraph(f'${total_damage:,.2f}', styles['warn_val']),
            Paragraph('Valor depreciado\na cubrir', styles['cell_c']),
        ])

    total_rows = len(data) - n   # 1 or 2

    tbl = Table(data, colWidths=cw, repeatRows=1)

    base_style = [
        ('FONTNAME',      (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 0), (-1, -1), 7.5),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        # Header
        ('BACKGROUND',    (0, 0), (-1, 0), DARK),
        ('TEXTCOLOR',     (0, 0), (-1, 0), white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
        # Grid data rows
        ('GRID',          (0, 0), (-1, n - 1), 0.4, BORDER),
        ('ROWBACKGROUNDS',(0, 1), (-1, n - 1), [GRAY_ROW, colors.white]),
        # Total row 1
        ('SPAN',          (0, n), (4, n)),
        ('BACKGROUND',    (0, n), (4, n), DARK_LT),
        ('BACKGROUND',    (5, n), (5, n), DARK),
        ('FONTNAME',      (0, n), (-1, n), 'Helvetica-Bold'),
        ('GRID',          (0, n), (-1, n), 0.4, BORDER),
        ('TOPPADDING',    (0, n), (-1, n), 6),
        ('BOTTOMPADDING', (0, n), (-1, n), 6),
    ]

    if total_damage > 0:
        r = n + 1
        base_style += [
            ('SPAN',          (0, r), (4, r)),
            ('BACKGROUND',    (0, r), (4, r), WARN_LT),
            ('BACKGROUND',    (5, r), (5, r), WARN),
            ('TEXTCOLOR',     (5, r), (5, r), white),
            ('FONTNAME',      (0, r), (-1, r), 'Helvetica-Bold'),
            ('GRID',          (0, r), (-1, r), 0.4, BORDER),
            ('TOPPADDING',    (0, r), (-1, r), 6),
            ('BOTTOMPADDING', (0, r), (-1, r), 6),
        ]

    tbl.setStyle(TableStyle(base_style))
    return tbl, total_orig, total_current, total_damage


# ── Firmas ────────────────────────────────────────────────────────────────────
def _build_signatures(employee_name: str, styles, usable_w: float):
    hr = HRFlowable(width='80%', thickness=0.8, color=HexColor('#888888'), hAlign='CENTER')

    def col(name, roles):
        items = [Spacer(1, 1.6 * cm), hr, Spacer(1, 3),
                 Paragraph(name, styles['sig_name'])]
        for r in roles:
            items.append(Paragraph(r, styles['sig_role']))
        return items

    cols = [
        col(employee_name.upper(),
            ['COLABORADOR', 'Entrega equipo(s) listado(s) en este documento']),
        col('PEDRO ANTONIO BARBOGLIO MURRA',
            ['DIRECCIÓN GENERAL', 'Autoriza baja del colaborador']),
        col('RESPONSABLE IT / RRHH',
            ['DEPARTAMENTO IT / RECURSOS HUMANOS', 'Recibe equipo(s) y valida condición']),
    ]

    w3 = usable_w / 3
    sig_tbl = Table([cols], colWidths=[w3, w3, w3])
    sig_tbl.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
    ]))
    return sig_tbl


# ── Función principal ─────────────────────────────────────────────────────────
_BODY_TEXT = (
    "El colaborador identificado en el presente documento declara haber entregado el equipo descrito "
    "en buen estado de funcionamiento, salvo las observaciones indicadas en la columna de condición. "
    "Los bienes son propiedad exclusiva de <b>Remote Team Solutions</b> y fueron asignados únicamente "
    "para el ejercicio de sus funciones laborales. El colaborador reconoce que el valor de depreciación "
    "indicado fue calculado con base en la tasa establecida por el artículo 40 de la Ley del Impuesto "
    "Sobre la Renta (LISR). En caso de daño atribuible al colaborador, el monto de responsabilidad "
    "corresponde al valor en libros del activo a la fecha de entrega, según lo establecido en el "
    "artículo 134 fracción VI de la Ley Federal del Trabajo. La firma del presente documento libera "
    "al colaborador de responsabilidad sobre los activos aquí listados a partir de la fecha de entrega."
)


def generate_offboarding_pdf(employee, asset_entries: list,
                              offboarding_date=None, reason: str = 'otro') -> io.BytesIO:
    """
    Genera el Acta de Entrega-Recepción como PDF.

    Parameters
    ----------
    employee         : instancia Employee
    asset_entries    : list of dicts {asset, condition, damage_notes, depr}
    offboarding_date : datetime.date — por defecto hoy
    reason           : slug del motivo (ver OFFBOARDING_REASONS)
    """
    if offboarding_date is None:
        offboarding_date = _date.today()
    if hasattr(offboarding_date, 'year') and offboarding_date.year < 2000:
        offboarding_date = _date.today()

    reason_label = dict(OFFBOARDING_REASONS).get(reason, reason)

    buf    = io.BytesIO()
    margin = 2.0 * cm
    foot_h = 14 * mm

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
        title='Acta de Entrega-Recepción de Equipo',
        author='Remote Team Solutions',
        subject=f'Offboarding — {employee.name}',
        creator='RTS Intranet',
    )
    doc.addPageTemplates([
        PageTemplate(id='offboarding', frames=[main_frame], onPage=_draw_footer)
    ])

    st = _styles()
    date_str = (f"Torreón, Coahuila, a {offboarding_date.day} de "
                f"{_MONTHS_ES[offboarding_date.month]} de {offboarding_date.year}")

    asset_tbl, total_orig, total_curr, total_dmg = _build_asset_table(
        asset_entries, st, usable_w)

    # Spacer dinámico para empujar firmas al fondo
    frame_h    = page_h - 2 * margin - foot_h
    est_used   = (2.2 + 0.5 + 0.8 + 1.2 + (len(asset_entries) + 2) * 0.65
                  + (0.65 if total_dmg > 0 else 0) + 3.5 + 4.5) * cm
    push       = max(frame_h - est_used, 0.6 * cm)

    story = [
        _build_header(st, usable_w),
        HRFlowable(width='100%', thickness=2.5, color=DARK, spaceBefore=2, spaceAfter=6),
        Paragraph(date_str, st['date']),
        Spacer(1, 4),
        _build_emp_info(employee, offboarding_date, reason_label, st, usable_w),
        Spacer(1, 8),
        Paragraph('RELACIÓN DE ACTIVOS ENTREGADOS', st['section']),
        asset_tbl,
        Spacer(1, 6),
        Paragraph(_BODY_TEXT, st['body']),
        Spacer(1, push),
        KeepTogether(_build_signatures(employee.name, st, usable_w)),
    ]

    doc.build(story)
    buf.seek(0)
    return buf
