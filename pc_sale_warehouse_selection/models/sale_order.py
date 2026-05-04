from collections import defaultdict

from odoo import _, api, fields, models
from odoo.tools.float_utils import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def _pc_default_virtual_warehouse(self):
        """If the active company has a virtual aggregator warehouse with at
        least one physical child, use it as the default warehouse for new
        sale orders. Falls back to the standard Odoo default otherwise."""
        return self.env['stock.warehouse'].search([
            ('is_virtual_warehouse', '=', True),
            ('pc_child_warehouse_ids', '!=', False),
            ('company_id', '=', self.env.company.id),
        ], limit=1)

    warehouse_id = fields.Many2one(
        default=lambda self: (
            self._pc_default_virtual_warehouse()
            or self.env['stock.warehouse'].search(
                [('company_id', '=', self.env.company.id)], limit=1
            )
        ),
    )

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
    pc_picking_count = fields.Integer(
        string='Transfers',
        compute='_compute_pc_picking_count',
    )

    @api.depends('name', 'picking_ids')
    def _compute_pc_picking_count(self):
        for order in self:
            order.pc_picking_count = len(order._pc_get_all_pickings())

    def _pc_get_all_pickings(self):
        """All pickings linked to this SO via ``origin`` -- includes the
        customer pick + delivery and any inter-warehouse consolidation
        transfers triggered by the auto-selection."""
        self.ensure_one()
        if not self.name:
            return self.env['stock.picking']
        return self.env['stock.picking'].search([('origin', '=', self.name)])

    def action_view_pc_pickings(self):
        self.ensure_one()
        pickings = self._pc_get_all_pickings()
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
    # Cancellation flow
    # ------------------------------------------------------------------
    def _action_cancel(self):
        """Cancel the inter-warehouse consolidation transfers triggered by
        this sale order along with the standard cancel. Without this hook
        those pickings keep their stock reservations active and starve the
        next sale order that targets the same products and locations."""
        cancel_pickings = self.env['stock.picking']
        for order in self:
            if not order.name:
                continue
            cancel_pickings |= order._pc_get_all_pickings().filtered(
                lambda p: p.state not in ('done', 'cancel')
                and p.id not in order.picking_ids.ids
            )
        res = super()._action_cancel()
        if cancel_pickings:
            cancel_pickings.action_cancel()
        return res

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
        in the winner warehouse, attach inter-warehouse resupply
        procurements as ``move_orig_ids`` of the customer pick move.

        Unlike the previous implementation, we do NOT split the customer
        pick move. The pick move keeps its original demand (e.g. 25 uds)
        and the partial reservation already done by ``super()._action_confirm()``
        (e.g. 20 uds). The procurements we trigger here only cover the
        missing quantity (5 uds) and target the consolidation location;
        the inter-warehouse arrivals attach themselves as ``move_orig_ids``
        of the customer pick move so the latter switches to ``waiting``
        until the chain is complete and then auto-reserves the missing
        quantity from the consolidation location.

        Result: a single line per product in the customer pick, with
        demand = total order qty and quantity gradually rising from
        ``reserved`` to ``demand`` as the consolidation completes.
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
            reserved = pick_move.quantity
            demand = pick_move.product_uom_qty
            if float_compare(demand, reserved, precision_digits=precision) <= 0:
                continue
            missing = demand - reserved
            self._pc_chain_resupply_for_move(line, pick_move, missing, winner, others)

        # Force the customer pick, the downstream customer delivery and the
        # consolidation receipt to behave all-or-nothing. Without this:
        #   - the customer pick / delivery could ship the MTS portion alone
        #     before the MTO arrived,
        #   - the consolidation receipt at the winner (the IN picking that
        #     lands on the Consolidation location) could be validated as
        #     soon as the first inter-warehouse transfer arrives, leaving
        #     the rest of the moves of that same picking in waiting.
        downstream_pickings = self.env['stock.picking']
        for pkg in affected_pickings:
            downstream_pickings |= pkg.move_ids.move_dest_ids.picking_id
        # Consolidation receipts: pickings landing on the winner's
        # consolidation location (or any descendant of it).
        consolidation_pickings = self.env['stock.picking']
        consol_loc = winner.pc_consolidation_location_id or winner.lot_stock_id
        if consol_loc:
            consolidation_pickings = self.env['stock.picking'].search([
                ('origin', '=', self.name),
                ('location_dest_id', 'child_of', consol_loc.id),
            ])
        all_to_lock = affected_pickings | downstream_pickings | consolidation_pickings
        if all_to_lock:
            all_to_lock.write({'move_type': 'one'})
            all_to_lock._compute_state()

    def _pc_winner_pick_move_for(self, line, winner):
        """The first move in the customer pick that originates from the
        winner's stock location for this sale line."""
        return line.move_ids.filtered(
            lambda m: m.location_id == winner.lot_stock_id
            and m.state not in ('done', 'cancel')
        )[:1]

    def _pc_chain_resupply_for_move(self, line, pick_move, missing, winner, others):
        """Run resupply procurements that feed ``winner.lot_stock_id`` and
        chain (via ``move_dest_ids``) to ``pick_move`` so the customer pick
        waits until the inter-warehouse stock has arrived."""
        self.ensure_one()
        if not self.stock_reference_ids:
            self.env['stock.reference'].create(line._prepare_reference_vals())
        Procurement = self.env['stock.rule'].Procurement
        precision = self.env['decimal.precision'].precision_get('Product Unit')
        date_deadline = self.commitment_date or fields.Datetime.now()
        procurements = []

        # Procurement target: the warehouse-specific consolidation location
        # if configured, else the default stock location (legacy behaviour).
        consolidation_location = winner.pc_consolidation_location_id or winner.lot_stock_id
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
                'move_dest_ids': pick_move,
            }
            procurements.append(Procurement(
                line.product_id,
                take,
                line.product_uom_id,
                consolidation_location,
                _("Consolidation for %s", self.name),
                self.name,
                self.company_id,
                values,
            ))
            missing -= take

        if procurements:
            self.env['stock.rule'].run(procurements)
        # The pick_move is already confirmed (super did it). After attaching
        # the upstream chain via move_orig_ids, force a re-evaluation of its
        # state so it switches from ``assigned`` (with partial reservation)
        # to ``partially_available`` until the chain delivers the rest.
        pick_move._recompute_state()

    @staticmethod
    def _pc_resupply_route(supplied_wh, supplier_wh):
        return supplied_wh.resupply_route_ids.filtered(
            lambda r: r.supplier_wh_id == supplier_wh and r.active
        )[:1]
