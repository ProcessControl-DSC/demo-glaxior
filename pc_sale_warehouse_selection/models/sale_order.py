from collections import defaultdict

from odoo import _, api, fields, models
from odoo.tools.float_utils import float_compare


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
        of ``picking_ids`` — i.e. the inter-warehouse transfers launched to
        consolidate stock at the winner before the customer delivery."""
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

    def _action_confirm(self):
        for order in self:
            if order.warehouse_id.is_virtual_warehouse \
                    and order.warehouse_id.pc_child_warehouse_ids:
                order._pc_apply_warehouse_selection()
        return super()._action_confirm()

    def _pc_apply_warehouse_selection(self):
        self.ensure_one()
        virtual_wh = self.warehouse_id
        candidates = virtual_wh.pc_child_warehouse_ids
        eligible_lines = self.order_line.filtered(self._pc_is_line_eligible)
        total_demand = sum(eligible_lines.mapped('product_uom_qty'))
        if not candidates or not eligible_lines or total_demand <= 0.0:
            return

        coverage_by_wh = {}
        stock_by_wh_line = defaultdict(dict)
        for wh in candidates:
            covered = 0.0
            for line in eligible_lines:
                available = self._pc_get_available_stock(line.product_id, wh)
                stock_by_wh_line[wh.id][line.id] = available
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
            self._pc_launch_consolidation_procurements(
                winner, eligible_lines, stock_by_wh_line
            )

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

    def _pc_launch_consolidation_procurements(
        self, winner_wh, eligible_lines, stock_by_wh_line
    ):
        """For every line whose demand exceeds the winner's stock, launch
        resupply procurements from the other physical warehouses towards the
        winner, using the configured 'resupply from another warehouse' routes.

        In v19 the procurement engine is linked to the sale order through
        ``stock.reference`` records (the old ``procurement.group`` model was
        removed). The consolidation moves reuse the order's existing
        ``stock_reference_ids`` so everything stays attached to the sale.
        """
        self.ensure_one()
        other_whs = (
            self.pc_original_warehouse_id.pc_child_warehouse_ids - winner_wh
        )
        if not other_whs:
            return

        references = self._pc_ensure_stock_reference(eligible_lines)
        date_deadline = self.commitment_date or fields.Datetime.now()
        Procurement = self.env['stock.rule'].Procurement
        precision = self.env['decimal.precision'].precision_get('Product Unit')
        procurements = []

        for line in eligible_lines:
            in_winner = stock_by_wh_line[winner_wh.id][line.id]
            missing = line.product_uom_qty - in_winner
            if float_compare(missing, 0.0, precision_digits=precision) <= 0:
                continue
            for other in other_whs.sorted(lambda w: (w.sequence, w.id)):
                if float_compare(missing, 0.0, precision_digits=precision) <= 0:
                    break
                other_available = stock_by_wh_line[other.id][line.id]
                take = min(missing, other_available)
                if float_compare(take, 0.0, precision_digits=precision) <= 0:
                    continue
                route = self._pc_resupply_route(winner_wh, other)
                if not route:
                    continue
                values = {
                    'date_planned': date_deadline,
                    'date_deadline': date_deadline,
                    'warehouse_id': winner_wh,
                    'partner_id': self.partner_shipping_id.id,
                    'company_id': self.company_id,
                    'origin': self.name,
                    'reference_ids': references,
                    'route_ids': route,
                }
                procurements.append(Procurement(
                    line.product_id,
                    take,
                    line.product_uom_id,
                    winner_wh.lot_stock_id,
                    _("Consolidation for %s", self.name),
                    self.name,
                    self.company_id,
                    values,
                ))
                missing -= take

        if procurements:
            self.env['stock.rule'].run(procurements)

    def _pc_ensure_stock_reference(self, eligible_lines):
        """Return the sale order's stock.reference recordset, creating one
        from the first eligible line if none exists yet. In v19 the core
        builds a stock.reference lazily inside _action_launch_stock_rule;
        when we inject procurements before that, we must guarantee one
        exists."""
        self.ensure_one()
        references = self.stock_reference_ids
        if references:
            return references
        first_line = eligible_lines[:1]
        if not first_line:
            return self.env['stock.reference']
        return self.env['stock.reference'].create(
            first_line._prepare_reference_vals()
        )

    @staticmethod
    def _pc_resupply_route(supplied_wh, supplier_wh):
        return supplied_wh.resupply_route_ids.filtered(
            lambda r: r.supplier_wh_id == supplier_wh and r.active
        )[:1]
