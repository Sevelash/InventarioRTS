"""
Script para poblar la base de datos con datos de ejemplo de RTS.
Ejecutar una sola vez: python seed.py
"""
from app import app
from models import db, Category, Asset, Employee, Assignment
from datetime import date

with app.app_context():
    db.create_all()

    # Categorias
    cats = [
        Category(name='Laptops', description='Computadoras portátiles'),
        Category(name='Monitores', description='Pantallas y monitores de escritorio'),
        Category(name='Periféricos', description='Teclados, ratones, auriculares'),
        Category(name='Teléfonos', description='Celulares y teléfonos IP'),
        Category(name='Servidores', description='Equipos de servidor y NAS'),
        Category(name='Redes', description='Routers, switches, access points'),
        Category(name='Impresoras', description='Impresoras y escáneres'),
    ]
    for c in cats:
        if not Category.query.filter_by(name=c.name).first():
            db.session.add(c)
    db.session.commit()

    laptop_id = Category.query.filter_by(name='Laptops').first().id
    monitor_id = Category.query.filter_by(name='Monitores').first().id
    periph_id  = Category.query.filter_by(name='Periféricos').first().id
    phone_id   = Category.query.filter_by(name='Teléfonos').first().id

    # Activos
    assets = [
        Asset(name='Laptop Dell XPS 15', asset_tag='RTS-L001', serial_number='DL-XPS-00123',
              manufacturer='Dell', model='XPS 15 9530', category_id=laptop_id,
              status='in_use', location='Oficina Central',
              purchase_date=date(2024, 3, 10), purchase_cost=1850.00,
              warranty_expiry=date(2027, 3, 10)),
        Asset(name='Laptop MacBook Pro M3', asset_tag='RTS-L002', serial_number='C02ZK1234XYZ',
              manufacturer='Apple', model='MacBook Pro 14" M3', category_id=laptop_id,
              status='available', location='Almacén IT',
              purchase_date=date(2024, 11, 5), purchase_cost=2399.00,
              warranty_expiry=date(2026, 11, 5)),
        Asset(name='Laptop HP EliteBook 840', asset_tag='RTS-L003', serial_number='HP-EB-55678',
              manufacturer='HP', model='EliteBook 840 G10', category_id=laptop_id,
              status='maintenance', location='Taller IT',
              purchase_date=date(2023, 6, 20), purchase_cost=1250.00,
              warranty_expiry=date(2026, 6, 20)),
        Asset(name='Monitor LG UltraWide 34"', asset_tag='RTS-M001', serial_number='LG-UW-34-001',
              manufacturer='LG', model='34WN80C-B', category_id=monitor_id,
              status='in_use', location='Oficina Central',
              purchase_date=date(2023, 9, 1), purchase_cost=480.00,
              warranty_expiry=date(2026, 9, 1)),
        Asset(name='Monitor Dell 27" 4K', asset_tag='RTS-M002', serial_number='DL-P2723QE',
              manufacturer='Dell', model='P2723QE', category_id=monitor_id,
              status='available', location='Almacén IT',
              purchase_date=date(2024, 1, 15), purchase_cost=550.00,
              warranty_expiry=date(2027, 1, 15)),
        Asset(name='iPhone 15 Pro', asset_tag='RTS-P001', serial_number='IP15P-RTS-001',
              manufacturer='Apple', model='iPhone 15 Pro 256GB', category_id=phone_id,
              status='in_use', location='Oficina Central',
              purchase_date=date(2024, 2, 1), purchase_cost=999.00,
              warranty_expiry=date(2026, 2, 1)),
        Asset(name='Mouse Logitech MX Master 3', asset_tag='RTS-PC001', serial_number=None,
              manufacturer='Logitech', model='MX Master 3S', category_id=periph_id,
              status='available', location='Almacén IT',
              purchase_date=date(2024, 5, 10), purchase_cost=99.99),
    ]
    for a in assets:
        if not Asset.query.filter_by(asset_tag=a.asset_tag).first():
            db.session.add(a)
    db.session.commit()

    # Empleados
    employees = [
        Employee(name='Carlos Méndez', employee_id='EMP-001', department='IT', email='cmendez@rts.com', phone='+1 787-555-0101'),
        Employee(name='Ana Rodríguez', employee_id='EMP-002', department='Contabilidad', email='arodriguez@rts.com', phone='+1 787-555-0102'),
        Employee(name='Luis Torres', employee_id='EMP-003', department='Ventas', email='ltorres@rts.com', phone='+1 787-555-0103'),
        Employee(name='María García', employee_id='EMP-004', department='RRHH', email='mgarcia@rts.com', phone='+1 787-555-0104'),
        Employee(name='Pedro Colón', employee_id='EMP-005', department='IT', email='pcolon@rts.com', phone='+1 787-555-0105'),
    ]
    for e in employees:
        if not Employee.query.filter_by(employee_id=e.employee_id).first():
            db.session.add(e)
    db.session.commit()

    # Asignaciones
    l001 = Asset.query.filter_by(asset_tag='RTS-L001').first()
    m001 = Asset.query.filter_by(asset_tag='RTS-M001').first()
    p001 = Asset.query.filter_by(asset_tag='RTS-P001').first()
    emp1 = Employee.query.filter_by(employee_id='EMP-001').first()
    emp2 = Employee.query.filter_by(employee_id='EMP-002').first()
    emp3 = Employee.query.filter_by(employee_id='EMP-003').first()

    assignments = [
        Assignment(asset_id=l001.id, employee_id=emp1.id, assigned_date=date(2024, 3, 15), notes='Asignación inicial'),
        Assignment(asset_id=m001.id, employee_id=emp2.id, assigned_date=date(2024, 1, 10), notes='Puesto de trabajo'),
        Assignment(asset_id=p001.id, employee_id=emp3.id, assigned_date=date(2024, 2, 5)),
    ]
    for a in assignments:
        if not Assignment.query.filter_by(asset_id=a.asset_id, returned_date=None).first():
            db.session.add(a)
    db.session.commit()

    print("✓ Base de datos poblada con datos de ejemplo.")
    print(f"  {Category.query.count()} categorías")
    print(f"  {Asset.query.count()} activos")
    print(f"  {Employee.query.count()} empleados")
    print(f"  {Assignment.query.count()} asignaciones")
