{
    'name': 'PoS Restrict Negative Stock',
    'summary': 'Bloquea la venta en PoS de productos sin stock disponible en el almacén configurado, con bypass opcional mediante PIN de empleado autorizado.',
    'description': """
Restringe la venta en el Punto de Venta de productos almacenables cuya cantidad disponible
en el almacén de la configuración del PoS sea insuficiente para cubrir la suma de líneas
del ticket actual.

Soporta los dos modos de actualización de stock de Odoo:
  - Tiempo real: usa `qty_available` sobre el almacén del PoS.
  - Al cierre de sesión: descuenta las ventas confirmadas en todas las sesiones abiertas
    que operen sobre el mismo almacén para evitar sobreventa entre cajas.

Permite configurar una lista de empleados autorizados que pueden forzar la venta introduciendo
su PIN. Cada autorización queda registrada en el pedido.
    """,
    'author': 'Process Control',
    'website': 'https://www.processcontrol.es',
    'category': 'Sales/Point of Sale',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'point_of_sale',
        'stock',
        'hr',
    ],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pc_pos_restrict_negative_stock/static/src/overrides/models/pos_store.js',
            'pc_pos_restrict_negative_stock/static/src/overrides/components/auth_dialog/auth_dialog.js',
            'pc_pos_restrict_negative_stock/static/src/overrides/components/auth_dialog/auth_dialog.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
