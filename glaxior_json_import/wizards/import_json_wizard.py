import base64
import json

from odoo import api, fields, models
from odoo.exceptions import UserError


class GlaxiorImportJsonWizard(models.TransientModel):
    _name = 'glaxior.import.json.wizard'
    _description = 'Importar JSON MyGlaxior'

    json_file = fields.Binary(
        string="Fichero JSON",
        required=True,
        help="Selecciona el fichero JSON generado por el configurador MyGlaxior.",
    )
    json_filename = fields.Char(
        string="Nombre fichero",
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Cliente",
        required=True,
        domain=[('customer_rank', '>', 0)],
    )
    price_unit = fields.Float(
        string="Precio unitario",
        help="Precio del sistema configurado. Si el configurador lo incluye en el JSON, "
             "se completará automáticamente.",
    )
    notes = fields.Text(
        string="Notas",
        help="Notas adicionales que se añadirán al pedido.",
    )

    # Campos de previsualización (readonly, calculados al cargar el JSON)
    preview_type = fields.Char(string="Tipo sistema", readonly=True)
    preview_structure = fields.Char(string="Nº Estructura", readonly=True)
    preview_address = fields.Char(string="Dirección", readonly=True)
    preview_openings = fields.Integer(string="Aperturas", readonly=True)
    preview_panels = fields.Integer(string="Paneles cristal", readonly=True)
    preview_glass_thickness = fields.Char(string="Espesor vidrio", readonly=True)
    preview_profile_color = fields.Char(string="Color perfiles", readonly=True)

    @api.onchange('json_file')
    def _onchange_json_file(self):
        """Parsea el JSON al cargarlo y muestra la previsualización."""
        if not self.json_file:
            self.preview_type = False
            self.preview_structure = False
            self.preview_address = False
            self.preview_openings = 0
            self.preview_panels = 0
            self.preview_glass_thickness = False
            self.preview_profile_color = False
            return

        data = self._parse_json(self.json_file)
        self.preview_type = data.get('product_type_display', '')
        self.preview_structure = data.get('structure_number', '')
        self.preview_address = data.get('address', '')
        self.preview_openings = data.get('openings', 0)
        self.preview_panels = data.get('total_panels', 0)
        self.preview_glass_thickness = data.get('glass_thickness', '')
        self.preview_profile_color = data.get('profile_color', '')

    def _parse_json(self, json_b64):
        """Parsea el JSON y extrae los datos relevantes."""
        try:
            raw = base64.b64decode(json_b64).decode('utf-8')
            content = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise UserError(f"El fichero no es un JSON válido: {e}")

        # Detectar tipo de sistema (clave raíz: GXR, GXS, etc.)
        product_type_key = None
        header = None
        for key in content:
            if key.startswith('GX'):
                product_type_key = key
                header = content[key]
                break

        if not header:
            raise UserError(
                "El JSON no contiene una clave de sistema válida (GXR, GXS, ...). "
                "Verifica que es un fichero del configurador MyGlaxior."
            )

        # Extraer datos de cabecera
        structure_number = header.get('structure_number', '')
        country = header.get('country', '')
        product_type = header.get('product_type', '')
        address = header.get('address', '')
        line = header.get('line', '')
        floor = header.get('floor', '')
        unit = header.get('Unit', '')
        num_openings = header.get('product_openings', 0)

        # Construir dirección completa
        address_parts = [p for p in [address, f"Planta {floor}" if floor else '', f"Unidad {unit}" if unit else '', f"Línea {line}" if line else ''] if p]
        full_address = ', '.join(address_parts)

        # Recorrer aperturas para extraer paneles, espesores y colores
        total_panels = 0
        glass_thicknesses = set()
        profile_colors = set()
        openings_detail = []

        for opening in header.get('Product_opening', []):
            panels = opening.get('glass_panel_amount', 0)
            total_panels += panels
            thickness = opening.get('glass_thickness')
            if thickness:
                glass_thicknesses.add(f"{thickness}mm")
            upper_color = opening.get('upper_profile_color', '')
            lower_color = opening.get('lower_profile_color', '')
            if upper_color:
                profile_colors.add(upper_color)
            if lower_color and lower_color != upper_color:
                profile_colors.add(lower_color)

            # Detalle por apertura
            sides = opening.get('side', [])
            opening_info = {
                'panels': panels,
                'sides': len(sides),
                'thickness': thickness,
                'dimensions': [],
            }
            for side in sides:
                length = side.get('length', 0)
                height = side.get('height', 0)
                opening_info['dimensions'].append(f"{length}x{height}mm")
            openings_detail.append(opening_info)

        # Mapeo tipo sistema
        type_display_map = {
            'GXR': 'GXR — Abatible',
            'GXS': 'GXS — Corredera',
        }

        return {
            'raw_json': raw,
            'content': content,
            'product_type_key': product_type_key,
            'product_type_display': type_display_map.get(product_type_key, product_type_key),
            'structure_number': structure_number,
            'country': country,
            'product_type': product_type,
            'address': full_address,
            'openings': num_openings,
            'total_panels': total_panels,
            'glass_thickness': ', '.join(sorted(glass_thicknesses)) or 'N/D',
            'profile_color': ', '.join(sorted(profile_colors)) or 'N/D',
            'openings_detail': openings_detail,
        }

    def _build_description(self, data):
        """Construye la descripción de la línea de pedido."""
        lines = []
        lines.append(f"Sistema Acristalamiento {data['product_type_key']}")
        lines.append(f"Estructura: {data['structure_number']}")
        if data['address']:
            lines.append(f"Dirección instalación: {data['address']}")
        lines.append(f"Aperturas: {data['openings']} | Paneles: {data['total_panels']}")
        lines.append(f"Vidrio: {data['glass_thickness']} | Perfiles: {data['profile_color']}")

        # Detalle por apertura
        for i, opening in enumerate(data.get('openings_detail', []), 1):
            dims = ' + '.join(opening['dimensions'])
            lines.append(f"  Apertura {i}: {opening['panels']} paneles, {opening['sides']} lados ({dims})")

        return '\n'.join(lines)

    def action_import(self):
        """Importa el JSON y crea el pedido de venta."""
        self.ensure_one()

        if not self.json_file:
            raise UserError("Selecciona un fichero JSON.")

        data = self._parse_json(self.json_file)

        # Buscar producto genérico para sistemas configurados
        product = self.env.ref(
            'glaxior_json_import.product_sistema_acristalamiento',
            raise_if_not_found=False,
        )
        if not product:
            product = self.env['product.product'].search(
                [('default_code', '=', 'GLAXIOR-CONF')], limit=1,
            )

        # Crear el pedido de venta
        description = self._build_description(data)
        order_line_vals = {
            'name': description,
            'product_uom_qty': 1,
            'price_unit': self.price_unit,
        }
        if product:
            order_line_vals['product_id'] = product.id

        so_vals = {
            'partner_id': self.partner_id.id,
            'glaxior_structure_number': data.get('structure_number', ''),
            'glaxior_product_type': data.get('product_type_key') if data.get('product_type_key') in ('GXR', 'GXS') else False,
            'glaxior_install_address': data.get('address', ''),
            'glaxior_openings': data.get('openings', 0),
            'glaxior_total_panels': data.get('total_panels', 0),
            'glaxior_json_filename': self.json_filename or 'configuracion.json',
            'order_line': [(0, 0, order_line_vals)],
        }
        if self.notes:
            so_vals['note'] = self.notes

        sale_order = self.env['sale.order'].create(so_vals)

        # Adjuntar el JSON original al pedido
        self.env['ir.attachment'].create({
            'name': self.json_filename or 'configuracion_myglaxior.json',
            'type': 'binary',
            'datas': self.json_file,
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'mimetype': 'application/json',
        })

        # Abrir el pedido creado
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
            'target': 'current',
        }
