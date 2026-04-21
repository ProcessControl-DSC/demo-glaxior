from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_restrict_negative_stock = fields.Boolean(
        related="pos_config_id.restrict_negative_stock",
        readonly=False,
    )
    pos_allow_negative_stock_override = fields.Boolean(
        related="pos_config_id.allow_negative_stock_override",
        readonly=False,
    )
    pos_negative_stock_authorizer_ids = fields.Many2many(
        related="pos_config_id.negative_stock_authorizer_ids",
        readonly=False,
    )
