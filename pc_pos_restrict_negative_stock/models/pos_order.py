from odoo import fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    negative_stock_authorizer_id = fields.Many2one(
        "hr.employee",
        string="Negative Stock Authoriser",
        readonly=True,
        help="Employee who authorised the sale below available stock by entering their PIN.",
    )
