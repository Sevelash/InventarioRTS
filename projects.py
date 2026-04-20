from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify)
from models import (db, Project, Task, TaskComment, ProjectActivity,
                    ProjectMember, User, Client, log_action)
from auth import module_required
from datetime import datetime, date, timedelta
import notifications as notif

projects_bp = Blueprint('projects', __name__, url_prefix='/projects')

# ── Label / Badge maps ────────────────────────────────────────────────────────

PROJECT_STATUS_LABELS = {
    'planning': 'Planning', 'active': 'Active',
    'on_hold': 'On Hold',   'completed': 'Completed', 'cancelled': 'Cancelled',
}
PROJECT_STATUS_BADGES = {
    'planning': 'secondary', 'active': 'primary',
    'on_hold': 'warning',    'completed': 'success', 'cancelled': 'danger',
}
TASK_STATUS_LABELS = {
    'pending': 'To Do', 'in_progress': 'In Progress',
    'review': 'In Review', 'done': 'Done', 'cancelled': 'Cancelled',
}
TASK_STATUS_BADGES = {
    'pending': 'secondary', 'in_progress': 'primary',
    'review': 'warning',    'done': 'success', 'cancelled': 'danger',
}
PRIORITY_LABELS = {'low': 'Low', 'medium': 'Medium', 'high': 'High', 'critical': 'Critical'}
PRIORITY_BADGES = {'low': 'success', 'medium': 'info', 'high': 'warning', 'critical': 'danger'}
PRIORITY_COLORS = {'low': '#28A745', 'medium': '#089ACF', 'high': '#FFA000', 'critical': '#DC3545'}

_MAPS = dict(
    PROJECT_STATUS_LABELS=PROJECT_STATUS_LABELS,
    PROJECT_STATUS_BADGES=PROJECT_STATUS_BADGES,
    TASK_STATUS_LABELS=TASK_STATUS_LABELS,
    TASK_STATUS_BADGES=TASK_STATUS_BADGES,
    PRIORITY_LABELS=PRIORITY_LABELS,
    PRIORITY_BADGES=PRIORITY_BADGES,
    PRIORITY_COLORS=PRIORITY_COLORS,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(v):
    if not v:
        return None
    try:
        return datetime.strptime(v, '%Y-%m-%d').date()
    except ValueError:
        return None


def _auto_code():
    last = Project.query.order_by(Project.id.desc()).first()
    return f'PRJ-{((last.id + 1) if last else 1):04d}'


def _current_user():
    return session.get('user', {})


def _add_activity(project_id: int, action: str, entity_type: str,
                  entity_name: str = '', details: str = '',
                  icon: str = 'circle', color: str = 'secondary'):
    u = _current_user()
    act = ProjectActivity(
        project_id=project_id,
        user_id=u.get('id'),
        user_name=u.get('name', 'System'),
        action=action,
        entity_type=entity_type,
        entity_name=entity_name,
        details=details,
        icon=icon,
        color=color,
    )
    db.session.add(act)


# ── My Tasks ──────────────────────────────────────────────────────────────────

@projects_bp.route('/my-tasks')
@module_required('projects')
def my_tasks():
    today  = date.today()
    uid    = _current_user().get('id')
    status = request.args.get('status', '')   # filter by status

    query = Task.query.filter_by(assigned_to_id=uid)
    if status:
        query = query.filter_by(status=status)
    else:
        query = query.filter(Task.status.notin_(['done', 'cancelled']))

    tasks = query.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc()).all()

    # Group by project
    by_project = {}
    for t in tasks:
        proj = t.project
        if proj.id not in by_project:
            by_project[proj.id] = {'project': proj, 'tasks': []}
        by_project[proj.id]['tasks'].append(t)

    overdue_count = sum(1 for t in tasks if t.due_date and t.due_date < today
                        and t.status not in ('done', 'cancelled'))
    due_today     = sum(1 for t in tasks if t.due_date == today)

    return render_template('projects/my_tasks.html',
                           by_project=list(by_project.values()),
                           tasks=tasks,
                           status_filter=status,
                           overdue_count=overdue_count,
                           due_today=due_today,
                           today=today,
                           **_MAPS)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@projects_bp.route('/')
@module_required('projects')
def dashboard():
    today = date.today()
    total      = Project.query.count()
    active     = Project.query.filter_by(status='active').count()
    completed  = Project.query.filter_by(status='completed').count()
    on_hold    = Project.query.filter_by(status='on_hold').count()
    overdue    = Project.query.filter(
        Project.end_date < today,
        Project.status.notin_(['completed', 'cancelled'])
    ).count()
    total_tasks   = Task.query.count()
    done_tasks    = Task.query.filter_by(status='done').count()
    pending_tasks = Task.query.filter(
        Task.status.in_(['pending', 'in_progress', 'review'])).count()
    overdue_tasks = Task.query.filter(
        Task.due_date < today,
        Task.status.notin_(['done', 'cancelled'])
    ).count()

    recent_projects = Project.query.order_by(Project.updated_at.desc()).limit(8).all()
    my_id    = _current_user().get('id')
    my_tasks = (Task.query.filter_by(assigned_to_id=my_id)
                .filter(Task.status.notin_(['done', 'cancelled']))
                .order_by(Task.due_date.asc().nullslast())
                .limit(10).all())

    status_chart = {
        'labels': [PROJECT_STATUS_LABELS.get(s, s) for s in Project.STATUS_CHOICES],
        'data':   [Project.query.filter_by(status=s).count() for s in Project.STATUS_CHOICES],
    }
    return render_template('projects/dashboard.html',
        total=total, active=active, completed=completed,
        on_hold=on_hold, overdue=overdue,
        total_tasks=total_tasks, done_tasks=done_tasks,
        pending_tasks=pending_tasks, overdue_tasks=overdue_tasks,
        recent_projects=recent_projects, my_tasks=my_tasks,
        status_chart=status_chart, today=today, **_MAPS)


# ── Project List ──────────────────────────────────────────────────────────────

@projects_bp.route('/list')
@module_required('projects')
def project_list():
    q               = request.args.get('q', '')
    status_filter   = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    client_filter   = request.args.get('client_id', '')

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
    return render_template('projects/list.html',
        projects=projects, clients=clients, today=date.today(),
        q=q, status_filter=status_filter,
        priority_filter=priority_filter, client_filter=client_filter, **_MAPS)


# ── Project Gantt ─────────────────────────────────────────────────────────────

@projects_bp.route('/<int:id>/gantt')
@module_required('projects')
def project_gantt(id):
    project = Project.query.get_or_404(id)
    today   = date.today()
    # Build task data with position calculations
    start = project.start_date or today
    end   = project.end_date   or (today + timedelta(days=30))
    total_days = max((end - start).days, 1)

    tasks_data = []
    for t in project.tasks:
        if t.status == 'cancelled':
            continue
        t_start = start   # fallback to project start
        t_end   = t.due_date or end
        if t_end < start:
            t_end = start
        s_pct = max(0, min(100, (t_start - start).days / total_days * 100))
        w_pct = max(1,  min(100 - s_pct, (t_end - t_start).days / total_days * 100))
        overdue = t.due_date and t.due_date < today and t.status not in ('done','cancelled')
        tasks_data.append({
            'id':       t.id,
            'title':    t.title,
            'status':   t.status,
            'priority': t.priority,
            'due_date': t.due_date,
            'assigned': t.assigned_to.name if t.assigned_to else None,
            's_pct':    round(s_pct, 1),
            'w_pct':    round(w_pct, 1),
            'overdue':  overdue,
            'done':     t.status == 'done',
        })

    return render_template('projects/gantt.html',
                           project=project,
                           tasks_data=tasks_data,
                           start=start,
                           end=end,
                           total_days=total_days,
                           today=today,
                           **_MAPS)


# ── Project New ───────────────────────────────────────────────────────────────

@projects_bp.route('/new', methods=['GET', 'POST'])
@module_required('projects')
def project_new():
    clients = Client.query.filter_by(active=True).order_by(Client.name).all()
    users   = User.query.filter_by(active=True).order_by(User.name).all()

    if request.method == 'POST':
        code = request.form.get('code', '').strip() or _auto_code()
        if Project.query.filter_by(code=code).first():
            flash(f'Project code "{code}" already exists.', 'danger')
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
            owner_id=request.form.get('owner_id') or _current_user().get('id'),
        )
        db.session.add(project)
        db.session.flush()

        # Owner auto-added as manager member
        db.session.add(ProjectMember(project_id=project.id,
                                     user_id=project.owner_id, role='manager'))
        _add_activity(project.id, 'created_project', 'project',
                      entity_name=project.name,
                      details=f'Project {code} created.',
                      icon='plus-circle', color='primary')
        log_action('create', 'project', entity_name=project.name,
                   details=f'Code: {code} | Status: {project.status}')
        db.session.commit()

        by_name = _current_user().get('name', 'Someone')
        notif.on_project_created(project, by_name)

        flash(f'Project "{project.name}" created.', 'success')
        return redirect(url_for('projects.project_detail', id=project.id))

    return render_template('projects/form.html', project=None, form={},
                           clients=clients, users=users,
                           suggested_code=_auto_code())


# ── Project Detail (tabbed: Overview | Board | Backlog | Activity | Team) ─────

@projects_bp.route('/<int:id>')
@module_required('projects')
def project_detail(id):
    project  = Project.query.get_or_404(id)
    users    = User.query.filter_by(active=True).order_by(User.name).all()
    today    = date.today()
    tab      = request.args.get('tab', 'board')

    total_tasks   = len(project.tasks)
    done_tasks    = len([t for t in project.tasks if t.status == 'done'])
    open_tasks    = len([t for t in project.tasks if t.status not in ('done', 'cancelled')])
    overdue_tasks = len([t for t in project.tasks if t.is_overdue])
    calc_progress = int(done_tasks / total_tasks * 100) if total_tasks else 0

    # Kanban: group tasks by status
    tasks_by_status = {s: [] for s in TASK_STATUS_LABELS}
    for t in project.tasks:
        tasks_by_status.setdefault(t.status, []).append(t)

    member_user_ids  = {m.user_id for m in project.members}
    available_users  = [u for u in users if u.id not in member_user_ids]

    # Activity feed (last 50)
    activities = (ProjectActivity.query
                  .filter_by(project_id=project.id)
                  .order_by(ProjectActivity.created_at.desc())
                  .limit(50).all())

    return render_template('projects/detail.html',
        project=project, users=users, today=today, tab=tab,
        total_tasks=total_tasks, done_tasks=done_tasks,
        open_tasks=open_tasks, overdue_tasks=overdue_tasks,
        calc_progress=calc_progress,
        tasks_by_status=tasks_by_status,
        available_users=available_users,
        member_user_ids=member_user_ids,
        activities=activities, **_MAPS)


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
            flash(f'Code "{new_code}" already exists.', 'danger')
            return render_template('projects/form.html', project=project,
                                   form=request.form, clients=clients, users=users)
        old_status = project.status
        changes    = []
        if project.status != request.form.get('status'):
            changes.append(f'status: {project.status} → {request.form.get("status")}')
        if project.priority != request.form.get('priority'):
            changes.append(f'priority: {project.priority} → {request.form.get("priority")}')

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

        if changes:
            _add_activity(project.id, 'updated_project', 'project',
                          entity_name=project.name,
                          details='; '.join(changes),
                          icon='pencil', color='info')
        log_action('update', 'project', entity_id=project.id, entity_name=project.name,
                   details='; '.join(changes) if changes else 'Updated')
        db.session.commit()

        by_name = _current_user().get('name', 'Someone')
        if old_status != project.status:
            notif.on_project_status_changed(project, old_status, project.status, by_name)

        flash(f'Project "{project.name}" updated.', 'success')
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
               details=f'Project deleted: {project.code}')
    db.session.delete(project)
    db.session.commit()
    flash(f'Project "{name}" deleted.', 'warning')
    return redirect(url_for('projects.project_list'))


# ── Tasks ─────────────────────────────────────────────────────────────────────

@projects_bp.route('/<int:id>/tasks/new', methods=['POST'])
@module_required('projects')
def task_new(id):
    project = Project.query.get_or_404(id)
    assigned_id = request.form.get('assigned_to_id') or None
    task = Task(
        project_id=project.id,
        title=request.form.get('title', '').strip(),
        description=request.form.get('description', '').strip() or None,
        status=request.form.get('status', 'pending'),
        priority=request.form.get('priority', 'medium'),
        assigned_to_id=assigned_id,
        due_date=_parse_date(request.form.get('due_date')),
    )
    db.session.add(task)
    db.session.flush()

    _add_activity(project.id, 'created_task', 'task',
                  entity_name=task.title,
                  details=f'Priority: {task.priority}',
                  icon='plus-circle', color='success')
    log_action('create', 'task', entity_name=task.title,
               details=f'Project: {project.code} | Priority: {task.priority}')
    db.session.commit()

    by_name = _current_user().get('name', 'Someone')
    if assigned_id:
        assignee = User.query.get(assigned_id)
        if assignee:
            notif.on_task_assigned(task, project, assignee, by_name)

    flash(f'Task "{task.title}" created.', 'success')
    return redirect(url_for('projects.project_detail', id=id, tab='board'))


@projects_bp.route('/<int:id>/tasks/<int:task_id>/status', methods=['POST'])
@module_required('projects')
def task_status(id, task_id):
    task       = Task.query.get_or_404(task_id)
    old_status = task.status
    new_status = request.form.get('status', task.status)
    if old_status == new_status:
        # AJAX move from Kanban — return JSON OK
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': True})
        return redirect(url_for('projects.project_detail', id=id, tab='board'))

    task.status     = new_status
    task.updated_at = datetime.utcnow()

    _add_activity(id, 'moved_task', 'task',
                  entity_name=task.title,
                  details=f'{TASK_STATUS_LABELS.get(old_status, old_status)} → {TASK_STATUS_LABELS.get(new_status, new_status)}',
                  icon='arrow-left-right', color='info')
    db.session.commit()

    by_name = _current_user().get('name', 'Someone')
    project = Project.query.get(id)
    notif.on_task_status_changed(task, project, old_status, new_status, by_name)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'new_status': new_status})
    return redirect(url_for('projects.project_detail', id=id, tab='board'))


@projects_bp.route('/<int:id>/tasks/<int:task_id>/edit', methods=['POST'])
@module_required('projects')
def task_edit(id, task_id):
    task        = Task.query.get_or_404(task_id)
    old_assigned = task.assigned_to_id
    new_assigned = request.form.get('assigned_to_id') or None

    task.title          = request.form.get('title', '').strip()
    task.description    = request.form.get('description', '').strip() or None
    task.status         = request.form.get('status', task.status)
    task.priority       = request.form.get('priority', task.priority)
    task.assigned_to_id = new_assigned
    task.due_date       = _parse_date(request.form.get('due_date'))
    task.updated_at     = datetime.utcnow()

    _add_activity(id, 'updated_task', 'task',
                  entity_name=task.title,
                  icon='pencil', color='secondary')
    db.session.commit()

    by_name = _current_user().get('name', 'Someone')
    if new_assigned and new_assigned != str(old_assigned):
        assignee = User.query.get(new_assigned)
        project  = Project.query.get(id)
        if assignee and project:
            notif.on_task_assigned(task, project, assignee, by_name)

    flash(f'Task "{task.title}" updated.', 'success')
    return redirect(url_for('projects.project_detail', id=id, tab='board'))


@projects_bp.route('/<int:id>/tasks/<int:task_id>/delete', methods=['POST'])
@module_required('projects')
def task_delete(id, task_id):
    task  = Task.query.get_or_404(task_id)
    title = task.title
    _add_activity(id, 'deleted_task', 'task',
                  entity_name=title,
                  icon='trash', color='danger')
    db.session.delete(task)
    db.session.commit()
    flash(f'Task "{title}" deleted.', 'warning')
    return redirect(url_for('projects.project_detail', id=id, tab='backlog'))


# ── Task Comments ─────────────────────────────────────────────────────────────

@projects_bp.route('/<int:id>/tasks/<int:task_id>/comment', methods=['POST'])
@module_required('projects')
def task_comment(id, task_id):
    task    = Task.query.get_or_404(task_id)
    content = request.form.get('content', '').strip()
    if not content:
        flash('Comment cannot be empty.', 'warning')
        return redirect(url_for('projects.project_detail', id=id, tab='board'))

    u = _current_user()
    comment = TaskComment(
        task_id=task_id,
        user_id=u.get('id'),
        user_name=u.get('name', 'Unknown'),
        content=content,
    )
    db.session.add(comment)

    _add_activity(id, 'commented', 'comment',
                  entity_name=task.title,
                  details=content[:120],
                  icon='chat', color='info')
    db.session.commit()

    project = Project.query.get(id)
    notif.on_comment_added(content, task, project, u.get('name', 'Someone'))

    flash('Comment added.', 'success')
    return redirect(url_for('projects.project_detail', id=id, tab='board'))


# ── Members ───────────────────────────────────────────────────────────────────

@projects_bp.route('/<int:id>/members/add', methods=['POST'])
@module_required('projects')
def member_add(id):
    project = Project.query.get_or_404(id)
    user_id = request.form.get('user_id')
    role    = request.form.get('role', 'member')
    if not user_id:
        flash('Select a user.', 'danger')
        return redirect(url_for('projects.project_detail', id=id, tab='team'))
    if ProjectMember.query.filter_by(project_id=id, user_id=user_id).first():
        flash('User is already a member.', 'warning')
        return redirect(url_for('projects.project_detail', id=id, tab='team'))

    db.session.add(ProjectMember(project_id=id, user_id=int(user_id), role=role))
    user = User.query.get(user_id)
    _add_activity(id, 'member_added', 'member',
                  entity_name=user.name if user else str(user_id),
                  details=f'Role: {role}',
                  icon='person-plus', color='primary')
    log_action('update', 'project', entity_id=project.id, entity_name=project.name,
               details=f'Member added: {user.name if user else user_id} ({role})')
    db.session.commit()
    flash('Member added.', 'success')
    return redirect(url_for('projects.project_detail', id=id, tab='team'))


@projects_bp.route('/<int:id>/members/<int:member_id>/remove', methods=['POST'])
@module_required('projects')
def member_remove(id, member_id):
    member    = ProjectMember.query.get_or_404(member_id)
    user_name = member.user.name if member.user else '?'
    _add_activity(id, 'member_removed', 'member',
                  entity_name=user_name,
                  icon='person-dash', color='warning')
    db.session.delete(member)
    db.session.commit()
    flash(f'"{user_name}" removed from project.', 'info')
    return redirect(url_for('projects.project_detail', id=id, tab='team'))
