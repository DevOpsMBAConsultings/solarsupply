# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.onchange('partner_id')
    def _onchange_partner_dgi_validated(self):
        """
        Muestra advertencia amarilla al seleccionar cliente no validado con la DGI.
        Se dispara en cualquier contexto: crear manual o desde smart button del cliente.
        """
        if self.partner_id:
            partner_valid = self._check_partner_dgi_validation(self.partner_id)

            if not partner_valid:
                return {
                    'name': _("Cliente no Validado con DGI"),
                    'type': 'ir.actions.act_window',
                    'res_model': 'partner.dgi.warning.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_partner_name': self.partner_id.name,
                        'default_message_type': 'sale',
                    }
                }

    def _check_partner_dgi_validation(self, partner):
        """
        Verifica si un partner está validado con DGI.
        Considera parent_id si el partner actual no está validado.
        """
        if not partner:
            return True

        partner_valid = partner.l10n_pa_is_dgi_validated
        if not partner_valid and partner.parent_id:
            partner_valid = partner.parent_id.l10n_pa_is_dgi_validated

        return partner_valid

    @api.constrains('partner_id')
    def _check_partner_dgi_validated(self):
        """
        Advertencia previa al guardar. No bloquea la creación o guardado de la cotización.
        """
        pass

    dgi_payment_notes = fields.Text(
        string="Notas complementarias (FE DGI)",
        help="Detalles del cliente para la factura (AI17 InfoInteres, máx. 200 caracteres en DGI). Por defecto desde el contacto; si se cambia aquí, aplica a la factura al facturar esta cotización.",
    )

    dgi_amount_untaxed = fields.Monetary(
        string="Subtotal",
        compute="_compute_dgi_totals",
        store=True,
        currency_field="currency_id",
    )
    dgi_amount_taxes = fields.Monetary(
        string="ITBMS 7%",
        compute="_compute_dgi_totals",
        store=True,
        currency_field="currency_id",
    )
    dgi_amount_total = fields.Monetary(
        string="Total Factura (DGI)",
        compute="_compute_dgi_totals",
        store=True,
        currency_field="currency_id",
    )
    dgi_show_retention_block = fields.Boolean(
        string="Mostrar Bloque Retención DGI",
        compute="_compute_dgi_show_retention_block",
    )
    dgi_retention_type_id = fields.Many2one(
        "dgi.retention.type",
        string="Retención (DGI)",
        ondelete="set null",
        help="Tipo de retención para calcular el monto a retener del ITBMS.",
    )
    dgi_retention_amount = fields.Monetary(
        string="Monto Retención (DGI)",
        compute="_compute_dgi_totals",
        store=True,
        currency_field="currency_id",
    )

    @api.onchange("partner_id")
    def _onchange_partner_id_dgi_payment_notes(self):
        """Rellenar notas complementarias desde el contacto al cambiar el cliente."""
        if self.partner_id:
            inv_partner = self.partner_id.address_get(["invoice"]).get("invoice")
            p = self.env["res.partner"].browse(inv_partner) if inv_partner else self.partner_id
            self.dgi_payment_notes = (p.dgi_payment_notes or "") or (self.partner_id.dgi_payment_notes or "")

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.env.context.get("dgi_document_type_id"):
            vals["dgi_document_type_id"] = self.env.context["dgi_document_type_id"]
        if self.env.context.get("dgi_naturaleza_operacion"):
            vals["dgi_naturaleza_operacion"] = self.env.context["dgi_naturaleza_operacion"]
        if self.env.context.get("dgi_tipo_operacion"):
            vals["dgi_tipo_operacion"] = self.env.context["dgi_tipo_operacion"]
        if self.env.context.get("dgi_plazo_due_date"):
            vals["dgi_plazo_due_date"] = self.env.context["dgi_plazo_due_date"]
        
        # Propagate payment term settings to prevent invoice address defaults from overriding them
        if getattr(self.partner_id, "dgi_payment_term_type", None):
            vals["dgi_payment_term_type"] = self.partner_id.dgi_payment_term_type
        if getattr(self.partner_id, "dgi_plazo_option", None):
            vals["dgi_plazo_option"] = self.partner_id.dgi_plazo_option
        if getattr(self.partner_id, "dgi_payment_method_id", None):
            vals["dgi_payment_method_id"] = self.partner_id.dgi_payment_method_id.id
            
        if self.env.context.get("dgi_payment_method_other_desc") is not None:
            vals["dgi_payment_method_other_desc"] = self.env.context["dgi_payment_method_other_desc"]
        # Notas complementarias: incluir número de cotización de origen y notas del pedido/contacto
        quote_ref = f"Cotización: {self.name}"
        existing_notes = (self.dgi_payment_notes or self.partner_id.dgi_payment_notes or "").strip()
        if existing_notes:
            if quote_ref not in existing_notes:
                notes = f"{quote_ref} - {existing_notes}"
            else:
                notes = existing_notes
        else:
            notes = quote_ref

        vals["dgi_payment_notes"] = notes.strip()
        if self.dgi_retention_type_id:
            vals["dgi_retention_type_id"] = self.dgi_retention_type_id.id
        return vals

    def action_create_invoice_direct(self):
        """
        Creates the invoice directly without going through the wizard sale.advance.payment.inv.
        Equivalent to creating a regular 100% invoice.
        """
        self.ensure_one()
        # Contado + Método 99 (Otro): obligatorio pedir la descripción de forma de pago
        partner = self.partner_id
        if (
            getattr(partner, "dgi_payment_term_type", None) == "contado"
            and partner.dgi_payment_method_id
            and (partner.dgi_payment_method_id.code or "").strip() == "99"
        ):
            return {
                "type": "ir.actions.act_window",
                "name": _("Descripción de forma de pago (99 - Otro)"),
                "res_model": "sale.order.payment.other.desc.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {"active_id": self.id, "default_sale_order_id": self.id},
            }
        # Crédito + Otro: obligatorio pedir la fecha de vencimiento (DGI exige dInfPagPlazo y fecha)
        if (
            getattr(partner, "dgi_payment_term_type", None) == "credito"
            and getattr(partner, "dgi_plazo_option", None) == "other"
        ):
            return {
                "type": "ir.actions.act_window",
                "name": _("Fecha de vencimiento (Crédito otro)"),
                "res_model": "sale.order.credit.other.due.date.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {"active_id": self.id, "default_sale_order_id": self.id},
            }

        # 1. Verificar si el cliente está validado con la DGI antes de crear la factura
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

        if self.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice'):
            raise UserError(_("Esta orden de venta ya tiene facturas generadas y no puede ser refacturada."))

        invoice = self._create_invoices(final=True)
        if not invoice:
            raise UserError(_("No hay nada que facturar o la factura ya fue creada."))
        
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': invoice[0].id,
            'target': 'current',
        }

    @api.depends('state', 'order_line.invoice_status', 'invoice_ids')
    def _compute_invoice_status(self):
        super()._compute_invoice_status()
        for order in self:
            if order.state == 'sale' and order.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice'):
                order.invoice_status = 'invoiced'

    @api.constrains('partner_id')
    def _check_partner_dgi_validated(self):
        """
        Final validation layer to ensure no sale order is created or saved
        with a partner that has not been initialized with DGI data.
        """
        for order in self:
            if order.partner_id:
                partner_valid = order.partner_id.l10n_pa_is_dgi_validated
                if not partner_valid and order.partner_id.parent_id:
                    partner_valid = order.partner_id.parent_id.l10n_pa_is_dgi_validated
                    
                # Si estamos usando un modulo de conector PAC, las reglas requerirán 
                # que los partners tengan la validación de la DGI completa (RUC, Provincia, etc).
                # Por ahora es una buena práctica advertir.
                if hasattr(order.partner_id, 'l10n_pa_is_dgi_validated') and not partner_valid:
                    # Not raising UserError to avoid blocking standard flow if EDI isn't fully strictly enforced,
                    # but leaving hook point for PAC modules.
                    pass

    @api.depends('partner_id', 'fiscal_position_id', 'dgi_retention_type_id')
    def _compute_dgi_show_retention_block(self):
        for order in self:
            fp = order.fiscal_position_id
            if not fp and order.partner_id:
                fp = order.partner_id.property_account_position_id
            is_retenedor = getattr(fp, "dgi_es_retenedor", False)
            if not is_retenedor and fp:
                nombre = (fp.name or "").lower()
                is_retenedor = bool("retención" in nombre or "retenedor" in nombre or "agente de retención" in nombre or "retencion" in nombre)
            order.dgi_show_retention_block = bool(is_retenedor or order.dgi_retention_type_id)

    @api.depends(
        "order_line.price_total",
        "order_line.price_subtotal",
        "order_line.tax_ids",
        "partner_id",
        "fiscal_position_id",
        "dgi_retention_type_id",
    )
    def _compute_dgi_totals(self):
        """
        Calcula totales para mostrar al vendedor
        """
        for order in self:
            untaxed = 0.0
            taxes_positive = 0.0
            retention_from_lines = 0.0
            
            for line in order.order_line:
                untaxed += line.price_subtotal
                taxes = line.tax_ids
                if taxes:
                    tax_res = taxes.compute_all(
                        line.price_unit,
                        currency=order.currency_id,
                        quantity=line.product_uom_qty,
                        product=line.product_id,
                        partner=order.partner_id,
                    )
                    for t in tax_res.get("taxes", []):
                        amt = t.get("amount", 0.0)
                        if amt > 0:
                            taxes_positive += amt
                        elif amt < 0:
                            retention_from_lines += abs(amt)
            
            order.dgi_amount_untaxed = untaxed
            order.dgi_amount_taxes = taxes_positive

            ret_amount = 0.0
            if order.dgi_retention_type_id:
                ret_amount = taxes_positive * (order.dgi_retention_type_id.percentage / 100.0)
            elif retention_from_lines > 0:
                if order.amount_tax:
                    derived_retention = taxes_positive - order.amount_tax
                    if abs(derived_retention - retention_from_lines) < 0.05:
                        ret_amount = derived_retention
                    else:
                        ret_amount = retention_from_lines
                else:
                    ret_amount = retention_from_lines
            
            order.dgi_retention_amount = ret_amount
            order.dgi_amount_total = order.dgi_amount_untaxed + taxes_positive

    def _fe_line_has_positive_tax(self, line, order):
        """
        [FE-TAX-CONFIRM] Verifica si la línea tiene al menos un componente de impuesto
        base (ITBMS) asignado usando compute_all().

        Regla: la línea es válida si tiene al menos un impuesto con amount >= 0.
        - ITBMS 7%, 10%, 15% → válido (amount > 0).
        - ITBMS 0% / Exento → válido (amount == 0). Cliente exento: la DGI exige
          declarar Code=00, Description=ITBMS, Amount=0.00. No es ausencia de impuesto.
        - Solo retenciones negativas (amount < 0) sin ningún ITBMS → inválido.
        - Sin impuestos (tax_id vacío) → inválido.
        """
        if not line.tax_ids:
            return False  # Sin impuestos → inválido
        tax_res = line.tax_ids.compute_all(
            abs(line.price_unit) or 1.0,
            currency=order.currency_id,
            quantity=abs(line.product_uom_qty) or 1.0,
            product=line.product_id,
            partner=order.partner_id,
        )
        # Aceptar amount >= 0: incluye ITBMS 0% (cliente exento) y ITBMS positivo.
        # Rechazar si TODOS los componentes son negativos (solo retenciones).
        return any(
            t.get("amount", 0.0) >= 0
            for t in tax_res.get("taxes", [])
        )

    def action_confirm(self):
        """
        Sobrescribe action_confirm para validar que no haya líneas sin impuesto.
        """
        for order in self:
            invalid_lines = order.order_line.filtered(
                lambda l: l.product_id
                and not l.display_type
                and not self._fe_line_has_positive_tax(l, order)
            )
            if invalid_lines:
                names = ", ".join(
                    invalid_lines[:3].mapped(
                        lambda l: l.product_id.display_name or l.name or "(sin nombre)"
                    )
                )
                if len(invalid_lines) > 3:
                    names += " … (+%s más)" % (len(invalid_lines) - 3)
                raise UserError(
                    _(
                        "No se puede confirmar el pedido: las siguientes líneas "
                        "no tienen un impuesto (ITBMS o Exento) asignado.\n\n"
                        "La DGI exige que todas las líneas declaren un impuesto base. "
                        "Si el cliente es exento, utilice la Posición Fiscal adecuada para aplicar el impuesto 0%% (Exento), pero el campo de impuestos no puede quedar vacío.\n\n"
                        "Líneas afectadas: %s"
                    )
                    % names
                )
        return super().action_confirm()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_dgi_item_description(self):
        """
        Retorna únicamente la descripción personalizada para reportes y DGI.
        Si el producto es genérico (is_dgi_generic):
        - Remueve el prefijo [código] si existe.
        - Remueve el nombre del catálogo del producto.
        Ej: '[NO-STOCK] Articulo Genérico acrilico' -> 'acrilico'
        """
        self.ensure_one()
        prod = self.product_id
        is_generic = getattr(prod, "is_dgi_generic", False) if prod else False
        raw_name = (self.name or "").strip()

        if is_generic and prod:
            # 1. Quitar prefijo [SKU] si existe
            if prod.default_code:
                code_prefix = f"[{prod.default_code.strip()}]"
                if raw_name.upper().startswith(code_prefix.upper()):
                    raw_name = raw_name[len(code_prefix):].strip()

            # 2. Quitar nombre del catálogo si antecede a la descripción
            prod_name = (prod.name or "").strip()
            if prod_name and raw_name.upper().startswith(prod_name.upper()):
                raw_name = raw_name[len(prod_name):].strip()

            return raw_name or prod_name

        # Para productos normales, limpiar solo el prefijo [SKU] (ya mostrado en Referencia)
        if prod and prod.default_code:
            code_prefix = f"[{prod.default_code.strip()}]"
            if raw_name.upper().startswith(code_prefix.upper()):
                return raw_name[len(code_prefix):].strip()

        return raw_name or (prod.name if prod else "")

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line(**optional_values)
        if self.product_id and getattr(self.product_id, "is_dgi_generic", False):
            clean_desc = self._get_dgi_item_description()
            if clean_desc:
                res["name"] = clean_desc
        return res

    @api.depends('invoice_lines.move_id.state', 'invoice_lines.quantity')
    def _compute_qty_invoiced(self):
        """
        MBA Consultings: Regla lineal de facturación.
        Una orden facturada no se vuelve a refacturar.
        Se cuentan las cantidades de las facturas de cliente (out_invoice) generadas, 
        sin descontar por notas de crédito (out_refund) ni por cancelaciones posteriores.
        """
        for line in self:
            qty_invoiced = 0.0
            for invoice_line in line._get_invoice_lines():
                if invoice_line.move_id.move_type == 'out_invoice':
                    qty_invoiced += invoice_line.product_uom_id._compute_quantity(
                        invoice_line.quantity, line.product_uom_id, round=False
                    )
            line.qty_invoiced = qty_invoiced

    def _get_dgi_line_tax(self):
        """
        Retorna el monto de impuesto positivo (ITBMS bruto) de la línea,
        excluyendo retenciones negativas, para mostrar en reportes.
        """
        self.ensure_one()
        if not self.tax_ids:
            return 0.0
        tax_res = self.tax_ids.compute_all(
            self.price_unit,
            currency=self.order_id.currency_id,
            quantity=self.product_uom_qty,
            product=self.product_id,
            partner=self.order_id.partner_id,
        )
        return sum(
            t.get("amount", 0.0)
            for t in tax_res.get("taxes", [])
            if t.get("amount", 0.0) > 0
        )


