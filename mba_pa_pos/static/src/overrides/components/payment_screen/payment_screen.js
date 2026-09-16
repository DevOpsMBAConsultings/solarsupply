/** @odoo-module **/
// -*- coding: utf-8 -*-
//
// Panamá - POS Facturación Electrónica DGI (MBA Consultings)
//

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { DgiNumberPopup } from "@mba_pa_pos/overrides/components/payment_screen/dgi_number_popup";

patch(PaymentScreen.prototype, {
    onMounted() {
        super.onMounted();
        if (!this.pos.config.l10n_pa_fiscal_printer) {
            this.currentOrder.set_to_invoice(true);
        }
    },

    toggleIsToInvoice() {
        if (this.pos.config.l10n_pa_fiscal_printer) {
            super.toggleIsToInvoice();
        }
    },

    shouldDownloadInvoice() {
        if (!this.pos.config.l10n_pa_fiscal_printer) {
            return false;
        }
        return super.shouldDownloadInvoice();
    },

    async _isOrderValid(isForceValidate) {
        const isValid = await super._isOrderValid(...arguments);
        if (!isValid) {
            return false;
        }

        if (!this.pos.config.l10n_pa_fiscal_printer) {
            // Si la orden ya fue confirmada con un número DGI, no volver a preguntar
            if (this.currentOrder.l10n_pa_custom_numero_df) {
                return true;
            }

            // Guard para evitar apertura duplicada por doble clic o llamadas paralelas
            if (this.dgi_popup_open) {
                return false;
            }
            this.dgi_popup_open = true;

            let suggestedNum = "0000000001";
            try {
                if (this.pos.data && this.pos.data.orm) {
                    const res = await this.pos.data.orm.call(
                        "pos.order",
                        "get_next_dgi_number",
                        [this.pos.config.id]
                    );
                    if (res) {
                        suggestedNum = String(res);
                    }
                }
            } catch (e) {
                console.warn("No se pudo obtener el consecutivo DGI:", e);
            }

            let payload;
            try {
                payload = await makeAwaitable(this.dialog, DgiNumberPopup, {
                    startingValue: suggestedNum,
                });
            } finally {
                this.dgi_popup_open = false;
            }

            if (payload !== undefined && payload !== false && payload !== null) {
                let confirmedNum = String(payload).replace(/\D/g, "");
                if (confirmedNum) {
                    confirmedNum = confirmedNum.slice(-10).padStart(10, "0");
                    this.currentOrder.l10n_pa_custom_numero_df = confirmedNum;
                }
            } else {
                return false;
            }
        }
        return true;
    },
});
