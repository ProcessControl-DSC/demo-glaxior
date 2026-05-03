from odoo import api, fields, models


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

    # ------------------------------------------------------------------
    # Deliver-in-2-steps: enforce pull+pull MTO/MTS pattern
    # ------------------------------------------------------------------
    # Odoo 19 ships the Deliver-in-2-steps route with a pull (Stock->Customer,
    # MTS) plus a push (Output->Customer, MTO). With that pattern, the
    # customer delivery picking only materialises when the warehouse pick
    # is validated. Our flow needs both pickings created at sale order
    # confirmation so consolidation can chain MTO from the very start.
    # We override the route generation to write the rules with the classic
    # pull+pull pattern and we re-apply it after each warehouse write that
    # could regenerate the route (delivery_steps changes, route resets).

    def _pc_apply_2step_chain_pattern_all(self):
        """Class-level helper used by the post_init hook. Walks every
        warehouse that has a Deliver-in-2-steps route and rewrites its
        rules to the pull+pull MTO/MTS pattern."""
        warehouses = self.sudo().search([('delivery_steps', '=', 'pick_ship')])
        for wh in warehouses:
            wh._pc_apply_2step_chain_pattern()

    def _pc_apply_2step_chain_pattern(self):
        """Rewrite the rules of this warehouse's Deliver-in-2-steps route
        from pull+push to pull+pull MTO/MTS. Idempotent: re-running it on
        an already-converted route is a no-op."""
        self.ensure_one()
        if self.delivery_steps != 'pick_ship' or not self.delivery_route_id:
            return
        rules = self.delivery_route_id.rule_ids
        customer_loc = self.env.ref('stock.stock_location_customers',
                                    raise_if_not_found=False)
        if not customer_loc:
            return
        pull_to_customer = rules.filtered(
            lambda r: r.action == 'pull'
            and r.location_dest_id == customer_loc
            and r.location_src_id == self.lot_stock_id
        )
        push_to_customer = rules.filtered(
            lambda r: r.action == 'push'
            and r.location_dest_id == customer_loc
            and r.location_src_id == self.wh_output_stock_loc_id
        )
        # If the rules are already in the new pattern, do nothing.
        already_chained = rules.filtered(
            lambda r: r.action == 'pull'
            and r.location_src_id == self.wh_output_stock_loc_id
            and r.location_dest_id == customer_loc
            and r.procure_method == 'make_to_order'
        )
        if already_chained and not (pull_to_customer or push_to_customer):
            return
        if not pull_to_customer or not push_to_customer:
            # Unfamiliar shape, leave it alone.
            return
        pull_to_customer.sudo().write({
            'name': '%s: Output → Customers' % self.code,
            'location_src_id': self.wh_output_stock_loc_id.id,
            'location_dest_id': customer_loc.id,
            'picking_type_id': self.out_type_id.id,
            'procure_method': 'make_to_order',
            'action': 'pull',
            'auto': 'manual',
        })
        push_to_customer.sudo().write({
            'name': '%s: Stock → Output' % self.code,
            'action': 'pull',
            'location_src_id': self.lot_stock_id.id,
            'location_dest_id': self.wh_output_stock_loc_id.id,
            'picking_type_id': self.pick_type_id.id,
            'procure_method': 'make_to_stock',
            'auto': 'manual',
        })

    def write(self, vals):
        # Detect operations that may rebuild the delivery route and re-apply
        # the pull+pull pattern after the standard write completes.
        relevant = {'delivery_steps', 'delivery_route_id', 'lot_stock_id',
                    'wh_output_stock_loc_id'}
        rebuild = bool(set(vals) & relevant)
        res = super().write(vals)
        if rebuild:
            for wh in self:
                wh._pc_apply_2step_chain_pattern()
        return res
