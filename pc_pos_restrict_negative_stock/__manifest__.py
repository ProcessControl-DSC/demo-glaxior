{
    'name': 'PoS Restrict Negative Stock',
    'summary': 'Prevents selling Point of Sale products when the configured warehouse has insufficient stock, with optional PIN bypass by an authorised employee.',
    'description': """
PoS Restrict Negative Stock
===========================

Prevents overselling at the Point of Sale by checking, both when each line
is added and before payment, that the stock of the PoS warehouse covers the
requested quantity. Includes optional bypass by authorised employee PIN,
with full traceability of the authoriser on the order.

Key features
------------
* Strict control per ``pos.config`` warehouse (never considers other warehouses).
* Supports both Odoo stock update modes:
    - Real time: uses ``qty_available`` with warehouse context, no double discount.
    - At session closing: subtracts already paid lines from every open session on
      the same warehouse, preventing overselling between cashiers.
* Early blocking when the line is added: the cashier sees the error before
  continuing to scan.
* Full revalidation on Pay, including later modifications.
* Optional bypass with authorised employee PIN, configurable per PoS.
* Authoriser recorded in ``pos.order.negative_stock_authorizer_id``.

Configuration
-------------
Point of Sale > Configuration > Settings > PoS Interface > Restrict Negative Stock.

Compatibility
-------------
Odoo 19.0 Community and Enterprise. Dependencies: point_of_sale, stock, hr.

Developed by Process Control — https://www.processcontrol.es
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
        'views/pos_order_views.xml',
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
