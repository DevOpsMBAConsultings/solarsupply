# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrderCreditOtherDueDateWizard(models.TransientModel):
    _name = "sale.order.credit.other.due.date.wizard"
    _description = "Fecha de vencimiento (Crédito otro)"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Orden de venta",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    dgi_plazo_due_date = fields.Date(
        string="Fecha de vencimiento",
        required=True,
        help="Para facturación DGI con Crédito/Plazo «Otro» es obligatoria. Se usará en la factura al crearla.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list or [])
        active_id = self.env.context.get("active_id")
        if active_id and "sale_order_id" in (fields_list or []):
            res["sale_order_id"] = active_id
        return res

    def action_create_invoice(self):
        """Crear factura directamente pasando la fecha de vencimiento por contexto."""
        self.ensure_one()
        order = self.sale_order_id
        if order.invoice_status != "to invoice":
            return order.action_view_invoice()

        invoice = order.with_context(
            dgi_plazo_due_date=self.dgi_plazo_due_date
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
