# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrderPaymentOtherDescWizard(models.TransientModel):
    _name = "sale.order.payment.other.desc.wizard"
    _description = "Descripción de forma de pago (99 - Otro)"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Orden de venta",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    dgi_payment_method_other_desc = fields.Char(
        string="Descripción de forma de pago",
        required=True,
        help="Indique el método de pago (obligatorio DGI cuando la forma de pago es 99 - Otro).",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list or [])
        active_id = self.env.context.get("active_id")
        if active_id and "sale_order_id" in (fields_list or []):
            res["sale_order_id"] = active_id
        return res

    def action_create_invoice(self):
        """Crear factura directamente pasando la descripción de la forma de pago por contexto."""
        self.ensure_one()
        order = self.sale_order_id
        if order.invoice_status != "to invoice":
            return order.action_view_invoice()

        invoice = order.with_context(
            dgi_payment_method_other_desc=(self.dgi_payment_method_other_desc or "").strip()
        )._create_invoices(final=True)

        if not invoice:
            raise UserError(_("No hay nada que facturar o la factura ya fue creada."))

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': invoice[0].id,
            'target': 'current',
        }
