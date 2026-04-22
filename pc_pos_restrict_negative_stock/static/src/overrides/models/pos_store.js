/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { NegativeStockAuthDialog } from "@pc_pos_restrict_negative_stock/overrides/components/auth_dialog/auth_dialog";

patch(PosStore.prototype, {
    async _pcFetchAvailability(productIds) {
        if (!productIds.length) {
            return {};
        }
        return await this.data.call(
            "pos.config",
            "get_available_stock_for_pos",
            [[this.config.id], productIds]
        );
    },

    /**
     * Returns [{ product, available, demand }] for the whole order.
     */
    async _pcCheckOrder(order) {
        if (!this.config.restrict_negative_stock) {
            return [];
        }
        const demand = {};
        for (const line of order.getOrderlines()) {
            const product = line.product_id;
            if (!product || !product.is_storable || line.qty <= 0) {
                continue;
            }
            demand[product.id] = (demand[product.id] || 0) + line.qty;
        }
        const productIds = Object.keys(demand).map(Number);
        const availability = await this._pcFetchAvailability(productIds);
        const violations = [];
        for (const productId of productIds) {
            const available = availability[productId] ?? 0;
            if (demand[productId] > available) {
                violations.push({
                    product: this.models["product.product"].get(productId),
                    available,
                    demand: demand[productId],
                });
            }
        }
        return violations;
    },

    _pcFormatViolations(violations) {
        return violations
            .map((v) =>
                _t("%(name)s: available %(available)s, requested %(demand)s", {
                    name: v.product.display_name,
                    available: v.available,
                    demand: v.demand,
                })
            )
            .join("\n");
    },

    _pcAskAuthorizerPin(violations) {
        return new Promise((resolve) => {
            this.dialog.add(NegativeStockAuthDialog, {
                body: this._pcFormatViolations(violations),
                validatePin: async (pin) => {
                    return await this.data.call(
                        "pos.config",
                        "check_negative_stock_pin",
                        [[this.config.id], pin]
                    );
                },
                onAuthorize: (employeeId) => resolve(employeeId),
                onCancel: () => resolve(false),
            });
        });
    },

    _pcResolveProduct(vals) {
        if (vals.product_id) {
            return typeof vals.product_id === "number"
                ? this.models["product.product"].get(vals.product_id)
                : vals.product_id;
        }
        let template = vals.product_tmpl_id;
        if (typeof template === "number") {
            template = this.data.models["product.template"].get(template);
        }
        return template?.product_variant_ids?.[0];
    },

    async addLineToOrder(vals, order, opts = {}, configure = true) {
        if (!this.config.restrict_negative_stock) {
            return super.addLineToOrder(vals, order, opts, configure);
        }
        const product = this._pcResolveProduct(vals);
        if (!product || !product.is_storable) {
            return super.addLineToOrder(vals, order, opts, configure);
        }
        const requestedQty = vals.qty ?? (order.preset_id?.is_return ? -1 : 1);
        if (requestedQty <= 0) {
            return super.addLineToOrder(vals, order, opts, configure);
        }
        const previousQty = order
            .getOrderlines()
            .filter((l) => l.product_id?.id === product.id && l.qty > 0)
            .reduce((acc, l) => acc + l.qty, 0);
        const availability = await this._pcFetchAvailability([product.id]);
        const available = availability[product.id] ?? 0;
        const newDemand = previousQty + requestedQty;
        if (newDemand > available) {
            const violations = [{ product, available, demand: newDemand }];
            if (!this.config.allow_negative_stock_override) {
                this.dialog.add(AlertDialog, {
                    title: _t("Not enough stock"),
                    body: this._pcFormatViolations(violations),
                });
                return;
            }
            this.dialog.add(AlertDialog, {
                title: _t("Stock warning"),
                body:
                    this._pcFormatViolations(violations) +
                    "\n\n" +
                    _t("An authoriser PIN will be required at payment."),
            });
        }
        return super.addLineToOrder(vals, order, opts, configure);
    },

    async pay() {
        const order = this.getOrder();
        if (!order || !this.config.restrict_negative_stock) {
            return super.pay();
        }
        const violations = await this._pcCheckOrder(order);
        if (!violations.length) {
            order.negative_stock_authorizer_id = null;
            return super.pay();
        }
        if (!this.config.allow_negative_stock_override) {
            this.dialog.add(AlertDialog, {
                title: _t("Not enough stock"),
                body: this._pcFormatViolations(violations),
            });
            return;
        }
        const employeeId = await this._pcAskAuthorizerPin(violations);
        if (!employeeId) {
            return;
        }
        order.negative_stock_authorizer_id = { id: employeeId };
        return super.pay();
    },
});
