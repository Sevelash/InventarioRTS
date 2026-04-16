from flask import Flask, render_template, request, redirect, url_for, flash, session
from models import db, Asset, Category, Client, Employee, Assignment, Shipment, AuditLog, log_action
from datetime import datetime, date
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'rts-inventory-2026-secret-key-change-in-prod'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rts_inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# ── Auth blueprint ────────────────────────────────────────────────────────────
from auth import auth_bp, login_required
app.register_blueprint(auth_bp)

# ── Admin blueprint ───────────────────────────────────────────────────────────
from admin import admin_bp
app.register_blueprint(admin_bp)

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
                     ('last_maintenance','DATE'), ('client_id','INTEGER')]:
        _add_col_if_missing('assets', col, typ)

    # audit_logs table is created by db.create_all() above

    # Crear admin por defecto si no existe ningún usuario
    from models import User
    if User.query.count() == 0:
        admin = User(name='Administrador', username='admin', role='admin')
        admin.set_password('rts2026')
        db.session.add(admin)
        db.session.commit()
        print('✅  Usuario admin creado  →  admin / rts2026')

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


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    total_assets      = Asset.query.count()
    available         = Asset.query.filter_by(status='available').count()
    in_use            = Asset.query.filter_by(status='in_use').count()
    maintenance       = Asset.query.filter_by(status='maintenance').count()
    retired           = Asset.query.filter_by(status='retired').count()
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

    # ── Gráfica: últimos 12 meses ─────────────────────────────────────────────
    MESES_ES = ['Ene','Feb','Mar','Abr','May','Jun',
                'Jul','Ago','Sep','Oct','Nov','Dic']
    today_d = date.today()

    # Lista de (año, mes) de los últimos 12 meses
    chart_months = []
    base = today_d.year * 12 + today_d.month - 1
    for i in range(11, -1, -1):
        idx = base - i
        chart_months.append((idx // 12, idx % 12 + 1))

    chart_labels = [f"{MESES_ES[m-1]} {y}" for y, m in chart_months]

    def _series(rows):
        """Dict {YYYY-MM: count} from a query result."""
        return {k: v for k, v in rows if k}

    def _fill(d):
        """Fill 12-month array from dict."""
        return [d.get(f'{y}-{m:02d}', 0) for y, m in chart_months]

    # ── Global (todas las categorías) ────────────────────────────────────────
    acq_global = _series(db.session.query(
        db.func.strftime('%Y-%m', Asset.created_at), db.func.count(Asset.id)
    ).group_by(db.func.strftime('%Y-%m', Asset.created_at)).all())

    baja_global = _series(db.session.query(
        db.func.strftime('%Y-%m', AuditLog.created_at), db.func.count(AuditLog.id)
    ).filter(
        AuditLog.entity_type == 'asset',
        db.or_(
            AuditLog.action == 'delete',
            db.and_(AuditLog.action == 'update',
                    db.or_(AuditLog.details.ilike('%→ retired%'),
                           AuditLog.details.ilike('%→ disposed%')))
        )
    ).group_by(db.func.strftime('%Y-%m', AuditLog.created_at)).all())

    reas_global = _series(db.session.query(
        db.func.strftime('%Y-%m', Assignment.created_at), db.func.count(Assignment.id)
    ).group_by(db.func.strftime('%Y-%m', Assignment.created_at)).all())

    # ── Por categoría ────────────────────────────────────────────────────────
    cats_for_chart = Category.query.order_by(Category.name).all()
    cat_chart_data = {
        'all': {
            'name': 'Todas las categorías',
            'adquisiciones':  _fill(acq_global),
            'bajas':          _fill(baja_global),
            'reasignaciones': _fill(reas_global),
        }
    }
    for cat in cats_for_chart:
        cat_acq = _series(db.session.query(
            db.func.strftime('%Y-%m', Asset.created_at), db.func.count(Asset.id)
        ).filter(Asset.category_id == cat.id
        ).group_by(db.func.strftime('%Y-%m', Asset.created_at)).all())

        cat_baja = _series(db.session.query(
            db.func.strftime('%Y-%m', Asset.updated_at), db.func.count(Asset.id)
        ).filter(Asset.category_id == cat.id,
                 Asset.status.in_(['retired', 'disposed'])
        ).group_by(db.func.strftime('%Y-%m', Asset.updated_at)).all())

        cat_reas = _series(db.session.query(
            db.func.strftime('%Y-%m', Assignment.created_at), db.func.count(Assignment.id)
        ).join(Asset, Assignment.asset_id == Asset.id
        ).filter(Asset.category_id == cat.id
        ).group_by(db.func.strftime('%Y-%m', Assignment.created_at)).all())

        cat_chart_data[str(cat.id)] = {
            'name':           cat.name,
            'adquisiciones':  _fill(cat_acq),
            'bajas':          _fill(cat_baja),
            'reasignaciones': _fill(cat_reas),
        }

    return render_template('dashboard.html',
                           total_assets=total_assets, available=available,
                           in_use=in_use, maintenance=maintenance, retired=retired,
                           total_employees=total_employees, total_categories=total_categories,
                           foraneo_count=foraneo_count, in_transit_count=in_transit_count,
                           recent_assignments=recent_assignments,
                           recent_shipments=recent_shipments,
                           cat_stats=cat_stats,
                           chart_labels=chart_labels,
                           cat_chart_data=cat_chart_data,
                           cats_for_chart=cats_for_chart)


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
    assets     = query.order_by(Asset.asset_tag).all()
    categories = Category.query.order_by(Category.name).all()
    return render_template('assets/list.html', assets=assets, categories=categories,
                           q=q, status_filter=status_filter,
                           category_filter=category_filter, loc_filter=loc_filter)


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
    return render_template('assets/detail.html', asset=asset, return_url=return_url)


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
    employees = query.order_by(Employee.name).all()
    return render_template('employees/list.html', employees=employees,
                           q=q, show_inactive=show_inactive)


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
    shipments = query.order_by(Shipment.created_at.desc()).all()
    return render_template('shipments/list.html',
                           shipments=shipments, status_filter=status_filter)


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
        flash(f'Envío {shipment.carrier} #{shipment.tracking_number} registrado.', 'success')
        return redirect(url_for('shipment_detail', id=shipment.id))
    return render_template('shipments/form.html',
                           foraneo_assets=foraneo_assets, shipment=None,
                           pre_asset=str(pre_asset) if pre_asset else '', form={})


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


@app.context_processor
def inject_globals():
    return {
        'today': date.today(),
        'current_user': session.get('user'),
        'logo_exists': _img_exists('logo.png'),
        'remoties_exists': _img_exists('remoties.png'),
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


if __name__ == '__main__':
    app.run(debug=True, port=5050)
