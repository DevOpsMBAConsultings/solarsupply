# -*- coding: utf-8 -*-
from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError
from markupsafe import Markup


class AccountInvoiceStockReturnWizard(models.TransientModel):
    _name = "account.invoice.stock.return.wizard"
    _description = "Asistente de Devolución de Mercancía a Bodega desde Facturación"

    credit_note_id = fields.Many2one(
        "account.move",
        string="Nota de Crédito",
        readonly=True,
    )
    invoice_id = fields.Many2one(
        "account.move",
        string="Factura de Cliente",
        readonly=True,
    )
    target_move_id = fields.Many2one(
        "account.move",
        string="Documento Origen",
        compute="_compute_target_move",
    )
    original_invoice_id = fields.Many2one(
        "account.move",
        string="Factura Original",
        compute="_compute_original_invoice",
        readonly=True,
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Despacho Original Detectado",
        compute="_compute_picking",
        readonly=True,
        help="Albarán de despacho de la venta original que será devuelto.",
    )
    has_picking = fields.Boolean(
        string="Tiene Despacho Previo",
        compute="_compute_picking",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Bodega de Recepción",
        required=True,
        compute="_compute_warehouse",
        readonly=False,
        store=True,
    )
    line_ids = fields.One2many(
        "account.invoice.stock.return.wizard.line",
        "wizard_id",
        string="Productos a Devolver",
        compute="_compute_lines",
        precompute=True,
        readonly=False,
        store=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get("active_id")
        active_model = self.env.context.get("active_model")
        if active_id and active_model == "account.move":
            move = self.env["account.move"].browse(active_id)
            if move.move_type == "out_refund":
                res["credit_note_id"] = move.id
            else:
                res["invoice_id"] = move.id
        elif self.env.context.get("default_credit_note_id"):
            res["credit_note_id"] = self.env.context.get("default_credit_note_id")
        elif self.env.context.get("default_invoice_id"):
            res["invoice_id"] = self.env.context.get("default_invoice_id")
        return res

    @api.depends("credit_note_id", "invoice_id")
    def _compute_target_move(self):
        for wizard in self:
            wizard.target_move_id = wizard.credit_note_id or wizard.invoice_id

    @api.depends("credit_note_id", "invoice_id")
    def _compute_original_invoice(self):
        for wizard in self:
            if wizard.credit_note_id:
                wizard.original_invoice_id = wizard.credit_note_id.reversed_entry_id or False
            else:
                wizard.original_invoice_id = wizard.invoice_id

    @api.depends("credit_note_id", "invoice_id", "original_invoice_id")
    def _compute_picking(self):
        for wizard in self:
            picking = False
            orig_inv = wizard.original_invoice_id
            if orig_inv:
                # 1. Si la factura tiene un despacho directo
                if orig_inv.stock_delivery_picking_id and orig_inv.stock_delivery_picking_id.state == "done":
                    picking = orig_inv.stock_delivery_picking_id
                else:
                    # 2. Buscar en órdenes de venta
                    sale_orders = orig_inv.invoice_line_ids.mapped("sale_line_ids.order_id")
                    if not sale_orders and orig_inv.invoice_origin:
                        sale_orders = self.env["sale.order"].search([("name", "=", orig_inv.invoice_origin)])

                    if sale_orders:
                        pickings = sale_orders.mapped("picking_ids").filtered(
                            lambda p: p.state == "done" and p.picking_type_code == "outgoing"
                        )
                        if pickings:
                            picking = pickings[0]

            wizard.picking_id = picking
            wizard.has_picking = bool(picking)

    @api.depends("target_move_id", "picking_id")
    def _compute_warehouse(self):
        for wizard in self:
            if wizard.picking_id:
                wizard.warehouse_id = wizard.picking_id.picking_type_id.warehouse_id
            else:
                wizard.warehouse_id = self.env["stock.warehouse"].search(
                    [("company_id", "=", wizard.target_move_id.company_id.id or self.env.company.id)], limit=1
                )

    @api.depends("target_move_id", "original_invoice_id")
    def _compute_lines(self):
        for wizard in self:
            lines = [Command.clear()]
            move_source = wizard.target_move_id or wizard.original_invoice_id
            if move_source:
                line_fields = list(self.env["account.invoice.stock.return.wizard.line"]._fields)
                line_default_tmpl = self.env["account.invoice.stock.return.wizard.line"].default_get(line_fields)
                for line in move_source.invoice_line_ids:
                    if line.product_id and line.display_type == "product":
                        qty = abs(line.quantity)
                        if qty > 0:
                            line_data = dict(line_default_tmpl)
                            line_data.update({
                                "product_id": line.product_id.id,
                                "quantity": qty,
                                "uom_id": line.product_uom_id.id or line.product_id.uom_id.id,
                            })
                            lines.append(Command.create(line_data))
            wizard.line_ids = lines

    def action_confirm_return(self):
        """Genera el movimiento de retorno a bodega y lo valida automáticamente a estado DONE."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No hay productos para registrar devolución a bodega."))

        doc_source = self.target_move_id
        is_refund = bool(self.credit_note_id)
        doc_label = "Nota de Crédito" if is_refund else "Factura Anulada"
        doc_name = doc_source.name or "N/A"
        fac_name = self.original_invoice_id.name or doc_source.invoice_origin or doc_name
        ref_notes = f"Retorno automático generado desde Facturación:\n{doc_label}: {doc_name}\nFactura: {fac_name}"

        # Escenario A: Existe picking original de venta -> Usar asistente nativo de stock_return_picking
        if self.picking_id:
            return_wizard = self.env["stock.return.picking"].with_context(
                active_id=self.picking_id.id,
                active_model="stock.picking"
            ).create({
                "picking_id": self.picking_id.id,
            })
            
            nc_product_qtys = {l.product_id.id: l.quantity for l in self.line_ids}
            for r_line in return_wizard.product_return_moves:
                if r_line.product_id.id in nc_product_qtys:
                    r_line.quantity = nc_product_qtys[r_line.product_id.id]
                else:
                    r_line.quantity = 0.0

            res = return_wizard.action_create_returns()
            new_picking_id = res.get("res_id")
            new_picking = self.env["stock.picking"].browse(new_picking_id)
        else:
            # Escenario B: No hay picking previo -> Crear albarán de entrada directo
            picking_type = self.warehouse_id.in_type_id
            dest_location = picking_type.default_location_dest_id or self.warehouse_id.lot_stock_id
            partner_location = doc_source.partner_id.property_stock_customer or self.env.ref("stock.stock_location_customers")

            new_picking = self.env["stock.picking"].create({
                "partner_id": doc_source.partner_id.id,
                "picking_type_id": picking_type.id,
                "location_id": partner_location.id,
                "location_dest_id": dest_location.id,
                "origin": f"RETORNO: {doc_name}",
            })

            moves = []
            for l in self.line_ids:
                if l.quantity > 0:
                    moves.append((0, 0, {
                        "name": l.product_id.display_name,
                        "product_id": l.product_id.id,
                        "product_uom_qty": l.quantity,
                        "quantity": l.quantity,
                        "product_uom": l.uom_id.id,
                        "picking_id": new_picking.id,
                        "location_id": partner_location.id,
                        "location_dest_id": dest_location.id,
                    }))
            new_picking.move_ids = moves
            new_picking.action_confirm()

        # Asignar notas y trazabilidad
        new_picking.write({
            "note": (new_picking.note or "") + "\n" + ref_notes,
            "origin": f"{'NC' if is_refund else 'ANULACION'}: {doc_name}",
        })
        doc_source.stock_return_picking_id = new_picking.id

        # 3. Validar inmediatamente a estado DONE
        new_picking.action_assign()
        for move in new_picking.move_ids:
            move.quantity = move.product_uom_qty
        new_picking.with_context(skip_sanity_check=True).button_validate()

        # Tarjeta visual en el chatter del documento
        in_link = new_picking._get_html_link()
        html = f"""
        <div style="border-left: 4px solid #1192e8; padding-left: 12px; margin: 4px 0;">
            <h5 style="color: #012749; margin-bottom: 8px;">📥 <b>Devolución de Mercancía a Bodega ({doc_label})</b></h5>
            <div style="margin-bottom: 6px;">
                <span style="background: #e5f6ff; color: #0043ce; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">RECEPCIÓN VALIDADA</span>
                <span style="margin-left: 6px;">Albarán: <b>{in_link}</b></span>
                <ul style="margin: 4px 0 6px 18px; padding: 0;">
        """
        for l in self.line_ids.filtered(lambda x: x.quantity > 0):
            html += f"<li><b>{l.product_id.display_name}</b> — Cant: {l.quantity} {l.uom_id.name}</li>"
        html += "</ul></div></div>"
        doc_source.message_post(body=Markup(html))

        return {
            "name": _("Devolución Confirmada - %s") % new_picking.name,
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": new_picking.id,
            "view_mode": "form",
            "target": "current",
        }


class AccountInvoiceStockReturnWizardLine(models.TransientModel):
    _name = "account.invoice.stock.return.wizard.line"
    _description = "Línea de Devolución de Mercancía a Bodega"

    wizard_id = fields.Many2one("account.invoice.stock.return.wizard", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Producto", required=True)
    quantity = fields.Float(string="Cantidad a Devolver", required=True, default=1.0)
    uom_id = fields.Many2one("uom.uom", string="Unidad de Medida", required=True)
