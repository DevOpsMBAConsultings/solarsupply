# -*- coding: utf-8 -*-
from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError
from markupsafe import Markup


class AccountInvoiceStockExchangeWizard(models.TransientModel):
    _name = "account.invoice.stock.exchange.wizard"
    _description = "Asistente de Exchange / Cambio de Mercancía"

    invoice_id = fields.Many2one(
        "account.move",
        string="Factura de Cliente",
        required=True,
        readonly=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Bodega",
        required=True,
        compute="_compute_warehouse",
        readonly=False,
        store=True,
    )
    return_line_ids = fields.One2many(
        "account.invoice.stock.exchange.return.line",
        "wizard_id",
        string="Productos que Regresa el Cliente (Entrada)",
        compute="_compute_return_lines",
        precompute=True,
        readonly=False,
        store=True,
    )
    delivery_line_ids = fields.One2many(
        "account.invoice.stock.exchange.delivery.line",
        "wizard_id",
        string="Nuevos Productos que se Entregan (Salida)",
    )
    total_return_amount = fields.Monetary(
        string="Total Devuelto",
        currency_field="currency_id",
        compute="_compute_totals",
    )
    total_delivery_amount = fields.Monetary(
        string="Total Entregado",
        currency_field="currency_id",
        compute="_compute_totals",
    )
    difference_amount = fields.Monetary(
        string="Diferencia",
        currency_field="currency_id",
        compute="_compute_totals",
        help="Positivo: Cliente debe pagar diferencia. Negativo: Saldo a favor del cliente.",
    )
    currency_id = fields.Many2one(
        related="invoice_id.currency_id",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get("active_id") and self.env.context.get("active_model") == "account.move":
            res["invoice_id"] = self.env.context.get("active_id")
        elif self.env.context.get("default_invoice_id"):
            res["invoice_id"] = self.env.context.get("default_invoice_id")
        return res

    @api.depends("invoice_id")
    def _compute_warehouse(self):
        for wizard in self:
            wizard.warehouse_id = self.env["stock.warehouse"].search(
                [("company_id", "=", wizard.invoice_id.company_id.id or self.env.company.id)], limit=1
            )

    @api.depends("invoice_id")
    def _compute_return_lines(self):
        for wizard in self:
            lines = [Command.clear()]
            if wizard.invoice_id:
                line_fields = list(self.env["account.invoice.stock.exchange.return.line"]._fields)
                line_default_tmpl = self.env["account.invoice.stock.exchange.return.line"].default_get(line_fields)
                for line in wizard.invoice_id.invoice_line_ids:
                    if line.product_id and line.display_type == "product":
                        qty = abs(line.quantity)
                        if qty > 0:
                            line_data = dict(line_default_tmpl)
                            line_data.update({
                                "product_id": line.product_id.id,
                                "quantity": qty,
                                "price_unit": line.price_unit,
                                "uom_id": line.product_uom_id.id or line.product_id.uom_id.id,
                            })
                            lines.append(Command.create(line_data))
            wizard.return_line_ids = lines

    @api.depends("return_line_ids.subtotal", "delivery_line_ids.subtotal")
    def _compute_totals(self):
        for wizard in self:
            tot_ret = sum(l.subtotal for l in wizard.return_line_ids)
            tot_del = sum(l.subtotal for l in wizard.delivery_line_ids)
            wizard.total_return_amount = tot_ret
            wizard.total_delivery_amount = tot_del
            wizard.difference_amount = tot_del - tot_ret

    def action_confirm_exchange(self):
        """Procesa simultáneamente la entrada de lo devuelto y la salida de lo nuevo."""
        self.ensure_one()
        active_returns = self.return_line_ids.filtered(lambda l: l.quantity > 0)
        active_deliveries = self.delivery_line_ids.filtered(lambda l: l.quantity > 0)

        if not active_returns and not active_deliveries:
            raise UserError(_("Debe especificar al menos un producto a devolver o a entregar."))

        fac_name = self.invoice_id.name or "N/A"
        partner = self.invoice_id.partner_id
        partner_location = partner.property_stock_customer or self.env.ref("stock.stock_location_customers")

        pickings_created = []

        # 1. Crear Recepción (Entrada a Bodega de lo que regresa el cliente)
        if active_returns:
            in_type = self.warehouse_id.in_type_id
            dest_location = in_type.default_location_dest_id or self.warehouse_id.lot_stock_id
            in_picking = self.env["stock.picking"].create({
                "partner_id": partner.id,
                "picking_type_id": in_type.id,
                "location_id": partner_location.id,
                "location_dest_id": dest_location.id,
                "origin": f"EXCHANGE (Retorno) - FAC: {fac_name}",
                "note": f"Intercambio de Mercancía (Entrada de producto devuelto) - Factura {fac_name}",
            })
            in_moves = []
            for l in active_returns:
                in_moves.append((0, 0, {
                    "name": l.product_id.display_name,
                    "product_id": l.product_id.id,
                    "product_uom_qty": l.quantity,
                    "quantity": l.quantity,
                    "product_uom": l.uom_id.id,
                    "picking_id": in_picking.id,
                    "location_id": partner_location.id,
                    "location_dest_id": dest_location.id,
                }))
            in_picking.move_ids = in_moves
            in_picking.action_confirm()
            in_picking.action_assign()
            for move in in_picking.move_ids:
                move.quantity = move.product_uom_qty
            in_picking.with_context(skip_sanity_check=True).button_validate()
            pickings_created.append(in_picking)

        # 2. Crear Entrega (Salida de Bodega de los nuevos productos)
        if active_deliveries:
            out_type = self.warehouse_id.out_type_id
            src_location = out_type.default_location_src_id or self.warehouse_id.lot_stock_id
            out_picking = self.env["stock.picking"].create({
                "partner_id": partner.id,
                "picking_type_id": out_type.id,
                "location_id": src_location.id,
                "location_dest_id": partner_location.id,
                "origin": f"EXCHANGE (Entrega) - FAC: {fac_name}",
                "note": f"Intercambio de Mercancía (Salida de nuevo producto) - Factura {fac_name}",
            })
            out_moves = []
            for l in active_deliveries:
                out_moves.append((0, 0, {
                    "name": l.product_id.display_name,
                    "product_id": l.product_id.id,
                    "product_uom_qty": l.quantity,
                    "quantity": l.quantity,
                    "product_uom": l.uom_id.id,
                    "picking_id": out_picking.id,
                    "location_id": src_location.id,
                    "location_dest_id": partner_location.id,
                }))
            out_picking.move_ids = out_moves
            out_picking.action_confirm()
            out_picking.action_assign()
            for move in out_picking.move_ids:
                move.quantity = move.product_uom_qty
            out_picking.with_context(skip_sanity_check=True).button_validate()
            pickings_created.append(out_picking)

        # Registrar nota formateada con estilo visual en el chatter
        diff_color = "#198038" if self.difference_amount == 0 else ("#002d9c" if self.difference_amount > 0 else "#fa4d56")
        html = f"""
        <div style="border-left: 4px solid #1192e8; padding-left: 12px; margin: 4px 0;">
            <h5 style="color: #012749; margin-bottom: 8px;">🔄 <b>Exchange / Cambio de Mercancía</b></h5>
        """
        if active_returns:
            in_link = in_picking._get_html_link()
            html += f"""
            <div style="margin-bottom: 6px;">
                <span style="background: #e5f6ff; color: #0043ce; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">📥 ENTRADA / DEVOLUCIÓN</span>
                <span style="margin-left: 6px;">Albarán: <b>{in_link}</b></span>
                <ul style="margin: 4px 0 6px 18px; padding: 0;">
            """
            for l in active_returns:
                html += f"<li><b>{l.product_id.display_name}</b> — Cant: {l.quantity} {l.uom_id.name} (B/. {l.subtotal:.2f})</li>"
            html += "</ul></div>"

        if active_deliveries:
            out_link = out_picking._get_html_link()
            html += f"""
            <div style="margin-bottom: 6px;">
                <span style="background: #defbe6; color: #0e6027; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">📤 SALIDA / NUEVA ENTREGA</span>
                <span style="margin-left: 6px;">Albarán: <b>{out_link}</b></span>
                <ul style="margin: 4px 0 6px 18px; padding: 0;">
            """
            for l in active_deliveries:
                html += f"<li><b>{l.product_id.display_name}</b> — Cant: {l.quantity} {l.uom_id.name} (B/. {l.subtotal:.2f})</li>"
            html += "</ul></div>"

        html += f"""
            <div style="margin-top: 6px; font-size: 13px;">
                <b>Diferencia Económica:</b> <span style="font-weight: bold; color: {diff_color};">B/. {self.difference_amount:.2f}</span>
            </div>
        </div>
        """

        self.invoice_id.message_post(body=Markup(html))

        if len(pickings_created) == 1:
            return {
                "name": _("Albarán de Intercambio - %s") % pickings_created[0].name,
                "type": "ir.actions.act_window",
                "res_model": "stock.picking",
                "res_id": pickings_created[0].id,
                "view_mode": "form",
                "target": "current",
            }
        else:
            return {
                "name": _("Albaranes de Intercambio (Entrada y Salida)"),
                "type": "ir.actions.act_window",
                "res_model": "stock.picking",
                "domain": [("id", "in", [p.id for p in pickings_created])],
                "view_mode": "list,form",
                "target": "current",
            }


class AccountInvoiceStockExchangeReturnLine(models.TransientModel):
    _name = "account.invoice.stock.exchange.return.line"
    _description = "Línea de Devolución en Exchange"

    wizard_id = fields.Many2one("account.invoice.stock.exchange.wizard", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Producto", required=True)
    quantity = fields.Float(string="Cantidad", required=True, default=1.0)
    price_unit = fields.Float(string="Precio Unitario", required=True, default=0.0)
    subtotal = fields.Monetary(string="Subtotal", compute="_compute_subtotal", currency_field="currency_id")
    uom_id = fields.Many2one("uom.uom", string="Unidad de Medida", required=True)
    currency_id = fields.Many2one(related="wizard_id.currency_id")

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit


class AccountInvoiceStockExchangeDeliveryLine(models.TransientModel):
    _name = "account.invoice.stock.exchange.delivery.line"
    _description = "Línea de Entrega en Exchange"

    wizard_id = fields.Many2one("account.invoice.stock.exchange.wizard", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Nuevo Producto", required=True)
    quantity = fields.Float(string="Cantidad", required=True, default=1.0)
    price_unit = fields.Float(string="Precio Unitario", required=True, default=0.0)
    subtotal = fields.Monetary(string="Subtotal", compute="_compute_subtotal", currency_field="currency_id")
    uom_id = fields.Many2one("uom.uom", string="Unidad de Medida", required=True)
    currency_id = fields.Many2one(related="wizard_id.currency_id")

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.price_unit = self.product_id.lst_price
            self.uom_id = self.product_id.uom_id.id

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit
