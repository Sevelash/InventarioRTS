"""
RTS Intranet — Translations (i18n)
Supported: 'en' (default), 'es'
Access via context processor: {{ T.key }} in templates
"""

TRANSLATIONS = {
    'en': {
        # ── Sidebar nav sections ───────────────────────────────
        'nav_portal':      'Portal',
        'nav_home':        'Home',
        'nav_inventory':   'Inventory',
        'nav_projects':    'Projects',
        'nav_evaluation':  'Evaluation',
        'nav_repository':  'Repository',
        'nav_admin':       'Administration',

        # ── Sidebar nav links ──────────────────────────────────
        'nav_dashboard':   'Dashboard',
        'nav_assets':      'Assets',
        'nav_categories':  'Categories',
        'nav_clients':     'Clients',
        'nav_employees':   'Employees',
        'nav_assignments': 'Assignments',
        'nav_shipments':   'DHL Shipments',
        'nav_all_projects':'Projects',
        'nav_eval':        'Evaluations',
        'nav_repo':        'Repository',
        'nav_admin_panel': 'Admin Panel',
        'nav_logs':        'Logs',

        # ── Topbar / user menu ─────────────────────────────────
        'user_signout':    'Sign Out',
        'lang_switch_label': 'ES',
        'lang_switch_title': 'Cambiar a Español',

        # ── Portal ─────────────────────────────────────────────
        'portal_welcome':       'Welcome',
        'portal_subtitle':      'Select a module to continue.',
        'portal_no_modules':    'No modules assigned',
        'portal_no_modules_sub':'Contact your administrator to get access to the corresponding modules.',
        'portal_quick_admin':   'Quick access · Administration',
        'portal_admin_panel':   'Admin Panel',
        'portal_users':         'Users',

        # ── Module card descriptions ───────────────────────────
        'mod_inventory_name': 'Inventory Management',
        'mod_inventory_desc': 'Asset tracking & lifecycle management',
        'mod_projects_name':  'Project Management',
        'mod_projects_desc':  'Projects, tasks & team collaboration',
        'mod_eval_name':      'Evaluation',
        'mod_eval_desc':      'Performance evaluations & reviews',
        'mod_repo_name':      'Repository',
        'mod_repo_desc':      'Documents & knowledge base',

        # ── Common buttons ─────────────────────────────────────
        'btn_save':        'Save Changes',
        'btn_create':      'Create',
        'btn_cancel':      'Cancel',
        'btn_delete':      'Delete',
        'btn_edit':        'Edit',
        'btn_back':        'Back',
        'btn_new':         'New',
        'btn_filter':      'Filter',
        'btn_search':      'Search',
        'btn_view_all':    'View all',
        'btn_export':      'Export',
        'btn_close':       'Close',

        # ── Common table/form labels ───────────────────────────
        'lbl_name':        'Name',
        'lbl_status':      'Status',
        'lbl_category':    'Category',
        'lbl_client':      'Client',
        'lbl_date':        'Date',
        'lbl_notes':       'Notes',
        'lbl_actions':     'Actions',
        'lbl_search':      'Search',
        'lbl_all':         'All',
        'lbl_priority':    'Priority',
        'lbl_progress':    'Progress',
        'lbl_type':        'Type',
        'lbl_owner':       'Owner',
        'lbl_due_date':    'Due Date',
        'lbl_description': 'Description',
        'lbl_team':        'Team',
        'lbl_tasks':       'Tasks',
        'lbl_code':        'Code',
        'lbl_budget':      'Budget',
        'lbl_start_date':  'Start Date',
        'lbl_end_date':    'End Date',

        # ── Asset statuses ─────────────────────────────────────
        'status_available':   'Available',
        'status_in_use':      'In Use',
        'status_maintenance': 'Maintenance',
        'status_retired':     'Retired',
        'status_disposed':    'Disposed',

        # ── Location types ─────────────────────────────────────
        'loc_en_sitio': 'On Site',
        'loc_foraneo':  'Remote',
        'loc_hibrido':  'Hybrid',

        # ── Project statuses ───────────────────────────────────
        'proj_planning':  'Planning',
        'proj_active':    'Active',
        'proj_on_hold':   'On Hold',
        'proj_completed': 'Completed',
        'proj_cancelled': 'Cancelled',

        # ── Task statuses ──────────────────────────────────────
        'task_pending':     'Pending',
        'task_in_progress': 'In Progress',
        'task_review':      'In Review',
        'task_done':        'Done',
        'task_cancelled':   'Cancelled',

        # ── Priority ───────────────────────────────────────────
        'prio_low':      'Low',
        'prio_medium':   'Medium',
        'prio_high':     'High',
        'prio_critical': 'Critical',

        # ── Inventory Dashboard ────────────────────────────────
        'inv_chart_title':       'Equipment Trend',
        'inv_period':            'Period:',
        'inv_cat_label':         'Category:',
        'inv_all_cats':          'All Categories',
        'inv_last12':            'Last 12 months',
        'inv_last24':            'Last 24 months',
        'inv_acquisitions':      'Acquisitions',
        'inv_retirements':       'Retirements',
        'inv_reassignments':     'Reassignments',
        'inv_total_assets':      'Total Assets',
        'inv_available':         'Available',
        'inv_in_use':            'In Use',
        'inv_maintenance':       'Maintenance',
        'inv_retired':           'Retired',
        'inv_employees':         'Active Employees',
        'inv_categories':        'Categories',
        'inv_remote':            'Remote Assets',
        'inv_in_transit':        'In Transit',
        'inv_recent_assign':     'Recent Assignments',
        'inv_active_shipments':  'Active Shipments',
        'inv_by_category':       'Assets by Category',
        'inv_summary':           'General Summary',
        'inv_new_asset':         'New Asset',

        # ── Projects Dashboard ─────────────────────────────────
        'proj_total':         'Total Projects',
        'proj_active_kpi':    'Active',
        'proj_completed_kpi': 'Completed',
        'proj_on_hold_kpi':   'On Hold',
        'proj_overdue':       'Overdue',
        'proj_total_tasks':   'Total Tasks',
        'proj_recent':        'Recent Projects',
        'proj_by_status':     'Projects by Status',
        'proj_my_tasks':      'My Pending Tasks',
        'proj_task_summary':  'Task Summary',
        'proj_done_tasks':    'Completed',
        'proj_pending_tasks': 'In Progress / Pending',
        'proj_overdue_tasks': 'Overdue Tasks',
        'proj_new_project':   'New Project',

        # ── Shipment statuses ──────────────────────────────────
        'ship_pendiente':   'Pending',
        'ship_en_transito': 'In Transit',
        'ship_en_aduana':   'In Customs',
        'ship_entregado':   'Delivered',
        'ship_devuelto':    'Returned',

        # ── Coming soon ────────────────────────────────────────
        'coming_soon_eval_title': 'Evaluation Module',
        'coming_soon_eval_desc':  'This module is under construction. Soon you\'ll be able to manage performance evaluations and team review records.',
        'coming_soon_repo_title': 'RTS Repository',
        'coming_soon_repo_desc':  'The centralized repository for documents, processes and knowledge of Remote Team Solutions. Under construction.',
        'coming_soon_back':       'Back to Portal',

        # ── Auth ───────────────────────────────────────────────
        'login_title':    'Sign In',
        'login_username': 'Username',
        'login_password': 'Password',
        'login_btn':      'Sign In',
    },

    'es': {
        # ── Sidebar nav sections ───────────────────────────────
        'nav_portal':      'Portal',
        'nav_home':        'Inicio',
        'nav_inventory':   'Inventario',
        'nav_projects':    'Proyectos',
        'nav_evaluation':  'Evaluación',
        'nav_repository':  'Repositorio',
        'nav_admin':       'Administración',

        # ── Sidebar nav links ──────────────────────────────────
        'nav_dashboard':   'Dashboard',
        'nav_assets':      'Activos',
        'nav_categories':  'Categorías',
        'nav_clients':     'Clientes',
        'nav_employees':   'Empleados',
        'nav_assignments': 'Asignaciones',
        'nav_shipments':   'Envíos DHL',
        'nav_all_projects':'Proyectos',
        'nav_eval':        'Evaluaciones',
        'nav_repo':        'Repositorio',
        'nav_admin_panel': 'Panel Admin',
        'nav_logs':        'Logs',

        # ── Topbar / user menu ─────────────────────────────────
        'user_signout':    'Cerrar Sesión',
        'lang_switch_label': 'EN',
        'lang_switch_title': 'Switch to English',

        # ── Portal ─────────────────────────────────────────────
        'portal_welcome':       'Bienvenido',
        'portal_subtitle':      'Selecciona un módulo para continuar.',
        'portal_no_modules':    'Sin módulos asignados',
        'portal_no_modules_sub':'Contacta al administrador para que te asigne acceso a los módulos correspondientes.',
        'portal_quick_admin':   'Acceso rápido · Administración',
        'portal_admin_panel':   'Panel Admin',
        'portal_users':         'Usuarios',

        # ── Module card descriptions ───────────────────────────
        'mod_inventory_name': 'Inventory Management',
        'mod_inventory_desc': 'Seguimiento y gestión del ciclo de vida de activos',
        'mod_projects_name':  'Project Management',
        'mod_projects_desc':  'Proyectos, tareas y colaboración en equipo',
        'mod_eval_name':      'Evaluación',
        'mod_eval_desc':      'Evaluaciones de desempeño y revisiones',
        'mod_repo_name':      'Repositorio',
        'mod_repo_desc':      'Documentos y base de conocimiento',

        # ── Common buttons ─────────────────────────────────────
        'btn_save':        'Guardar Cambios',
        'btn_create':      'Crear',
        'btn_cancel':      'Cancelar',
        'btn_delete':      'Eliminar',
        'btn_edit':        'Editar',
        'btn_back':        'Regresar',
        'btn_new':         'Nuevo',
        'btn_filter':      'Filtrar',
        'btn_search':      'Buscar',
        'btn_view_all':    'Ver todos',
        'btn_export':      'Exportar',
        'btn_close':       'Cerrar',

        # ── Common table/form labels ───────────────────────────
        'lbl_name':        'Nombre',
        'lbl_status':      'Estado',
        'lbl_category':    'Categoría',
        'lbl_client':      'Cliente',
        'lbl_date':        'Fecha',
        'lbl_notes':       'Notas',
        'lbl_actions':     'Acciones',
        'lbl_search':      'Buscar',
        'lbl_all':         'Todos',
        'lbl_priority':    'Prioridad',
        'lbl_progress':    'Progreso',
        'lbl_type':        'Tipo',
        'lbl_owner':       'Responsable',
        'lbl_due_date':    'Vencimiento',
        'lbl_description': 'Descripción',
        'lbl_team':        'Equipo',
        'lbl_tasks':       'Tareas',
        'lbl_code':        'Código',
        'lbl_budget':      'Presupuesto',
        'lbl_start_date':  'Fecha Inicio',
        'lbl_end_date':    'Fecha Fin',

        # ── Asset statuses ─────────────────────────────────────
        'status_available':   'Disponible',
        'status_in_use':      'En Uso',
        'status_maintenance': 'Mantenimiento',
        'status_retired':     'Retirado',
        'status_disposed':    'Desechado',

        # ── Location types ─────────────────────────────────────
        'loc_en_sitio': 'En Sitio',
        'loc_foraneo':  'Foráneo',
        'loc_hibrido':  'Híbrido',

        # ── Project statuses ───────────────────────────────────
        'proj_planning':  'Planeación',
        'proj_active':    'Activo',
        'proj_on_hold':   'En Pausa',
        'proj_completed': 'Completado',
        'proj_cancelled': 'Cancelado',

        # ── Task statuses ──────────────────────────────────────
        'task_pending':     'Pendiente',
        'task_in_progress': 'En Progreso',
        'task_review':      'En Revisión',
        'task_done':        'Listo',
        'task_cancelled':   'Cancelado',

        # ── Priority ───────────────────────────────────────────
        'prio_low':      'Baja',
        'prio_medium':   'Media',
        'prio_high':     'Alta',
        'prio_critical': 'Crítica',

        # ── Inventory Dashboard ────────────────────────────────
        'inv_chart_title':       'Tendencia de Equipos',
        'inv_period':            'Período:',
        'inv_cat_label':         'Categoría:',
        'inv_all_cats':          'Todas las Categorías',
        'inv_last12':            'Últimos 12 meses',
        'inv_last24':            'Últimos 24 meses',
        'inv_acquisitions':      'Adquisiciones',
        'inv_retirements':       'Bajas',
        'inv_reassignments':     'Reasignaciones',
        'inv_total_assets':      'Total Activos',
        'inv_available':         'Disponibles',
        'inv_in_use':            'En Uso',
        'inv_maintenance':       'Mantenimiento',
        'inv_retired':           'Retirados',
        'inv_employees':         'Empleados Activos',
        'inv_categories':        'Categorías',
        'inv_remote':            'Activos Foráneos',
        'inv_in_transit':        'En Tránsito',
        'inv_recent_assign':     'Asignaciones Recientes',
        'inv_active_shipments':  'Envíos Activos',
        'inv_by_category':       'Activos por Categoría',
        'inv_summary':           'Resumen General',
        'inv_new_asset':         'Nuevo Activo',

        # ── Projects Dashboard ─────────────────────────────────
        'proj_total':         'Total Proyectos',
        'proj_active_kpi':    'Activos',
        'proj_completed_kpi': 'Completados',
        'proj_on_hold_kpi':   'En Pausa',
        'proj_overdue':       'Vencidos',
        'proj_total_tasks':   'Total Tareas',
        'proj_recent':        'Proyectos Recientes',
        'proj_by_status':     'Proyectos por Estado',
        'proj_my_tasks':      'Mis Tareas Pendientes',
        'proj_task_summary':  'Resumen de Tareas',
        'proj_done_tasks':    'Completadas',
        'proj_pending_tasks': 'En Progreso / Pendientes',
        'proj_overdue_tasks': 'Tareas Vencidas',
        'proj_new_project':   'Nuevo Proyecto',

        # ── Shipment statuses ──────────────────────────────────
        'ship_pendiente':   'Pendiente',
        'ship_en_transito': 'En Tránsito',
        'ship_en_aduana':   'En Aduana',
        'ship_entregado':   'Entregado',
        'ship_devuelto':    'Devuelto',

        # ── Coming soon ────────────────────────────────────────
        'coming_soon_eval_title': 'Módulo de Evaluación',
        'coming_soon_eval_desc':  'Este módulo está en construcción. Próximamente podrás gestionar evaluaciones de desempeño.',
        'coming_soon_repo_title': 'Repositorio RTS',
        'coming_soon_repo_desc':  'El repositorio centralizado de documentos, procesos y conocimiento de Remote Team Solutions.',
        'coming_soon_back':       'Volver al Portal',

        # ── Auth ───────────────────────────────────────────────
        'login_title':    'Iniciar Sesión',
        'login_username': 'Usuario',
        'login_password': 'Contraseña',
        'login_btn':      'Entrar',
    },
}

SUPPORTED_LANGS = list(TRANSLATIONS.keys())
DEFAULT_LANG    = 'en'


def get_translations(lang: str) -> dict:
    if lang not in TRANSLATIONS:
        lang = DEFAULT_LANG
    return TRANSLATIONS[lang]
