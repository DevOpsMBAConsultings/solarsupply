# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = "account.move"

    dgi_milestone_percentage = fields.Float(
        string="% Hito",
        compute="_compute_dgi_milestone_percentage",
        help="Porcentaje que representa este anticipo sobre el total de la orden de venta.",
    )

    @api.depends('amount_total', 'invoice_line_ids.sale_line_ids.order_id.amount_total')
    def _compute_dgi_milestone_percentage(self):
        for move in self:
            sale_orders = move.invoice_line_ids.sale_line_ids.order_id
            order = sale_orders[:1]
            if order and order.amount_total:
                pct = (move.amount_total / order.amount_total) * 100.0
                move.dgi_milestone_percentage = round(pct, 2)
            else:
                move.dgi_milestone_percentage = 0.0
