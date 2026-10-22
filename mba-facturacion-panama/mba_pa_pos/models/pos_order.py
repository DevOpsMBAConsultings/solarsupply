# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    # ─── Campos DGI en la orden POS ─────────────────────────────────────────
    l10n_pa_dgi_payment_method_id = fields.Many2one(
        "dgi.payment.method",
        string="Método de Pago (DGI)",
        help="Método de pago DGI para la factura electrónica generada desde POS.",
    )

    l10n_pa_dgi_payment_term_type = fields.Selection(
        selection=[
            ("contado", "Contado"),
            ("credito", "Crédito/Plazo"),
        ],
        string="Plazos (DGI)",
        default="contado",
        help="Tipo de plazo para la factura electrónica DGI.",
    )

    l10n_pa_dgi_payment_notes = fields.Text(
        string="Notas complementarias (DGI)",
        help="Notas complementarias para la factura electrónica (AI17 InfoInteres, máx. 200 caracteres en DGI).",
    )

    l10n_pa_is_fiscal_printer = fields.Boolean(
        string="Usa Impresora Fiscal",
        related="config_id.l10n_pa_fiscal_printer",
        store=True,
        readonly=True,
        help="Indica si este POS usa impresora fiscal (tomado de la configuración).",
    )

    l10n_pa_custom_numero_df = fields.Char(
        string="Número DF Personalizado POS",
        copy=False,
        help="Número fiscal DGI confirmado/editado por el cajero en el POS.",
    )

    @api.model
    def get_next_dgi_number(self, config_id=None):
        """Retorna el siguiente consecutivo fiscal DGI sugerido para la caja POS."""
        journal = False
        company = self.env.company
        if config_id:
            config = self.env['pos.config'].browse(config_id)
            if config.exists():
                journal = config.l10n_pa_pos_journal_id or config.invoice_journal_id
                company = config.company_id
        if not journal:
            journal = self.env['account.journal'].search([
                ('company_id', '=', company.id),
                ('type', '=', 'sale'),
            ], limit=1)
        if not journal:
            return "0000000001"

        dummy_move = self.env['account.move'].new({
            'company_id': company.id,
            'journal_id': journal.id,
            'move_type': 'out_invoice',
        })
        return dummy_move._pa_next_numero()

    # ─── Auto-rellenar datos DGI desde el partner ──────────────────────────

    @api.onchange("partner_id")
    def _onchange_partner_id_dgi_pos(self):
        """Rellena los campos DGI desde el partner seleccionado."""
        if self.partner_id:
            partner = self.partner_id
            # Método de pago DGI
            if hasattr(partner, "dgi_payment_method_id") and partner.dgi_payment_method_id:
                self.l10n_pa_dgi_payment_method_id = partner.dgi_payment_method_id
            # Tipo de plazo DGI
            if hasattr(partner, "dgi_payment_term_type") and partner.dgi_payment_term_type:
                self.l10n_pa_dgi_payment_term_type = partner.dgi_payment_term_type
            # Notas complementarias
            if hasattr(partner, "dgi_payment_notes") and partner.dgi_payment_notes:
                self.l10n_pa_dgi_payment_notes = partner.dgi_payment_notes

    # ─── Sobrescritura de _prepare_invoice_vals ─────────────────────────────

    def _prepare_invoice_vals(self):
        """
        Extiende los valores de la factura para incluir los campos DGI
        cuando el POS NO usa impresora fiscal.
        """
        vals = super()._prepare_invoice_vals()

        # Solo inyectar campos DGI si NO usa impresora fiscal
        if self.config_id.l10n_pa_fiscal_printer:
            return vals

        # Tipo de documento DGI desde la config del POS
        if self.config_id.l10n_pa_dgi_document_type_id:
            vals["dgi_document_type_id"] = self.config_id.l10n_pa_dgi_document_type_id.id

        # Diario DGI específico para POS (si configurado)
        if self.config_id.l10n_pa_pos_journal_id:
            vals["journal_id"] = self.config_id.l10n_pa_pos_journal_id.id

        # Naturaleza y tipo de operación por defecto para ventas POS
        vals["dgi_naturaleza_operacion"] = "01"  # Venta
        vals["dgi_tipo_operacion"] = "1"  # Salida o Venta

        # Método de pago DGI: desde la orden POS o desde el partner
        if self.l10n_pa_dgi_payment_method_id:
            vals["dgi_payment_method_id"] = self.l10n_pa_dgi_payment_method_id.id
        elif self.partner_id and hasattr(self.partner_id, "dgi_payment_method_id") and self.partner_id.dgi_payment_method_id:
            vals["dgi_payment_method_id"] = self.partner_id.dgi_payment_method_id.id

        # Tipo de plazo
        if self.l10n_pa_dgi_payment_term_type:
            vals["dgi_payment_term_type"] = self.l10n_pa_dgi_payment_term_type

        # Notas complementarias
        notes = self.l10n_pa_dgi_payment_notes or ""
        if not notes and self.partner_id and hasattr(self.partner_id, "dgi_payment_notes"):
            notes = self.partner_id.dgi_payment_notes or ""
        if notes:
            vals["dgi_payment_notes"] = notes

        return vals

    # ─── Sobrescritura de _generate_pos_order_invoice ───────────────────────

    def _generate_pos_order_invoice(self):
        """
        Sobrescribe la generación de facturas POS para:
        - Sin impresora fiscal: genera la factura, le asigna número DGI,
          la envía al PAC sincrónicamente y la publica para que el cliente
          se la lleve en mostrador. Concilia los pagos inmediatamente.
        - Con impresora fiscal: flujo normal de Odoo (publica automáticamente).
        """
        # Separar órdenes según si usan impresora fiscal o no
        fiscal_printer_orders = self.filtered(lambda o: o.config_id.l10n_pa_fiscal_printer)
        dgi_orders = self - fiscal_printer_orders

        moves = self.env["account.move"]

        # ── Flujo normal para órdenes con impresora fiscal ──────────────────
        if fiscal_printer_orders:
            result = super(PosOrder, fiscal_printer_orders)._generate_pos_order_invoice()
            if result and result.get("res_id"):
                moves += self.env["account.move"].browse(result["res_id"])

        # ── Flujo DGI Síncrono para órdenes sin impresora fiscal ────────────
        for order in dgi_orders:
            if order.account_move:
                moves += order.account_move
                continue

            if not order.partner_id:
                raise UserError(_("Debe seleccionar un cliente para facturar la orden POS."))

            move_vals = order._prepare_invoice_vals()
            new_move = order._create_invoice(move_vals)

            order.write({"state": "invoiced"})
            
            # Fecha de factura por defecto si no tiene
            if not new_move.invoice_date:
                new_move.invoice_date = fields.Date.context_today(self)

            # 1. Reservar número fiscal (usar el personalizado si el cajero lo editó en POS)
            custom_num = (order.l10n_pa_custom_numero_df or "").strip()
            new_move._pa_reserve_numero(numero=custom_num or None)

            # 2. Enviar al PAC sincrónicamente (si falla, lanza UserError y hace rollback)
            new_move.action_l10n_pa_send_to_pac()

            # 3. Publicar la factura saltando el wizard
            new_move.sudo().with_company(order.company_id).with_context(
                skip_pac_send=True, **order._get_invoice_post_context()
            )._post()

            moves += new_move

            # 4. Aplicar pagos automáticamente
            payment_moves = order._apply_invoice_payments(order.session_id.state == 'closed')

            # Send and Print
            if self.env.context.get('generate_pdf', True):
                new_move.with_context(skip_invoice_sync=True)._generate_and_send()

            if order.session_id.state == 'closed':
                order._create_misc_reversal_move(payment_moves)

        if not moves:
            return {}

        return {
            "name": _("Factura Cliente"),
            "view_mode": "form",
            "view_id": self.env.ref("account.view_move_form").id,
            "res_model": "account.move",
            "context": "{'move_type':'out_invoice'}",
            "type": "ir.actions.act_window",
            "target": "current",
            "res_id": moves and moves.ids[0] or False,
        }

    @api.model
    def _order_fields(self, ui_order):
        fields_val = super()._order_fields(ui_order)
        if ui_order.get("l10n_pa_custom_numero_df"):
            fields_val["l10n_pa_custom_numero_df"] = ui_order["l10n_pa_custom_numero_df"]
        return fields_val

    @api.model
    def _process_order(self, order, draft, *args, **kwargs):
        if 'session_id' in order:
            session = self.env['pos.session'].browse(order['session_id'])
            if not session.config_id.l10n_pa_fiscal_printer:
                if not order.get('partner_id'):
                    raise UserError(_("Debes seleccionar un cliente para generar la Factura Electrónica DGI (Consumidor Final o Contribuyente)."))
                order['to_invoice'] = True
        return super(PosOrder, self)._process_order(order, draft, *args, **kwargs)
