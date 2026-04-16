"""
RTS Asset Management — Panel de Administración
  /admin/           → resumen
  /admin/branding   → subir logo, remoties, favicon
  /admin/users      → gestión de usuarios + invitaciones
  /admin/logs       → audit trail completo
"""
import os, json
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, current_app)
from werkzeug.utils import secure_filename
from models import db, User, AuditLog, log_action
from auth import admin_required

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
    total_users   = User.query.count()
    total_logs    = AuditLog.query.count()
    recent_logs   = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()
    images_dir    = _static_images()
    logo_exists      = os.path.exists(os.path.join(images_dir, 'logo.png'))
    remoties_exists  = os.path.exists(os.path.join(images_dir, 'remoties.png'))
    favicon_exists   = os.path.exists(os.path.join(images_dir, 'favicon.png'))
    return render_template('admin/index.html',
                           total_users=total_users, total_logs=total_logs,
                           recent_logs=recent_logs,
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
