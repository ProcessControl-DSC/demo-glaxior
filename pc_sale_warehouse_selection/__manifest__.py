{
    'name': 'Sale Warehouse Auto-Selection and Consolidation',
    'summary': 'Automatically pick the physical warehouse with the best stock '
               'coverage when a sale order targets a virtual aggregator warehouse, '
               'and trigger inter-warehouse resupply when consolidation is needed.',
    'description': """
Sale Warehouse Auto-Selection and Consolidation
===============================================

When a sale order is confirmed against a warehouse flagged as a virtual
aggregator, this module rewrites the sale order warehouse to the physical
child warehouse that best covers the demand.

Selection rules
---------------
* Coverage is computed per order, across all lines, by total quantity.
* Case A -- the best-covering warehouse covers 100% of the demand: the order
  is simply reassigned to that warehouse. Pick + Out flow runs natively.
* Case B -- no single warehouse covers 100%: the order is reassigned to the
  warehouse that contributes the most, and inter-warehouse procurements are
  launched from every other physical warehouse towards the winner, pulling
  the missing quantity through the configured resupply routes.
* Ties are broken deterministically (warehouse sequence, then id).

Trace fields
------------
* ``pc_warehouse_selection_mode`` -- case_a / case_b / no_stock / manual.
* ``pc_requires_consolidation`` -- boolean flag shown on the sale order.
* ``pc_original_warehouse_id`` -- the virtual warehouse originally set on the
  order, preserved for reporting.

Compatibility
-------------
Odoo 19.0 Enterprise. Requires ``sale_stock`` and ``stock`` and expects the
virtual aggregator warehouse (view location with physical sub-warehouses'
Stock locations as children) to be configured as documented in the Odoo
Inventory manual, section "Sell stock from multiple warehouses using virtual
locations".

Developed by Process Control -- https://www.processcontrol.es
    """,
    'author': 'Process Control',
    'website': 'https://www.processcontrol.es',
    'category': 'Sales/Sales',
    'version': '19.0.1.2.0',
    'license': 'LGPL-3',
    'depends': [
        'sale_stock',
        'stock',
    ],
    'data': [
        'views/stock_warehouse_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
