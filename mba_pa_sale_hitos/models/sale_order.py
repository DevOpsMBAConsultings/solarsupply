# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dgi_downpayment_count = fields.Integer(
        string="Cantidad Hitos",
        compute="_compute_dgi_downpayment_stats",
    )
    dgi_downpayment_invoiced = fields.Monetary(
        string="Monto Hitos",
        compute="_compute_dgi_downpayment_stats",
        currency_field="currency_id",
    )
    dgi_downpayment_percentage = fields.Float(
        string="% Hitos Facturados",
        compute="_compute_dgi_downpayment_stats",
    )
    dgi_downpayment_invoice_ids = fields.Many2many(
        comodel_name="account.move",
        string="Facturas de Hitos",
        compute="_compute_dgi_downpayment_stats",
    )
    dgi_amount_residual = fields.Monetary(
        string="Saldo Pendiente por Facturar",
        compute="_compute_dgi_downpayment_stats",
        currency_field="currency_id",
    )
    dgi_has_final_invoice = fields.Boolean(
        string="Tiene Factura Final",
        compute="_compute_dgi_downpayment_stats",
    )

    @api.depends('order_line.is_downpayment', 'order_line.price_subtotal', 'invoice_ids.state', 'invoice_ids.amount_total')
    def _compute_dgi_downpayment_stats(self):
        for order in self:
            dp_lines = order.order_line.filtered(lambda l: l.is_downpayment and not l.display_type)
            total = order.amount_total or 0.0
            
            # Detectar si ya existe factura final (con líneas de producto reales)
            final_invs = order.invoice_ids.filtered(
                lambda i: i.state in ('draft', 'posted')
                and i.move_type == 'out_invoice'
                and any(line.sale_line_ids and not line.sale_line_ids.is_downpayment for line in i.invoice_line_ids)
            )

            # Buscar facturas de anticipos vinculadas a esta orden
            dp_invoices = order.invoice_ids.filtered(
                lambda i: i.state in ('draft', 'posted') 
                and i.move_type == 'out_invoice' 
                and any(line.name and ('anticipo' in line.name.lower() or 'down payment' in line.name.lower()) for line in i.invoice_line_ids)
            )

            count = len(dp_invoices) or len(dp_lines)
            invoiced_amt = sum(dp_invoices.mapped('amount_total')) if dp_invoices else sum(abs(l.price_total) for l in dp_lines)
            pct = (invoiced_amt / total * 100.0) if total else 0.0

            order.dgi_downpayment_count = count
            order.dgi_downpayment_invoiced = invoiced_amt
            order.dgi_downpayment_percentage = round(pct, 2)
            order.dgi_downpayment_invoice_ids = dp_invoices
            order.dgi_amount_residual = max(total - invoiced_amt, 0.0)
            order.dgi_has_final_invoice = bool(final_invs)

    def action_create_invoice_advance(self):
        """
        Abre el wizard de anticipos / hitos de facturación (Down Payments),
        validando previamente el estado DGI del cliente.
        """
        self.ensure_one()
        partner = self.partner_id
        partner_valid = partner.l10n_pa_is_dgi_validated if partner else True
        if partner and not partner_valid and partner.parent_id:
            partner_valid = partner.parent_id.l10n_pa_is_dgi_validated

        if not partner_valid and not self.env.context.get('skip_dgi_warning_wizard'):
            return {
                'name': _("Cliente no Validado con DGI"),
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order.dgi.warning.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_sale_order_id': self.id,
                    'default_partner_name': partner.name,
                }
            }

        return {
            'name': _('Crear Anticipo / Hito de Facturación'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.advance.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
            }
        }

    def action_view_downpayments(self):
        self.ensure_one()
        dp_invoices = self.invoice_ids.filtered(
            lambda i: i.move_type == 'out_invoice' 
            and any(line.name and ('anticipo' in line.name.lower() or 'down payment' in line.name.lower()) for line in i.invoice_line_ids)
        )
        action = {
            'name': _('Hitos / Anticipos Facturados (%s)', self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', dp_invoices.ids)],
            'context': {'default_move_type': 'out_invoice'},
        }
        if len(dp_invoices) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = dp_invoices.id
        return action

    def action_create_final_invoice(self):
        """
        Crea la factura final de liquidación de la orden, desglosando
        los productos reales y deduciendo los anticipos/hitos previos.
        """
        self.ensure_one()
        partner = self.partner_id
        partner_valid = partner.l10n_pa_is_dgi_validated if partner else True
        if partner and not partner_valid and partner.parent_id:
            partner_valid = partner.parent_id.l10n_pa_is_dgi_validated

        if not partner_valid and not self.env.context.get('skip_dgi_warning_wizard'):
            return {
                'name': _("Cliente no Validado con DGI"),
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order.dgi.warning.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_sale_order_id': self.id,
                    'default_partner_name': partner.name,
                }
            }

        invoices = self._create_invoices(final=True)
        if not invoices:
            raise UserError(_("No se pudo generar la factura final o ya no hay líneas pendientes de entrega."))

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': invoices[0].id,
            'target': 'current',
        }
