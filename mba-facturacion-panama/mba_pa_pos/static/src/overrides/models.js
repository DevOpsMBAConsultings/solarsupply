/** @odoo-module **/

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        if (this.l10n_pa_custom_numero_df) {
            json.l10n_pa_custom_numero_df = this.l10n_pa_custom_numero_df;
        }
        return json;
    },

    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        if (json.l10n_pa_custom_numero_df) {
            this.l10n_pa_custom_numero_df = json.l10n_pa_custom_numero_df;
        }
    },
});
