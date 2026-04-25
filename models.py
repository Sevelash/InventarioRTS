from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import cached_property

db = SQLAlchemy()


class AppSetting(db.Model):
    """Configuración clave-valor genérica de la aplicación (API keys, integraciones, etc.)."""
    __tablename__ = 'app_settings'
    key   = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)

    @classmethod
    def get(cls, key, default=None):
        row = cls.query.get(key)
        return row.value if row else default

    @classmethod
    def set(cls, key, value):
        row = cls.query.get(key)
        if row:
            row.value = value if value is not None else ''
        else:
            db.session.add(cls(key=key, value=value or ''))

    def __repr__(self):
        return f'<AppSetting {self.key}>'

# All available modules — order matters for display
ALL_MODULES = [
    {'slug': 'inventory',   'name': 'Inventory Management', 'icon': 'bi-laptop',         'color': '#089ACF', 'desc': 'Asset tracking & lifecycle management'},
    {'slug': 'projects',    'name': 'Project Management',   'icon': 'bi-kanban',          'color': '#233C6E', 'desc': 'Projects, tasks & team collaboration'},
    {'slug': 'evaluation',  'name': 'Evaluation',           'icon': 'bi-clipboard-check', 'color': '#28A745', 'desc': 'Performance evaluations & reviews'},
    {'slug': 'repository',  'name': 'Repository',           'icon': 'bi-folder2-open',    'color': '#6F42C1', 'desc': 'Documents & knowledge base'},
]


class User(db.Model):
    __tablename__ = 'users'
    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(150), nullable=False)
    username       = db.Column(db.String(80),  nullable=False, unique=True, index=True)
    email          = db.Column(db.String(150), unique=True)
    pwd_hash       = db.Column(db.String(256), nullable=False)
    role           = db.Column(db.String(20),  nullable=False, default='viewer')  # admin | viewer
    active         = db.Column(db.Boolean, default=True)
    module_access  = db.Column(db.Text, default='')  # comma-separated slugs, e.g. "inventory,projects"
    department_id  = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)
    totp_secret          = db.Column(db.String(32),  nullable=True)   # base32 TOTP secret
    mfa_enabled          = db.Column(db.Boolean, default=False)
    force_password_change = db.Column(db.Boolean, default=False)      # first-login flag
    failed_logins        = db.Column(db.Integer, default=0)
    locked_until         = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.pwd_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.pwd_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

    def get_modules(self):
        """Returns list of module slugs accessible to this user."""
        if self.role == 'admin':
            return [m['slug'] for m in ALL_MODULES]
        if not self.module_access:
            return []
        return [s.strip() for s in self.module_access.split(',') if s.strip()]

    def set_modules(self, slugs):
        """Set module access from a list of slugs."""
        self.module_access = ','.join(slugs)

    def is_locked(self):
        if self.locked_until and datetime.utcnow() < self.locked_until:
            return True
        return False

    def record_failed_login(self):
        self.failed_logins = (self.failed_logins or 0) + 1
        if self.failed_logins >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=15)
        db.session.commit()

    def reset_failed_logins(self):
        self.failed_logins = 0
        self.locked_until = None

    def __repr__(self):
        return f'<User {self.username}>'


class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    assets = db.relationship('Asset', backref='category', lazy=True)

    def __repr__(self):
        return f'<Category {self.name}>'


class Department(db.Model):
    """Internal departments — each can have its own inventory view."""
    __tablename__ = 'departments'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False, unique=True)
    code          = db.Column(db.String(20),  nullable=False, unique=True)  # e.g. "IT", "MKT", "HR"
    color         = db.Column(db.String(7),   default='#233C6E')            # hex
    manager_name  = db.Column(db.String(150))
    manager_email = db.Column(db.String(150))
    active        = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    users  = db.relationship('User',  backref='department', lazy=True,
                             foreign_keys='User.department_id')
    assets = db.relationship('Asset', backref='department', lazy=True,
                             foreign_keys='Asset.department_id')

    def __repr__(self):
        return f'<Department {self.code}>'


class Client(db.Model):
    __tablename__ = 'clients'
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(150), nullable=False, unique=True)
    # Tipo de cliente
    location_type = db.Column(db.String(10), nullable=False, default='local')  # local | foraneo
    # Contacto
    contact_name  = db.Column(db.String(150))
    email         = db.Column(db.String(150))
    phone         = db.Column(db.String(50))
    # Ubicación
    country       = db.Column(db.String(80))
    city          = db.Column(db.String(80))
    address       = db.Column(db.String(300))
    # Datos fiscales / comerciales
    rfc           = db.Column(db.String(20))          # RFC o Tax ID
    industry      = db.Column(db.String(100))         # Giro/industria
    website       = db.Column(db.String(200))
    # Fechas
    start_date    = db.Column(db.Date)                # Fecha de inicio del cliente
    notes         = db.Column(db.Text)
    active        = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    assets        = db.relationship('Asset', backref='client', lazy=True)

    LOCATION_CHOICES = [('local', 'Local'), ('foraneo', 'Foráneo')]

    @property
    def location_label(self):
        return 'Foráneo' if self.location_type == 'foraneo' else 'Local'

    def __repr__(self):
        return f'<Client {self.name}>'


class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(150), nullable=False, unique=True)
    contact_name = db.Column(db.String(150))
    email        = db.Column(db.String(150))
    phone        = db.Column(db.String(50))
    website      = db.Column(db.String(200))
    country      = db.Column(db.String(80))
    notes        = db.Column(db.Text)
    active       = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Supplier {self.name}>'


class Brand(db.Model):
    __tablename__ = 'brands'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(300))
    active      = db.Column(db.Boolean, default=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    assets = db.relationship('Asset', backref='brand', lazy=True)

    def __repr__(self):
        return f'<Brand {self.name}>'


class IDConfig(db.Model):
    """Stores the asset tag auto-generation rules."""
    __tablename__ = 'id_config'
    id                   = db.Column(db.Integer, primary_key=True)
    prefix               = db.Column(db.String(10),  default='RTS')
    separator            = db.Column(db.String(3),   default='-')
    use_category_code    = db.Column(db.Boolean,     default=True)
    category_code_len    = db.Column(db.Integer,     default=1)   # chars from category name
    use_year             = db.Column(db.Boolean,     default=False)
    year_format          = db.Column(db.String(6),   default='YY')  # YY or YYYY
    consecutive_digits   = db.Column(db.Integer,     default=3)    # 001, 0001, etc.
    next_consecutive     = db.Column(db.Integer,     default=1)
    updated_at           = db.Column(db.DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get():
        """Get config (create default if none)."""
        cfg = IDConfig.query.first()
        if not cfg:
            cfg = IDConfig()
            db.session.add(cfg)
            db.session.commit()
        return cfg

    def generate_tag(self, category_name: str = '') -> str:
        """Generate next asset tag based on current config."""
        from datetime import datetime as dt
        parts = [self.prefix] if self.prefix else []
        if self.use_category_code and category_name:
            code = ''.join(c for c in category_name.upper() if c.isalpha())[:self.category_code_len]
            parts.append(code)
        if self.use_year:
            fmt = '%Y' if self.year_format == 'YYYY' else '%y'
            parts.append(dt.utcnow().strftime(fmt))
        consecutive = str(self.next_consecutive).zfill(self.consecutive_digits)
        parts.append(consecutive)
        return self.separator.join(parts)

    def preview(self) -> str:
        """Show example with current settings."""
        return self.generate_tag(category_name='Laptop')

    def __repr__(self):
        return f'<IDConfig prefix={self.prefix}>'


class PurchaseOrder(db.Model):
    """Orden de Compra — reutilizable en múltiples activos."""
    __tablename__ = 'purchase_orders'
    id            = db.Column(db.Integer, primary_key=True)
    number        = db.Column(db.String(100), nullable=False)   # N° de OC
    date          = db.Column(db.Date)
    supplier_id   = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)
    supplier_name = db.Column(db.String(150))                   # nombre libre si no hay Supplier
    total_amount  = db.Column(db.Float)
    currency      = db.Column(db.String(3), default='MXN')
    notes         = db.Column(db.Text)
    file_path     = db.Column(db.String(500))                   # ruta en disco
    file_name     = db.Column(db.String(300))                   # nombre original
    file_mime     = db.Column(db.String(100))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    supplier      = db.relationship('Supplier', backref='purchase_orders', lazy=True)

    @property
    def display(self):
        parts = [f'OC #{self.number}']
        if self.date:
            parts.append(self.date.strftime('%d/%m/%Y'))
        s = self.supplier_name or (self.supplier.name if self.supplier else '')
        if s:
            parts.append(f'· {s}')
        return '  '.join(parts)

    def __repr__(self):
        return f'<PurchaseOrder #{self.number}>'


class Invoice(db.Model):
    """Factura — reutilizable en múltiples activos."""
    __tablename__ = 'invoices'
    id            = db.Column(db.Integer, primary_key=True)
    number        = db.Column(db.String(100), nullable=False)   # N° de factura
    date          = db.Column(db.Date)
    supplier_id   = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)
    supplier_name = db.Column(db.String(150))
    total_amount  = db.Column(db.Float)
    currency      = db.Column(db.String(3), default='MXN')
    notes         = db.Column(db.Text)
    file_path     = db.Column(db.String(500))
    file_name     = db.Column(db.String(300))
    file_mime     = db.Column(db.String(100))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    supplier      = db.relationship('Supplier', backref='invoices', lazy=True)

    @property
    def display(self):
        parts = [f'FAC #{self.number}']
        if self.date:
            parts.append(self.date.strftime('%d/%m/%Y'))
        s = self.supplier_name or (self.supplier.name if self.supplier else '')
        if s:
            parts.append(f'· {s}')
        return '  '.join(parts)

    def __repr__(self):
        return f'<Invoice #{self.number}>'


class Asset(db.Model):
    __tablename__ = 'assets'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    asset_tag = db.Column(db.String(50), unique=True, nullable=False, index=True)
    serial_number = db.Column(db.String(100))
    manufacturer = db.Column(db.String(100))
    model = db.Column(db.String(100))
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    client_id   = db.Column(db.Integer, db.ForeignKey('clients.id'))
    status = db.Column(db.String(30), nullable=False, default='available', index=True)
    # En Sitio vs Foráneo
    location_type = db.Column(db.String(20), nullable=False, default='en_sitio')  # en_sitio | hibrido | foraneo
    location = db.Column(db.String(150))
    # Tipo de equipo
    asset_type   = db.Column(db.String(30), nullable=False, default='laptop')
    # laptop | desktop | monitor | headset | teclado | mouse | tablet | impresora | camara | otro
    # Specs (aplica solo a laptop/desktop/tablet)
    ram          = db.Column(db.String(50))
    os_version   = db.Column(db.String(100))
    cpu          = db.Column(db.String(150))
    # Compra
    purchase_date   = db.Column(db.Date)
    purchase_cost   = db.Column(db.Float)   # almacenado en MXN
    supplier        = db.Column(db.String(150))
    warranty_expiry = db.Column(db.Date)
    last_maintenance = db.Column(db.Date)
    notes = db.Column(db.Text)
    department_id     = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    brand_id          = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=True)
    invoice_id        = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=True)
    # ── Absolute Secure Endpoint ──────────────────────────────────────────────
    absolute_id       = db.Column(db.String(100), nullable=True)   # UID en Absolute
    absolute_status   = db.Column(db.String(30),  nullable=True)   # Active|Inactive|Stolen…
    absolute_username = db.Column(db.String(150), nullable=True)   # último usuario logueado
    absolute_last_seen= db.Column(db.DateTime,    nullable=True)   # último check-in (UTC)
    absolute_sync_at  = db.Column(db.DateTime,    nullable=True)   # cuándo sincronizamos
    # ─────────────────────────────────────────────────────────────────────────
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    assignments = db.relationship('Assignment', backref='asset', lazy=True,
                                  order_by='Assignment.assigned_date.desc()')
    shipments = db.relationship('Shipment', backref='asset', lazy=True,
                                order_by='Shipment.created_at.desc()')

    STATUS_CHOICES = ['available', 'in_use', 'maintenance', 'retired', 'disposed']

    ASSET_TYPE_CHOICES = [
        ('laptop',     'Laptop / Notebook'),
        ('desktop',    'Desktop / PC'),
        ('monitor',    'Monitor / Pantalla'),
        ('tablet',     'Tablet / iPad'),
        ('headset',    'Headset / Audífonos'),
        ('teclado',    'Teclado'),
        ('mouse',      'Mouse'),
        ('impresora',  'Impresora'),
        ('camara',     'Cámara / Webcam'),
        ('otro',       'Otro'),
    ]
    # Asset types that have computer specs (RAM, CPU, OS)
    SPEC_TYPES = {'laptop', 'desktop', 'tablet'}

    @property
    def current_assignment(self):
        # Si la vista pre-cargó la asignación, usar el caché (evita N+1)
        if hasattr(self, '_cached_assignment'):
            return self._cached_assignment
        return Assignment.query.filter_by(asset_id=self.id, returned_date=None).first()

    @property
    def active_shipment(self):
        return Shipment.query.filter(
            Shipment.asset_id == self.id,
            Shipment.status.notin_(['entregado', 'devuelto'])
        ).order_by(Shipment.created_at.desc()).first()

    def __repr__(self):
        return f'<Asset {self.asset_tag} - {self.name}>'


class Employee(db.Model):
    __tablename__ = 'employees'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(150), nullable=False)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    position    = db.Column(db.String(150))           # Puesto / cargo
    department  = db.Column(db.String(100))
    email       = db.Column(db.String(150))
    phone       = db.Column(db.String(50))
    whatsapp    = db.Column(db.String(50))          # número de WhatsApp (puede diferir del tel)
    active      = db.Column(db.Boolean, default=True)
    # Cliente al que pertenece el empleado
    client_id   = db.Column(db.Integer, db.ForeignKey('clients.id'))
    client      = db.relationship('Client', foreign_keys=[client_id])
    # Ubicación: 'sitio' (local) | 'foraneo'
    site_type   = db.Column(db.String(10), default='sitio')
    address     = db.Column(db.Text)                # dirección cuando es foráneo
    assignments = db.relationship('Assignment', backref='employee', lazy=True,
                                  order_by='Assignment.assigned_date.desc()')

    @property
    def current_assets(self):
        return Assignment.query.filter_by(employee_id=self.id, returned_date=None).all()

    @property
    def wa_link(self):
        """URL de WhatsApp para abrir chat directo."""
        num = self.whatsapp or self.phone or ''
        clean = ''.join(c for c in num if c.isdigit())
        return f'https://wa.me/{clean}' if clean else None

    def __repr__(self):
        return f'<Employee {self.employee_id} - {self.name}>'


class Assignment(db.Model):
    __tablename__ = 'assignments'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    assigned_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    returned_date = db.Column(db.Date, index=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Assignment Asset:{self.asset_id} -> Employee:{self.employee_id}>'


class Shipment(db.Model):
    __tablename__ = 'shipments'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    # Carrier & tracking
    carrier = db.Column(db.String(30), nullable=False, default='DHL')  # DHL, FedEx, UPS, etc.
    tracking_number = db.Column(db.String(100), nullable=False)
    # Locations
    origin = db.Column(db.String(200))
    destination = db.Column(db.String(200))
    recipient_name = db.Column(db.String(150))
    # Status: pendiente | en_transito | en_aduana | entregado | devuelto
    status = db.Column(db.String(30), nullable=False, default='pendiente')
    # Dates
    ship_date = db.Column(db.Date)
    estimated_delivery = db.Column(db.Date)
    actual_delivery = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # ── AfterShip tracking ────────────────────────────────────────────────
    aftership_slug      = db.Column(db.String(50),   nullable=True)   # carrier slug p.ej. 'fedex'
    tracking_events     = db.Column(db.Text,          nullable=True)   # JSON con historial
    last_tracking_at    = db.Column(db.DateTime,      nullable=True)   # última consulta
    tracking_tag        = db.Column(db.String(30),    nullable=True)   # tag AfterShip (InTransit, etc.)
    est_delivery_afship = db.Column(db.DateTime,      nullable=True)   # ETA de AfterShip

    # Direction: outbound = RTS → Remotie (we send); inbound = Remotie → RTS (they return)
    direction = db.Column(db.String(10), nullable=False, default='outbound')

    CARRIER_CHOICES = ['DHL', 'FedEx', 'UPS', 'USPS', 'Estafeta', 'Otro']
    STATUS_CHOICES = ['pendiente', 'en_transito', 'en_aduana', 'entregado', 'devuelto']

    # Mapa AfterShip tag → nuestro status interno
    AFTERSHIP_STATUS_MAP = {
        'Pending':          'pendiente',
        'InfoReceived':     'pendiente',
        'InTransit':        'en_transito',
        'OutForDelivery':   'en_transito',
        'AttemptFail':      'en_transito',
        'Delivered':        'entregado',
        'AvailableForPickup': 'en_transito',
        'Exception':        'en_transito',
        'Expired':          'en_transito',
    }

    def __repr__(self):
        return f'<Shipment {self.carrier} {self.tracking_number}>'


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    user_name   = db.Column(db.String(150))          # guardado para historial
    action      = db.Column(db.String(30))            # create | update | delete | login | logout | upload
    entity_type = db.Column(db.String(50))            # asset | employee | user | category | shipment | branding
    entity_id   = db.Column(db.Integer, nullable=True)
    entity_name = db.Column(db.String(250), nullable=True)
    details     = db.Column(db.Text, nullable=True)   # descripción legible del cambio
    ip_address  = db.Column(db.String(50), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', backref='audit_logs', lazy=True,
                           foreign_keys=[user_id])

    def __repr__(self):
        return f'<AuditLog {self.action} {self.entity_type} by {self.user_name}>'


# ── Project Management Models ─────────────────────────────────────────────────


class Project(db.Model):
    __tablename__ = 'projects'
    id          = db.Column(db.Integer, primary_key=True)
    code        = db.Column(db.String(30), unique=True, nullable=False, index=True)
    name        = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    client_id   = db.Column(db.Integer, db.ForeignKey('clients.id'))
    status      = db.Column(db.String(30), nullable=False, default='planning')
    # planning | active | on_hold | completed | cancelled
    priority    = db.Column(db.String(20), nullable=False, default='medium')
    # low | medium | high | critical
    start_date  = db.Column(db.Date)
    end_date    = db.Column(db.Date)
    budget      = db.Column(db.Float)
    progress    = db.Column(db.Integer, default=0)   # 0-100
    owner_id    = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tasks   = db.relationship('Task', backref='project', lazy=True,
                              cascade='all, delete-orphan',
                              order_by='Task.created_at.asc()')
    members = db.relationship('ProjectMember', backref='project', lazy=True,
                              cascade='all, delete-orphan')
    client  = db.relationship('Client', backref='projects', lazy=True)
    owner   = db.relationship('User', backref='owned_projects', lazy=True,
                              foreign_keys=[owner_id])

    STATUS_CHOICES   = ['planning', 'active', 'on_hold', 'completed', 'cancelled']
    PRIORITY_CHOICES = ['low', 'medium', 'high', 'critical']

    @property
    def is_overdue(self):
        from datetime import date
        return (self.end_date and self.end_date < date.today()
                and self.status not in ('completed', 'cancelled'))

    @property
    def open_tasks(self):
        return [t for t in self.tasks if t.status not in ('done', 'cancelled')]

    @property
    def done_tasks(self):
        return [t for t in self.tasks if t.status == 'done']

    def __repr__(self):
        return f'<Project {self.code} – {self.name}>'


class Task(db.Model):
    __tablename__ = 'tasks'
    id             = db.Column(db.Integer, primary_key=True)
    project_id     = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    title          = db.Column(db.String(200), nullable=False)
    description    = db.Column(db.Text)
    status         = db.Column(db.String(30), nullable=False, default='pending')
    # pending | in_progress | review | done | cancelled
    priority       = db.Column(db.String(20), nullable=False, default='medium')
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    due_date       = db.Column(db.Date)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assigned_to = db.relationship('User', backref='assigned_tasks', lazy=True,
                                  foreign_keys=[assigned_to_id])

    STATUS_CHOICES   = ['pending', 'in_progress', 'review', 'done', 'cancelled']
    PRIORITY_CHOICES = ['low', 'medium', 'high', 'critical']

    @property
    def is_overdue(self):
        from datetime import date
        return (self.due_date and self.due_date < date.today()
                and self.status not in ('done', 'cancelled'))

    def __repr__(self):
        return f'<Task {self.id} – {self.title}>'


class ProjectMember(db.Model):
    __tablename__ = 'project_members'
    id         = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role       = db.Column(db.String(50), default='member')  # manager | member
    joined_at  = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='project_memberships', lazy=True)

    def __repr__(self):
        return f'<ProjectMember project={self.project_id} user={self.user_id}>'


class TaskComment(db.Model):
    __tablename__ = 'task_comments'
    id         = db.Column(db.Integer, primary_key=True)
    task_id    = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'))
    user_name  = db.Column(db.String(150))   # snapshot for history
    content    = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='task_comments', lazy=True)
    task = db.relationship('Task', backref='comments', lazy=True,
                           foreign_keys=[task_id])

    def __repr__(self):
        return f'<TaskComment task={self.task_id} by={self.user_name}>'


class ProjectActivity(db.Model):
    """Timeline of everything that happens in a project."""
    __tablename__ = 'project_activities'
    id          = db.Column(db.Integer, primary_key=True)
    project_id  = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'))
    user_name   = db.Column(db.String(150))
    action      = db.Column(db.String(100))   # created_task | moved_task | commented | member_added etc.
    entity_type = db.Column(db.String(50))    # task | project | comment | member
    entity_name = db.Column(db.String(200))
    details     = db.Column(db.Text)
    icon        = db.Column(db.String(50), default='circle')  # bootstrap icon
    color       = db.Column(db.String(20), default='secondary')
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ProjectActivity {self.action} in project={self.project_id}>'


class AccessRequest(db.Model):
    """A user's request to access a module (e.g. inventory for their department)."""
    __tablename__ = 'access_requests'
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    user_name       = db.Column(db.String(150))          # snapshot
    module_slug     = db.Column(db.String(50), nullable=False)   # 'inventory' | 'projects' | …
    department_id   = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    reason          = db.Column(db.Text)                 # user-supplied justification
    status          = db.Column(db.String(20), nullable=False, default='pending')
    # pending | approved | denied
    admin_notes     = db.Column(db.Text)                 # optional reviewer comment
    reviewed_by     = db.Column(db.String(150))          # admin name snapshot
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at     = db.Column(db.DateTime, nullable=True)

    user       = db.relationship('User',       backref='access_requests', lazy=True)
    department = db.relationship('Department', backref='access_requests', lazy=True)

    def __repr__(self):
        return f'<AccessRequest {self.user_name} → {self.module_slug} [{self.status}]>'


class Maintenance(db.Model):
    __tablename__ = 'maintenance'
    id              = db.Column(db.Integer, primary_key=True)
    asset_id        = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)

    # Identificación del ticket
    ticket_folio        = db.Column(db.String(50))          # AC-001
    maintenance_type    = db.Column(db.String(20), nullable=False, default='correctivo')
    status              = db.Column(db.String(20), default='pendiente')
    prev_asset_status   = db.Column(db.String(30))          # para restaurar al cerrar

    # Quién / cuándo reportó
    reported_date       = db.Column(db.Date)
    reported_by         = db.Column(db.String(150))         # nombre y cargo

    # Proceso
    process_name        = db.Column(db.String(150))
    process_responsible = db.Column(db.String(150))

    # Fuente de la no conformidad (clave del checkbox)
    nc_source           = db.Column(db.String(100))

    # Descripción del problema
    description         = db.Column(db.Text)

    # Análisis de causa raíz (FO-SGSI-20 sección 2)
    analysis_method     = db.Column(db.String(150))
    participants        = db.Column(db.String(300))
    root_cause_analysis = db.Column(db.Text)     # desarrollo
    root_cause          = db.Column(db.Text)     # causa raíz identificada
    correction_desc     = db.Column(db.Text)     # corrección realizada/a realizar

    # Plan de acción (JSON: [{task, responsible, deadline}])
    action_plan         = db.Column(db.Text)
    proposed_close_date = db.Column(db.Date)

    # Seguimiento y cierre
    followup_responsible = db.Column(db.String(150))
    close_responsible    = db.Column(db.String(150))
    effectiveness_ok     = db.Column(db.Boolean)
    effectiveness_notes  = db.Column(db.Text)
    actual_close_date    = db.Column(db.Date)

    # Archivos
    document_path  = db.Column(db.String(500))   # formato firmado subido
    document_name  = db.Column(db.String(200))
    photos         = db.Column(db.Text)           # JSON [{path,name,photo_type,caption}]

    # Notas internas
    notes          = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    asset = db.relationship('Asset', backref='maintenance_records')

    # ── Catálogos ──────────────────────────────────────────────
    TYPE_CHOICES = [
        ('preventivo', 'Preventivo'),
        ('correctivo', 'Correctivo'),
        ('mejora',     'De Mejora'),
    ]
    STATUS_CHOICES = [
        ('pendiente',   'Pendiente'),
        ('en_proceso',  'En Proceso'),
        ('completado',  'Completado'),
        ('cerrado',     'Cerrado'),
    ]
    NC_SOURCES = [
        ('quejas',        'Quejas y reclamos recurrentes de los usuarios'),
        ('auditoria',     'Informes de Auditoría Interna o Externa'),
        ('direccion',     'Resultados de la Revisión por la Dirección'),
        ('satisfaccion',  'Resultados de las Mediciones de Satisfacción'),
        ('indicadores',   'Mediciones de Indicadores'),
        ('autoevaluacion','Resultados de Autoevaluación'),
        ('riesgos',       'Gestión de Riesgos'),
        ('otro',          'Otro'),
    ]

    STATUS_COLORS = {
        'pendiente':  'warning',
        'en_proceso': 'primary',
        'completado': 'success',
        'cerrado':    'secondary',
    }
    TYPE_COLORS = {
        'preventivo': 'info',
        'correctivo': 'danger',
        'mejora':     'success',
    }

    @property
    def status_label(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.status, 'secondary')

    @property
    def type_label(self):
        return dict(self.TYPE_CHOICES).get(self.maintenance_type, self.maintenance_type)

    @property
    def type_color(self):
        return self.TYPE_COLORS.get(self.maintenance_type, 'secondary')

    @property
    def photos_list(self):
        if self.photos:
            import json as _j
            try:
                return _j.loads(self.photos)
            except Exception:
                return []
        return []

    @property
    def action_plan_list(self):
        if self.action_plan:
            import json as _j
            try:
                return _j.loads(self.action_plan)
            except Exception:
                return []
        return []

    def __repr__(self):
        return f'<Maintenance #{self.id} Asset:{self.asset_id} [{self.maintenance_type}]>'


class License(db.Model):
    """Registro maestro de una licencia de software."""
    __tablename__ = 'licenses'
    id           = db.Column(db.Integer, primary_key=True)

    # Identificación
    name         = db.Column(db.String(200), nullable=False)   # "Microsoft 365 Business Premium"
    vendor       = db.Column(db.String(100))                   # Microsoft, Adobe, etc.
    software     = db.Column(db.String(150))                   # nombre del producto/SKU
    category     = db.Column(db.String(50))                    # office_suite | os | antivirus | …
    license_type = db.Column(db.String(30), default='subscription')
    license_key  = db.Column(db.String(500))                   # clave de producto (non-MS)

    # ── Microsoft 365 / Azure ──────────────────────────────────────────────
    is_microsoft    = db.Column(db.Boolean, default=False)
    tenant_id       = db.Column(db.String(100))   # Azure AD Directory / Tenant ID
    tenant_name     = db.Column(db.String(200))   # nombre de la organización
    tenant_domain   = db.Column(db.String(200))   # ej. company.onmicrosoft.com
    subscription_id = db.Column(db.String(100))   # GUID de la suscripción MS
    sku_name        = db.Column(db.String(100))   # ej. "ENTERPRISEPREMIUM"

    # Asientos
    seat_count   = db.Column(db.Integer)           # NULL = OEM/unidad única

    # Financiero
    purchase_cost  = db.Column(db.Float)
    renewal_cost   = db.Column(db.Float)
    currency       = db.Column(db.String(10), default='MXN')

    # Fechas
    purchase_date  = db.Column(db.Date)
    expiry_date    = db.Column(db.Date)
    renewal_date   = db.Column(db.Date)

    # Estado
    status   = db.Column(db.String(20), default='active')  # active|expiring|expired|cancelled

    notes      = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignments = db.relationship('LicenseAssignment', backref='license',
                                  lazy=True, cascade='all, delete-orphan',
                                  order_by='LicenseAssignment.assigned_date.desc()')

    # ── Catálogos ──────────────────────────────────────────────────────────
    CATEGORY_CHOICES = [
        ('office_suite',  'Suite de Oficina'),
        ('os',            'Sistema Operativo'),
        ('antivirus',     'Antivirus / Seguridad'),
        ('design',        'Diseño / Creativo'),
        ('dev_tools',     'Herramientas Dev'),
        ('communication', 'Comunicación / Video'),
        ('erp',           'ERP / CRM'),
        ('other',         'Otro'),
    ]
    TYPE_CHOICES = [
        ('subscription', 'Suscripción'),
        ('perpetual',    'Perpetua'),
        ('oem',          'OEM'),
        ('volume',       'Volumen'),
        ('trial',        'Trial / Demo'),
    ]
    CURRENCY_CHOICES = ['MXN', 'USD', 'EUR']
    STATUS_COLORS  = {'active': 'success', 'expiring': 'warning',
                      'expired': 'danger',  'cancelled': 'secondary'}
    STATUS_LABELS  = {'active': 'Activa', 'expiring': 'Por Vencer',
                      'expired': 'Vencida', 'cancelled': 'Cancelada'}

    @property
    def effective_status(self):
        if self.status == 'cancelled':
            return 'cancelled'
        if self.expiry_date:
            from datetime import date as _d
            today = _d.today()
            if self.expiry_date < today:
                return 'expired'
            if (self.expiry_date - today).days <= 30:
                return 'expiring'
        return 'active'

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.effective_status, self.effective_status)

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.effective_status, 'secondary')

    @property
    def used_seats(self):
        return len(self.assignments)

    @property
    def available_seats(self):
        if self.seat_count is None:
            return None
        return max(0, self.seat_count - self.used_seats)

    @property
    def days_until_expiry(self):
        if not self.expiry_date:
            return None
        from datetime import date as _d
        return (self.expiry_date - _d.today()).days

    @property
    def category_label(self):
        return dict(self.CATEGORY_CHOICES).get(self.category, self.category or '—')

    @property
    def type_label(self):
        return dict(self.TYPE_CHOICES).get(self.license_type, self.license_type or '—')

    def __repr__(self):
        return f'<License {self.name}>'


class LicenseAssignment(db.Model):
    """Un seat/asiento de una licencia asignado a un empleado o activo."""
    __tablename__ = 'license_assignments'
    id          = db.Column(db.Integer, primary_key=True)
    license_id  = db.Column(db.Integer,
                            db.ForeignKey('licenses.id', ondelete='CASCADE'),
                            nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=True)
    asset_id    = db.Column(db.Integer, db.ForeignKey('assets.id'),    nullable=True)
    assigned_date = db.Column(db.Date)
    notes       = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', backref='license_assignments', lazy=True)
    asset    = db.relationship('Asset',    backref='license_assignments', lazy=True)

    def __repr__(self):
        return f'<LicenseAssignment lic={self.license_id} emp={self.employee_id} asset={self.asset_id}>'


def log_action(action, entity_type, entity_id=None, entity_name=None, details=None):
    """Registra una acción en el audit log. El caller debe hacer commit."""
    try:
        from flask import session as _sess, request as _req
        u = _sess.get('user', {})
        # X-Forwarded-For support for reverse proxies
        forwarded = _req.headers.get('X-Forwarded-For', '')
        ip = forwarded.split(',')[0].strip() if forwarded else _req.remote_addr
    except RuntimeError:
        u, ip = {}, None
    entry = AuditLog(
        user_id=u.get('id') if u else None,
        user_name=u.get('name', 'Sistema') if u else 'Sistema',
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        details=details,
        ip_address=ip,
    )
    db.session.add(entry)


# ── Performance Evaluation ────────────────────────────────────────────────────

EVAL_SCORE_LABELS = {
    5: 'Sobresaliente',
    4: 'Notable',
    3: 'Adecuado',
    2: 'Deficiente',
    1: 'Insuficiente',
}

# Fixed competencies seeded into every new evaluation
EVAL_COMPETENCIES = [
    ('Dirección y Asignación de Responsabilidades',
     'Establece y supervisa que las normas y los altos estándares de desempeño se cumplan '
     'de acuerdo a sus instrucciones. Señala las acciones a seguir ante el bajo desempeño.'),
    ('Liderazgo de Equipo',
     'Obtiene los recursos necesarios para el grupo, para asegurar que los objetivos se '
     'cumplan en tiempo y calidad, fomentando el trabajo en equipo.'),
    ('Desarrollo de Otros',
     'Proporciona retroalimentación continua, promoviendo el aprendizaje y el desarrollo '
     'de habilidades. Fomentando el análisis y la toma de decisiones.'),
    ('Orientación al Logro',
     'Cumple objetivos desafiantes implementando mejoras cuantificables y específicas.'),
    ('Planeación',
     'Mediante acciones concretas, establece planes para prevenir y minimizar los problemas '
     'de corto plazo (de 0 a 3 meses).'),
    ('Orientación al Cliente',
     'Analiza los requerimientos de sus clientes y se esfuerza por generar valor a las '
     'soluciones propuestas.'),
    ('Entendimiento Interpersonal e Impacto',
     'Logra impactar en aspectos muy específicos, tomando acciones para adaptar sus argumentos '
     'y presentación al auditorio. Se anticipa a las posibles reacciones del mismo, '
     'comprendiendo la intención del interlocutor.'),
    ('Autoconfianza',
     'Explícitamente, indica confianza en sus propias habilidades y discernimiento, se '
     'considera como alguien que hace que sucedan las cosas, promotor u originador.'),
    ('Conocimiento Organizacional',
     'Reconoce las limitaciones organizacionales no expresadas, lo que es y no es posible '
     'en ciertas épocas y puestos, utilizando la cultura corporativa que producirá la mejor '
     'respuesta.'),
    ('Pensamiento Analítico',
     'Utiliza técnicas avanzadas de análisis para identificar varias soluciones posibles y '
     'sopesar el valor de cada una.'),
    ('Creatividad e Innovación',
     'Redefine los problemas y los presenta de una manera poco convencional. Implementa '
     'métodos, productos y procesos de trabajo innovadores de manera sistemática y continua '
     'que generan valor a la compañía.'),
]


class Evaluation(db.Model):
    """Evaluación de desempeño — conecta evaluado (User) con jefe inmediato (User)."""
    __tablename__ = 'evaluations'

    id              = db.Column(db.Integer, primary_key=True)
    evaluatee_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    chief_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    period          = db.Column(db.String(20))          # ej. "2026"
    empresa         = db.Column(db.String(150))
    localidad       = db.Column(db.String(150))
    nivel           = db.Column(db.String(100))
    # Status: draft → open → completed
    status          = db.Column(db.String(20), default='draft')
    # Chief-only scores
    knowledge_score  = db.Column(db.Float)              # 1-5
    experience_score = db.Column(db.Float)              # 1-5
    # Submission timestamps
    employee_submitted_at = db.Column(db.DateTime)
    chief_submitted_at    = db.Column(db.DateTime)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime)

    evaluatee   = db.relationship('User', foreign_keys=[evaluatee_id])
    chief       = db.relationship('User', foreign_keys=[chief_id])
    goals       = db.relationship('EvaluationGoal', backref='evaluation',
                                  cascade='all,delete-orphan',
                                  order_by='EvaluationGoal.order')
    competencies = db.relationship('EvaluationCompetency', backref='evaluation',
                                   cascade='all,delete-orphan',
                                   order_by='EvaluationCompetency.order')

    # ── Computed scores (cached_property: se calcula una sola vez por request) ─
    @cached_property
    def goals_avg(self):
        """Promedio simple de scores del jefe en objetivos."""
        scored = [g.chief_score for g in self.goals if g.chief_score is not None]
        return round(sum(scored) / len(scored), 2) if scored else None

    @cached_property
    def competencies_avg(self):
        """Promedio simple de scores del jefe en competencias."""
        scored = [c.chief_score for c in self.competencies if c.chief_score is not None]
        return round(sum(scored) / len(scored), 2) if scored else None

    @cached_property
    def final_score(self):
        g  = self.goals_avg
        sk = self.competencies_avg
        kn = self.knowledge_score
        ex = self.experience_score
        if any(v is None for v in [g, sk, kn, ex]):
            return None
        return round(g * 0.65 + sk * 0.15 + kn * 0.10 + ex * 0.10, 2)

    @cached_property
    def level_label(self):
        s = self.final_score
        if s is None:
            return '—'
        if s >= 5:
            return 'Sobresaliente'
        if s >= 4:
            return 'Notable'
        if s >= 3:
            return 'Adecuado'
        if s >= 2:
            return 'Deficiente'
        return 'Insuficiente'

    @cached_property
    def employee_goals_avg(self):
        """Promedio self-eval del empleado en objetivos."""
        scored = [g.employee_score for g in self.goals if g.employee_score is not None]
        return round(sum(scored) / len(scored), 2) if scored else None

    @cached_property
    def employee_competencies_avg(self):
        scored = [c.employee_score for c in self.competencies if c.employee_score is not None]
        return round(sum(scored) / len(scored), 2) if scored else None

    def __repr__(self):
        return f'<Evaluation {self.id} evaluatee={self.evaluatee_id}>'


class EvaluationGoal(db.Model):
    """Objetivo definido por el jefe en una evaluación."""
    __tablename__ = 'evaluation_goals'

    id              = db.Column(db.Integer, primary_key=True)
    evaluation_id   = db.Column(db.Integer, db.ForeignKey('evaluations.id'), nullable=False)
    order           = db.Column(db.Integer, default=0)
    category        = db.Column(db.String(100))         # Financiero, Operacional, etc.
    description     = db.Column(db.Text)
    weight          = db.Column(db.Integer, default=0)  # porcentaje (suma = 100)
    period          = db.Column(db.String(50))          # ej. "Ene - Dic"
    employee_score  = db.Column(db.Integer)             # 1-5 (self-eval)
    chief_score     = db.Column(db.Integer)             # 1-5
    comments        = db.Column(db.Text)


class EvaluationCompetency(db.Model):
    """Competencia pre-seeded en cada evaluación."""
    __tablename__ = 'evaluation_competencies'

    id              = db.Column(db.Integer, primary_key=True)
    evaluation_id   = db.Column(db.Integer, db.ForeignKey('evaluations.id'), nullable=False)
    order           = db.Column(db.Integer, default=0)
    name            = db.Column(db.String(200))
    description     = db.Column(db.Text)
    employee_score  = db.Column(db.Integer)             # 1-5 (self-eval)
    chief_score     = db.Column(db.Integer)             # 1-5
