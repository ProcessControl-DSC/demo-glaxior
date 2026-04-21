/** @odoo-module **/

import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class NegativeStockAuthDialog extends Component {
    static template = "pc_pos_restrict_negative_stock.NegativeStockAuthDialog";
    static components = { Dialog };
    static props = {
        body: String,
        validatePin: Function,
        onAuthorize: Function,
        onCancel: Function,
        close: Function,
    };

    setup() {
        this.state = useState({
            pin: "",
            error: "",
            pending: false,
        });
        this.inputRef = useRef("pinInput");
        onMounted(() => {
            if (this.inputRef.el) {
                this.inputRef.el.focus();
            }
        });
    }

    get title() {
        return _t("Authoriser PIN required");
    }

    async onConfirm() {
        if (this.state.pending) {
            return;
        }
        const pin = (this.state.pin || "").trim();
        if (!pin) {
            this.state.error = _t("Enter the authoriser PIN.");
            return;
        }
        this.state.pending = true;
        this.state.error = "";
        try {
            const employeeId = await this.props.validatePin(pin);
            if (employeeId) {
                this.props.onAuthorize(employeeId);
                this.props.close();
                return;
            }
            this.state.error = _t("PIN not valid for an authorised employee.");
            this.state.pin = "";
        } finally {
            this.state.pending = false;
        }
    }

    onCancel() {
        this.props.onCancel();
        this.props.close();
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            this.onConfirm();
        }
    }
}
