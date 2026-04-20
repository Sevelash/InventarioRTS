import re
from flask import (Blueprint, redirect, url_for, session,
                   request, render_template, flash)
from functools import wraps
from models import db, User, ALL_MODULES, log_action
from extensions import limiter

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


# ── Password validator ────────────────────────────────────────────────────────

def _validate_password(pwd: str) -> list:
    """Returns list of validation errors; empty list = valid."""
    errors = []
    if len(pwd) < 12:
        errors.append('Mínimo 12 caracteres')
    if not re.search(r'[A-Z]', pwd):
        errors.append('Al menos una mayúscula')
    if not re.search(r'[0-9]', pwd):
        errors.append('Al menos un número')
    if not re.search(r'[!@#$%^&*()\-_=+\[\]{};:\'",.<>/?\\|`~]', pwd):
        errors.append('Al menos un carácter especial (!@#$…)')
    return errors


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
    """Decorator that checks if the logged-in user has access to a module (validated from DB)."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('user'):
                return redirect(url_for('auth.login'))
            u = User.query.get(session['user'].get('id'))
            if not u or not u.active:
                session.clear()
                return redirect(url_for('auth.login'))
            if u.role == 'admin':
                return f(*args, **kwargs)
            if slug not in u.get_modules():
                flash('No tienes acceso a este módulo. Contacta al administrador.', 'danger')
                return redirect(url_for('portal'))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Login / Logout ────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("20 per minute")   # brute-force protection
def login():
    if session.get('user'):
        return redirect(url_for('portal'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')

        # Basic input validation
        if not username or not password or len(username) > 80 or len(password) > 256:
            flash('Datos inválidos.', 'danger')
            return render_template('auth/login.html')

        user = User.query.filter_by(username=username).first()

        # Account lockout check
        if user and user.is_locked():
            flash('Cuenta bloqueada temporalmente. Intenta en 15 minutos.', 'danger')
            log_action('login_blocked', 'user', entity_id=user.id,
                       entity_name=user.name, details=f'Cuenta bloqueada: {username}')
            db.session.commit()
            return render_template('auth/login.html')

        if user and user.active and user.check_password(password):
            user.reset_failed_logins()

            # Force password change on first login
            if user.force_password_change:
                session['_force_change_user_id'] = user.id
                return redirect(url_for('auth.first_login'))

            # MFA check
            if user.mfa_enabled:
                session['_mfa_user_id'] = user.id
                return redirect(url_for('auth.mfa_verify'))

            # Success
            session.permanent = True
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
            if user:
                user.record_failed_login()
                remaining = max(0, 5 - (user.failed_logins or 0))
                if remaining == 0:
                    flash('Demasiados intentos fallidos. Cuenta bloqueada 15 minutos.', 'danger')
                else:
                    flash(f'Contraseña incorrecta. {remaining} intento(s) restante(s).', 'danger')
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


# ── First login — force password change ──────────────────────────────────────

@auth_bp.route('/first-login', methods=['GET', 'POST'])
def first_login():
    uid = session.get('_force_change_user_id')
    if not uid:
        return redirect(url_for('auth.login'))
    user = User.query.get_or_404(uid)

    errors = []
    if request.method == 'POST':
        pwd1 = request.form.get('password', '')
        pwd2 = request.form.get('password2', '')
        if pwd1 != pwd2:
            errors.append('Las contraseñas no coinciden.')
        errors += _validate_password(pwd1)
        if not errors:
            user.set_password(pwd1)
            user.force_password_change = False
            db.session.commit()
            session.pop('_force_change_user_id', None)
            session.permanent = True
            session['user'] = {
                'id':      user.id,
                'name':    user.name,
                'email':   user.email or '',
                'role':    user.role,
                'modules': user.get_modules(),
            }
            log_action('password_change', 'user', entity_id=user.id,
                       entity_name=user.name, details='Primera contraseña establecida')
            db.session.commit()
            flash('Contraseña establecida correctamente. ¡Bienvenido!', 'success')
            return redirect(url_for('portal'))

    return render_template('auth/first_login.html', user=user, errors=errors)


# ── MFA Verify ────────────────────────────────────────────────────────────────

@auth_bp.route('/mfa', methods=['GET', 'POST'])
@limiter.limit("10 per minute")   # strict: prevents TOTP brute-forcing
def mfa_verify():
    import pyotp
    uid = session.get('_mfa_user_id')
    if not uid:
        return redirect(url_for('auth.login'))
    user = User.query.get_or_404(uid)

    error = None
    if request.method == 'POST':
        code = request.form.get('code', '').strip().replace(' ', '')
        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(code, valid_window=1):
            session.pop('_mfa_user_id', None)
            session.permanent = True
            session['user'] = {
                'id':      user.id,
                'name':    user.name,
                'email':   user.email or '',
                'role':    user.role,
                'modules': user.get_modules(),
            }
            log_action('login', 'user', entity_id=user.id, entity_name=user.name,
                       details='Login con MFA')
            db.session.commit()
            flash(f'¡Bienvenido, {user.name}!', 'success')
            return redirect(url_for('portal'))
        else:
            error = 'Código incorrecto. Verifica tu app de autenticación.'

    return render_template('auth/mfa.html', user=user, error=error)


# ── MFA Setup ─────────────────────────────────────────────────────────────────

@auth_bp.route('/mfa/setup', methods=['GET', 'POST'])
@login_required
def mfa_setup():
    import pyotp, qrcode, io, base64
    uid  = session['user']['id']
    user = User.query.get_or_404(uid)

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'enable':
            secret = request.form.get('secret', '')
            code   = request.form.get('code', '').strip()
            totp   = pyotp.TOTP(secret)
            if totp.verify(code, valid_window=1):
                user.totp_secret  = secret
                user.mfa_enabled  = True
                db.session.commit()
                flash('MFA activado correctamente.', 'success')
                return redirect(url_for('user_profile'))
            else:
                flash('Código incorrecto. Escanea de nuevo el QR.', 'danger')
        elif action == 'disable':
            user.totp_secret  = None
            user.mfa_enabled  = False
            db.session.commit()
            flash('MFA desactivado.', 'warning')
            return redirect(url_for('user_profile'))

    # Generate new secret + QR
    secret = pyotp.random_base32()
    totp   = pyotp.TOTP(secret)
    uri    = totp.provisioning_uri(name=user.email or user.username,
                                   issuer_name='RTS Intranet')
    img    = qrcode.make(uri)
    buf    = io.BytesIO()
    img.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render_template('auth/mfa_setup.html', user=user,
                           secret=secret, qr_b64=qr_b64)


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
        pwd = request.form.get('password', '')
        pwd_errors = _validate_password(pwd)
        if pwd_errors:
            flash('Contraseña inválida: ' + '; '.join(pwd_errors), 'danger')
            return render_template('auth/user_form.html', user=None,
                                   form=request.form, all_modules=ALL_MODULES)
        selected_modules = request.form.getlist('modules')
        u = User(
            name=request.form.get('name', '').strip(),
            username=username,
            email=request.form.get('email', '').strip() or None,
            role=request.form.get('role', 'viewer'),
        )
        u.set_password(pwd)
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
            pwd_errors = _validate_password(new_pwd)
            if pwd_errors:
                flash('Contraseña inválida: ' + '; '.join(pwd_errors), 'danger')
                return render_template('auth/user_form.html', user=u,
                                       form=request.form, all_modules=ALL_MODULES)
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
