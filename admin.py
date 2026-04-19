"""
RTS Asset Management — Panel de Administración
  /admin/                  → resumen
  /admin/branding          → logo / remoties / favicon
  /admin/users             → user management
  /admin/departments       → department CRUD
  /admin/access-requests   → approve / deny module access requests
  /admin/notifications     → Teams + Email notification settings
  /admin/logs              → audit trail
"""
import os, json
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, current_app)
from werkzeug.utils import secure_filename
from models import db, User, AuditLog, log_action, Department, AccessRequest, ALL_MODULES
from auth import admin_required
import notifications as notif

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

ALLOWED_IMG = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}


def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMG


def _static_images():
    return os.path.join(current_app.root_path, 'static', 'images')


# ── Inicio del panel ──────────────────────────────────────────────────────────

@admin_bp.route('/')
@admin_required
def index():
    total_users      = User.query.count()
    total_logs       = AuditLog.query.count()
    recent_logs      = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()
    pending_requests = AccessRequest.query.filter_by(status='pending').count()
    images_dir       = _static_images()
    logo_exists      = os.path.exists(os.path.join(images_dir, 'logo.png'))
    remoties_exists  = os.path.exists(os.path.join(images_dir, 'remoties.png'))
    favicon_exists   = os.path.exists(os.path.join(images_dir, 'favicon.png'))
    return render_template('admin/index.html',
                           total_users=total_users, total_logs=total_logs,
                           recent_logs=recent_logs,
                           pending_requests=pending_requests,
                           logo_exists=logo_exists,
                           remoties_exists=remoties_exists,
                           favicon_exists=favicon_exists)


# ── Branding ──────────────────────────────────────────────────────────────────

@admin_bp.route('/branding', methods=['GET', 'POST'])
@admin_required
def branding():
    images_dir = _static_images()
    os.makedirs(images_dir, exist_ok=True)

    if request.method == 'POST':
        action_done = []

        # Subir cualquiera de los 3 slots
        slots = {
            'logo':     ('logo.png',     'Logo principal'),
            'remoties': ('remoties.png', 'Emoji Remoties'),
            'favicon':  ('favicon.png',  'Favicon'),
        }
        for slot, (fname, label) in slots.items():
            f = request.files.get(slot)
            if f and f.filename and _allowed(f.filename):
                dest = os.path.join(images_dir, fname)
                f.save(dest)
                log_action('upload', 'branding',
                           entity_name=label,
                           details=f'Archivo subido: {secure_filename(f.filename)} → {fname}')
                action_done.append(label)

        # Eliminar
        for slot, (fname, label) in slots.items():
            if request.form.get(f'delete_{slot}'):
                path = os.path.join(images_dir, fname)
                if os.path.exists(path):
                    os.remove(path)
                    log_action('delete', 'branding',
                               entity_name=label,
                               details=f'Imagen eliminada: {fname}')
                    action_done.append(f'{label} eliminado')

        if action_done:
            db.session.commit()
            flash('Cambios guardados: ' + ', '.join(action_done), 'success')
        return redirect(url_for('admin.branding'))

    files = {}
    for fname in ['logo.png', 'remoties.png', 'favicon.png']:
        p = os.path.join(images_dir, fname)
        files[fname] = {
            'exists': os.path.exists(p),
            'size':   f'{os.path.getsize(p) / 1024:.1f} KB' if os.path.exists(p) else None,
            'mtime':  os.path.getmtime(p) if os.path.exists(p) else None,
        }
    return render_template('admin/branding.html', files=files)


# ── Usuarios ──────────────────────────────────────────────────────────────────

@admin_bp.route('/users')
@admin_required
def users():
    all_users = User.query.order_by(User.name).all()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@admin_required
def user_new():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        if User.query.filter_by(username=username).first():
            flash(f'El usuario "{username}" ya existe.', 'danger')
            return render_template('admin/user_form.html', user=None, form=request.form)
        u = User(
            name=request.form.get('name', '').strip(),
            username=username,
            email=request.form.get('email', '').strip() or None,
            role=request.form.get('role', 'viewer'),
        )
        u.set_password(request.form.get('password', ''))
        db.session.add(u)
        log_action('create', 'user', entity_name=u.name,
                   details=f'Usuario creado: {username} ({u.role})')
        db.session.commit()
        flash(f'Usuario "{u.name}" creado.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=None, form={})


@admin_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def user_edit(id):
    u = User.query.get_or_404(id)
    if request.method == 'POST':
        new_un = request.form.get('username', '').strip().lower()
        existing = User.query.filter_by(username=new_un).first()
        if existing and existing.id != u.id:
            flash(f'El usuario "{new_un}" ya existe.', 'danger')
            return render_template('admin/user_form.html', user=u, form=request.form)
        changes = []
        if u.name != request.form.get('name', '').strip():
            changes.append(f'nombre: {u.name} → {request.form.get("name").strip()}')
        if u.role != request.form.get('role'):
            changes.append(f'rol: {u.role} → {request.form.get("role")}')
        u.name     = request.form.get('name', '').strip()
        u.username = new_un
        u.email    = request.form.get('email', '').strip() or None
        u.role     = request.form.get('role', 'viewer')
        u.active   = 'active' in request.form
        pwd = request.form.get('password', '').strip()
        if pwd:
            u.set_password(pwd)
            changes.append('contraseña actualizada')
        log_action('update', 'user', entity_id=u.id, entity_name=u.name,
                   details='; '.join(changes) if changes else 'Sin cambios registrados')
        db.session.commit()
        flash(f'Usuario "{u.name}" actualizado.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=u, form={})


@admin_bp.route('/users/<int:id>/toggle', methods=['POST'])
@admin_required
def user_toggle(id):
    u = User.query.get_or_404(id)
    if u.id == session['user']['id']:
        flash('No puedes desactivarte a ti mismo.', 'danger')
        return redirect(url_for('admin.users'))
    u.active = not u.active
    log_action('update', 'user', entity_id=u.id, entity_name=u.name,
               details=f'Estado cambiado a: {"activo" if u.active else "inactivo"}')
    db.session.commit()
    flash(f'Usuario "{u.name}" {"activado" if u.active else "desactivado"}.', 'info')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:id>/delete', methods=['POST'])
@admin_required
def user_delete(id):
    u = User.query.get_or_404(id)
    if u.id == session['user']['id']:
        flash('No puedes eliminarte a ti mismo.', 'danger')
        return redirect(url_for('admin.users'))
    name = u.name
    log_action('delete', 'user', entity_id=u.id, entity_name=name,
               details=f'Usuario eliminado: {u.username}')
    db.session.delete(u)
    db.session.commit()
    flash(f'Usuario "{name}" eliminado.', 'warning')
    return redirect(url_for('admin.users'))


# ── Notifications ─────────────────────────────────────────────────────────────

@admin_bp.route('/notifications', methods=['GET', 'POST'])
@admin_required
def notifications():
    cfg = notif.load_config()

    if request.method == 'POST':
        action = request.form.get('action', 'save')

        if action == 'test_teams':
            notif.send_teams(
                'RTS Test Notification',
                'Teams integration is working correctly from RTS Intranet! 🎉',
                facts=[('Sent by', session['user']['name']), ('Source', 'Admin Panel')],
                color='28A745'
            )
            flash('Test notification sent to Teams. Check your channel in a moment.', 'info')
            return redirect(url_for('admin.notifications'))

        if action == 'test_email':
            notif.send_email(
                session['user'].get('email', ''),
                '[RTS] Test Email Notification',
                'RTS Email Test',
                'Email integration is working correctly from RTS Intranet! 🎉',
                facts=[('Sent by', session['user']['name']), ('Source', 'Admin Panel')],
            )
            flash('Test email sent. Check your inbox in a moment.', 'info')
            return redirect(url_for('admin.notifications'))

        # Save config
        new_cfg = {
            'enabled':               'enabled' in request.form,
            'teams_enabled':         'teams_enabled' in request.form,
            'teams_webhook_url':     request.form.get('teams_webhook_url', '').strip(),
            'teams_channel_name':    request.form.get('teams_channel_name', 'RTS Projects').strip(),
            'email_enabled':         'email_enabled' in request.form,
            'smtp_host':             request.form.get('smtp_host', 'smtp.office365.com').strip(),
            'smtp_port':             int(request.form.get('smtp_port', 587)),
            'smtp_user':             request.form.get('smtp_user', '').strip(),
            'smtp_from':             request.form.get('smtp_from', '').strip(),
            'smtp_from_name':        request.form.get('smtp_from_name', 'RTS Intranet').strip(),
            'app_base_url':          request.form.get('app_base_url', '').strip(),
            'notify_task_assigned':  'notify_task_assigned' in request.form,
            'notify_status_change':  'notify_status_change' in request.form,
            'notify_comment':        'notify_comment' in request.form,
            'notify_project_created':'notify_project_created' in request.form,
            'notify_project_updated':'notify_project_updated' in request.form,
        }
        # Only update password if provided (don't overwrite with blank)
        new_pwd = request.form.get('smtp_password', '').strip()
        new_cfg['smtp_password'] = new_pwd if new_pwd else cfg.get('smtp_password', '')

        notif.save_config(new_cfg)
        log_action('update', 'notifications', entity_name='Notification Config',
                   details='Notification settings updated via admin panel')
        db.session.commit()
        flash('Notification settings saved.', 'success')
        return redirect(url_for('admin.notifications'))

    return render_template('admin/notifications.html', cfg=cfg)


# ── Logs ──────────────────────────────────────────────────────────────────────

@admin_bp.route('/logs')
@admin_required
def logs():
    page         = request.args.get('page', 1, type=int)
    user_filter  = request.args.get('user', '')
    action_filter= request.args.get('action', '')
    entity_filter= request.args.get('entity', '')

    query = AuditLog.query
    if user_filter:
        query = query.filter(AuditLog.user_name.ilike(f'%{user_filter}%'))
    if action_filter:
        query = query.filter_by(action=action_filter)
    if entity_filter:
        query = query.filter_by(entity_type=entity_filter)

    logs_paged = query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False)

    # Valores únicos para los filtros
    actions  = [r[0] for r in db.session.query(AuditLog.action).distinct().all()]
    entities = [r[0] for r in db.session.query(AuditLog.entity_type).distinct().all()]

    return render_template('admin/logs.html',
                           logs=logs_paged,
                           user_filter=user_filter,
                           action_filter=action_filter,
                           entity_filter=entity_filter,
                           actions=sorted(actions),
                           entities=sorted(entities))


# ── Departments ───────────────────────────────────────────────────────────────

@admin_bp.route('/departments')
@admin_required
def departments():
    depts = Department.query.order_by(Department.name).all()
    return render_template('admin/departments.html', departments=depts)


@admin_bp.route('/departments/new', methods=['GET', 'POST'])
@admin_required
def department_new():
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        if Department.query.filter_by(code=code).first():
            flash(f'Department code "{code}" already exists.', 'danger')
            return render_template('admin/department_form.html', dept=None, form=request.form)
        d = Department(
            name=request.form.get('name', '').strip(),
            code=code,
            color=request.form.get('color', '#233C6E').strip(),
            manager_name=request.form.get('manager_name', '').strip() or None,
            manager_email=request.form.get('manager_email', '').strip() or None,
        )
        db.session.add(d)
        log_action('create', 'department', entity_name=d.name,
                   details=f'Department created: {code}')
        db.session.commit()
        flash(f'Department "{d.name}" created.', 'success')
        return redirect(url_for('admin.departments'))
    return render_template('admin/department_form.html', dept=None, form={})


@admin_bp.route('/departments/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def department_edit(id):
    d = Department.query.get_or_404(id)
    if request.method == 'POST':
        d.name          = request.form.get('name', '').strip()
        d.code          = request.form.get('code', '').strip().upper()
        d.color         = request.form.get('color', '#233C6E').strip()
        d.manager_name  = request.form.get('manager_name', '').strip() or None
        d.manager_email = request.form.get('manager_email', '').strip() or None
        d.active        = 'active' in request.form
        log_action('update', 'department', entity_id=d.id, entity_name=d.name)
        db.session.commit()
        flash(f'Department "{d.name}" updated.', 'success')
        return redirect(url_for('admin.departments'))
    return render_template('admin/department_form.html', dept=d, form={})


@admin_bp.route('/departments/<int:id>/delete', methods=['POST'])
@admin_required
def department_delete(id):
    d = Department.query.get_or_404(id)
    name = d.name
    log_action('delete', 'department', entity_id=d.id, entity_name=name)
    db.session.delete(d)
    db.session.commit()
    flash(f'Department "{name}" deleted.', 'warning')
    return redirect(url_for('admin.departments'))


# ── Access Requests ───────────────────────────────────────────────────────────

@admin_bp.route('/access-requests')
@admin_required
def access_requests():
    status_filter = request.args.get('status', 'pending')
    query = AccessRequest.query
    if status_filter and status_filter != 'all':
        query = query.filter_by(status=status_filter)
    reqs = query.order_by(AccessRequest.created_at.desc()).all()
    mod_names = {m['slug']: m['name'] for m in ALL_MODULES}
    return render_template('admin/access_requests.html',
                           requests=reqs,
                           status_filter=status_filter,
                           mod_names=mod_names,
                           departments=Department.query.filter_by(active=True).all())


@admin_bp.route('/access-requests/<int:id>/review', methods=['POST'])
@admin_required
def access_request_review(id):
    req     = AccessRequest.query.get_or_404(id)
    action  = request.form.get('action')          # approve | deny
    notes   = request.form.get('admin_notes', '').strip()
    dept_id = request.form.get('department_id', type=int)

    if action not in ('approve', 'deny'):
        flash('Invalid action.', 'danger')
        return redirect(url_for('admin.access_requests'))

    req.status      = 'approved' if action == 'approve' else 'denied'
    req.admin_notes = notes
    req.reviewed_by = session['user']['name']
    req.reviewed_at = datetime.utcnow()

    if action == 'approve':
        # Grant the module to the user
        user = User.query.get(req.user_id)
        if user:
            mods = user.get_modules()
            if req.module_slug not in mods:
                mods.append(req.module_slug)
                user.set_modules(mods)
            # Set department if provided
            if dept_id:
                user.department_id = dept_id
            elif req.department_id:
                user.department_id = req.department_id

        log_action('update', 'access_request', entity_id=req.id,
                   entity_name=req.user_name,
                   details=f'Approved access to {req.module_slug}')

        # Notify user by email
        if user and user.email:
            mod_name = next((m['name'] for m in ALL_MODULES if m['slug'] == req.module_slug),
                            req.module_slug)
            notif.send_email(
                user.email,
                f'[RTS] Access approved: {mod_name}',
                f'Access Granted — {mod_name}',
                f'Your request to access <b>{mod_name}</b> has been <b>approved</b> by {req.reviewed_by}.',
                facts=[('Module', mod_name), ('Approved by', req.reviewed_by)],
                url=notif._url(notif.load_config(), '/')
            )
    else:
        log_action('update', 'access_request', entity_id=req.id,
                   entity_name=req.user_name,
                   details=f'Denied access to {req.module_slug}')
        # Notify user of denial
        user = User.query.get(req.user_id)
        if user and user.email:
            mod_name = next((m['name'] for m in ALL_MODULES if m['slug'] == req.module_slug),
                            req.module_slug)
            notif.send_email(
                user.email,
                f'[RTS] Access request update: {mod_name}',
                f'Access Request Update — {mod_name}',
                f'Your request to access <b>{mod_name}</b> was reviewed by {req.reviewed_by}.'
                + (f'<br><br><b>Note:</b> {notes}' if notes else ''),
                facts=[('Module', mod_name), ('Status', 'Not approved'),
                       ('Reviewed by', req.reviewed_by)],
            )

    db.session.commit()
    flash(f'Request {"approved" if action == "approve" else "denied"} for {req.user_name}.', 'success')
    return redirect(url_for('admin.access_requests'))
