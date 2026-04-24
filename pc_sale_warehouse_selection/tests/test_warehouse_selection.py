from odoo.addons.base.tests.common import DISABLED_MAIL_CONTEXT
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWarehouseSelection(TransactionCase):
    """Acceptance tests for pc_sale_warehouse_selection.

    Scenarios covered:
        CA01 -- Case A monoproduct, default winner covers 100%.
        CA02 -- Case A monoproduct, stock only in a non-default warehouse.
        CA03 -- Case A multiproduct, one warehouse covers every line.
        CA04 -- Case B, no warehouse covers alone, consolidation launched.
        CA06 -- Tie-break is deterministic (sequence, then id).
        CA07 -- No stock anywhere -> mode=no_stock, warehouse untouched.
        CA08 -- Virtual warehouse with only services -> logic skipped.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, **DISABLED_MAIL_CONTEXT))

        Warehouse = cls.env['stock.warehouse']
        Location = cls.env['stock.location']

        cls.partner = cls.env['res.partner'].create({'name': 'Test Customer'})

        cls.wh_mp = Warehouse.create({
            'name': 'Test Mata de Pera',
            'code': 'TMP',
            'reception_steps': 'one_step',
            'delivery_steps': 'pick_ship',
        })
        cls.wh_e = Warehouse.create({
            'name': 'Test Esplugas',
            'code': 'TE',
            'reception_steps': 'one_step',
            'delivery_steps': 'pick_ship',
        })
        cls.wh_t = Warehouse.create({
            'name': 'Test Terraza',
            'code': 'TT',
            'reception_steps': 'one_step',
            'delivery_steps': 'pick_ship',
        })
        cls.wh_virtual = Warehouse.create({
            'name': 'Test Virtual',
            'code': 'TVW',
            'reception_steps': 'one_step',
            'delivery_steps': 'ship_only',
        })

        # Reparent physical Stock locations under virtual's Stock (view).
        cls.wh_virtual.lot_stock_id.replenish_location = False
        for wh in (cls.wh_mp, cls.wh_e, cls.wh_t):
            wh.lot_stock_id.location_id = cls.wh_virtual.lot_stock_id
        cls.wh_virtual.lot_stock_id.usage = 'view'

        # Configure resupply among physical warehouses.
        cls.wh_mp.resupply_wh_ids = [(6, 0, [cls.wh_e.id, cls.wh_t.id])]
        cls.wh_e.resupply_wh_ids = [(6, 0, [cls.wh_mp.id, cls.wh_t.id])]
        cls.wh_t.resupply_wh_ids = [(6, 0, [cls.wh_mp.id, cls.wh_e.id])]

        # Mark virtual as aggregator and set children.
        cls.wh_virtual.write({
            'is_virtual_warehouse': True,
            'pc_child_warehouse_ids': [(6, 0, [
                cls.wh_mp.id, cls.wh_e.id, cls.wh_t.id,
            ])],
        })

        # Give a deterministic tie-break order: MP < E < T.
        cls.wh_mp.sequence = 10
        cls.wh_e.sequence = 20
        cls.wh_t.sequence = 30

        # Stockable product factory.
        cls.Product = cls.env['product.product']
        cls.Quant = cls.env['stock.quant']

    def _make_product(self, code):
        return self.Product.create({
            'name': code,
            'default_code': code,
            'type': 'consu',
            'is_storable': True,
            'list_price': 100.0,
        })

    def _set_stock(self, product, warehouse, qty):
        if qty <= 0:
            return
        quant = self.Quant.with_context(inventory_mode=True).create({
            'product_id': product.id,
            'location_id': warehouse.lot_stock_id.id,
            'inventory_quantity': qty,
        })
        quant.action_apply_inventory()

    def _make_sale(self, lines):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'warehouse_id': self.wh_virtual.id,
            'order_line': [
                (0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': qty,
                })
                for product, qty in lines
            ],
        })
        return order

    # ------------------------------------------------------------------ CA01
    def test_ca01_case_a_single_product_default_winner(self):
        product = self._make_product('T-CA01')
        self._set_stock(product, self.wh_mp, 50.0)
        order = self._make_sale([(product, 10.0)])

        order.action_confirm()

        self.assertEqual(order.pc_warehouse_selection_mode, 'case_a')
        self.assertFalse(order.pc_requires_consolidation)
        self.assertEqual(order.warehouse_id, self.wh_mp)
        self.assertEqual(order.pc_original_warehouse_id, self.wh_virtual)
        self.assertEqual(
            order.picking_ids.mapped('picking_type_id.warehouse_id'),
            self.wh_mp,
        )

    # ------------------------------------------------------------------ CA02
    def test_ca02_case_a_switch_to_non_default_warehouse(self):
        product = self._make_product('T-CA02')
        self._set_stock(product, self.wh_e, 100.0)
        order = self._make_sale([(product, 50.0)])

        order.action_confirm()

        self.assertEqual(order.pc_warehouse_selection_mode, 'case_a')
        self.assertEqual(order.warehouse_id, self.wh_e)

    # ------------------------------------------------------------------ CA03
    def test_ca03_case_a_multiproduct_one_warehouse_covers(self):
        product_a = self._make_product('T-CA03-A')
        product_b = self._make_product('T-CA03-B')
        # MP covers both lines fully; E does not.
        self._set_stock(product_a, self.wh_mp, 30.0)
        self._set_stock(product_a, self.wh_e, 5.0)
        self._set_stock(product_b, self.wh_mp, 40.0)
        self._set_stock(product_b, self.wh_e, 3.0)

        order = self._make_sale([(product_a, 20.0), (product_b, 15.0)])
        order.action_confirm()

        self.assertEqual(order.pc_warehouse_selection_mode, 'case_a')
        self.assertEqual(order.warehouse_id, self.wh_mp)

    # ------------------------------------------------------------------ CA04
    def test_ca04_case_b_consolidation(self):
        product = self._make_product('T-CA04')
        self._set_stock(product, self.wh_mp, 100.0)
        self._set_stock(product, self.wh_e, 102.0)
        self._set_stock(product, self.wh_t, 18.0)

        order = self._make_sale([(product, 220.0)])
        order.action_confirm()

        # Winner is the one that contributes most: Esplugas (102).
        self.assertEqual(order.warehouse_id, self.wh_e)
        self.assertEqual(order.pc_warehouse_selection_mode, 'case_b')
        self.assertTrue(order.pc_requires_consolidation)

        # Inter-warehouse pickings (consolidation transfers) must have been
        # created under the SO's origin. Check via the helper the smart
        # button uses, which also populates pc_consolidation_picking_count.
        consol_pickings = order._pc_get_consolidation_pickings()
        self.assertTrue(
            consol_pickings,
            "Expected inter-warehouse pickings created for consolidation",
        )
        self.assertEqual(
            order.pc_consolidation_picking_count,
            len(consol_pickings),
            "The smart button counter must match the helper result",
        )
        consol_moves = consol_pickings.mapped('move_ids').filtered(
            lambda m: m.product_id == product
        )
        self.assertTrue(consol_moves, "Expected inter-warehouse moves")
        total_consol_qty = sum(consol_moves.mapped('product_uom_qty'))
        # 100 (MP) + 18 (T) = 118 gets duplicated across pick+out+in legs of
        # each resupply route, so we just require >= 118 of flow through.
        self.assertGreaterEqual(
            total_consol_qty, 118.0,
            "Expected at least 118 units flowing through inter-warehouse moves",
        )

    # ------------------------------------------------------------------ CA06
    def test_ca06_tie_break_by_sequence(self):
        product = self._make_product('T-CA06')
        # Tie: MP and E both have exactly the same covering capacity.
        self._set_stock(product, self.wh_mp, 50.0)
        self._set_stock(product, self.wh_e, 50.0)

        order = self._make_sale([(product, 30.0)])
        order.action_confirm()

        self.assertEqual(order.pc_warehouse_selection_mode, 'case_a')
        # MP has sequence=10, E has sequence=20 => MP wins.
        self.assertEqual(order.warehouse_id, self.wh_mp)

    # ------------------------------------------------------------------ CA07
    def test_ca07_no_stock_anywhere_keeps_virtual(self):
        product = self._make_product('T-CA07')
        order = self._make_sale([(product, 5.0)])

        order.action_confirm()

        self.assertEqual(order.pc_warehouse_selection_mode, 'no_stock')
        self.assertEqual(order.warehouse_id, self.wh_virtual)

    # ------------------------------------------------------------------ CA08
    def test_ca08_service_lines_do_not_trigger_logic(self):
        service = self.env['product.product'].create({
            'name': 'T-CA08-service',
            'default_code': 'T-CA08',
            'type': 'service',
            'list_price': 50.0,
        })
        order = self._make_sale([(service, 1.0)])
        order.action_confirm()

        self.assertFalse(order.pc_warehouse_selection_mode)
        self.assertEqual(order.warehouse_id, self.wh_virtual)
