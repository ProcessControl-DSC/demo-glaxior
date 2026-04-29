from collections import defaultdict

from odoo import _, api, fields, models
from odoo.tools.float_utils import float_compare, float_is_zero


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    pc_warehouse_selection_mode = fields.Selection(
        selection=[
            ('case_a', 'Single Warehouse Covers'),
            ('case_b', 'Consolidation Required'),
            ('no_stock', 'No Stock Available'),
        ],
        string='Warehouse Selection Mode',
        readonly=True,
        copy=False,
    )
    pc_requires_consolidation = fields.Boolean(
        string='Requires Inter-Warehouse Consolidation',
        readonly=True,
        copy=False,
    )
    pc_original_warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Original Virtual Warehouse',
        readonly=True,
        copy=False,
        help="Virtual warehouse set on the sale order before auto-selection.",
    )
    pc_consolidation_picking_count = fields.Integer(
        string='Consolidation Transfers',
        compute='_compute_pc_consolidation_picking_count',
    )

    @api.depends('name', 'picking_ids')
    def _compute_pc_consolidation_picking_count(self):
        for order in self:
            order.pc_consolidation_picking_count = len(
                order._pc_get_consolidation_pickings()
            )

    def _pc_get_consolidation_pickings(self):
        """Return pickings linked to this SO via ``origin`` that are not part
        of ``picking_ids`` -- i.e. the inter-warehouse transfers that feed
        stock to the winner warehouse before the customer delivery."""
        self.ensure_one()
        if not self.name:
            return self.env['stock.picking']
        return self.env['stock.picking'].search([
            ('origin', '=', self.name),
            ('id', 'not in', self.picking_ids.ids),
        ])

    def action_view_pc_consolidation_pickings(self):
        self.ensure_one()
        pickings = self._pc_get_consolidation_pickings()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'stock.action_picking_tree_all'
        )
        action['domain'] = [('id', 'in', pickings.ids)]
        action['context'] = {
            'default_origin': self.name,
            'search_default_origin': self.name,
        }
        return action

    # ------------------------------------------------------------------
    # Confirmation flow
    # ------------------------------------------------------------------
    def _action_confirm(self):
        # Phase 1: choose the winner physical warehouse before super() generates
        # any picking, so the SO pickings are created in the correct warehouse.
        for order in self:
            if order.warehouse_id.is_virtual_warehouse \
                    and order.warehouse_id.pc_child_warehouse_ids:
                order._pc_apply_warehouse_selection()
        # Phase 2: super() generates the customer pickings (Pick + Out) at the
        # winner warehouse with default ``make_to_stock`` rules.
        res = super()._action_confirm()
        # Phase 3: for case_b orders, replace the MTS slack with a properly
        # chained Make-To-Order leg fed by inter-warehouse resupply moves so
        # the customer pick cannot start until all stock is consolidated.
        for order in self:
            if order.pc_warehouse_selection_mode == 'case_b':
                order._pc_build_consolidation_chain()
        return res

    # ------------------------------------------------------------------
    # Phase 1 -- winner selection
    # ------------------------------------------------------------------
    def _pc_apply_warehouse_selection(self):
        self.ensure_one()
        virtual_wh = self.warehouse_id
        candidates = virtual_wh.pc_child_warehouse_ids
        eligible_lines = self.order_line.filtered(self._pc_is_line_eligible)
        total_demand = sum(eligible_lines.mapped('product_uom_qty'))
        if not candidates or not eligible_lines or total_demand <= 0.0:
            return

        coverage_by_wh = {}
        for wh in candidates:
            covered = 0.0
            for line in eligible_lines:
                available = self._pc_get_available_stock(line.product_id, wh)
                covered += min(available, line.product_uom_qty)
            coverage_by_wh[wh.id] = covered

        if max(coverage_by_wh.values()) <= 0.0:
            self.pc_original_warehouse_id = virtual_wh
            self.pc_warehouse_selection_mode = 'no_stock'
            return

        winner = self._pc_pick_winner(candidates, coverage_by_wh)
        self.pc_original_warehouse_id = virtual_wh
        self.warehouse_id = winner

        precision = self.env['decimal.precision'].precision_get('Product Unit')
        if float_compare(
            coverage_by_wh[winner.id], total_demand, precision_digits=precision
        ) >= 0:
            self.pc_warehouse_selection_mode = 'case_a'
            self.pc_requires_consolidation = False
        else:
            self.pc_warehouse_selection_mode = 'case_b'
            self.pc_requires_consolidation = True

    @staticmethod
    def _pc_is_line_eligible(line):
        return (
            line.product_id
            and line.product_id.type == 'consu'
            and line.product_uom_qty > 0.0
        )

    def _pc_pick_winner(self, candidates, coverage_by_wh):
        def sort_key(wh):
            return (-coverage_by_wh[wh.id], wh.sequence, wh.id)
        return sorted(candidates, key=sort_key)[0]

    def _pc_get_available_stock(self, product, warehouse):
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id', 'child_of', warehouse.lot_stock_id.id),
        ])
        total = sum(quants.mapped('available_quantity'))
        return max(0.0, total)

    # ------------------------------------------------------------------
    # Phase 3 -- consolidation chain
    # ------------------------------------------------------------------
    def _pc_build_consolidation_chain(self):
        """For each eligible line whose demand exceeds the stock available
        in the winner warehouse, split the customer pick move into two:

          * an MTS portion equal to ``available`` (reserves stock right away);
          * an MTO portion equal to the missing quantity, chained backwards
            to inter-warehouse resupply moves.

        The MTO portion's ``move_orig_ids`` will be populated by the
        procurement engine, so the customer pick cannot start until the
        consolidation is complete.
        """
        self.ensure_one()
        winner = self.warehouse_id
        if not winner or not self.pc_original_warehouse_id:
            return
        others = self.pc_original_warehouse_id.pc_child_warehouse_ids - winner
        if not others:
            return

        precision = self.env['decimal.precision'].precision_get('Product Unit')
        affected_pickings = self.env['stock.picking']
        for line in self.order_line.filtered(self._pc_is_line_eligible):
            pick_move = self._pc_winner_pick_move_for(line, winner)
            if not pick_move:
                continue
            if pick_move.picking_id:
                affected_pickings |= pick_move.picking_id
            # ``super()._action_confirm()`` already reserved every unit of
            # ``pick_move`` that the winner had physically on hand. The MTS
            # portion is exactly what the move could grab; the rest is the
            # quantity we have to bring in from other warehouses.
            reserved = pick_move.quantity
            demand = pick_move.product_uom_qty
            if float_compare(demand, reserved, precision_digits=precision) <= 0:
                continue
            missing = demand - reserved
            mto_move = self._pc_split_pick_move(pick_move, missing, reserved, precision)
            if not mto_move:
                continue
            self._pc_chain_resupply_for_move(line, mto_move, missing, winner, others)

        # Force the customer pick to behave all-or-nothing so the operator
        # cannot ship the MTS portion while the MTO portion is still in
        # transit, and refresh its state to reflect the new waiting moves.
        if affected_pickings:
            affected_pickings.write({'move_type': 'one'})
            affected_pickings._compute_state()

    def _pc_winner_pick_move_for(self, line, winner):
        """The first move in the customer pick that originates from the
        winner's stock location for this sale line."""
        return line.move_ids.filtered(
            lambda m: m.location_id == winner.lot_stock_id
            and m.state not in ('done', 'cancel')
        )[:1]

    def _pc_split_pick_move(self, pick_move, missing, available, precision):
        """Reduce ``pick_move`` so it carries only the MTS-reservable portion
        and return the new MTO move that holds the missing quantity. When no
        stock is available at all, the original move itself becomes the MTO
        move (no split needed).

        The new move is left **unconfirmed** on purpose: we will later run
        the consolidation procurements with ``move_dest_ids=mto_move`` so
        the resupply moves attach themselves as ``move_orig_ids`` of the
        MTO move *before* it is confirmed. Only then we call
        ``_action_confirm`` so the MTO chain is honoured (a confirm with
        no origins yet would fire an unrouted MTO procurement and crash
        with "no rule found")."""
        if float_is_zero(available, precision_digits=precision):
            pick_move.write({'procure_method': 'make_to_order'})
            return pick_move
        new_move_vals = pick_move._split(missing)
        if not new_move_vals:
            return self.env['stock.move']
        for vals in new_move_vals:
            vals['procure_method'] = 'make_to_order'
            if pick_move.picking_id:
                vals.setdefault('picking_id', pick_move.picking_id.id)
        mto_move = self.env['stock.move'].create(new_move_vals)
        return mto_move

    def _pc_chain_resupply_for_move(self, line, mto_move, missing, winner, others):
        """Run resupply procurements that feed ``winner.lot_stock_id`` and
        chain (via ``move_dest_ids``) to ``mto_move`` so the customer pick
        waits until the inter-warehouse stock has arrived."""
        self.ensure_one()
        if not self.stock_reference_ids:
            self.env['stock.reference'].create(line._prepare_reference_vals())
        Procurement = self.env['stock.rule'].Procurement
        precision = self.env['decimal.precision'].precision_get('Product Unit')
        date_deadline = self.commitment_date or fields.Datetime.now()
        procurements = []

        for other in others.sorted(lambda w: (w.sequence, w.id)):
            if float_compare(missing, 0.0, precision_digits=precision) <= 0:
                break
            avail_other = self._pc_get_available_stock(line.product_id, other)
            take = min(missing, avail_other)
            if float_compare(take, 0.0, precision_digits=precision) <= 0:
                continue
            route = self._pc_resupply_route(winner, other)
            if not route:
                continue
            values = {
                'date_planned': date_deadline,
                'date_deadline': date_deadline,
                'warehouse_id': winner,
                'partner_id': self.partner_shipping_id.id,
                'company_id': self.company_id,
                'origin': self.name,
                'reference_ids': self.stock_reference_ids,
                'route_ids': route,
                # ``stock.rule._get_stock_move_values`` iterates over this and
                # reads ``.id`` on each item, so it must be a recordset rather
                # than a list of (4, id) commands.
                'move_dest_ids': mto_move,
            }
            procurements.append(Procurement(
                line.product_id,
                take,
                line.product_uom_id,
                winner.lot_stock_id,
                _("Consolidation for %s", self.name),
                self.name,
                self.company_id,
                values,
            ))
            missing -= take

        if procurements:
            self.env['stock.rule'].run(procurements)
        # Confirm the MTO move now that ``move_orig_ids`` has been populated
        # by the resupply moves. Skip if it is the original pick move (it was
        # already confirmed by ``super()._action_confirm()``).
        if mto_move.state == 'draft':
            mto_move._action_confirm(merge=False)

    @staticmethod
    def _pc_resupply_route(supplied_wh, supplier_wh):
        return supplied_wh.resupply_route_ids.filtered(
            lambda r: r.supplier_wh_id == supplier_wh and r.active
        )[:1]
