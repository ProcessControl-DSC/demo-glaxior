from odoo import api, models


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        for field in ("update_stock_at_closing",):
            if field not in params:
                params.append(field)
        return params
