from flask import (Blueprint, redirect, url_for, session,
                   request, render_template, flash)
from functools import wraps
from models import db, User, ALL_MODULES, log_action

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


# ── Decoradores ───────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if session['user'].get('role') != 'admin':
            flash('Necesitas permisos de administrador.', 'danger')
            return redirect(url_for('portal'))
        return f(*args, **kwargs)
    return decorated


def module_required(slug):
    """Decorator that checks if the logged-in user has access to a module."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('user'):
                return redirect(url_for('auth.login'))
            user = session['user']
            # Admins always have access
            if user.get('role') == 'admin':
                return f(*args, **kwargs)
            modules = user.get('modules', [])
            if slug not in modules:
                flash('No tienes acceso a este módulo. Contacta al administrador.', 'danger')
                return redirect(url_for('portal'))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Login / Logout ────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user'):
        return redirect(url_for('portal'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username, active=True).first()

        if user and user.check_password(password):
            session['user'] = {
                'id':      user.id,
                'name':    user.name,
                'email':   user.email or '',
                'role':    user.role,
                'modules': user.get_modules(),
            }
            log_action('login', 'user', entity_id=user.id, entity_name=user.name,
                       details=f'Inicio de sesión: {username}')
            db.session.commit()
            flash(f'¡Bienvenido, {user.name}!', 'success')
            return redirect(url_for('portal'))
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    u = session.get('user', {})
    if u:
        log_action('logout', 'user', entity_id=u.get('id'), entity_name=u.get('name'),
                   details='Cierre de sesión')
        db.session.commit()
    session.clear()
    flash('Sesión cerrada.', 'info')
    return redirect(url_for('auth.login'))


# ── Gestión de usuarios (solo admin) ─────────────────────────────────────────

@auth_bp.route('/users')
@admin_required
def users_list():
    users = User.query.order_by(User.name).all()
    return render_template('auth/users.html', users=users)


@auth_bp.route('/users/new', methods=['GET', 'POST'])
@admin_required
def user_new():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        if User.query.filter_by(username=username).first():
            flash(f'El usuario "{username}" ya existe.', 'danger')
            return render_template('auth/user_form.html', user=None,
                                   form=request.form, all_modules=ALL_MODULES)
        selected_modules = request.form.getlist('modules')
        u = User(
            name=request.form.get('name', '').strip(),
            username=username,
            email=request.form.get('email', '').strip() or None,
            role=request.form.get('role', 'viewer'),
        )
        u.set_password(request.form.get('password', ''))
        u.set_modules(selected_modules)
        db.session.add(u)
        db.session.commit()
        flash(f'Usuario "{u.name}" creado correctamente.', 'success')
        return redirect(url_for('auth.users_list'))
    return render_template('auth/user_form.html', user=None, form={}, all_modules=ALL_MODULES)


@auth_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def user_edit(id):
    u = User.query.get_or_404(id)
    if request.method == 'POST':
        new_username = request.form.get('username', '').strip().lower()
        existing = User.query.filter_by(username=new_username).first()
        if existing and existing.id != u.id:
            flash(f'El usuario "{new_username}" ya existe.', 'danger')
            return render_template('auth/user_form.html', user=u,
                                   form=request.form, all_modules=ALL_MODULES)
        u.name     = request.form.get('name', '').strip()
        u.username = new_username
        u.email    = request.form.get('email', '').strip() or None
        u.role     = request.form.get('role', 'viewer')
        u.active   = 'active' in request.form
        selected_modules = request.form.getlist('modules')
        u.set_modules(selected_modules)
        new_pwd = request.form.get('password', '').strip()
        if new_pwd:
            u.set_password(new_pwd)
        db.session.commit()
        flash(f'Usuario "{u.name}" actualizado.', 'success')
        return redirect(url_for('auth.users_list'))
    return render_template('auth/user_form.html', user=u, form={}, all_modules=ALL_MODULES)


@auth_bp.route('/users/<int:id>/delete', methods=['POST'])
@admin_required
def user_delete(id):
    u = User.query.get_or_404(id)
    if u.id == session['user']['id']:
        flash('No puedes eliminarte a ti mismo.', 'danger')
        return redirect(url_for('auth.users_list'))
    name = u.name
    db.session.delete(u)
    db.session.commit()
    flash(f'Usuario "{name}" eliminado.', 'warning')
    return redirect(url_for('auth.users_list'))
