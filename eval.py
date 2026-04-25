"""
Módulo de Evaluación de Desempeño — RTS Intranet
Flujo:
  1. Jefe crea evaluación (draft): define objetivos, pesos, período.
  2. Jefe la abre (open): el evaluado puede auto-evaluarse.
  3. Evaluado llena sus scores (employee_score).
  4. Jefe llena sus scores (chief_score) + conocimiento/experiencia.
  5. Jefe completa (completed): ambos pueden descargar PDF.
"""
from __future__ import annotations

from datetime import datetime, date

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, send_file, abort)

from auth import module_required
from models import (db, User, Evaluation, EvaluationGoal, EvaluationCompetency,
                    EVAL_COMPETENCIES, EVAL_SCORE_LABELS)

eval_bp = Blueprint('eval', __name__, url_prefix='/evaluation')


# ── Helpers ───────────────────────────────────────────────────────────────────

def _uid():
    return session.get('user', {}).get('id')

def _is_admin():
    return session.get('user', {}).get('role') == 'admin'

def _can_view(ev):
    uid = _uid()
    return _is_admin() or ev.evaluatee_id == uid or ev.chief_id == uid

def _is_chief(ev):
    return ev.chief_id == _uid() or _is_admin()

def _is_evaluatee(ev):
    return ev.evaluatee_id == _uid()

def _save_goals(ev, form):
    categories   = form.getlist('goal_category')
    descriptions = form.getlist('goal_description')
    weights      = form.getlist('goal_weight')
    periods      = form.getlist('goal_period')
    for i, (cat, desc, wt, per) in enumerate(
            zip(categories, descriptions, weights, periods), start=1):
        if not desc.strip():
            continue
        try:
            wt_int = int(wt) if wt else 0
        except ValueError:
            wt_int = 0
        db.session.add(EvaluationGoal(
            evaluation_id=ev.id, order=i,
            category=cat.strip() or None,
            description=desc.strip(),
            weight=wt_int,
            period=per.strip() or None,
        ))


# ── LIST ──────────────────────────────────────────────────────────────────────

@eval_bp.route('/')
@module_required('evaluation')
def index():
    uid = _uid()
    if _is_admin():
        evals = Evaluation.query.order_by(Evaluation.created_at.desc()).all()
    else:
        evals = Evaluation.query.filter(
            db.or_(Evaluation.evaluatee_id == uid, Evaluation.chief_id == uid)
        ).order_by(Evaluation.created_at.desc()).all()

    total   = len(evals)
    pending = sum(1 for e in evals if e.status in ('draft', 'open'))
    done    = sum(1 for e in evals if e.status == 'completed')

    return render_template('eval/list.html',
                           evals=evals, total=total,
                           pending=pending, done=done,
                           SCORE_LABELS=EVAL_SCORE_LABELS)


# ── CREATE ────────────────────────────────────────────────────────────────────

@eval_bp.route('/new', methods=['GET', 'POST'])
@module_required('evaluation')
def new_eval():
    users = User.query.filter_by(active=True).order_by(User.name).all()
    if request.method == 'POST':
        evaluatee_id = request.form.get('evaluatee_id', type=int)
        chief_id     = request.form.get('chief_id', type=int)
        if not evaluatee_id or not chief_id:
            flash('Selecciona evaluado y jefe inmediato.', 'danger')
            return render_template('eval/form.html', users=users, form=request.form, ev=None)

        ev = Evaluation(
            evaluatee_id=evaluatee_id,
            chief_id=chief_id,
            period=request.form.get('period', '').strip() or str(date.today().year),
            empresa=request.form.get('empresa', '').strip() or None,
            localidad=request.form.get('localidad', '').strip() or None,
            nivel=request.form.get('nivel', '').strip() or None,
            status='draft',
        )
        db.session.add(ev)
        db.session.flush()

        # Seed competencies
        for i, (name, desc) in enumerate(EVAL_COMPETENCIES, start=1):
            db.session.add(EvaluationCompetency(
                evaluation_id=ev.id, order=i, name=name, description=desc))

        _save_goals(ev, request.form)
        db.session.commit()
        flash('Evaluación creada en borrador. Agrega/edita objetivos y luego ábrela.', 'success')
        return redirect(url_for('eval.edit_eval', id=ev.id))

    return render_template('eval/form.html', users=users, form={}, ev=None)


# ── EDIT GOALS (draft only) ───────────────────────────────────────────────────

@eval_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@module_required('evaluation')
def edit_eval(id):
    ev = Evaluation.query.get_or_404(id)
    if not _is_chief(ev):
        abort(403)
    if ev.status not in ('draft',):
        flash('Solo editable en estado Borrador.', 'warning')
        return redirect(url_for('eval.detail', id=id))

    users = User.query.filter_by(active=True).order_by(User.name).all()
    if request.method == 'POST':
        ev.period       = request.form.get('period', '').strip() or ev.period
        ev.empresa      = request.form.get('empresa', '').strip() or None
        ev.localidad    = request.form.get('localidad', '').strip() or None
        ev.nivel        = request.form.get('nivel', '').strip() or None
        ev.evaluatee_id = request.form.get('evaluatee_id', type=int) or ev.evaluatee_id
        ev.chief_id     = request.form.get('chief_id', type=int) or ev.chief_id
        ev.updated_at   = datetime.utcnow()

        for g in list(ev.goals):
            db.session.delete(g)
        db.session.flush()
        _save_goals(ev, request.form)
        db.session.commit()
        flash('Evaluación actualizada.', 'success')
        return redirect(url_for('eval.edit_eval', id=id))

    return render_template('eval/form.html', users=users, form={}, ev=ev)


# ── OPEN ──────────────────────────────────────────────────────────────────────

@eval_bp.route('/<int:id>/open', methods=['POST'])
@module_required('evaluation')
def open_eval(id):
    ev = Evaluation.query.get_or_404(id)
    if not _is_chief(ev):
        abort(403)
    if not ev.goals:
        flash('Agrega al menos un objetivo antes de abrir la evaluación.', 'warning')
        return redirect(url_for('eval.edit_eval', id=id))
    ev.status = 'open'
    ev.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Evaluación abierta. El evaluado ya puede llenar su auto-evaluación.', 'success')
    return redirect(url_for('eval.detail', id=id))


# ── DETAIL / FILL ─────────────────────────────────────────────────────────────

@eval_bp.route('/<int:id>', methods=['GET', 'POST'])
@module_required('evaluation')
def detail(id):
    ev = Evaluation.query.get_or_404(id)
    if not _can_view(ev):
        abort(403)

    is_chief    = _is_chief(ev)
    is_employee = _is_evaluatee(ev)

    if request.method == 'POST' and ev.status == 'open':
        action = request.form.get('action', '')

        if is_employee and action in ('save_employee', 'submit_employee'):
            for g in ev.goals:
                val = request.form.get(f'emp_goal_{g.id}')
                g.employee_score = int(val) if val and val.isdigit() else None
            for c in ev.competencies:
                val = request.form.get(f'emp_comp_{c.id}')
                c.employee_score = int(val) if val and val.isdigit() else None
            if action == 'submit_employee':
                ev.employee_submitted_at = datetime.utcnow()
                flash('Auto-evaluación enviada. ✅', 'success')
            else:
                flash('Auto-evaluación guardada.', 'info')
            ev.updated_at = datetime.utcnow()
            db.session.commit()

        if is_chief and action in ('save_chief', 'complete'):
            for g in ev.goals:
                val = request.form.get(f'chief_goal_{g.id}')
                g.chief_score = int(val) if val and val.isdigit() else None
                g.comments    = request.form.get(f'comments_{g.id}', '').strip() or None
            for c in ev.competencies:
                val = request.form.get(f'chief_comp_{c.id}')
                c.chief_score = int(val) if val and val.isdigit() else None
            kn = request.form.get('knowledge_score')
            ex = request.form.get('experience_score')
            ev.knowledge_score  = float(kn) if kn else None
            ev.experience_score = float(ex) if ex else None
            if action == 'complete':
                ev.chief_submitted_at = datetime.utcnow()
                ev.status = 'completed'
                flash('Evaluación completada. Pueden descargar el PDF. 🎉', 'success')
            else:
                flash('Evaluación del jefe guardada.', 'info')
            ev.updated_at = datetime.utcnow()
            db.session.commit()

        return redirect(url_for('eval.detail', id=id))

    return render_template('eval/detail.html',
                           ev=ev, is_chief=is_chief, is_employee=is_employee,
                           SCORE_LABELS=EVAL_SCORE_LABELS,
                           today=date.today())


# ── REOPEN ────────────────────────────────────────────────────────────────────

@eval_bp.route('/<int:id>/reopen', methods=['POST'])
@module_required('evaluation')
def reopen_eval(id):
    ev = Evaluation.query.get_or_404(id)
    if not _is_chief(ev):
        abort(403)
    ev.status = 'open'
    ev.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Evaluación re-abierta para correcciones.', 'info')
    return redirect(url_for('eval.detail', id=id))


# ── DELETE ────────────────────────────────────────────────────────────────────

@eval_bp.route('/<int:id>/delete', methods=['POST'])
@module_required('evaluation')
def delete_eval(id):
    ev = Evaluation.query.get_or_404(id)
    if not (_is_chief(ev) or _is_admin()):
        abort(403)
    db.session.delete(ev)
    db.session.commit()
    flash('Evaluación eliminada.', 'warning')
    return redirect(url_for('eval.index'))


# ── PDF ───────────────────────────────────────────────────────────────────────

@eval_bp.route('/<int:id>/pdf')
@module_required('evaluation')
def download_pdf(id):
    ev = Evaluation.query.get_or_404(id)
    if not _can_view(ev):
        abort(403)
    from eval_pdf import generate_eval_pdf
    buf   = generate_eval_pdf(ev, EVAL_SCORE_LABELS)
    fname = f'Evaluacion_{ev.evaluatee.name.replace(" ", "_")}_{ev.period}.pdf'
    return send_file(buf, as_attachment=True, download_name=fname,
                     mimetype='application/pdf')
