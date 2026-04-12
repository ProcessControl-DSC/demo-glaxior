{
    'name': 'GLAXIOR - Importación JSON Configurador',
    'summary': 'Importa ficheros JSON del configurador MyGlaxior y crea pedidos de venta',
    'description': """
        Módulo para GLAXIOR (Soluciones de Acristalamiento).
        Permite importar manualmente los ficheros JSON generados por el configurador
        MyGlaxior y crear automáticamente pedidos de venta con toda la información
        de la configuración adjunta.
    """,
    'category': 'Sales/Sales',
    'version': '19.0.1.0.0',
    'depends': [
        'sale_management',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/product_data.xml',
        'wizards/import_json_wizard_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
