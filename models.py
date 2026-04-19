from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

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
    username       = db.Column(db.String(80),  nullable=False, unique=True)
    email          = db.Column(db.String(150), unique=True)
    pwd_hash       = db.Column(db.String(256), nullable=False)
    role           = db.Column(db.String(20),  nullable=False, default='viewer')  # admin | viewer
    active         = db.Column(db.Boolean, default=True)
    module_access  = db.Column(db.Text, default='')  # comma-separated slugs, e.g. "inventory,projects"
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

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


class Client(db.Model):
    __tablename__ = 'clients'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(150), nullable=False, unique=True)
    active     = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    assets     = db.relationship('Asset', backref='client', lazy=True)

    def __repr__(self):
        return f'<Client {self.name}>'


class Asset(db.Model):
    __tablename__ = 'assets'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    asset_tag = db.Column(db.String(50), unique=True, nullable=False)
    serial_number = db.Column(db.String(100))
    manufacturer = db.Column(db.String(100))
    model = db.Column(db.String(100))
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    client_id   = db.Column(db.Integer, db.ForeignKey('clients.id'))
    status = db.Column(db.String(30), nullable=False, default='available')
    # En Sitio vs Foráneo
    location_type = db.Column(db.String(20), nullable=False, default='en_sitio')  # en_sitio | hibrido | foraneo
    location = db.Column(db.String(150))
    # Specs
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    assignments = db.relationship('Assignment', backref='asset', lazy=True,
                                  order_by='Assignment.assigned_date.desc()')
    shipments = db.relationship('Shipment', backref='asset', lazy=True,
                                order_by='Shipment.created_at.desc()')

    STATUS_CHOICES = ['available', 'in_use', 'maintenance', 'retired', 'disposed']

    @property
    def current_assignment(self):
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
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    department = db.Column(db.String(100))
    email = db.Column(db.String(150))
    phone = db.Column(db.String(30))
    active = db.Column(db.Boolean, default=True)
    assignments = db.relationship('Assignment', backref='employee', lazy=True,
                                  order_by='Assignment.assigned_date.desc()')

    @property
    def current_assets(self):
        return Assignment.query.filter_by(employee_id=self.id, returned_date=None).all()

    def __repr__(self):
        return f'<Employee {self.employee_id} - {self.name}>'


class Assignment(db.Model):
    __tablename__ = 'assignments'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    assigned_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    returned_date = db.Column(db.Date)
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

    CARRIER_CHOICES = ['DHL', 'FedEx', 'UPS', 'USPS', 'Estafeta', 'Otro']
    STATUS_CHOICES = ['pendiente', 'en_transito', 'en_aduana', 'entregado', 'devuelto']

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
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='audit_logs', lazy=True,
                           foreign_keys=[user_id])

    def __repr__(self):
        return f'<AuditLog {self.action} {self.entity_type} by {self.user_name}>'


# ── Project Management Models ─────────────────────────────────────────────────


class Project(db.Model):
    __tablename__ = 'projects'
    id          = db.Column(db.Integer, primary_key=True)
    code        = db.Column(db.String(30), unique=True, nullable=False)
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


def log_action(action, entity_type, entity_id=None, entity_name=None, details=None):
    """Registra una acción en el audit log. El caller debe hacer commit."""
    try:
        from flask import session as _sess, request as _req
        u  = _sess.get('user', {})
        ip = _req.remote_addr
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
