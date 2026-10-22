/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);

        if (this.props.resModel !== "sale.order") {
            return;
        }

        const actionService = useService("action");
        const orm = useService("orm");
        const state = useState({ lastPartnerId: null });

        // Función auxiliar para chequear validación DGI
        const checkDgiValidation = async (partnerId, partnerName) => {
            if (!partnerId) return;

            const partners = await orm.read(
                "res.partner",
                [partnerId],
                ["l10n_pa_is_dgi_validated", "parent_id", "name"]
            );

            if (!partners.length) return;
            const partner = partners[0];

            let isValid = partner.l10n_pa_is_dgi_validated;
            if (!isValid && partner.parent_id) {
                const parents = await orm.read(
                    "res.partner",
                    [partner.parent_id[0]],
                    ["l10n_pa_is_dgi_validated"]
                );
                if (parents.length) {
                    isValid = parents[0].l10n_pa_is_dgi_validated;
                }
            }

            if (!isValid) {
                await actionService.doAction({
                    name: "Cliente no Validado con DGI",
                    type: "ir.actions.act_window",
                    res_model: "partner.dgi.warning.wizard",
                    view_mode: "form",
                    views: [[false, "form"]],
                    target: "new",
                    context: {
                        default_partner_name: partnerName || partner.name,
                        default_message_type: "sale",
                    },
                });
            }
        };

        onMounted(async () => {
            const record = this.model.root;

            // Solo para registros nuevos (sin ID guardado)
            if (record.resId) {
                return;
            }

            // Chequear partner pre-cargado
            if (record.data.partner_id) {
                const partnerId = record.data.partner_id[0];
                state.lastPartnerId = partnerId;
                await checkDgiValidation(partnerId, record.data.partner_id[1]);
            }

            // Listener para cambios posteriores del partner
            const observer = setInterval(async () => {
                const currentPartnerId = record.data.partner_id ? record.data.partner_id[0] : null;

                // Si cambió el partner, ejecutar validación
                if (currentPartnerId !== state.lastPartnerId) {
                    state.lastPartnerId = currentPartnerId;
                    if (currentPartnerId) {
                        await checkDgiValidation(currentPartnerId, record.data.partner_id[1]);
                    }
                }
            }, 500);

            // Limpiar listener cuando se desmonta el componente
            this.env.bus.addEventListener("web_client:before_unload", () => {
                clearInterval(observer);
            });
        });
    },
});
