from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    glaxior_structure_number = fields.Char(
        string="Nº Estructura MyGlaxior",
        help="Número de estructura del configurador MyGlaxior (structure_number del JSON).",
        copy=False,
    )
    glaxior_product_type = fields.Selection(
        string="Tipo Sistema",
        selection=[
            ('GXR', 'GXR — Abatible'),
            ('GXS', 'GXS — Corredera'),
        ],
        help="Tipo de sistema de acristalamiento configurado.",
        copy=False,
    )
    glaxior_install_address = fields.Char(
        string="Dirección Instalación",
        help="Dirección donde se instalará el sistema (del JSON).",
        copy=False,
    )
    glaxior_openings = fields.Integer(
        string="Nº Aperturas",
        help="Número total de aperturas del sistema configurado.",
        copy=False,
    )
    glaxior_total_panels = fields.Integer(
        string="Nº Paneles Cristal",
        help="Número total de paneles de cristal en el sistema.",
        copy=False,
    )
    glaxior_json_filename = fields.Char(
        string="Fichero JSON",
        copy=False,
    )
