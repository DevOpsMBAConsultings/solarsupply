# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class SaleOrderDgiWarningWizard(models.TransientModel):
    _name = 'sale.order.dgi.warning.wizard'
    _description = 'Advertencia de Cliente no Validado con DGI al Crear Factura'

    sale_order_id = fields.Many2one('sale.order', string='Orden de Venta', required=True)
    partner_name = fields.Char(string='Nombre del Cliente')

    def action_confirm_create_invoice(self):
        self.ensure_one()
        return self.sale_order_id.with_context(skip_dgi_warning_wizard=True).action_create_invoice_direct()
