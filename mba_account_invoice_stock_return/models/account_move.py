# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class AccountMove(models.Model):
    _inherit = "account.move"

    stock_return_picking_id = fields.Many2one(
        "stock.picking",
        string="Devolución de Inventario",
        copy=False,
        readonly=True,
        help="Albarán de recepción generado para el retorno de productos a bodega.",
    )
    stock_delivery_picking_id = fields.Many2one(
        "stock.picking",
        string="Despacho de Inventario",
        copy=False,
        readonly=True,
        help="Albarán de salida generado para el despacho de productos desde bodega.",
    )
    has_sale_order = fields.Boolean(
        string="Viene de Orden de Venta",
        compute="_compute_has_sale_order",
        store=True,
    )
    reconciliation_alert_type = fields.Selection(
        [
            ("auto_reconciled", "Cruzada Automáticamente"),
            ("credit_available", "Saldo a Favor del Cliente"),
            ("pending_reconcile", "Pendiente de Cruzar"),
        ],
        string="Alerta de Conciliación",
        compute="_compute_reconciliation_alert",
    )
    credit_note_count = fields.Integer(
        string="Cantidad de Notas de Crédito",
        compute="_compute_credit_note_count",
    )

    @api.depends("reversal_move_ids")
    def _compute_credit_note_count(self):
        for move in self:
            move.credit_note_count = len(move.reversal_move_ids)

    def action_view_credit_notes(self):
        """Abre las Notas de Crédito vinculadas a esta Factura."""
        self.ensure_one()
        action = {
            "name": _("Notas de Crédito de %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "context": {"default_move_type": "out_refund"},
        }
        if len(self.reversal_move_ids) == 1:
            action["views"] = [(False, "form")]
            action["res_id"] = self.reversal_move_ids[0].id
        else:
            action["views"] = [(False, "list"), (False, "form")]
            action["domain"] = [("id", "in", self.reversal_move_ids.ids)]
        return action

    @api.depends("invoice_line_ids.sale_line_ids", "invoice_origin")
    def _compute_has_sale_order(self):
        for move in self:
            has_so = bool(
                move.invoice_line_ids.sale_line_ids
                or (move.invoice_origin and self.env["sale.order"].search_count([("name", "=", move.invoice_origin)]))
            )
            move.has_sale_order = has_so

    @api.depends("state", "move_type", "reversed_entry_id", "payment_state", "amount_residual")
    def _compute_reconciliation_alert(self):
        for move in self:
            alert = False
            if move.move_type == "out_refund" and move.state == "posted" and move.reversed_entry_id:
                if move.payment_state in ("paid", "in_payment", "reversed"):
                    alert = "auto_reconciled"
                elif move.reversed_entry_id.payment_state in ("paid", "in_payment"):
                    alert = "credit_available"
                elif move.reversed_entry_id.amount_residual > 0:
                    alert = "pending_reconcile"
            move.reconciliation_alert_type = alert

    def action_auto_reconcile_with_invoice(self):
        """Cruza automáticamente la Nota de Crédito con su Factura Original."""
        self.ensure_one()
        if self.move_type == "out_refund" and self.reversed_entry_id:
            lines = (self.line_ids + self.reversed_entry_id.line_ids).filtered(
                lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled
            )
            if lines:
                lines.reconcile()

    def action_post(self):
        """Al publicar la Nota de Crédito, auto-concilia con la factura si tiene saldo pendiente."""
        res = super().action_post()
        for move in self:
            if move.move_type == "out_refund" and move.reversed_entry_id and move.reversed_entry_id.amount_residual > 0:
                try:
                    move.action_auto_reconcile_with_invoice()
                except Exception:
                    pass
        return res

    def action_open_stock_return_wizard(self):
        """Abre el wizard de devolución de inventario para Nota de Crédito o Factura Anulada."""
        self.ensure_one()
        ctx = {}
        if self.move_type == "out_refund":
            ctx["default_credit_note_id"] = self.id
        else:
            ctx["default_invoice_id"] = self.id
        return {
            "name": _("Devolución de Productos a Bodega"),
            "type": "ir.actions.act_window",
            "res_model": "account.invoice.stock.return.wizard",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }

    def action_open_stock_delivery_wizard(self):
        """Abre el wizard de despacho de inventario para Facturas directas."""
        self.ensure_one()
        return {
            "name": _("Despacho de Productos desde Bodega"),
            "type": "ir.actions.act_window",
            "res_model": "account.invoice.stock.delivery.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_invoice_id": self.id,
            },
        }

    def action_open_stock_exchange_wizard(self):
        """Abre el wizard de intercambio de mercancía para Facturas."""
        self.ensure_one()
        return {
            "name": _("Exchange / Cambio de Mercancía"),
            "type": "ir.actions.act_window",
            "res_model": "account.invoice.stock.exchange.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_invoice_id": self.id,
            },
        }
