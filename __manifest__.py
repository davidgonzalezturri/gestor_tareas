{
    'name': 'Gestor de Tareas',
    'version': '1.0',
    'author': 'David',
    'category': 'Productivity',
    'depends': ['base', 'project', 'contacts', 'hr'],
    'data': [
        'views/gestor_tareas_view.xml',  #
        'data/gestor_tareas_cron.xml',  # Acciones programadas
        'security/ir.model.access.csv',  # Permisos de acceso
    ],
    'assets': {
        'web.assets_backend': [
            'gestor_tareas/static/src/css/kanban_background.css',
        ],
    },
    'installable': True,
    'application': True,
}
