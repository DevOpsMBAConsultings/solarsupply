# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SaleOrderAdvancePaymentWizard(models.TransientModel):
    _name = 'sale.order.advance.payment.wizard'
    _description = 'Crear Anticipo / Hito de Facturación'

    sale_order_id = fields.Many2one('sale.order', string='Orden de Venta', required=True)
    currency_id = fields.Many2one(related='sale_order_id.currency_id')

    # Resumen Financiero del Pedido
    total_amount = fields.Monetary(string='Total de la Venta', compute='_compute_financial_summary')
    amount_invoiced = fields.Monetary(string='Ya Facturado', compute='_compute_financial_summary')
    invoiced_percentage = fields.Float(string='% Facturado', compute='_compute_financial_summary')
    amount_to_invoice = fields.Monetary(string='Saldo Pendiente', compute='_compute_financial_summary')
    pending_percentage = fields.Float(string='% Pendiente', compute='_compute_financial_summary')

    # Entrada del Hito
    advance_type = fields.Selection([
        ('percentage', 'Anticipo (porcentaje)'),
        ('fixed', 'Anticipo (importe fijo)'),
    ], string='Tipo de Anticipo', default='percentage', required=True)

    amount_percentage = fields.Float(string='Porcentaje a facturar (%)', default=0.0)
    amount_fixed = fields.Monetary(string='Importe fijo a facturar', currency_field='currency_id')

    # Simulación del Hito Actual
    simulated_amount = fields.Monetary(string='Monto de este Hito', compute='_compute_simulation')
    simulated_remaining_amount = fields.Monetary(string='Saldo posterior al hito', compute='_compute_simulation')
    simulated_remaining_percentage = fields.Float(string='% Restante posterior', compute='_compute_simulation')

    @api.depends('sale_order_id')
    def _compute_financial_summary(self):
        for wiz in self:
            order = wiz.sale_order_id
            total = order.amount_total or 0.0
            invoiced = sum(order._origin.mapped('amount_invoiced')) if hasattr(order, 'amount_invoiced') else 0.0
            # Si no está amount_invoiced nativo, sumar facturas no canceladas
            if not invoiced and order.invoice_ids:
                invoiced = sum(
                    inv.amount_total for inv in order.invoice_ids.filtered(lambda i: i.state in ('draft', 'posted') and i.move_type == 'out_invoice')
                )
            pending = max(total - invoiced, 0.0)
            inv_pct = (invoiced / total * 100.0) if total else 0.0
            pend_pct = (pending / total * 100.0) if total else 0.0

            wiz.total_amount = total
            wiz.amount_invoiced = invoiced
            wiz.invoiced_percentage = round(inv_pct, 2)
            wiz.amount_to_invoice = pending
            wiz.pending_percentage = round(pend_pct, 2)

    @api.depends('sale_order_id', 'advance_type', 'amount_percentage', 'amount_fixed')
    def _compute_simulation(self):
        for wiz in self:
            total = wiz.sale_order_id.amount_total or 0.0
            invoiced = wiz.amount_invoiced or 0.0
            current_milestone = 0.0

            if wiz.advance_type == 'percentage':
                current_milestone = total * (wiz.amount_percentage / 100.0)
            else:
                current_milestone = wiz.amount_fixed

            remaining = total - (invoiced + current_milestone)
            remaining_pct = (remaining / total * 100.0) if total else 0.0

            wiz.simulated_amount = current_milestone
            wiz.simulated_remaining_amount = remaining
            wiz.simulated_remaining_percentage = round(remaining_pct, 2)

    def action_create_advance_invoice(self):
        self.ensure_one()
        order = self.sale_order_id
        if self.advance_type == 'percentage':
            if self.amount_percentage <= 0 or self.amount_percentage > 100:
                raise UserError(_("El porcentaje debe ser mayor a 0 y menor o igual a 100."))
            advance_inv = self.env['sale.advance.payment.inv'].with_context(
                active_id=order.id, active_ids=order.ids
            ).create({
                'advance_payment_method': 'percentage',
                'amount': self.amount_percentage,
                'sale_order_ids': [(6, 0, order.ids)],
            })
        else:
            if self.amount_fixed <= 0 or self.amount_fixed > order.amount_total:
                raise UserError(_("El importe fijo debe ser mayor a 0 y no puede exceder el total de la orden."))
            advance_inv = self.env['sale.advance.payment.inv'].with_context(
                active_id=order.id, active_ids=order.ids
            ).create({
                'advance_payment_method': 'fixed',
                'fixed_amount': self.amount_fixed,
                'sale_order_ids': [(6, 0, order.ids)],
            })

        return advance_inv.create_invoices()
