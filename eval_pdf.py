"""
Generador de PDF — Evaluación de Desempeño RTS
Basado en: Reporte_Desempeño_nombre_2025.docx  (A4 landscape)
"""
from __future__ import annotations
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.colors import HexColor

# ── Paleta RTS ─────────────────────────────────────────────────────────────
NAVY   = HexColor('#1A2E5A')
BLUE   = HexColor('#089ACF')
GRAY   = HexColor('#6c757d')
LGRAY  = HexColor('#f0f4f8')
WHITE  = colors.white
BLACK  = colors.black
GREEN  = HexColor('#28a745')
ORANGE = HexColor('#fd7e14')
RED    = HexColor('#dc3545')

SCORE_COLORS = {5: GREEN, 4: BLUE, 3: HexColor('#6f42c1'), 2: ORANGE, 1: RED}

PAGE_W, PAGE_H = landscape(A4)
MARGIN = 1.5 * cm
USABLE_W = PAGE_W - 2 * MARGIN


def _styles():
    return {
        'title': ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=14,
                                textColor=NAVY, alignment=TA_CENTER, spaceAfter=4),
        'hdr': ParagraphStyle('hdr', fontName='Helvetica-Bold', fontSize=7,
                              textColor=WHITE, alignment=TA_CENTER),
        'hdr_left': ParagraphStyle('hdr_left', fontName='Helvetica-Bold', fontSize=7,
                                   textColor=WHITE, alignment=TA_LEFT),
        'label': ParagraphStyle('label', fontName='Helvetica-Bold', fontSize=7,
                                textColor=GRAY),
        'val': ParagraphStyle('val', fontName='Helvetica', fontSize=8,
                              textColor=BLACK),
        'val_bold': ParagraphStyle('val_bold', fontName='Helvetica-Bold', fontSize=9,
                                   textColor=NAVY),
        'cell': ParagraphStyle('cell', fontName='Helvetica', fontSize=7,
                               textColor=BLACK, leading=9),
        'cell_bold': ParagraphStyle('cell_bold', fontName='Helvetica-Bold', fontSize=7,
                                    textColor=NAVY, leading=9),
        'small': ParagraphStyle('small', fontName='Helvetica', fontSize=6.5,
                                textColor=GRAY, leading=8),
        'center': ParagraphStyle('center', fontName='Helvetica', fontSize=8,
                                 alignment=TA_CENTER),
        'center_bold': ParagraphStyle('center_bold', fontName='Helvetica-Bold',
                                      fontSize=9, alignment=TA_CENTER, textColor=NAVY),
    }


def _score_label(s, labels):
    if s is None:
        return '—'
    try:
        return f"{int(s)} – {labels.get(int(s), '')}"
    except Exception:
        return str(s)


def _draw_page(canvas, doc):
    """Footer con página."""
    canvas.saveState()
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(GRAY)
    canvas.drawRightString(PAGE_W - MARGIN, 0.6 * cm,
                           f'Página {doc.page}  |  Evaluación de Desempeño — RTS')
    canvas.restoreState()


def generate_eval_pdf(ev, score_labels: dict) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
    )

    st  = _styles()
    W   = USABLE_W
    story = []

    # ── TÍTULO ────────────────────────────────────────────────
    story.append(Paragraph(f'EVALUACIÓN DEL DESEMPEÑO {ev.period}', st['title']))
    story.append(Spacer(1, 4))

    # ── DATOS DEL EMPLEADO ────────────────────────────────────
    today_str = date.today().strftime('%d/%m/%Y')
    emp_data = [
        [Paragraph('<b>EMPLEADO:</b>', st['label']),
         Paragraph(ev.evaluatee.name, st['val_bold']),
         Paragraph('<b>JEFE INMEDIATO:</b>', st['label']),
         Paragraph(ev.chief.name, st['val'])],
        [Paragraph('<b>PUESTO:</b>', st['label']),
         Paragraph(getattr(ev.evaluatee, 'position', '') or '—', st['val']),
         Paragraph('<b>DEPARTAMENTO:</b>', st['label']),
         Paragraph(getattr(ev.evaluatee, 'department', '') or '—', st['val'])],
        [Paragraph('<b>EMPRESA:</b>', st['label']),
         Paragraph(ev.empresa or 'Remote Team Solutions', st['val']),
         Paragraph('<b>LOCALIDAD:</b>', st['label']),
         Paragraph(ev.localidad or '—', st['val'])],
        [Paragraph('<b>NIVEL:</b>', st['label']),
         Paragraph(ev.nivel or '—', st['val']),
         Paragraph('<b>FECHA:</b>', st['label']),
         Paragraph(today_str, st['val'])],
    ]
    cw_emp = [W * 0.12, W * 0.38, W * 0.12, W * 0.38]
    emp_tbl = Table(emp_data, colWidths=cw_emp)
    emp_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LGRAY),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [WHITE, LGRAY]),
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#dee2e6')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(emp_tbl)
    story.append(Spacer(1, 6))

    # ── ESCALA DE VALORACIÓN ──────────────────────────────────
    scale_data = [[
        Paragraph('<b>ESCALAS DE VALORACIÓN</b>', st['hdr'])
    ]]
    scale_tbl = Table(scale_data, colWidths=[W])
    scale_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(scale_tbl)

    scale_vals = [[
        Paragraph('<b>5. Sobresaliente</b>', st['center_bold']),
        Paragraph('<b>4. Notable</b>', st['center_bold']),
        Paragraph('<b>3. Adecuado</b>', st['center_bold']),
        Paragraph('<b>2. Deficiente</b>', st['center_bold']),
        Paragraph('<b>1. Insuficiente</b>', st['center_bold']),
    ]]
    scale_v_tbl = Table(scale_vals, colWidths=[W / 5] * 5)
    scale_v_tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, GRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND', (0, 0), (-1, -1), LGRAY),
    ]))
    story.append(scale_v_tbl)
    story.append(Spacer(1, 6))

    # ── OBJETIVOS ─────────────────────────────────────────────
    obj_hdr = [[
        Paragraph('<b>OBJETIVOS</b>', st['hdr_left']),
        Paragraph('<b>PESO</b>', st['hdr']),
        Paragraph('<b>PERÍODO</b>', st['hdr']),
        Paragraph('<b>EVAL. EMPLEADO</b>', st['hdr']),
        Paragraph('<b>EVAL. JEFE</b>', st['hdr']),
        Paragraph('<b>COMENTARIOS</b>', st['hdr']),
    ]]
    cw_obj = [W * 0.34, W * 0.07, W * 0.09, W * 0.11, W * 0.11, W * 0.28]
    obj_rows = []
    for g in ev.goals:
        cat  = f'<font color="#089ACF"><b>{g.category}</b></font> — ' if g.category else ''
        desc = Paragraph(cat + (g.description or ''), st['cell'])
        obj_rows.append([
            desc,
            Paragraph(f'{g.weight}%', st['center']),
            Paragraph(g.period or '—', st['center']),
            Paragraph(_score_label(g.employee_score, score_labels), st['center']),
            Paragraph(_score_label(g.chief_score, score_labels), st['center']),
            Paragraph(g.comments or '', st['small']),
        ])

    # Fila promedio
    ga  = ev.goals_avg
    ega = ev.employee_goals_avg
    obj_rows.append([
        Paragraph('<b>PROMEDIO OBJETIVOS:</b>', st['cell_bold']),
        '', '',
        Paragraph(str(ega) if ega else '—', st['center_bold']),
        Paragraph(str(ga) if ga else '—', st['center_bold']),
        '',
    ])

    obj_data = obj_hdr + obj_rows
    obj_tbl  = Table(obj_data, colWidths=cw_obj, repeatRows=1)
    obj_style = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [WHITE, LGRAY]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8f3fa')),
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#dee2e6')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, -1), (2, -1)),
    ]
    obj_tbl.setStyle(TableStyle(obj_style))
    story.append(obj_tbl)
    story.append(Spacer(1, 6))

    # ── COMPETENCIAS ──────────────────────────────────────────
    comp_hdr = [[
        Paragraph('<b>HABILIDADES / COMPETENCIAS</b>', st['hdr_left']),
        Paragraph('<b>CONDUCTA ACTUAL</b>', st['hdr_left']),
        Paragraph('<b>AUTO-EVAL.</b>', st['hdr']),
        Paragraph('<b>EVAL. JEFE</b>', st['hdr']),
    ]]
    cw_comp = [W * 0.20, W * 0.54, W * 0.13, W * 0.13]
    comp_rows = []
    for c in ev.competencies:
        comp_rows.append([
            Paragraph(f'<b>{c.name}</b>', st['cell_bold']),
            Paragraph(c.description or '', st['small']),
            Paragraph(_score_label(c.employee_score, score_labels), st['center']),
            Paragraph(_score_label(c.chief_score, score_labels), st['center']),
        ])

    ca  = ev.competencies_avg
    eca = ev.employee_competencies_avg
    comp_rows.append([
        Paragraph('<b>PROMEDIO COMPETENCIAS:</b>', st['cell_bold']),
        '',
        Paragraph(str(eca) if eca else '—', st['center_bold']),
        Paragraph(str(ca) if ca else '—', st['center_bold']),
    ])

    comp_data = comp_hdr + comp_rows
    comp_tbl  = Table(comp_data, colWidths=cw_comp, repeatRows=1)
    comp_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [WHITE, LGRAY]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8f3fa')),
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#dee2e6')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, -1), (1, -1)),
    ]))
    story.append(comp_tbl)
    story.append(Spacer(1, 6))

    # ── CONOCIMIENTO / EXPERIENCIA ────────────────────────────
    ke_hdr = [[
        Paragraph('<b>EVALUACIÓN</b>', st['hdr_left']),
        Paragraph('<b>SCORE</b>', st['hdr']),
        Paragraph('<b>NIVEL</b>', st['hdr']),
    ]]
    kn = ev.knowledge_score
    ex = ev.experience_score
    ke_rows = [
        [Paragraph('Evaluación de Conocimientos Técnicos y Educación', st['cell']),
         Paragraph(str(int(kn)) if kn else '—', st['center_bold']),
         Paragraph(score_labels.get(int(kn), '—') if kn else '—', st['center'])],
        [Paragraph('Evaluación de Experiencia', st['cell']),
         Paragraph(str(int(ex)) if ex else '—', st['center_bold']),
         Paragraph(score_labels.get(int(ex), '—') if ex else '—', st['center'])],
    ]
    ke_data = ke_hdr + ke_rows
    cw_ke   = [W * 0.60, W * 0.15, W * 0.25]
    ke_tbl  = Table(ke_data, colWidths=cw_ke)
    ke_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LGRAY]),
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#dee2e6')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(ke_tbl)
    story.append(Spacer(1, 6))

    # ── EVALUACIÓN GLOBAL ─────────────────────────────────────
    fs    = ev.final_score
    level = ev.level_label

    global_hdr = [[
        Paragraph('<b>EVALUACIÓN GLOBAL DE DESEMPEÑO</b>', st['hdr_left']),
        Paragraph('<b>RESULTADO</b>', st['hdr']),
        Paragraph('<b>× FACTOR PONDERACIÓN</b>', st['hdr']),
        Paragraph('<b>RESULTADO FINAL</b>', st['hdr']),
    ]]
    cw_gl  = [W * 0.55, W * 0.15, W * 0.15, W * 0.15]

    def _fmt(v):
        return f'{v:.2f}' if v is not None else '—'

    global_rows = [
        [Paragraph('Cumplimiento de Objetivos', st['cell']),
         Paragraph(_fmt(ga), st['center_bold']),
         Paragraph('0.65', st['center']),
         Paragraph(_fmt(ga * 0.65 if ga else None), st['center_bold'])],
        [Paragraph('Desempeño por Habilidades / Competencias', st['cell']),
         Paragraph(_fmt(ca), st['center_bold']),
         Paragraph('0.15', st['center']),
         Paragraph(_fmt(ca * 0.15 if ca else None), st['center_bold'])],
        [Paragraph('Evaluación de Conocimientos Técnicos y Educación', st['cell']),
         Paragraph(_fmt(kn), st['center_bold']),
         Paragraph('0.10', st['center']),
         Paragraph(_fmt(kn * 0.10 if kn else None), st['center_bold'])],
        [Paragraph('Evaluación de Experiencia', st['cell']),
         Paragraph(_fmt(ex), st['center_bold']),
         Paragraph('0.10', st['center']),
         Paragraph(_fmt(ex * 0.10 if ex else None), st['center_bold'])],
        # Suma final
        [Paragraph('<b>SUMA FINAL:</b>', st['cell_bold']),
         '', '',
         Paragraph(f'<b>{_fmt(fs)}</b>', ParagraphStyle('big', fontName='Helvetica-Bold',
                   fontSize=12, alignment=TA_CENTER, textColor=NAVY))],
        # Nivel
        [Paragraph('<b>NIVEL DE COMPETENCIA:</b>', st['cell_bold']),
         '', '',
         Paragraph(f'<b>{level}</b>', ParagraphStyle('lvl', fontName='Helvetica-Bold',
                   fontSize=11, alignment=TA_CENTER, textColor=NAVY))],
    ]

    global_data = global_hdr + global_rows
    global_tbl  = Table(global_data, colWidths=cw_gl)
    global_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -3), [WHITE, LGRAY]),
        ('BACKGROUND', (0, -2), (-1, -1), colors.HexColor('#e8f3fa')),
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#dee2e6')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, -2), (2, -2)),
        ('SPAN', (0, -1), (2, -1)),
    ]))
    story.append(global_tbl)
    story.append(Spacer(1, 10))

    # ── FIRMAS ────────────────────────────────────────────────
    sig_hdr = [[Paragraph('<b>FIRMAS</b>', st['hdr'])]]
    sig_hdr_tbl = Table(sig_hdr, colWidths=[W])
    sig_hdr_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(sig_hdr_tbl)

    sig_labels = ['EMPLEADO', 'JEFE INMEDIATO', 'GERENTE DE ÁREA', 'REC. HUMANOS']
    sig_data   = [
        [Paragraph('', st['center'])] * 4,   # espacio para firma
        [Paragraph(f'<b>{l}</b>', st['center']) for l in sig_labels],
    ]
    sig_tbl = Table(sig_data, colWidths=[W / 4] * 4, rowHeights=[1.8 * cm, 0.5 * cm])
    sig_tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, GRAY),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, BLACK),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
    ]))
    story.append(sig_tbl)

    doc.build(story, onFirstPage=_draw_page, onLaterPages=_draw_page)
    buf.seek(0)
    return buf
