from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    negative_stock_authorizer_id = fields.Many2one(
        "hr.employee",
        string="Negative Stock Authoriser",
        readonly=True,
        help="Employee who authorised the sale below available stock by entering their PIN.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        if "negative_stock_authorizer_id" not in params:
            params.append("negative_stock_authorizer_id")
        return params
