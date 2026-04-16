"""
RTS Asset Management — Importador de Inventario Excel
======================================================
Lee el archivo Excel con todas las hojas de equipo y las carga
a la base de datos SQLite de la aplicación.

Uso:
    python3 import_excel.py
    python3 import_excel.py /ruta/al/archivo.xlsx
"""
import sys, os, re
from datetime import datetime, date
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app
from models import db, Asset, Category, Employee, Assignment

EXCEL_PATH = (sys.argv[1] if len(sys.argv) > 1
              else '/Users/michvelazquez/Downloads/0 - Inventario Equipos RTS-2.xlsx')

# ── Mapa hoja → categoría ──────────────────────────────────────────────────────
SHEET_CATEGORY = {
    'Laptops':            'Laptops',
    'iMacs':              'Laptops',
    'Desktop PCs':        'Computadoras de Escritorio',
    'Headsets':           'Headsets',
    'Monitores':          'Monitores',
    'Teclados':           'Teclados',
    'Mouse':              'Mouse',
    'Celular':            'Celulares',
    'Tabletas':           'Tabletas',
    'SERVER':             'Servidores',
    'TVS':                'TVs',
    'APS':                'APs / Access Points',
    'FIREWALL':           'Firewalls',
    'SWITCH':             'Switches',
    'Lectoras':           'Control de Acceso',
    'ACC':                'Control de Acceso',
    'Torniquetes':        'Control de Acceso',
    'NVR':                'NVR / Cámaras',
    'DVR':                'NVR / Cámaras',
    'Videoconferencia':   'Videoconferencia',
    'No Breaks':          'UPS / No Breaks',
    'Impresora':          'Impresoras',
    'Aires':              'Aires Acondicionados',
    'Refrigerador':       'Electrodomésticos',
    'Microondas':         'Electrodomésticos',
    'Secador de manos':   'Electrodomésticos',
    'Otros':              'Otros',
    'Switches de red APs':'Switches',
}

# ── Mapeo de columnas por tipo ─────────────────────────────────────────────────
# Cada entry: lista de posibles nombres de columna (case-insensitive, primer match gana)
COL_MAP = {
    'id':           ['ID', 'ID NUMBER', 'IDS', 'ID2'],
    'name':         ['EQUIPO', 'Descripcion del producto'],
    'manufacturer': ['Marca', 'MARCA'],
    'model':        ['Modelo', 'MODEL'],
    'serial':       ['# de serie', 'SERIAL NO.', '# de Serie', 'S/N'],
    'purchase_date':['FECHA DE COMPRA', 'Fecha de Compra', 'Fecha de compra', 'FECHA DE COMPRA.1'],
    'cost':         ['COST (MXN)', 'Costo (MXN)', 'COSTO(MXN)', 'COSTO(USD)'],
    'status':       ['STATUS', 'Status', 'Estatus'],
    'location':     ['Ubicacion', 'Ubicación', 'SALA', 'Oficina'],
    'employee':     ['EMPLOYEE', 'Asignado A:', 'Asigando a', 'Employee', 'Column3'],
    'department':   ['DEPARTAMENTO', 'Departamento'],
    'company':      ['CLIENTE', 'Empresa', 'COMPANY', 'Empresa - propietario'],
    'os':           ['OS', 'Sistema Operativo', 'SO'],
    'ram':          ['RAM', 'RAM installed'],
    'cpu':          ['PROCESADOR', 'Procesador'],
    'hostname':     ['Nombre del Dispositivo (hostname)'],
}

STATUS_MAP = {
    'active':    'in_use',
    'activo':    'in_use',
    'in use':    'in_use',
    'en uso':    'in_use',
    'inactive':  'retired',
    'inactivo':  'retired',
    'baja':      'retired',
    'retired':   'retired',
    'available': 'available',
    'disponible':'available',
    'maintenance':'maintenance',
    'mantenimiento':'maintenance',
}

MXN_TO_USD = 0.052   # approximate rate — adjust if needed

# ── Helpers ────────────────────────────────────────────────────────────────────

def col(df, keys):
    """Return first matching column name (case-insensitive)."""
    cols_lower = {c.strip().lower(): c for c in df.columns}
    for k in keys:
        if k.strip().lower() in cols_lower:
            return cols_lower[k.strip().lower()]
    return None


def val(row, df, keys, default=''):
    c = col(df, keys)
    if c is None:
        return default
    v = row.get(c, default)
    if pd.isna(v):
        return default
    return str(v).strip()


def parse_date(v):
    if not v or v in ('nan', '', 'NaT', 'None'):
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y',
                '%d-%m-%Y', '%m-%d-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(str(v).strip()[:10], fmt[:len(str(v).strip()[:10].replace('-','/'))]).date()
        except Exception:
            pass
    try:
        return pd.to_datetime(v).date()
    except Exception:
        return None


def parse_cost(v):
    if not v or v in ('nan', '', 'None'):
        return None
    v = re.sub(r'[^\d.]', '', str(v))
    try:
        mxn = float(v)
        return round(mxn * MXN_TO_USD, 2) if mxn > 0 else None
    except Exception:
        return None


def map_status(v):
    if not v:
        return 'available'
    return STATUS_MAP.get(v.lower().strip(), 'in_use')


def get_or_create_category(name, session):
    cat = Category.query.filter_by(name=name).first()
    if not cat:
        cat = Category(name=name)
        session.add(cat)
        session.flush()
    return cat


def get_or_create_employee(name, dept, session):
    if not name or name.lower() in ('nan', ''):
        return None
    emp = Employee.query.filter(
        Employee.name.ilike(name.strip())).first()
    if not emp:
        # generate a simple employee_id
        count = Employee.query.count() + 1
        emp = Employee(
            name=name.strip(),
            employee_id=f'EMP-{count:04d}',
            department=dept or None,
            active=True,
        )
        session.add(emp)
        session.flush()
    return emp


def build_asset_name(row, df, sheet_name):
    name = val(row, df, COL_MAP['name'])
    brand = val(row, df, COL_MAP['manufacturer'])
    model = val(row, df, COL_MAP['model'])
    if name and name not in ('nan', ''):
        return name
    parts = [p for p in [brand, model] if p and p not in ('nan', '')]
    return ' '.join(parts) if parts else sheet_name


def build_notes(row, df):
    parts = []
    for key in ['company', 'os', 'ram', 'cpu', 'hostname']:
        v = val(row, df, COL_MAP[key])
        if v and v not in ('nan', ''):
            label = {'company': 'Empresa', 'os': 'OS', 'ram': 'RAM',
                     'cpu': 'CPU', 'hostname': 'Hostname'}[key]
            parts.append(f'{label}: {v}')
    return ' | '.join(parts) if parts else None


# ── Main import ────────────────────────────────────────────────────────────────

def run_import():
    print(f'\n📂  Leyendo: {EXCEL_PATH}')
    all_sheets = pd.read_excel(EXCEL_PATH, sheet_name=None, dtype=str)

    imported, skipped, errors = 0, 0, 0
    existing_tags = {a.asset_tag for a in Asset.query.all()}

    for sheet_name, category_name in SHEET_CATEGORY.items():
        if sheet_name not in all_sheets:
            continue
        df = all_sheets[sheet_name]
        if df.empty:
            continue

        category = get_or_create_category(category_name, db.session)
        sheet_count = 0

        for _, row in df.iterrows():
            try:
                asset_id = val(row, df, COL_MAP['id'])
                if not asset_id or asset_id in ('nan', '', 'None'):
                    skipped += 1
                    continue

                # Skip if already imported
                if asset_id in existing_tags:
                    skipped += 1
                    continue

                asset_name = build_asset_name(row, df, sheet_name)
                if not asset_name or asset_name in ('nan', ''):
                    skipped += 1
                    continue

                serial = val(row, df, COL_MAP['serial']) or None
                manufacturer = val(row, df, COL_MAP['manufacturer']) or None
                model = val(row, df, COL_MAP['model']) or None
                purchase_date = parse_date(val(row, df, COL_MAP['purchase_date']))
                cost_usd = parse_cost(val(row, df, COL_MAP['cost']))
                status_raw = val(row, df, COL_MAP['status'])
                status = map_status(status_raw) if status_raw else 'available'
                location = val(row, df, COL_MAP['location']) or None
                notes = build_notes(row, df)
                emp_name = val(row, df, COL_MAP['employee'])
                dept = val(row, df, COL_MAP['department']) or None

                # Determine location_type: anything assigned to a client = foraneo
                company = val(row, df, COL_MAP['company'])
                location_type = 'foraneo' if company and company.lower() not in (
                    'nan', '', 'remote team solutions', 'rts') else 'en_sitio'

                asset = Asset(
                    name=asset_name[:150],
                    asset_tag=asset_id[:50],
                    serial_number=(serial or '')[:100] or None,
                    manufacturer=(manufacturer or '')[:100] or None,
                    model=(model or '')[:100] or None,
                    category_id=category.id,
                    status=status,
                    location_type=location_type,
                    location=location,
                    purchase_date=purchase_date,
                    purchase_cost=cost_usd,
                    notes=notes,
                )
                db.session.add(asset)
                db.session.flush()
                existing_tags.add(asset_id)

                # Create employee & assignment if assigned
                if emp_name and emp_name not in ('nan', ''):
                    emp = get_or_create_employee(emp_name, dept, db.session)
                    if emp:
                        existing_assign = Assignment.query.filter_by(
                            asset_id=asset.id, returned_date=None).first()
                        if not existing_assign:
                            assign = Assignment(
                                asset_id=asset.id,
                                employee_id=emp.id,
                                assigned_date=purchase_date or date.today(),
                            )
                            db.session.add(assign)
                            if status == 'available':
                                asset.status = 'in_use'

                imported += 1
                sheet_count += 1

            except Exception as e:
                errors += 1
                print(f'  ⚠️  Error en {sheet_name}: {e}')

        if sheet_count:
            db.session.commit()
            print(f'  ✅  {sheet_name:<25} → {category_name:<30} ({sheet_count} activos)')

    db.session.commit()
    print(f'\n{"─"*55}')
    print(f'  Importados : {imported}')
    print(f'  Omitidos   : {skipped}  (sin ID / duplicados)')
    print(f'  Errores    : {errors}')
    print(f'{"─"*55}')
    print(f'  Total activos en BD : {Asset.query.count()}')
    print(f'  Total empleados     : {Employee.query.count()}')
    print(f'  Total categorías    : {Category.query.count()}')
    print(f'{"─"*55}\n')


if __name__ == '__main__':
    with app.app_context():
        run_import()
