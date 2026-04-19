from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify)
from models import db, Project, Task, ProjectMember, User, Client, log_action
from auth import module_required, login_required
from datetime import datetime, date

projects_bp = Blueprint('projects', __name__, url_prefix='/projects')

# ── Helpers ───────────────────────────────────────────────────────────────────

PROJECT_STATUS_LABELS = {
    'planning':  'Planeación',
    'active':    'Activo',
    'on_hold':   'En Pausa',
    'completed': 'Completado',
    'cancelled': 'Cancelado',
}

PROJECT_STATUS_BADGES = {
    'planning':  'secondary',
    'active':    'primary',
    'on_hold':   'warning',
    'completed': 'success',
    'cancelled': 'danger',
}

TASK_STATUS_LABELS = {
    'pending':     'Pendiente',
    'in_progress': 'En Progreso',
    'review':      'En Revisión',
    'done':        'Listo',
    'cancelled':   'Cancelado',
}

TASK_STATUS_BADGES = {
    'pending':     'secondary',
    'in_progress': 'primary',
    'review':      'warning',
    'done':        'success',
    'cancelled':   'danger',
}

PRIORITY_LABELS = {
    'low':      'Baja',
    'medium':   'Media',
    'high':     'Alta',
    'critical': 'Crítica',
}

PRIORITY_BADGES = {
    'low':      'success',
    'medium':   'info',
    'high':     'warning',
    'critical': 'danger',
}


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _auto_code():
    """Generate next available project code: PRJ-0001, PRJ-0002…"""
    last = Project.query.order_by(Project.id.desc()).first()
    num  = (last.id + 1) if last else 1
    return f'PRJ-{num:04d}'


# ── Dashboard ─────────────────────────────────────────────────────────────────

@projects_bp.route('/')
@module_required('projects')
def dashboard():
    today = date.today()

    total      = Project.query.count()
    active     = Project.query.filter_by(status='active').count()
    completed  = Project.query.filter_by(status='completed').count()
    on_hold    = Project.query.filter_by(status='on_hold').count()
    planning   = Project.query.filter_by(status='planning').count()
    cancelled  = Project.query.filter_by(status='cancelled').count()

    overdue = Project.query.filter(
        Project.end_date < today,
        Project.status.notin_(['completed', 'cancelled'])
    ).count()

    total_tasks    = Task.query.count()
    done_tasks     = Task.query.filter_by(status='done').count()
    pending_tasks  = Task.query.filter(Task.status.in_(['pending', 'in_progress', 'review'])).count()
    overdue_tasks  = Task.query.filter(
        Task.due_date < today,
        Task.status.notin_(['done', 'cancelled'])
    ).count()

    recent_projects = (Project.query
                       .order_by(Project.updated_at.desc())
                       .limit(8).all())

    my_id = session['user']['id']
    my_tasks = (Task.query
                .filter_by(assigned_to_id=my_id)
                .filter(Task.status.notin_(['done', 'cancelled']))
                .order_by(Task.due_date.asc().nullslast())
                .limit(10).all())

    # Projects by status for chart
    status_chart = {
        'labels': [PROJECT_STATUS_LABELS.get(s, s) for s in Project.STATUS_CHOICES],
        'data':   [Project.query.filter_by(status=s).count() for s in Project.STATUS_CHOICES],
    }

    return render_template('projects/dashboard.html',
        total=total, active=active, completed=completed,
        on_hold=on_hold, planning=planning, cancelled=cancelled,
        overdue=overdue, total_tasks=total_tasks,
        done_tasks=done_tasks, pending_tasks=pending_tasks,
        overdue_tasks=overdue_tasks,
        recent_projects=recent_projects,
        my_tasks=my_tasks,
        status_chart=status_chart,
        PROJECT_STATUS_LABELS=PROJECT_STATUS_LABELS,
        PROJECT_STATUS_BADGES=PROJECT_STATUS_BADGES,
        TASK_STATUS_LABELS=TASK_STATUS_LABELS,
        TASK_STATUS_BADGES=TASK_STATUS_BADGES,
        PRIORITY_LABELS=PRIORITY_LABELS,
        PRIORITY_BADGES=PRIORITY_BADGES,
    )


# ── Project List ──────────────────────────────────────────────────────────────

@projects_bp.route('/list')
@module_required('projects')
def project_list():
    q              = request.args.get('q', '')
    status_filter  = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    client_filter  = request.args.get('client_id', '')

    query = Project.query
    if q:
        query = query.filter(db.or_(
            Project.name.ilike(f'%{q}%'),
            Project.code.ilike(f'%{q}%'),
            Project.description.ilike(f'%{q}%'),
        ))
    if status_filter:
        query = query.filter_by(status=status_filter)
    if priority_filter:
        query = query.filter_by(priority=priority_filter)
    if client_filter:
        query = query.filter_by(client_id=client_filter)

    projects = query.order_by(Project.updated_at.desc()).all()
    clients  = Client.query.filter_by(active=True).order_by(Client.name).all()
    today    = date.today()

    return render_template('projects/list.html',
        projects=projects, clients=clients,
        q=q, status_filter=status_filter,
        priority_filter=priority_filter, client_filter=client_filter,
        today=today,
        PROJECT_STATUS_LABELS=PROJECT_STATUS_LABELS,
        PROJECT_STATUS_BADGES=PROJECT_STATUS_BADGES,
        PRIORITY_LABELS=PRIORITY_LABELS,
        PRIORITY_BADGES=PRIORITY_BADGES,
    )


# ── Project New ───────────────────────────────────────────────────────────────

@projects_bp.route('/new', methods=['GET', 'POST'])
@module_required('projects')
def project_new():
    clients = Client.query.filter_by(active=True).order_by(Client.name).all()
    users   = User.query.filter_by(active=True).order_by(User.name).all()

    if request.method == 'POST':
        code = request.form.get('code', '').strip() or _auto_code()
        if Project.query.filter_by(code=code).first():
            flash(f'El código de proyecto "{code}" ya existe.', 'danger')
            return render_template('projects/form.html', project=None,
                                   form=request.form, clients=clients, users=users)
        project = Project(
            code=code,
            name=request.form.get('name', '').strip(),
            description=request.form.get('description', '').strip() or None,
            client_id=request.form.get('client_id') or None,
            status=request.form.get('status', 'planning'),
            priority=request.form.get('priority', 'medium'),
            start_date=_parse_date(request.form.get('start_date')),
            end_date=_parse_date(request.form.get('end_date')),
            budget=float(request.form.get('budget')) if request.form.get('budget') else None,
            progress=int(request.form.get('progress', 0)),
            owner_id=request.form.get('owner_id') or session['user']['id'],
        )
        db.session.add(project)
        db.session.flush()  # get project.id

        # Add owner as manager member
        owner_member = ProjectMember(
            project_id=project.id,
            user_id=project.owner_id,
            role='manager',
        )
        db.session.add(owner_member)

        log_action('create', 'project', entity_name=project.name,
                   details=f'Código: {code} | Estado: {project.status} | Prioridad: {project.priority}')
        db.session.commit()
        flash(f'Proyecto "{project.name}" creado correctamente.', 'success')
        return redirect(url_for('projects.project_detail', id=project.id))

    suggested_code = _auto_code()
    return render_template('projects/form.html', project=None, form={},
                           clients=clients, users=users,
                           suggested_code=suggested_code)


# ── Project Detail ────────────────────────────────────────────────────────────

@projects_bp.route('/<int:id>')
@module_required('projects')
def project_detail(id):
    project  = Project.query.get_or_404(id)
    users    = User.query.filter_by(active=True).order_by(User.name).all()
    today    = date.today()

    # Task stats
    total_tasks   = len(project.tasks)
    done_tasks    = len([t for t in project.tasks if t.status == 'done'])
    open_tasks    = len([t for t in project.tasks if t.status not in ('done', 'cancelled')])
    overdue_tasks = len([t for t in project.tasks if t.is_overdue])
    calc_progress = int(done_tasks / total_tasks * 100) if total_tasks else 0

    # Members already in project
    member_user_ids = {m.user_id for m in project.members}
    available_users = [u for u in users if u.id not in member_user_ids]

    return render_template('projects/detail.html',
        project=project, users=users, today=today,
        total_tasks=total_tasks, done_tasks=done_tasks,
        open_tasks=open_tasks, overdue_tasks=overdue_tasks,
        calc_progress=calc_progress,
        available_users=available_users,
        member_user_ids=member_user_ids,
        PROJECT_STATUS_LABELS=PROJECT_STATUS_LABELS,
        PROJECT_STATUS_BADGES=PROJECT_STATUS_BADGES,
        TASK_STATUS_LABELS=TASK_STATUS_LABELS,
        TASK_STATUS_BADGES=TASK_STATUS_BADGES,
        PRIORITY_LABELS=PRIORITY_LABELS,
        PRIORITY_BADGES=PRIORITY_BADGES,
    )


# ── Project Edit ──────────────────────────────────────────────────────────────

@projects_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@module_required('projects')
def project_edit(id):
    project = Project.query.get_or_404(id)
    clients = Client.query.filter_by(active=True).order_by(Client.name).all()
    users   = User.query.filter_by(active=True).order_by(User.name).all()

    if request.method == 'POST':
        new_code = request.form.get('code', '').strip()
        existing = Project.query.filter_by(code=new_code).first()
        if existing and existing.id != project.id:
            flash(f'El código "{new_code}" ya existe en otro proyecto.', 'danger')
            return render_template('projects/form.html', project=project,
                                   form=request.form, clients=clients, users=users)
        changes = []
        if project.status != request.form.get('status'):
            changes.append(f'estado: {project.status} → {request.form.get("status")}')
        if project.priority != request.form.get('priority'):
            changes.append(f'prioridad: {project.priority} → {request.form.get("priority")}')

        project.code        = new_code
        project.name        = request.form.get('name', '').strip()
        project.description = request.form.get('description', '').strip() or None
        project.client_id   = request.form.get('client_id') or None
        project.status      = request.form.get('status', 'planning')
        project.priority    = request.form.get('priority', 'medium')
        project.start_date  = _parse_date(request.form.get('start_date'))
        project.end_date    = _parse_date(request.form.get('end_date'))
        project.budget      = float(request.form.get('budget')) if request.form.get('budget') else None
        project.progress    = int(request.form.get('progress', 0))
        project.owner_id    = request.form.get('owner_id') or project.owner_id
        project.updated_at  = datetime.utcnow()

        log_action('update', 'project', entity_id=project.id, entity_name=project.name,
                   details='; '.join(changes) if changes else 'Actualización de datos')
        db.session.commit()
        flash(f'Proyecto "{project.name}" actualizado.', 'success')
        return redirect(url_for('projects.project_detail', id=project.id))

    return render_template('projects/form.html', project=project, form={},
                           clients=clients, users=users)


# ── Project Delete ────────────────────────────────────────────────────────────

@projects_bp.route('/<int:id>/delete', methods=['POST'])
@module_required('projects')
def project_delete(id):
    project = Project.query.get_or_404(id)
    name    = project.name
    log_action('delete', 'project', entity_id=project.id, entity_name=name,
               details=f'Proyecto eliminado: {project.code}')
    db.session.delete(project)
    db.session.commit()
    flash(f'Proyecto "{name}" eliminado.', 'warning')
    return redirect(url_for('projects.project_list'))


# ── Tasks ─────────────────────────────────────────────────────────────────────

@projects_bp.route('/<int:id>/tasks/new', methods=['POST'])
@module_required('projects')
def task_new(id):
    project = Project.query.get_or_404(id)
    task = Task(
        project_id=project.id,
        title=request.form.get('title', '').strip(),
        description=request.form.get('description', '').strip() or None,
        status=request.form.get('status', 'pending'),
        priority=request.form.get('priority', 'medium'),
        assigned_to_id=request.form.get('assigned_to_id') or None,
        due_date=_parse_date(request.form.get('due_date')),
    )
    db.session.add(task)
    log_action('create', 'task', entity_name=task.title,
               details=f'Proyecto: {project.code} | Prioridad: {task.priority}')
    db.session.commit()
    flash(f'Tarea "{task.title}" creada.', 'success')
    return redirect(url_for('projects.project_detail', id=id))


@projects_bp.route('/<int:id>/tasks/<int:task_id>/status', methods=['POST'])
@module_required('projects')
def task_status(id, task_id):
    task       = Task.query.get_or_404(task_id)
    old_status = task.status
    new_status = request.form.get('status', task.status)
    task.status     = new_status
    task.updated_at = datetime.utcnow()
    log_action('update', 'task', entity_id=task.id, entity_name=task.title,
               details=f'Estado: {old_status} → {new_status}')
    db.session.commit()
    return redirect(url_for('projects.project_detail', id=id))


@projects_bp.route('/<int:id>/tasks/<int:task_id>/edit', methods=['POST'])
@module_required('projects')
def task_edit(id, task_id):
    task = Task.query.get_or_404(task_id)
    task.title          = request.form.get('title', '').strip()
    task.description    = request.form.get('description', '').strip() or None
    task.status         = request.form.get('status', task.status)
    task.priority       = request.form.get('priority', task.priority)
    task.assigned_to_id = request.form.get('assigned_to_id') or None
    task.due_date       = _parse_date(request.form.get('due_date'))
    task.updated_at     = datetime.utcnow()
    db.session.commit()
    flash(f'Tarea "{task.title}" actualizada.', 'success')
    return redirect(url_for('projects.project_detail', id=id))


@projects_bp.route('/<int:id>/tasks/<int:task_id>/delete', methods=['POST'])
@module_required('projects')
def task_delete(id, task_id):
    task = Task.query.get_or_404(task_id)
    title = task.title
    db.session.delete(task)
    db.session.commit()
    flash(f'Tarea "{title}" eliminada.', 'warning')
    return redirect(url_for('projects.project_detail', id=id))


# ── Members ───────────────────────────────────────────────────────────────────

@projects_bp.route('/<int:id>/members/add', methods=['POST'])
@module_required('projects')
def member_add(id):
    project = Project.query.get_or_404(id)
    user_id = request.form.get('user_id')
    role    = request.form.get('role', 'member')
    if not user_id:
        flash('Selecciona un usuario.', 'danger')
        return redirect(url_for('projects.project_detail', id=id))
    existing = ProjectMember.query.filter_by(project_id=id, user_id=user_id).first()
    if existing:
        flash('Este usuario ya es miembro del proyecto.', 'warning')
        return redirect(url_for('projects.project_detail', id=id))
    member = ProjectMember(project_id=id, user_id=int(user_id), role=role)
    db.session.add(member)
    user = User.query.get(user_id)
    log_action('update', 'project', entity_id=project.id, entity_name=project.name,
               details=f'Miembro agregado: {user.name if user else user_id} ({role})')
    db.session.commit()
    flash(f'Miembro agregado al proyecto.', 'success')
    return redirect(url_for('projects.project_detail', id=id))


@projects_bp.route('/<int:id>/members/<int:member_id>/remove', methods=['POST'])
@module_required('projects')
def member_remove(id, member_id):
    member = ProjectMember.query.get_or_404(member_id)
    user_name = member.user.name if member.user else '?'
    db.session.delete(member)
    db.session.commit()
    flash(f'"{user_name}" removido del proyecto.', 'info')
    return redirect(url_for('projects.project_detail', id=id))
