{
    'name': 'PoS Restrict Negative Stock',
    'summary': 'Bloquea la venta en PoS de productos sin stock disponible en el almacén configurado, con bypass opcional mediante PIN de empleado autorizado.',
    'description': """
PoS Restrict Negative Stock
===========================

Evita la sobreventa en el Punto de Venta comprobando, al añadir cada línea y
antes del pago, que el stock del almacén de la caja cubre la cantidad solicitada.
Incluye bypass opcional por PIN de empleado autorizador con trazabilidad del
autorizador en el pedido.

Funcionalidades clave
---------------------
* Control estricto por almacén de la ``pos.config`` (nunca considera otros almacenes).
* Soporte de los dos modos de actualización de stock de Odoo:
    - Tiempo real: usa ``qty_available`` con contexto de almacén, sin doble descuento.
    - Al cierre de sesión: descuenta líneas ya pagadas de todas las sesiones
      abiertas con el mismo almacén, evitando sobreventa entre cajas.
* Bloqueo temprano al añadir la línea: el cajero ve el error antes de seguir escaneando.
* Revalidación completa al pulsar Pago, incluyendo modificaciones posteriores.
* Bypass opcional con PIN de empleado autorizado configurable por PoS.
* Registro del autorizador en ``pos.order.negative_stock_authorizer_id``.

Configuración
-------------
Punto de Venta > Configuración > Ajustes > Interfaz de PoS > Restrict Negative Stock.

Compatibilidad
--------------
Odoo 19.0 Community y Enterprise. Dependencias: point_of_sale, stock, hr.

Desarrollado por Process Control — https://www.processcontrol.es
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
