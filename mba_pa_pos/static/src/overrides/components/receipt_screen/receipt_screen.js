/** @odoo-module **/
// -*- coding: utf-8 -*-
//
// Panamá - POS Facturación Electrónica DGI (MBA Consultings)
//
// Cuando el POS no usa impresora fiscal, cada orden genera una factura DGI
// real (ver payment_screen.js de este mismo módulo y pos_order.py). Odoo ya
// descarga ese PDF automáticamente al validar (PaymentScreen._finalizeValidation
// -> invoiceService.downloadPdf), pero aquí se desactiva esa descarga silenciosa
// en payment_screen.js para en su lugar mostrar el PDF de la Factura Electrónica
// DGI embebido en línea dentro de la pantalla de recibo (ReceiptScreen).
// Además, se mantiene un botón "Imprimir Factura" para abrir/imprimir el PDF
// en una pestaña independiente.

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { useTrackedAsync } from "@point_of_sale/app/utils/hooks";
import { useState, onWillStart } from "@odoo/owl";

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        this.invoiceService = useService("account_move");
        this.action = useService("action");
        this.doPrintInvoice = useTrackedAsync(() => this.printInvoice());
        this.dgiInvoiceState = useState({
            attachmentId: null,
            loading: false,
            error: false,
        });
        onWillStart(async () => {
            if (this.hasDgiInvoice) {
                await this.loadDgiInvoicePdf();
            }
        });
    },

    /**
     * True solo cuando la orden generó una factura DGI real (to_invoice y
     * account_move existentes). Con impresora fiscal, o si algo falló al
     * generar la factura, este botón permanece oculto.
     */
    get hasDgiInvoice() {
        return Boolean(
            this.currentOrder.is_to_invoice() && this.currentOrder.raw.account_move
        );
    },

    /**
     * Devuelve la URL en línea (/web/content/...) para visualizar el PDF de la
     * factura electrónica dentro del iframe en la pantalla de recibo.
     */
    get dgiInvoiceUrl() {
        if (!this.dgiInvoiceState.attachmentId) {
            return "";
        }
        return `/web/content/${this.dgiInvoiceState.attachmentId}?download=false`;
    },

    /**
     * Consulta el attachmentId (invoice_pdf_report_id) del account.move
     * generado para la orden POS actual.
     */
    async loadDgiInvoicePdf() {
        if (!this.hasDgiInvoice) {
            return;
        }
        this.dgiInvoiceState.loading = true;
        this.dgiInvoiceState.error = false;
        try {
            const accountMoveId = this.currentOrder.raw.account_move;
            const [move] = await this.pos.data.call("account.move", "read", [
                [accountMoveId],
                ["invoice_pdf_report_id"],
            ]);
            const attachmentId =
                move && move.invoice_pdf_report_id && move.invoice_pdf_report_id[0];
            if (attachmentId) {
                this.dgiInvoiceState.attachmentId = attachmentId;
            } else {
                this.dgiInvoiceState.error = true;
            }
        } catch (e) {
            this.dgiInvoiceState.error = true;
        } finally {
            this.dgiInvoiceState.loading = false;
        }
    },

    /**
     * Abre el PDF de la factura para VISUALIZARLO en el navegador (como el
     * adjunto en el chatter del backend), en vez de forzar una descarga.
     *
     * 'invoiceService.downloadPdf()' llama a account.move.action_invoice_
     * download_pdf(), que sirve el PDF vía /account/download_invoice_
     * documents/<id>/pdf. Esa ruta SIEMPRE fuerza "Guardar como" (respuesta
     * con Content-Disposition: attachment) — por eso, aunque el PDF fuera
     * el correcto, al cajero le aparecía un diálogo de guardar archivo en
     * vez de ver la factura en pantalla.
     *
     * En cambio, /web/content/<attachment_id>?download=false (el mismo
     * mecanismo que usa el chatter para previsualizar adjuntos) sirve el
     * PDF inline (as_attachment=False, ver addons/web/controllers/
     * binary.py) y el navegador lo muestra directo con su visor nativo.
     *
     * Se usa 'invoice_pdf_report_id' (campo estándar de account.move, no
     * algo propio de un PAC en particular) para no acoplar este módulo a
     * un conector específico (HKA, Digifact, etc.): cualquiera que sea el
     * PAC activo, ese campo ya apunta al PDF real una vez la factura fue
     * aceptada, gracias al invalidate_recordset que hace cada conector.
     */
    async printInvoice() {
        if (!this.hasDgiInvoice) {
            return;
        }
        let attachmentId = this.dgiInvoiceState.attachmentId;
        if (!attachmentId) {
            await this.loadDgiInvoicePdf();
            attachmentId = this.dgiInvoiceState.attachmentId;
        }

        if (!attachmentId) {
            // Respaldo: todavía no hay adjunto propio (caso raro/edge); se
            // recurre al flujo estándar, que al menos genera y descarga algo.
            const accountMoveId = this.currentOrder.raw.account_move;
            await this.invoiceService.downloadPdf(accountMoveId);
            return;
        }

        this.action.doAction({
            type: "ir.actions.act_url",
            url: `/web/content/${attachmentId}?download=false`,
            target: "new",
        });
    },
});

