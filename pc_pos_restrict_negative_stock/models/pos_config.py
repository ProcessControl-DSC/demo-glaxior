from collections import defaultdict

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    restrict_negative_stock = fields.Boolean(
        string="Restrict Negative Stock",
        help="Prevents the sale of storable products when the available quantity "
             "in the PoS warehouse cannot cover the ticket.",
    )
    allow_negative_stock_override = fields.Boolean(
        string="Allow PIN Override",
        help="When enabled, an authorised employee can force the sale by entering their PIN.",
    )
    negative_stock_authorizer_ids = fields.Many2many(
        "hr.employee",
        "pos_config_negative_stock_authorizer_rel",
        "config_id",
        "employee_id",
        string="Negative Stock Authorisers",
        help="Employees allowed to authorise a sale below available stock by PIN.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        for field in ("restrict_negative_stock", "allow_negative_stock_override"):
            if field not in params:
                params.append(field)
        return params

    def get_available_stock_for_pos(self, product_ids):
        """Return {product_id: available_qty} for the PoS warehouse.

        - In real-time stock mode, returns ``qty_available`` scoped to the PoS warehouse.
        - In close-of-session mode, subtracts the quantities already sold in paid orders
          of every open session that shares the same warehouse. This prevents overselling
          between cashiers working on the same stock.
        Non-storable products are omitted from the result.
        """
        self.ensure_one()
        if not self.warehouse_id or not product_ids:
            return {}

        products = self.env["product.product"].browse(product_ids).exists().filtered("is_storable")
        if not products:
            return {}

        warehouse = self.warehouse_id
        result = {}
        for product in products.with_context(warehouse_id=warehouse.id):
            result[product.id] = product.qty_available

        if self._uses_closing_stock_mode():
            sold = self._get_open_sessions_sold_qty(products, warehouse)
            for product_id, qty in sold.items():
                if product_id in result:
                    result[product_id] -= qty

        return result

    def _uses_closing_stock_mode(self):
        self.ensure_one()
        return self.company_id.point_of_sale_update_stock_quantities == "closing"

    def _get_open_sessions_sold_qty(self, products, warehouse):
        """Sum of qty in paid/done/invoiced lines across open close-of-session PoS."""
        sessions = self.env["pos.session"].search([
            ("state", "in", ("opened", "opening_control")),
            ("config_id.warehouse_id", "=", warehouse.id),
            ("update_stock_at_closing", "=", True),
        ])
        if not sessions:
            return {}
        lines = self.env["pos.order.line"].search([
            ("order_id.session_id", "in", sessions.ids),
            ("order_id.state", "in", ("paid", "done", "invoiced")),
            ("product_id", "in", products.ids),
        ])
        sold = defaultdict(float)
        for line in lines:
            sold[line.product_id.id] += line.qty
        return sold

    def check_negative_stock_pin(self, pin):
        """Return the ``hr.employee`` id whose PIN matches and is in the authoriser list, else False."""
        self.ensure_one()
        if not self.allow_negative_stock_override or not pin:
            return False
        employee = self.negative_stock_authorizer_ids.filtered(lambda e: e.pin and e.pin == pin)
        return employee[:1].id or False
