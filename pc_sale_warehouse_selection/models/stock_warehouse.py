from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    is_virtual_warehouse = fields.Boolean(
        string='Virtual Aggregator Warehouse',
        help="If checked, sale orders confirmed against this warehouse are "
             "automatically reassigned to the physical child warehouse with "
             "the best stock coverage. Intended for view-type aggregator "
             "warehouses that sit above several physical warehouses.",
    )
    pc_child_warehouse_ids = fields.Many2many(
        comodel_name='stock.warehouse',
        relation='pc_virtual_children_rel',
        column1='parent_wh_id',
        column2='child_wh_id',
        string='Physical Child Warehouses',
        help="Physical warehouses that the virtual aggregator pulls stock "
             "from. Only used when 'Virtual Aggregator Warehouse' is set.",
    )
    pc_consolidation_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Consolidation Location',
        domain="[('usage', '=', 'internal')]",
        help="Location where inter-warehouse transfers land before being "
             "picked for the customer. Must be a child of the warehouse "
             "stock location so the customer pick can reserve from it. "
             "If left empty, consolidation lands directly on the warehouse "
             "stock location (legacy behaviour).",
    )
