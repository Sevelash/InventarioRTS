from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
from models import db, Asset, Category, Client, Employee, Assignment, Shipment, AuditLog, log_action, ALL_MODULES, Department, AccessRequest
from datetime import datetime, date, timedelta
from i18n import get_translations, SUPPORTED_LANGS, DEFAULT_LANG
import os
from extensions import limiter, csrf

# Load .env file if present (dev convenience)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

# ── Security: require SECRET_KEY in production ────────────────────────────
_secret = os.environ.get('SECRET_KEY', '')
if not _secret:
    import secrets as _secrets
    _secret = _secrets.token_hex(32)
    print('WARNING: SECRET_KEY not set — using a random key (sessions will reset on restart)')
app.config['SECRET_KEY'] = _secret

# Default: siempre apunta a instance/rts_inventory.db relativo al directorio del script
_default_db = 'sqlite:///' + os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'rts_inventory.db')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', _default_db)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ── Session security ──────────────────────────────────────────────────────
app.config['PERMANENT_SESSION_LIFETIME']  = timedelta(hours=8)
app.config['SESSION_COOKIE_SECURE']       = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY']     = True
app.config['SESSION_COOKIE_SAMESITE']     = 'Lax'

# ── CSRF + Rate limiter (from extensions.py — shared to avoid circular imports) ───
csrf.init_app(app)
limiter.init_app(app)

db.init_app(app)

# ── Auth blueprint ────────────────────────────────────────────────────────────
from auth import auth_bp, login_required, module_required
app.register_blueprint(auth_bp)

# ── Admin blueprint ───────────────────────────────────────────────────────────
from admin import admin_bp
app.register_blueprint(admin_bp)

# ── Projects blueprint ────────────────────────────────────────────────────────
from projects import projects_bp
app.register_blueprint(projects_bp)

# ── Evaluation blueprint ──────────────────────────────────────────────────────
from eval import eval_bp
app.register_blueprint(eval_bp)

# ── Repository blueprint ──────────────────────────────────────────────────────
from repo import repo_bp
app.register_blueprint(repo_bp)

# ── Reports blueprint ─────────────────────────────────────────────────────────
from reports import reports_bp
app.register_blueprint(reports_bp)

# ── Jinja2 custom filters ─────────────────────────────────────────────────────
import json as _json_mod

@app.template_filter('from_json')
def from_json_filter(value):
    """Deserializa JSON almacenado en la DB para usarlo en templates."""
    if not value:
        return []
    try:
        return _json_mod.loads(value)
    except Exception:
        return []

# ── Security headers ──────────────────────────────────────────────────────
@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options']           = 'DENY'
    response.headers['X-Content-Type-Options']    = 'nosniff'
    response.headers['X-XSS-Protection']          = '1; mode=block'
    response.headers['Referrer-Policy']           = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy']        = 'geolocation=(), microphone=(), camera=()'
    if os.environ.get('FLASK_ENV') == 'production':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; "
        "font-src 'self' fonts.gstatic.com cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self';"
    )
    response.headers['Content-Security-Policy'] = csp
    return response


# ── Idle timeout (30 min inactivity) ─────────────────────────────────────
IDLE_TIMEOUT = timedelta(minutes=30)

@app.before_request
def check_idle_timeout():
    if not session.get('user'):
        return
    last = session.get('_last_activity')
    now  = datetime.utcnow()
    if last:
        from datetime import datetime as _dt
        last_dt = _dt.fromisoformat(last)
        if now - last_dt > IDLE_TIMEOUT:
            session.clear()
            flash('Tu sesión expiró por inactividad.', 'warning')
            from flask import redirect as _red, url_for as _ufor
            return _red(_ufor('auth.login'))
    session['_last_activity'] = now.isoformat()
    session.modified = True


with app.app_context():
    db.create_all()

    # ── Migración: agregar columnas nuevas si no existen ─────────────────────
    from sqlalchemy import text, inspect as sa_inspect
    def _add_col_if_missing(table, col, col_type):
        insp = sa_inspect(db.engine)
        existing = [c['name'] for c in insp.get_columns(table)]
        if col not in existing:
            with db.engine.connect() as conn:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}'))
                conn.commit()

    for col, typ in [('ram','VARCHAR(50)'), ('os_version','VARCHAR(100)'),
                     ('cpu','VARCHAR(150)'), ('supplier','VARCHAR(150)'),
                     ('last_maintenance','DATE'), ('client_id','INTEGER'),
                     ('department_id', 'INTEGER')]:
        _add_col_if_missing('assets', col, typ)

    # module_access + department_id on users
    _add_col_if_missing('users', 'module_access', 'TEXT')
    _add_col_if_missing('users', 'department_id', 'INTEGER')

    # security fields on users
    for col, typ in [('totp_secret', 'VARCHAR(32)'), ('mfa_enabled', 'INTEGER DEFAULT 0'),
                     ('force_password_change', 'INTEGER DEFAULT 0'),
                     ('failed_logins', 'INTEGER DEFAULT 0'),
                     ('locked_until', 'DATETIME')]:
        _add_col_if_missing('users', col, typ)

    # task_comments and project_activities — created by db.create_all() above
    for col, typ in [('icon', 'VARCHAR(50)'), ('color', 'VARCHAR(20)')]:
        _add_col_if_missing('project_activities', col, typ)

    # access_requests created by db.create_all() above; ensure columns exist
    for col, typ in [('department_id', 'INTEGER'), ('reason', 'TEXT'),
                     ('admin_notes', 'TEXT'), ('reviewed_by', 'VARCHAR(150)'),
                     ('reviewed_at', 'DATETIME')]:
        _add_col_if_missing('access_requests', col, typ)

    # Seed IT department if none exist
    from models import Department
    if Department.query.count() == 0:
        it = Department(name='IT', code='IT', color='#089ACF',
                        manager_name='IT Department')
        db.session.add(it)
        db.session.commit()
        print('✅  Departamento IT creado')

    # Crear admin por defecto si no existe ningún usuario
    from models import User
    if User.query.count() == 0:
        import secrets as _sec
        tmp_pwd = _sec.token_urlsafe(16)
        admin = User(name='Administrador', username='admin', role='admin',
                     force_password_change=True)
        admin.set_password(tmp_pwd)
        db.session.add(admin)
        db.session.commit()
        print(f'Usuario admin creado  ->  admin / {tmp_pwd}')
        print('Cambia la contrasena en el primer inicio de sesion.')

# ── Static image helpers ──────────────────────────────────────────────────────
STATIC = os.path.join(os.path.dirname(__file__), 'static', 'images')

def _img_exists(filename):
    return os.path.exists(os.path.join(STATIC, filename))


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


# ── Portal ────────────────────────────────────────────────────────────────────

_MODULE_URLS = {
    'inventory':  lambda: url_for('inventory_dashboard'),
    'projects':   lambda: url_for('projects.dashboard'),
    'evaluation': lambda: url_for('eval.index'),
    'repository': lambda: url_for('repo.index'),
}

@app.route('/')
@login_required
def portal():
    user     = session.get('user', {})
    modules  = user.get('modules', [])
    is_admin = user.get('role') == 'admin'
    uid      = user.get('id')

    # Pending access-request slugs for this user
    pending_slugs = set()
    denied_slugs  = set()
    if uid:
        my_reqs = AccessRequest.query.filter_by(user_id=uid).all()
        for r in my_reqs:
            if r.status == 'pending':
                pending_slugs.add(r.module_slug)
            elif r.status == 'denied':
                denied_slugs.add(r.module_slug)

    # Build card list — ALL modules, each tagged with access state
    all_cards = []
    for m in ALL_MODULES:
        card = dict(m)
        slug = m['slug']
        if is_admin or slug in modules:
            card['state'] = 'open'
            card['url']   = _MODULE_URLS[slug]()
        elif slug in pending_slugs:
            card['state'] = 'pending'
        else:
            card['state'] = 'locked'
        all_cards.append(card)

    return render_template('portal.html', all_cards=all_cards,
                           departments=Department.query.filter_by(active=True).all())


# ── Request Access ────────────────────────────────────────────────────────────

@app.route('/request-access/<slug>', methods=['POST'])
@login_required
def request_access(slug):
    user = session.get('user', {})
    uid  = user.get('id')
    # Verify slug is valid
    valid_slugs = [m['slug'] for m in ALL_MODULES]
    if slug not in valid_slugs:
        flash('Invalid module.', 'danger')
        return redirect(url_for('portal'))

    # Don't allow duplicate pending requests
    existing = AccessRequest.query.filter_by(
        user_id=uid, module_slug=slug, status='pending').first()
    if existing:
        flash('You already have a pending request for this module.', 'info')
        return redirect(url_for('portal'))

    dept_id = request.form.get('department_id', type=int) or None
    reason  = request.form.get('reason', '').strip()

    req = AccessRequest(
        user_id=uid,
        user_name=user.get('name'),
        module_slug=slug,
        department_id=dept_id,
        reason=reason,
        status='pending',
    )
    db.session.add(req)
    log_action('create', 'access_request',
               entity_name=f'{user.get("name")} → {slug}',
               details=reason[:200] if reason else None)
    db.session.commit()

    # Notify admins via Teams
    import notifications as notif
    cfg = notif.load_config()
    if cfg.get('enabled') and cfg.get('teams_enabled'):
        mod_name = next((m['name'] for m in ALL_MODULES if m['slug'] == slug), slug)
        notif.send_teams(
            f'Access Request: {mod_name}',
            f'{user.get("name")} is requesting access to **{mod_name}**.',
            facts=[('User', user.get('name')), ('Module', mod_name),
                   ('Reason', reason[:120] if reason else 'No reason given')],
            url=notif._url(cfg, '/admin/access-requests'),
            color='FFA000'
        )

    flash('Your request has been sent to IT. You\'ll be notified once it\'s reviewed.', 'success')
    return redirect(url_for('portal'))


# ── Inventory Dashboard ───────────────────────────────────────────────────────

@app.route('/inventory')
@module_required('inventory')
def inventory_dashboard():
    from models import User as _User
    sess_user   = session.get('user', {})
    is_admin    = sess_user.get('role') == 'admin'
    db_user     = _User.query.get(sess_user.get('id')) if sess_user.get('id') else None
    # Department-scoped access: non-admin users with a department see only that dept's assets
    dept_filter = None
    if not is_admin and db_user and db_user.department_id:
        dept_filter = db_user.department_id

    def _asset_q():
        q = Asset.query
        if dept_filter:
            q = q.filter_by(department_id=dept_filter)
        return q

    total_assets      = _asset_q().count()
    available         = _asset_q().filter_by(status='available').count()
    in_use            = _asset_q().filter_by(status='in_use').count()
    maintenance       = _asset_q().filter_by(status='maintenance').count()
    retired           = _asset_q().filter_by(status='retired').count()
    total_employees   = Employee.query.filter_by(active=True).count()
    total_categories  = Category.query.count()
    foraneo_count     = Asset.query.filter_by(location_type='foraneo').count()
    in_transit_count  = Shipment.query.filter_by(status='en_transito').count()
    recent_assignments = Assignment.query.order_by(Assignment.created_at.desc()).limit(8).all()
    recent_shipments  = Shipment.query.filter(
        Shipment.status.notin_(['entregado', 'devuelto'])
    ).order_by(Shipment.created_at.desc()).limit(5).all()
    categories  = Category.query.all()
    cat_stats   = [{'name': c.name, 'count': len(c.assets)} for c in categories]

    # ── Gráfica: datos raw (dicts por mes) para todas las fechas ─────────────
    # 4 queries totales — el JS resuelve cualquier rango/categoría client-side

    cats_for_chart = Category.query.order_by(Category.name).all()

    # 1) Adquisiciones por (category_id, YYYY-MM)
    acq_raw = db.session.query(
        Asset.category_id,
        db.func.strftime('%Y-%m', Asset.created_at),
        db.func.count(Asset.id)
    ).group_by(Asset.category_id,
               db.func.strftime('%Y-%m', Asset.created_at)).all()

    # 2) Bajas globales del audit log por YYYY-MM
    baja_raw = db.session.query(
        db.func.strftime('%Y-%m', AuditLog.created_at),
        db.func.count(AuditLog.id)
    ).filter(
        AuditLog.entity_type == 'asset',
        db.or_(
            AuditLog.action == 'delete',
            db.and_(AuditLog.action == 'update',
                    db.or_(AuditLog.details.ilike('%→ retired%'),
                           AuditLog.details.ilike('%→ disposed%')))
        )
    ).group_by(db.func.strftime('%Y-%m', AuditLog.created_at)).all()

    # 3) Bajas por categoría (activos retired/disposed, fecha updated_at)
    baja_cat_raw = db.session.query(
        Asset.category_id,
        db.func.strftime('%Y-%m', Asset.updated_at),
        db.func.count(Asset.id)
    ).filter(Asset.status.in_(['retired', 'disposed'])
    ).group_by(Asset.category_id,
               db.func.strftime('%Y-%m', Asset.updated_at)).all()

    # 4) Reasignaciones por (category_id, YYYY-MM)
    reas_raw = db.session.query(
        Asset.category_id,
        db.func.strftime('%Y-%m', Assignment.created_at),
        db.func.count(Assignment.id)
    ).join(Asset, Assignment.asset_id == Asset.id
    ).group_by(Asset.category_id,
               db.func.strftime('%Y-%m', Assignment.created_at)).all()

    # ── Construir estructura de dicts raw por categoría ───────────────────────
    cat_chart_raw = {
        'all': {'adquisiciones': {}, 'bajas': {}, 'reasignaciones': {}}
    }
    for cat in cats_for_chart:
        cat_chart_raw[str(cat.id)] = {'adquisiciones': {}, 'bajas': {}, 'reasignaciones': {}}

    for cat_id, ym, cnt in acq_raw:
        if not ym:
            continue
        cat_chart_raw['all']['adquisiciones'][ym] = \
            cat_chart_raw['all']['adquisiciones'].get(ym, 0) + cnt
        if cat_id and str(cat_id) in cat_chart_raw:
            cat_chart_raw[str(cat_id)]['adquisiciones'][ym] = cnt

    for ym, cnt in baja_raw:
        if ym:
            cat_chart_raw['all']['bajas'][ym] = cnt

    for cat_id, ym, cnt in baja_cat_raw:
        if ym and cat_id and str(cat_id) in cat_chart_raw:
            cat_chart_raw[str(cat_id)]['bajas'][ym] = cnt

    for cat_id, ym, cnt in reas_raw:
        if not ym:
            continue
        cat_chart_raw['all']['reasignaciones'][ym] = \
            cat_chart_raw['all']['reasignaciones'].get(ym, 0) + cnt
        if cat_id and str(cat_id) in cat_chart_raw:
            cat_chart_raw[str(cat_id)]['reasignaciones'][ym] = cnt

    chart_start_year = 2020

    active_dept = Department.query.get(dept_filter) if dept_filter else None

    # Warranty expiry alerts (30 / 60 days)
    soon_30 = date.today() + timedelta(days=30)
    soon_60 = date.today() + timedelta(days=60)
    warranty_expiring = _asset_q().filter(
        Asset.warranty_expiry != None,          # noqa: E711
        Asset.warranty_expiry <= soon_60,
        Asset.warranty_expiry >= date.today(),
        Asset.status.notin_(['retired', 'disposed'])
    ).order_by(Asset.warranty_expiry).limit(10).all()

    return render_template('inventory/dashboard.html',
                           total_assets=total_assets, available=available,
                           in_use=in_use, maintenance=maintenance, retired=retired,
                           total_employees=total_employees, total_categories=total_categories,
                           foraneo_count=foraneo_count, in_transit_count=in_transit_count,
                           recent_assignments=recent_assignments,
                           recent_shipments=recent_shipments,
                           cat_stats=cat_stats,
                           cat_chart_raw=cat_chart_raw,
                           cats_for_chart=cats_for_chart,
                           chart_start_year=chart_start_year,
                           chart_current_year=date.today().year,
                           active_dept=active_dept,
                           warranty_expiring=warranty_expiring,
                           soon_30=soon_30,
                           departments=Department.query.filter_by(active=True).order_by(Department.name).all())


# ── Assets ────────────────────────────────────────────────────────────────────

@app.route('/assets')
@login_required
def assets_list():
    q               = request.args.get('q', '')
    status_filter   = request.args.get('status', '')
    category_filter = request.args.get('category', '')
    loc_filter      = request.args.get('location_type', '')
    query = Asset.query
    if q:
        like = f'%{q}%'
        query = query.outerjoin(Client, Asset.client_id == Client.id).filter(db.or_(
            Asset.name.ilike(like), Asset.asset_tag.ilike(like),
            Asset.serial_number.ilike(like), Asset.manufacturer.ilike(like),
            Asset.model.ilike(like), Asset.supplier.ilike(like),
            Asset.location.ilike(like), Asset.cpu.ilike(like),
            Asset.ram.ilike(like), Client.name.ilike(like),
        ))
    if status_filter:
        query = query.filter_by(status=status_filter)
    if category_filter:
        query = query.filter_by(category_id=category_filter)
    if loc_filter:
        query = query.filter_by(location_type=loc_filter)
    page       = request.args.get('page', 1, type=int)
    per_page   = 50
    pagination = query.order_by(Asset.asset_tag).paginate(page=page, per_page=per_page, error_out=False)
    assets     = pagination.items
    categories = Category.query.order_by(Category.name).all()
    return render_template('assets/list.html', assets=assets, categories=categories,
                           q=q, status_filter=status_filter,
                           category_filter=category_filter, loc_filter=loc_filter,
                           pagination=pagination)


@app.route('/assets/new', methods=['GET', 'POST'])
@login_required
def asset_new():
    categories  = Category.query.order_by(Category.name).all()
    clients     = Client.query.filter_by(active=True).order_by(Client.name).all()
    return_url  = request.args.get('return_url') or url_for('assets_list')
    if request.method == 'POST':
        return_url = request.form.get('return_url') or return_url
        asset_tag  = request.form.get('asset_tag', '').strip()
        if Asset.query.filter_by(asset_tag=asset_tag).first():
            flash(f'El Asset Tag "{asset_tag}" ya existe.', 'danger')
            return render_template('assets/form.html', categories=categories,
                                   clients=clients, asset=None,
                                   form=request.form, return_url=return_url)
        asset = Asset(
            name=request.form.get('name', '').strip(),
            asset_tag=asset_tag,
            serial_number=request.form.get('serial_number', '').strip() or None,
            manufacturer=request.form.get('manufacturer', '').strip() or None,
            model=request.form.get('model', '').strip() or None,
            ram=request.form.get('ram', '').strip() or None,
            cpu=request.form.get('cpu', '').strip() or None,
            os_version=request.form.get('os_version', '').strip() or None,
            category_id=request.form.get('category_id') or None,
            client_id=request.form.get('client_id') or None,
            status=request.form.get('status', 'available'),
            location_type=request.form.get('location_type', 'en_sitio'),
            location=request.form.get('location', '').strip() or None,
            purchase_date=parse_date(request.form.get('purchase_date')),
            purchase_cost=float(request.form.get('purchase_cost')) if request.form.get('purchase_cost') else None,
            supplier=request.form.get('supplier', '').strip() or None,
            warranty_expiry=parse_date(request.form.get('warranty_expiry')),
            last_maintenance=parse_date(request.form.get('last_maintenance')),
            notes=request.form.get('notes', '').strip() or None,
        )
        db.session.add(asset)
        log_action('create', 'asset', entity_name=asset.name,
                   details=f'Tag: {asset_tag} | Estado: {asset.status} | Tipo: {asset.location_type}')
        db.session.commit()
        flash(f'Activo "{asset.name}" creado correctamente.', 'success')
        return redirect(return_url)
    return render_template('assets/form.html', categories=categories,
                           clients=clients, asset=None, form={}, return_url=return_url)


@app.route('/assets/<int:id>')
@login_required
def asset_detail(id):
    asset      = Asset.query.get_or_404(id)
    return_url = request.args.get('return_url') or url_for('assets_list')
    # Per-asset audit history
    history = AuditLog.query.filter(
        AuditLog.entity_type == 'asset',
        AuditLog.entity_id   == id,
    ).order_by(AuditLog.created_at.desc()).limit(50).all()
    return render_template('assets/detail.html', asset=asset, return_url=return_url,
                           history=history)


@app.route('/assets/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def asset_edit(id):
    asset      = Asset.query.get_or_404(id)
    categories = Category.query.order_by(Category.name).all()
    clients    = Client.query.filter_by(active=True).order_by(Client.name).all()
    return_url = request.args.get('return_url') or url_for('assets_list')
    if request.method == 'POST':
        return_url = request.form.get('return_url') or return_url
        new_tag    = request.form.get('asset_tag', '').strip()
        existing   = Asset.query.filter_by(asset_tag=new_tag).first()
        if existing and existing.id != asset.id:
            flash(f'El Asset Tag "{new_tag}" ya existe en otro activo.', 'danger')
            return render_template('assets/form.html', categories=categories,
                                   clients=clients, asset=asset,
                                   form=request.form, return_url=return_url)
        changes = []
        if asset.name != request.form.get('name', '').strip():
            changes.append(f'nombre: {asset.name} → {request.form.get("name").strip()}')
        if asset.status != request.form.get('status'):
            changes.append(f'estado: {asset.status} → {request.form.get("status")}')
        if asset.location_type != request.form.get('location_type'):
            changes.append(f'tipo: {asset.location_type} → {request.form.get("location_type")}')
        new_client_id = request.form.get('client_id') or None
        if str(asset.client_id or '') != str(new_client_id or ''):
            changes.append(f'cliente actualizado')

        asset.name             = request.form.get('name', '').strip()
        asset.asset_tag        = new_tag
        asset.serial_number    = request.form.get('serial_number', '').strip() or None
        asset.manufacturer     = request.form.get('manufacturer', '').strip() or None
        asset.model            = request.form.get('model', '').strip() or None
        asset.ram              = request.form.get('ram', '').strip() or None
        asset.cpu              = request.form.get('cpu', '').strip() or None
        asset.os_version       = request.form.get('os_version', '').strip() or None
        asset.category_id      = request.form.get('category_id') or None
        asset.client_id        = new_client_id
        asset.status           = request.form.get('status', 'available')
        asset.location_type    = request.form.get('location_type', 'en_sitio')
        asset.location         = request.form.get('location', '').strip() or None
        asset.purchase_date    = parse_date(request.form.get('purchase_date'))
        asset.purchase_cost    = float(request.form.get('purchase_cost')) if request.form.get('purchase_cost') else None
        asset.supplier         = request.form.get('supplier', '').strip() or None
        asset.warranty_expiry  = parse_date(request.form.get('warranty_expiry'))
        asset.last_maintenance = parse_date(request.form.get('last_maintenance'))
        asset.notes            = request.form.get('notes', '').strip() or None
        log_action('update', 'asset', entity_id=asset.id, entity_name=asset.name,
                   details='; '.join(changes) if changes else 'Actualización sin cambios clave')
        db.session.commit()
        flash(f'Activo "{asset.name}" actualizado.', 'success')
        return redirect(return_url)
    return render_template('assets/form.html', categories=categories,
                           clients=clients, asset=asset, form={}, return_url=return_url)


@app.route('/assets/<int:id>/delete', methods=['POST'])
@login_required
def asset_delete(id):
    asset = Asset.query.get_or_404(id)
    name  = asset.name
    tag   = asset.asset_tag
    log_action('delete', 'asset', entity_id=asset.id, entity_name=name,
               details=f'Activo eliminado: {tag}')
    db.session.delete(asset)
    db.session.commit()
    flash(f'Activo "{name}" eliminado.', 'warning')
    return redirect(url_for('assets_list'))


# ── Employees ─────────────────────────────────────────────────────────────────

@app.route('/employees')
@login_required
def employees_list():
    q            = request.args.get('q', '')
    show_inactive = request.args.get('inactive', '')
    query = Employee.query
    if not show_inactive:
        query = query.filter_by(active=True)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(
            Employee.name.ilike(like), Employee.employee_id.ilike(like),
            Employee.department.ilike(like), Employee.email.ilike(like)
        ))
    page       = request.args.get('page', 1, type=int)
    pagination = query.order_by(Employee.name).paginate(page=page, per_page=50, error_out=False)
    employees  = pagination.items
    return render_template('employees/list.html', employees=employees,
                           q=q, show_inactive=show_inactive, pagination=pagination)


@app.route('/employees/new', methods=['GET', 'POST'])
@login_required
def employee_new():
    if request.method == 'POST':
        emp_id = request.form.get('employee_id', '').strip()
        if Employee.query.filter_by(employee_id=emp_id).first():
            flash(f'El ID de empleado "{emp_id}" ya existe.', 'danger')
            return render_template('employees/form.html', employee=None, form=request.form)
        emp = Employee(
            name=request.form.get('name', '').strip(),
            employee_id=emp_id,
            department=request.form.get('department', '').strip() or None,
            email=request.form.get('email', '').strip() or None,
            phone=request.form.get('phone', '').strip() or None,
            active=True,
        )
        db.session.add(emp)
        log_action('create', 'employee', entity_name=emp.name,
                   details=f'ID: {emp_id} | Depto: {emp.department}')
        db.session.commit()
        flash(f'Empleado "{emp.name}" creado correctamente.', 'success')
        return redirect(url_for('employees_list'))
    return render_template('employees/form.html', employee=None, form={})


@app.route('/employees/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def employee_edit(id):
    emp = Employee.query.get_or_404(id)
    if request.method == 'POST':
        new_emp_id = request.form.get('employee_id', '').strip()
        existing   = Employee.query.filter_by(employee_id=new_emp_id).first()
        if existing and existing.id != emp.id:
            flash(f'El ID "{new_emp_id}" ya existe en otro empleado.', 'danger')
            return render_template('employees/form.html', employee=emp, form=request.form)
        changes = []
        if emp.name != request.form.get('name', '').strip():
            changes.append(f'nombre: {emp.name} → {request.form.get("name").strip()}')
        if emp.department != (request.form.get('department', '').strip() or None):
            changes.append(f'depto: {emp.department} → {request.form.get("department")}')
        emp.name       = request.form.get('name', '').strip()
        emp.employee_id = new_emp_id
        emp.department = request.form.get('department', '').strip() or None
        emp.email      = request.form.get('email', '').strip() or None
        emp.phone      = request.form.get('phone', '').strip() or None
        emp.active     = 'active' in request.form
        log_action('update', 'employee', entity_id=emp.id, entity_name=emp.name,
                   details='; '.join(changes) if changes else 'Sin cambios clave')
        db.session.commit()
        flash(f'Empleado "{emp.name}" actualizado.', 'success')
        return redirect(url_for('employees_list'))
    return render_template('employees/form.html', employee=emp, form={})


@app.route('/employees/<int:id>/delete', methods=['POST'])
@login_required
def employee_delete(id):
    emp  = Employee.query.get_or_404(id)
    name = emp.name
    log_action('delete', 'employee', entity_id=emp.id, entity_name=name,
               details=f'Empleado eliminado: {emp.employee_id}')
    db.session.delete(emp)
    db.session.commit()
    flash(f'Empleado "{name}" eliminado.', 'warning')
    return redirect(url_for('employees_list'))


# ── Assignments ───────────────────────────────────────────────────────────────

@app.route('/assignments')
@login_required
def assignments_list():
    active_only = request.args.get('active', '1')
    query = Assignment.query
    if active_only == '1':
        query = query.filter_by(returned_date=None)
    assignments = query.order_by(Assignment.assigned_date.desc()).all()
    return render_template('assignments/list.html',
                           assignments=assignments, active_only=active_only)


@app.route('/assignments/new', methods=['GET', 'POST'])
@login_required
def assignment_new():
    assets    = Asset.query.filter_by(status='available').order_by(Asset.name).all()
    employees = Employee.query.filter_by(active=True).order_by(Employee.name).all()
    pre_asset = request.args.get('asset_id')
    if request.method == 'POST':
        asset_id    = int(request.form.get('asset_id'))
        employee_id = int(request.form.get('employee_id'))
        asset = Asset.query.get_or_404(asset_id)
        if asset.current_assignment:
            flash('Este activo ya está asignado. Devuélvelo primero.', 'danger')
            return redirect(url_for('assignments_list'))
        emp = Employee.query.get_or_404(employee_id)
        assignment = Assignment(
            asset_id=asset_id,
            employee_id=employee_id,
            assigned_date=parse_date(request.form.get('assigned_date')) or date.today(),
            notes=request.form.get('notes', '').strip() or None,
        )
        asset.status = 'in_use'
        db.session.add(assignment)
        log_action('create', 'assignment',
                   entity_name=f'{asset.asset_tag} → {emp.name}',
                   details=f'Activo: {asset.name} asignado a {emp.name} ({emp.employee_id})')
        db.session.commit()
        flash('Asignación creada correctamente.', 'success')
        return redirect(url_for('assignments_list'))
    return render_template('assignments/form.html',
                           assets=assets, employees=employees, pre_asset=pre_asset)


@app.route('/assignments/<int:id>/return', methods=['POST'])
@login_required
def assignment_return(id):
    assignment = Assignment.query.get_or_404(id)
    if assignment.returned_date:
        flash('Este activo ya fue devuelto.', 'warning')
        return redirect(url_for('assignments_list'))
    assignment.returned_date   = parse_date(request.form.get('returned_date')) or date.today()
    assignment.asset.status    = 'available'
    log_action('update', 'assignment',
               entity_id=assignment.id,
               entity_name=assignment.asset.name,
               details=f'Devolución de {assignment.asset.asset_tag} por {assignment.employee.name}')
    db.session.commit()
    flash(f'Activo "{assignment.asset.name}" devuelto correctamente.', 'success')
    return redirect(url_for('assignments_list'))


# ── Categories ────────────────────────────────────────────────────────────────

@app.route('/categories')
@login_required
def categories_list():
    categories = Category.query.order_by(Category.name).all()
    return render_template('categories/list.html', categories=categories)


@app.route('/categories/new', methods=['GET', 'POST'])
@login_required
def category_new():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if Category.query.filter_by(name=name).first():
            flash(f'La categoría "{name}" ya existe.', 'danger')
            return render_template('categories/form.html', category=None, form=request.form)
        cat = Category(name=name,
                       description=request.form.get('description', '').strip() or None)
        db.session.add(cat)
        log_action('create', 'category', entity_name=name,
                   details=f'Categoría creada: {name}')
        db.session.commit()
        flash(f'Categoría "{cat.name}" creada.', 'success')
        return redirect(url_for('categories_list'))
    return render_template('categories/form.html', category=None, form={})


@app.route('/categories/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def category_edit(id):
    cat = Category.query.get_or_404(id)
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        existing = Category.query.filter_by(name=name).first()
        if existing and existing.id != cat.id:
            flash(f'La categoría "{name}" ya existe.', 'danger')
            return render_template('categories/form.html', category=cat, form=request.form)
        old_name = cat.name
        cat.name        = name
        cat.description = request.form.get('description', '').strip() or None
        log_action('update', 'category', entity_id=cat.id, entity_name=name,
                   details=f'Categoría renombrada: {old_name} → {name}' if old_name != name else 'Descripción actualizada')
        db.session.commit()
        flash(f'Categoría "{cat.name}" actualizada.', 'success')
        return redirect(url_for('categories_list'))
    return render_template('categories/form.html', category=cat, form={})


@app.route('/categories/<int:id>/delete', methods=['POST'])
@login_required
def category_delete(id):
    cat = Category.query.get_or_404(id)
    if cat.assets:
        flash(f'No se puede eliminar "{cat.name}": tiene activos asociados.', 'danger')
        return redirect(url_for('categories_list'))
    name = cat.name
    log_action('delete', 'category', entity_id=cat.id, entity_name=name,
               details=f'Categoría eliminada: {name}')
    db.session.delete(cat)
    db.session.commit()
    flash(f'Categoría "{name}" eliminada.', 'warning')
    return redirect(url_for('categories_list'))


# ── Shipments (DHL / Foráneo) ─────────────────────────────────────────────────

@app.route('/shipments')
@login_required
def shipments_list():
    status_filter = request.args.get('status', '')
    query = Shipment.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    page       = request.args.get('page', 1, type=int)
    pagination = query.order_by(Shipment.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    shipments  = pagination.items
    return render_template('shipments/list.html',
                           shipments=shipments, status_filter=status_filter,
                           pagination=pagination)


@app.route('/shipments/new', methods=['GET', 'POST'])
@app.route('/shipments/new/<int:asset_id>', methods=['GET', 'POST'])
@login_required
def shipment_new(asset_id=None):
    foraneo_assets = Asset.query.filter(
        Asset.location_type.in_(['foraneo', 'hibrido'])
    ).order_by(Asset.name).all()
    pre_asset = asset_id or request.args.get('asset_id')
    if request.method == 'POST':
        shipment = Shipment(
            asset_id=int(request.form.get('asset_id')),
            direction=request.form.get('direction', 'outbound'),
            carrier=request.form.get('carrier', 'DHL').strip(),
            tracking_number=request.form.get('tracking_number', '').strip(),
            origin=request.form.get('origin', '').strip() or None,
            destination=request.form.get('destination', '').strip() or None,
            recipient_name=request.form.get('recipient_name', '').strip() or None,
            status=request.form.get('status', 'pendiente'),
            ship_date=parse_date(request.form.get('ship_date')),
            estimated_delivery=parse_date(request.form.get('estimated_delivery')),
            notes=request.form.get('notes', '').strip() or None,
        )
        db.session.add(shipment)
        log_action('create', 'shipment',
                   entity_name=f'{shipment.carrier} #{shipment.tracking_number}',
                   details=f'Carrier: {shipment.carrier} | Tracking: {shipment.tracking_number} | Destino: {shipment.destination}')
        db.session.commit()
        # Auto-register in AfterShip
        import tracking as trk
        if trk._API_KEY and shipment.tracking_number:
            try:
                trk.refresh_shipment(shipment)
                db.session.commit()
            except Exception:
                pass
        flash(f'Envío {shipment.carrier} #{shipment.tracking_number} registrado.', 'success')
        return redirect(url_for('shipment_detail', id=shipment.id))
    return render_template('shipments/form.html',
                           foraneo_assets=foraneo_assets, shipment=None,
                           pre_asset=str(pre_asset) if pre_asset else '',
                           pre_direction='outbound', pre_origin='', form={})


@app.route('/shipments/<int:id>')
@login_required
def shipment_detail(id):
    shipment = Shipment.query.get_or_404(id)
    return render_template('shipments/detail.html', shipment=shipment)


@app.route('/shipments/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def shipment_edit(id):
    shipment       = Shipment.query.get_or_404(id)
    foraneo_assets = Asset.query.filter(
        Asset.location_type.in_(['foraneo', 'hibrido'])
    ).order_by(Asset.name).all()
    if request.method == 'POST':
        old_status = shipment.status
        shipment.carrier           = request.form.get('carrier', 'DHL').strip()
        shipment.tracking_number   = request.form.get('tracking_number', '').strip()
        shipment.origin            = request.form.get('origin', '').strip() or None
        shipment.destination       = request.form.get('destination', '').strip() or None
        shipment.recipient_name    = request.form.get('recipient_name', '').strip() or None
        shipment.status            = request.form.get('status', 'pendiente')
        shipment.ship_date         = parse_date(request.form.get('ship_date'))
        shipment.estimated_delivery = parse_date(request.form.get('estimated_delivery'))
        shipment.actual_delivery   = parse_date(request.form.get('actual_delivery'))
        shipment.notes             = request.form.get('notes', '').strip() or None
        log_action('update', 'shipment', entity_id=shipment.id,
                   entity_name=f'{shipment.carrier} #{shipment.tracking_number}',
                   details=f'Estado: {old_status} → {shipment.status}' if old_status != shipment.status else 'Actualización de datos')
        db.session.commit()
        flash(f'Envío #{shipment.tracking_number} actualizado.', 'success')
        return redirect(url_for('shipment_detail', id=shipment.id))
    return render_template('shipments/form.html',
                           foraneo_assets=foraneo_assets, shipment=shipment,
                           pre_asset=str(shipment.asset_id), form={})


@app.route('/shipments/<int:id>/delete', methods=['POST'])
@login_required
def shipment_delete(id):
    shipment = Shipment.query.get_or_404(id)
    log_action('delete', 'shipment', entity_id=shipment.id,
               entity_name=f'{shipment.carrier} #{shipment.tracking_number}',
               details='Envío eliminado')
    db.session.delete(shipment)
    db.session.commit()
    flash('Envío eliminado.', 'warning')
    return redirect(url_for('shipments_list'))


# ── Package Tracking (AfterShip) ─────────────────────────────────────────────

@app.route('/shipments/<int:id>/track', methods=['POST'])
@login_required
@csrf.exempt   # llamado también vía fetch desde el detalle
def shipment_track(id):
    """Rastrear un envío ahora mismo y actualizar su estado."""
    import tracking as trk
    shipment = Shipment.query.get_or_404(id)

    if not trk._API_KEY:
        return jsonify({'ok': False, 'error': 'AFTERSHIP_API_KEY no configurado en .env'}), 503

    ok = trk.refresh_shipment(shipment)
    if ok:
        db.session.commit()
        import json as _json
        events = []
        if shipment.tracking_events:
            try:
                events = _json.loads(shipment.tracking_events)
            except Exception:
                pass
        return jsonify({
            'ok':       True,
            'status':   shipment.status,
            'tag':      shipment.tracking_tag,
            'eta':      shipment.est_delivery_afship.isoformat() if shipment.est_delivery_afship else None,
            'updated':  shipment.last_tracking_at.strftime('%d/%m/%Y %H:%M') if shipment.last_tracking_at else None,
            'events':   events[-10:],   # últimos 10 para el timeline
        })
    return jsonify({'ok': False, 'error': 'No se pudo obtener información del carrier'}), 502


@app.route('/shipments/return/<int:asset_id>', methods=['GET', 'POST'])
@login_required
def shipment_return(asset_id):
    """Create an inbound (return) shipment for an asset."""
    asset = Asset.query.get_or_404(asset_id)
    ca = asset.current_assignment  # to get employee info
    foraneo_assets = Asset.query.filter(Asset.location_type.in_(['foraneo', 'hibrido'])).order_by(Asset.name).all()

    if request.method == 'POST':
        shipment = Shipment(
            asset_id=asset_id,
            direction='inbound',
            carrier=request.form.get('carrier', 'DHL').strip(),
            tracking_number=request.form.get('tracking_number', '').strip(),
            origin=request.form.get('origin', '').strip() or None,
            destination=request.form.get('destination', '').strip() or None,
            recipient_name=request.form.get('recipient_name', '').strip() or None,
            status=request.form.get('status', 'pendiente'),
            ship_date=parse_date(request.form.get('ship_date')),
            estimated_delivery=parse_date(request.form.get('estimated_delivery')),
            notes=request.form.get('notes', '').strip() or None,
        )
        db.session.add(shipment)
        log_action('create', 'shipment', entity_name=f'RETURN {shipment.carrier} #{shipment.tracking_number}',
                   details=f'Devolución de {asset.asset_tag} | Carrier: {shipment.carrier}')
        db.session.commit()

        # Auto-register in AfterShip if API key is set
        import tracking as trk
        if trk._API_KEY and shipment.tracking_number:
            try:
                trk.refresh_shipment(shipment)
                db.session.commit()
            except Exception:
                pass

        flash(f'Devolución registrada: {shipment.carrier} #{shipment.tracking_number}', 'success')
        return redirect(url_for('shipment_detail', id=shipment.id))

    # Pre-fill: origin = employee location, destination = RTS office
    pre_origin = ''
    if ca and ca.employee:
        pre_origin = ca.employee.department or ''

    return render_template('shipments/form.html',
                           foraneo_assets=foraneo_assets,
                           shipment=None,
                           pre_asset=str(asset_id),
                           pre_direction='inbound',
                           pre_origin=pre_origin,
                           form={})


@app.route('/webhooks/aftership', methods=['POST'])
@csrf.exempt
def aftership_webhook():
    """AfterShip sends real-time status updates here."""
    import tracking as trk, json as _json
    try:
        payload = request.get_json(force=True) or {}
        tracking_data = payload.get('data', {}).get('tracking', payload.get('data', {}))

        if not tracking_data:
            return jsonify({'ok': True})

        tracking_number = tracking_data.get('tracking_number')
        if not tracking_number:
            return jsonify({'ok': True})

        # Find matching shipment
        shipment = Shipment.query.filter_by(tracking_number=tracking_number).first()
        if shipment:
            shipment.tracking_tag     = tracking_data.get('tag')
            shipment.last_tracking_at = datetime.utcnow()

            tag = tracking_data.get('tag', '')
            new_status = Shipment.AFTERSHIP_STATUS_MAP.get(tag)
            if new_status:
                shipment.status = new_status

            # Store events
            events = tracking_data.get('events', tracking_data.get('checkpoints', []))[-20:]
            normalized = [{'message': e.get('message', ''), 'location': e.get('location', ''), 'checkpoint_time': e.get('occurred_at', e.get('checkpoint_time', ''))} for e in events]
            shipment.tracking_events = _json.dumps(normalized, ensure_ascii=False)

            db.session.commit()
            app.logger.info("Webhook: shipment %s updated to %s", shipment.id, shipment.status)
    except Exception as e:
        app.logger.exception("Webhook error: %s", e)

    return jsonify({'ok': True})


@app.route('/shipments/refresh-all', methods=['POST'])
@login_required
def shipments_refresh_all():
    """Actualiza todos los envíos activos — llamado por el scheduler o manualmente."""
    import tracking as trk
    updated = trk.refresh_all_active(app)
    flash(f'Tracking actualizado: {updated} envío(s) sincronizados.', 'success')
    return redirect(url_for('shipments_list'))


# ── Clients (Empresas) ────────────────────────────────────────────────────────

@app.route('/clients')
@login_required
def clients_list():
    q       = request.args.get('q', '')
    clients = Client.query
    if q:
        clients = clients.filter(Client.name.ilike(f'%{q}%'))
    clients = clients.order_by(Client.name).all()
    return render_template('clients/list.html', clients=clients, q=q)


@app.route('/clients/new', methods=['GET', 'POST'])
@login_required
def client_new():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('El nombre del cliente es obligatorio.', 'danger')
            return render_template('clients/form.html', client=None, form=request.form)
        if Client.query.filter_by(name=name).first():
            flash(f'El cliente "{name}" ya existe.', 'danger')
            return render_template('clients/form.html', client=None, form=request.form)
        cli = Client(name=name, active=True)
        db.session.add(cli)
        log_action('create', 'client', entity_name=name, details=f'Cliente creado: {name}')
        db.session.commit()
        flash(f'Cliente "{name}" creado correctamente.', 'success')
        return redirect(url_for('clients_list'))
    return render_template('clients/form.html', client=None, form={})


@app.route('/clients/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def client_edit(id):
    cli = Client.query.get_or_404(id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('El nombre del cliente es obligatorio.', 'danger')
            return render_template('clients/form.html', client=cli, form=request.form)
        existing = Client.query.filter_by(name=name).first()
        if existing and existing.id != cli.id:
            flash(f'El cliente "{name}" ya existe.', 'danger')
            return render_template('clients/form.html', client=cli, form=request.form)
        old_name  = cli.name
        cli.name   = name
        cli.active = 'active' in request.form
        log_action('update', 'client', entity_id=cli.id, entity_name=name,
                   details=f'Renombrado: {old_name} → {name}' if old_name != name else 'Actualizado')
        db.session.commit()
        flash(f'Cliente "{cli.name}" actualizado.', 'success')
        return redirect(url_for('clients_list'))
    return render_template('clients/form.html', client=cli, form={})


@app.route('/clients/<int:id>/delete', methods=['POST'])
@login_required
def client_delete(id):
    cli = Client.query.get_or_404(id)
    if cli.assets:
        flash(f'No se puede eliminar "{cli.name}": tiene activos asociados.', 'danger')
        return redirect(url_for('clients_list'))
    name = cli.name
    log_action('delete', 'client', entity_id=cli.id, entity_name=name,
               details=f'Cliente eliminado: {name}')
    db.session.delete(cli)
    db.session.commit()
    flash(f'Cliente "{name}" eliminado.', 'warning')
    return redirect(url_for('clients_list'))


# ── Template filters & context ────────────────────────────────────────────────

@app.template_filter('format_date')
def format_date(value):
    if not value:
        return '—'
    if isinstance(value, str):
        return value
    return value.strftime('%d/%m/%Y')


@app.template_filter('format_currency')
def format_currency(value):
    if value is None:
        return '—'
    return f'${value:,.2f} MXN'


# ── Import Assets from Excel ──────────────────────────────────────────────────

@app.route('/assets/import', methods=['GET', 'POST'])
@module_required('inventory')
def asset_import():
    if request.method == 'POST':
        f = request.files.get('file')
        if not f or not f.filename.endswith(('.xlsx', '.xls')):
            flash('Please upload a valid Excel file (.xlsx).', 'danger')
            return redirect(url_for('asset_import'))

        import openpyxl
        try:
            wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
        except Exception as e:
            flash(f'Could not read file: {e}', 'danger')
            return redirect(url_for('asset_import'))

        if len(rows) < 2:
            flash('File appears empty (no data rows).', 'warning')
            return redirect(url_for('asset_import'))

        # Map header → column index (case-insensitive)
        header = [str(h).strip().lower() if h else '' for h in rows[0]]
        def col(name):
            try: return header.index(name.lower())
            except ValueError: return None

        cat_cache = {c.name.lower(): c for c in Category.query.all()}
        created = updated = skipped = 0
        errors  = []

        for i, row in enumerate(rows[1:], start=2):
            def v(name, default=''):
                idx = col(name)
                val = row[idx] if idx is not None and idx < len(row) else None
                return str(val).strip() if val is not None else default

            tag = v('asset tag')
            if not tag:
                errors.append(f'Row {i}: missing asset tag — skipped.')
                skipped += 1
                continue

            existing = Asset.query.filter_by(asset_tag=tag).first()
            cat_name = v('category')
            category = cat_cache.get(cat_name.lower()) if cat_name else None
            if cat_name and not category:
                category = Category(name=cat_name)
                db.session.add(category)
                db.session.flush()
                cat_cache[cat_name.lower()] = category

            fields = {
                'name':         v('name') or tag,
                'asset_tag':    tag,
                'serial_number': v('serial number') or None,
                'manufacturer': v('manufacturer') or None,
                'model':        v('model') or None,
                'cpu':          v('cpu') or None,
                'ram':          v('ram') or None,
                'os_version':   v('os version') or None,
                'location':     v('location') or None,
                'location_type': v('location type') or 'en_sitio',
                'supplier':     v('supplier') or None,
                'notes':        v('notes') or None,
                'status':       v('status') or 'available',
                'category_id':  category.id if category else None,
            }
            # Parse dates
            for df in ['purchase date', 'warranty expiry', 'last maintenance']:
                val = v(df)
                field_name = df.replace(' ', '_')
                if val:
                    try:
                        import datetime as _dt
                        if isinstance(val, _dt.date):
                            fields[field_name] = val
                        else:
                            fields[field_name] = _dt.datetime.strptime(val[:10], '%Y-%m-%d').date()
                    except Exception:
                        pass
            # Cost
            cost_val = v('purchase cost')
            if cost_val:
                try: fields['purchase_cost'] = float(str(cost_val).replace(',', '').replace('$', ''))
                except Exception: pass

            if existing:
                for k, val in fields.items():
                    if val is not None and val != '':
                        setattr(existing, k, val)
                log_action('update', 'asset', entity_id=existing.id,
                           entity_name=existing.asset_tag, details='Updated via Excel import')
                updated += 1
            else:
                asset = Asset(**{k: v_ for k, v_ in fields.items() if v_ is not None and v_ != ''})
                db.session.add(asset)
                log_action('create', 'asset', entity_name=tag, details='Created via Excel import')
                created += 1

        db.session.commit()
        msg = f'Import complete: {created} created, {updated} updated, {skipped} skipped.'
        if errors:
            msg += f' ({len(errors)} errors — check logs.)'
        flash(msg, 'success' if not errors else 'warning')
        return redirect(url_for('assets_list'))

    # Template shows download link for the import template
    categories = Category.query.order_by(Category.name).all()
    return render_template('assets/import.html', categories=categories)


@app.route('/assets/import/template.xlsx')
@module_required('inventory')
def asset_import_template():
    """Download a blank Excel template for importing assets."""
    import openpyxl, io
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Assets'
    from openpyxl.styles import PatternFill, Font, Alignment
    headers = [
        'Asset Tag', 'Name', 'Category', 'Status', 'Location Type', 'Location',
        'Manufacturer', 'Model', 'CPU', 'RAM', 'OS Version', 'Serial Number',
        'Purchase Date', 'Purchase Cost', 'Supplier', 'Warranty Expiry',
        'Last Maintenance', 'Notes',
    ]
    navy = PatternFill('solid', fgColor='233C6E')
    for ci, h in enumerate(headers, 1):
        c = ws.cell(1, ci, value=h)
        c.fill = navy
        c.font = Font(name='Calibri', bold=True, color='FFFFFF', size=11)
        c.alignment = Alignment(horizontal='center', vertical='center')
        ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = max(len(h) + 4, 14)
    ws.row_dimensions[1].height = 22
    ws.freeze_panes = 'A2'
    # Example row
    example = ['RTS-001', 'Sample Laptop', 'Laptops', 'available', 'en_sitio', 'Office',
               'Dell', 'Latitude 5540', 'Intel Core i7', '16 GB', 'Windows 11', 'SN123456',
               '2024-01-15', '25000', 'CompuMexicana', '2026-01-15', '2025-06-01', 'Example row']
    for ci, val in enumerate(example, 1):
        ws.cell(2, ci, value=val)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True,
                     download_name='RTS_Asset_Import_Template.xlsx')


# ── Bulk Asset Operations ─────────────────────────────────────────────────────

@app.route('/assets/bulk', methods=['POST'])
@csrf.exempt
@module_required('inventory')
def asset_bulk():
    from flask import jsonify
    ids    = request.form.getlist('ids[]')
    action = request.form.get('action')
    if not ids or not action:
        return jsonify({'ok': False, 'error': 'Missing ids or action'})

    assets = Asset.query.filter(Asset.id.in_([int(i) for i in ids])).all()
    changed = 0

    if action in ('available', 'in_use', 'maintenance', 'retired', 'disposed'):
        for a in assets:
            a.status = action
            log_action('update', 'asset', entity_id=a.id, entity_name=a.asset_tag,
                       details=f'Bulk status → {action}')
            changed += 1
    elif action.startswith('dept:'):
        dept_id = int(action.split(':')[1]) or None
        for a in assets:
            a.department_id = dept_id
            log_action('update', 'asset', entity_id=a.id, entity_name=a.asset_tag,
                       details=f'Bulk dept → {dept_id}')
            changed += 1
    else:
        return jsonify({'ok': False, 'error': 'Unknown action'})

    db.session.commit()
    return jsonify({'ok': True, 'changed': changed})


@app.route('/search')
@csrf.exempt
@login_required
def global_search():
    from flask import jsonify
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'assets': [], 'employees': [], 'projects': []})

    like = f'%{q}%'
    results = {'assets': [], 'employees': [], 'projects': []}

    # Assets
    from models import User as _User
    sess_user = session.get('user', {})
    is_admin  = sess_user.get('role') == 'admin'
    db_user   = _User.query.get(sess_user.get('id')) if sess_user.get('id') else None
    dept_filter = None
    if not is_admin and db_user and db_user.department_id:
        dept_filter = db_user.department_id

    aq = Asset.query.filter(db.or_(
        Asset.name.ilike(like), Asset.asset_tag.ilike(like),
        Asset.serial_number.ilike(like), Asset.manufacturer.ilike(like),
        Asset.model.ilike(like),
    ))
    if dept_filter:
        aq = aq.filter_by(department_id=dept_filter)
    for a in aq.limit(6).all():
        results['assets'].append({
            'title': a.asset_tag,
            'sub':   a.name + (' · ' + a.category.name if a.category else ''),
            'url':   url_for('asset_detail', id=a.id),
        })

    # Employees
    for e in Employee.query.filter(db.or_(
        Employee.name.ilike(like), Employee.employee_id.ilike(like),
        Employee.email.ilike(like), Employee.department.ilike(like),
    )).limit(5).all():
        results['employees'].append({
            'title': e.name,
            'sub':   e.employee_id + (f' · {e.department}' if e.department else ''),
            'url':   url_for('employee_edit', id=e.id),
        })

    # Projects (if module access)
    from models import Project
    if is_admin or 'projects' in sess_user.get('modules', []):
        for p in Project.query.filter(db.or_(
            Project.name.ilike(like), Project.code.ilike(like),
        )).limit(5).all():
            results['projects'].append({
                'title': p.name,
                'sub':   p.code + f' · {p.status.replace("_"," ").title()}',
                'url':   url_for('projects.project_detail', id=p.id),
            })

    return jsonify(results)


# ── User Profile ──────────────────────────────────────────────────────────────

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    from models import User as _User
    uid  = session['user']['id']
    user = _User.query.get_or_404(uid)

    if request.method == 'POST':
        name  = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip() or None
        pwd   = request.form.get('password', '').strip()
        pwd2  = request.form.get('password2', '').strip()

        if not name:
            flash('Name cannot be empty.', 'danger')
            return render_template('profile.html', user=user)
        if pwd and pwd != pwd2:
            flash('Passwords do not match.', 'danger')
            return render_template('profile.html', user=user)

        user.name  = name
        user.email = email
        if pwd:
            user.set_password(pwd)
        # Refresh session
        session['user']['name']  = user.name
        session['user']['email'] = user.email
        session.modified = True

        log_action('update', 'user', entity_id=uid, entity_name=user.name,
                   details='Profile updated by user')
        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('user_profile'))

    return render_template('profile.html', user=user)


@app.route('/lang/<code>')
@login_required
def set_lang(code):
    if code in SUPPORTED_LANGS:
        session['lang'] = code
    return redirect(request.referrer or url_for('portal'))


@app.context_processor
def inject_globals():
    lang       = session.get('lang', DEFAULT_LANG)
    other_lang = 'es' if lang == 'en' else 'en'
    u          = session.get('user')

    # Pending access-requests count (admins only — shown in topbar badge)
    pending_requests_count = 0
    if u and u.get('role') == 'admin':
        try:
            pending_requests_count = AccessRequest.query.filter_by(status='pending').count()
        except Exception:
            pass

    # Warranty alerts for topbar (assets expiring in ≤30 days)
    warranty_alerts = 0
    if u and (u.get('role') == 'admin' or 'inventory' in u.get('modules', [])):
        try:
            soon = date.today() + timedelta(days=30)
            warranty_alerts = Asset.query.filter(
                Asset.warranty_expiry != None,        # noqa: E711
                Asset.warranty_expiry <= soon,
                Asset.warranty_expiry >= date.today(),
                Asset.status.notin_(['retired', 'disposed'])
            ).count()
        except Exception:
            pass

    return {
        'today': date.today(),
        'current_user': u,
        'logo_exists': _img_exists('logo.png'),
        'remoties_exists': _img_exists('remoties.png'),
        'favicon_exists': _img_exists('favicon.png'),
        'ALL_MODULES': ALL_MODULES,
        'T': get_translations(lang),
        'lang': lang,
        'other_lang': other_lang,
        'pending_requests_count': pending_requests_count,
        'warranty_alerts': warranty_alerts,
        'STATUS_BADGES': {
            'available':   'success',
            'in_use':      'primary',
            'maintenance': 'warning',
            'retired':     'secondary',
            'disposed':    'dark',
        },
        'STATUS_LABELS': {
            'available':   'Disponible',
            'in_use':      'En Uso',
            'maintenance': 'Mantenimiento',
            'retired':     'Retirado',
            'disposed':    'Desechado',
        },
        'SHIPMENT_STATUS_LABELS': {
            'pendiente':    'Pendiente',
            'en_transito':  'En Tránsito',
            'en_aduana':    'En Aduana',
            'entregado':    'Entregado',
            'devuelto':     'Devuelto',
        },
        'SHIPMENT_STATUS_BADGES': {
            'pendiente':    'secondary',
            'en_transito':  'primary',
            'en_aduana':    'warning',
            'entregado':    'success',
            'devuelto':     'dark',
        },
    }


@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('errors/500.html'), 500

@app.errorhandler(429)
def rate_limited(e):
    return render_template('errors/429.html'), 429


# ── Auto-tracking scheduler (cada 4 horas) ────────────────────────────────────
def _start_tracking_scheduler():
    """Lanza un hilo en background que refresca envíos activos cada 4 horas."""
    import threading, time, tracking as trk

    def _loop():
        # Primera corrida 60 s después de arrancar (da tiempo al DB de inicializarse)
        time.sleep(60)
        while True:
            try:
                if trk._API_KEY:
                    n = trk.refresh_all_active(app)
                    if n:
                        app.logger.info("Tracking scheduler: %d envíos actualizados", n)
            except Exception as e:
                app.logger.exception("Tracking scheduler error: %s", e)
            time.sleep(4 * 3600)   # cada 4 horas

    t = threading.Thread(target=_loop, daemon=True, name="tracking-scheduler")
    t.start()


# Arrancar scheduler solo si no estamos en modo debug-reloader (evita doble instancia)
if not os.environ.get('WERKZEUG_RUN_MAIN'):
    _start_tracking_scheduler()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', '0') == '1', port=5050, host='0.0.0.0')
