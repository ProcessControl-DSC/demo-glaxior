from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPosRestrictNegativeStock(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        cls.warehouse_a = cls.env["stock.warehouse"].create({
            "name": "WH-A Test",
            "code": "WHAT",
            "company_id": cls.company.id,
        })
        cls.warehouse_b = cls.env["stock.warehouse"].create({
            "name": "WH-B Test",
            "code": "WHBT",
            "company_id": cls.company.id,
        })

        cls.product_storable = cls.env["product.product"].create({
            "name": "Storable Test",
            "type": "consu",
            "is_storable": True,
            "available_in_pos": True,
        })
        cls.product_consumable = cls.env["product.product"].create({
            "name": "Consumable Test",
            "type": "consu",
            "is_storable": False,
            "available_in_pos": True,
        })

        cls._put_in_stock(cls.product_storable, cls.warehouse_a, 4)
        cls._put_in_stock(cls.product_storable, cls.warehouse_b, 10)

        cls.pos_config_a = cls.env["pos.config"].create({
            "name": "POS A Test",
            "warehouse_id": cls.warehouse_a.id,
            "restrict_negative_stock": True,
        })
        cls.pos_config_b = cls.env["pos.config"].create({
            "name": "POS B Test",
            "warehouse_id": cls.warehouse_b.id,
            "restrict_negative_stock": True,
        })

        cls.employee_authorizer = cls.env["hr.employee"].create({
            "name": "Authorizer Test",
            "pin": "1234",
        })
        cls.employee_regular = cls.env["hr.employee"].create({
            "name": "Regular Test",
            "pin": "9999",
        })

    @classmethod
    def _put_in_stock(cls, product, warehouse, qty):
        cls.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": product.id,
            "location_id": warehouse.lot_stock_id.id,
            "inventory_quantity": qty,
        }).action_apply_inventory()

    def _open_session(self, config):
        session = self.env["pos.session"].create({
            "config_id": config.id,
            "user_id": self.env.user.id,
            "update_stock_at_closing": self.company.point_of_sale_update_stock_quantities == "closing",
        })
        session.state = "opened"
        return session

    def _make_paid_order(self, session, product, qty):
        order = self.env["pos.order"].create({
            "session_id": session.id,
            "company_id": session.company_id.id,
            "lines": [(0, 0, {
                "name": "L1",
                "product_id": product.id,
                "qty": qty,
                "price_unit": 10.0,
                "price_subtotal": 10.0 * qty,
                "price_subtotal_incl": 10.0 * qty,
            })],
            "amount_tax": 0.0,
            "amount_total": 10.0 * qty,
            "amount_paid": 10.0 * qty,
            "amount_return": 0.0,
        })
        order.state = "paid"
        return order

    # ---- get_available_stock_for_pos ----

    def test_stock_uses_pos_warehouse(self):
        """El RPC devuelve el stock del almacén de la config, no el global."""
        res = self.pos_config_a.get_available_stock_for_pos([self.product_storable.id])
        self.assertEqual(res.get(self.product_storable.id), 4)

        res_b = self.pos_config_b.get_available_stock_for_pos([self.product_storable.id])
        self.assertEqual(res_b.get(self.product_storable.id), 10)

    def test_stock_ignores_non_storable_products(self):
        """Productos sin seguimiento de inventario no se devuelven."""
        res = self.pos_config_a.get_available_stock_for_pos([self.product_consumable.id])
        self.assertNotIn(self.product_consumable.id, res)

    def test_stock_empty_list_returns_empty(self):
        self.assertEqual(self.pos_config_a.get_available_stock_for_pos([]), {})

    def test_realtime_mode_does_not_discount_open_sessions(self):
        """En modo tiempo real, no descontamos ventas locales (ya las descuenta el picking)."""
        self.company.point_of_sale_update_stock_quantities = "real"
        session = self._open_session(self.pos_config_a)
        self.assertFalse(session.update_stock_at_closing)

        self._make_paid_order(session, self.product_storable, 2)

        res = self.pos_config_a.get_available_stock_for_pos([self.product_storable.id])
        self.assertEqual(
            res.get(self.product_storable.id), 4,
            "En real-time el descuento lo hace el servidor (stock.quant), no el módulo.",
        )

    def test_closing_mode_discounts_open_session_sales(self):
        """En modo al cierre, las ventas pagadas de sesiones abiertas del mismo almacén se descuentan."""
        self.company.point_of_sale_update_stock_quantities = "closing"
        session = self._open_session(self.pos_config_a)
        self.assertTrue(session.update_stock_at_closing)

        self._make_paid_order(session, self.product_storable, 3)

        res = self.pos_config_a.get_available_stock_for_pos([self.product_storable.id])
        self.assertEqual(
            res.get(self.product_storable.id), 1,
            "4 disponible - 3 vendido en sesión abierta = 1.",
        )

    def test_closing_mode_does_not_discount_other_warehouse_sessions(self):
        """Ventas en otra PoS con almacén distinto no deben afectar."""
        self.company.point_of_sale_update_stock_quantities = "closing"
        self._open_session(self.pos_config_a)
        session_b = self._open_session(self.pos_config_b)
        self._make_paid_order(session_b, self.product_storable, 5)

        res_a = self.pos_config_a.get_available_stock_for_pos([self.product_storable.id])
        self.assertEqual(
            res_a.get(self.product_storable.id), 4,
            "Ventas en warehouse B no deben descontar del disponible de warehouse A.",
        )

    # ---- check_negative_stock_pin ----

    def test_pin_returns_employee_when_valid_and_authorized(self):
        self.pos_config_a.write({
            "allow_negative_stock_override": True,
            "negative_stock_authorizer_ids": [(6, 0, [self.employee_authorizer.id])],
        })
        self.assertEqual(
            self.pos_config_a.check_negative_stock_pin("1234"),
            self.employee_authorizer.id,
        )

    def test_pin_returns_false_for_non_authorizer(self):
        """Un empleado con PIN válido pero no en la lista no autoriza."""
        self.pos_config_a.write({
            "allow_negative_stock_override": True,
            "negative_stock_authorizer_ids": [(6, 0, [self.employee_authorizer.id])],
        })
        self.assertFalse(self.pos_config_a.check_negative_stock_pin("9999"))

    def test_pin_returns_false_when_override_disabled(self):
        self.pos_config_a.write({
            "allow_negative_stock_override": False,
            "negative_stock_authorizer_ids": [(6, 0, [self.employee_authorizer.id])],
        })
        self.assertFalse(self.pos_config_a.check_negative_stock_pin("1234"))

    def test_pin_returns_false_for_empty_pin(self):
        self.pos_config_a.write({
            "allow_negative_stock_override": True,
            "negative_stock_authorizer_ids": [(6, 0, [self.employee_authorizer.id])],
        })
        self.assertFalse(self.pos_config_a.check_negative_stock_pin(""))
        self.assertFalse(self.pos_config_a.check_negative_stock_pin(False))
