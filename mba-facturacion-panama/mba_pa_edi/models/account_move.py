# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import re

# Namespace propio para pg_advisory_xact_lock. La primera clave identifica al
# módulo (para no chocar con los advisory locks que usa el core de Odoo) y la
# segunda es el diario sobre el que se serializa la asignación de consecutivo.
PA_NUMERO_LOCK_NS = 190378


class AccountMove(models.Model):
    _inherit = "account.move"

    dgi_document_type_id = fields.Many2one(
        "dgi.document.type",
        string="Tipo de documento (DGI)",
        compute="_compute_dgi_document_type_id",
        store=True,
        readonly=False,
        tracking=True,
    )

    dgi_naturaleza_operacion = fields.Selection(
        selection=[
            ("01", "01 Venta"),
            ("02", "02 Exportación"),
            ("10", "10 Transferencia"),
            ("11", "11 Devolución"),
            ("12", "12 Remesa"),
            ("13", "13 Consignación"),
            ("20", "20 Compra"),
            ("21", "21 Importación"),
        ],
        string="Naturaleza de la Operación",
        tracking=True,
        default="01",
    )
    
    dgi_tipo_operacion = fields.Selection(
        selection=[
            ("", "—"),
            ("1", "Salida o Venta"),
            ("2", "Entrada o Compra"),
        ],
        string="Tipo de la Operación",
        tracking=True,
        default="1",
    )

    dgi_payment_method_id = fields.Many2one(
        "dgi.payment.method",
        string="Método de Pago (DGI)",
        tracking=True,
    )

    dgi_payment_term_type = fields.Selection(
        selection=[
            ("", "—"),
            ("contado", "Contado"),
            ("credito", "Crédito/Plazo"),
        ],
        string="Plazos",
        default="contado",
        required=True,
        tracking=True,
    )

    # Missing DGI Fields
    dgi_plazo_option = fields.Selection(
        selection=[
            ("", "—"),
            ("30", "30 días"),
            ("60", "60 días"),
            ("90", "90 días"),
            ("other", "Otro"),
        ],
        string="Plazo (DGI)",
        help="Opción de plazo para ventas a crédito.",
    )
    dgi_plazo_due_date = fields.Date(
        string="Fecha de vencimiento (DGI)",
        tracking=True,
    )
    dgi_payment_method_other_desc = fields.Char(
        string="Descripción forma de pago",
        tracking=True,
    )
    dgi_payment_notes = fields.Text(
        string="Notas complementarias",
        tracking=True,
    )
    dgi_retention_type_id = fields.Many2one(
        "dgi.retention.type",
        string="Retención",
        compute="_compute_dgi_retention_auto",
        store=True,
        readonly=False,
        compute_sudo=False,
    )
    dgi_retention_amount = fields.Monetary(
        string="Monto Retención",
        currency_field="currency_id",
        compute="_compute_dgi_retention_amount",
    )
    dgi_retention_readonly = fields.Boolean(
        string="Retención Auto-seleccionada",
        compute="_compute_dgi_retention_auto",
        store=True,
        compute_sudo=False,
    )
    dgi_retention_receptor_filter = fields.Char(
        string="Filtro Receptor Retención",
        compute="_compute_dgi_retention_receptor_filter",
    )
    dgi_amount_untaxed = fields.Monetary(string="Base Imponible DGI", currency_field="currency_id", compute="_compute_dgi_totals")
    dgi_amount_taxes = fields.Monetary(string="Impuestos DGI", currency_field="currency_id", compute="_compute_dgi_totals")
    dgi_amount_total = fields.Monetary(string="Total a pagar DGI", currency_field="currency_id", compute="_compute_dgi_totals")

    @api.depends("invoice_line_ids.price_subtotal", "invoice_line_ids.tax_ids", "dgi_show_retention_block")
    def _compute_dgi_totals(self):
        for move in self:
            untaxed = 0.0
            taxes_positive = 0.0
            for line in move.invoice_line_ids:
                untaxed += line.price_subtotal
                if line.tax_ids:
                    tax_res = line.tax_ids.compute_all(
                        line.price_unit,
                        currency=move.currency_id,
                        quantity=line.quantity,
                        product=line.product_id,
                        partner=move.partner_id,
                    )
                    for t in tax_res.get("taxes", []):
                        if t.get("amount", 0.0) > 0:
                            taxes_positive += t.get("amount", 0.0)
            move.dgi_amount_untaxed = untaxed
            move.dgi_amount_taxes = taxes_positive
            move.dgi_amount_total = untaxed + taxes_positive
    dgi_show_retention_block = fields.Boolean(
        string="Mostrar Retención",
        compute="_compute_dgi_show_retention_block",
    )
    dgi_is_from_sale = fields.Boolean(
        string="Viene de Cotización",
        compute="_compute_dgi_is_from_sale",
        store=True,
        help="True si la factura fue generada desde una cotización/orden de venta aprobada."
    )

    l10n_pa_is_debit_note = fields.Boolean(
        string="Es Nota de Débito (DGI)",
        default=False,
        copy=False,
        tracking=True,
        help="Indica si este documento es una Nota de Débito DGI (Referenciada o Genérica)."
    )

    @api.depends("move_type", "reversed_entry_id", "l10n_pa_is_debit_note")
    def _compute_dgi_document_type_id(self):
        DocType = self.env["dgi.document.type"]
        for move in self:
            debit_origin = getattr(move, "debit_origin_id", False)
            is_debit = move.l10n_pa_is_debit_note or bool(debit_origin)
            
            if move.dgi_document_type_id and not self.env.context.get("force_recompute_dgi_type"):
                if is_debit and move.dgi_document_type_id.code not in ("nd_referenciada_fe", "nd_generica"):
                    pass
                else:
                    continue

            code = False
            if move.move_type == "out_refund":
                code = "nc_referenciada_fe" if move.reversed_entry_id else "nc_generica"
            elif move.move_type == "out_invoice":
                if debit_origin:
                    code = "nd_referenciada_fe"
                elif is_debit:
                    code = "nd_generica"
                else:
                    code = "factura_operacion_interna"
            if code:
                doc_type = DocType.search([("code", "=", code)], limit=1)
                if doc_type:
                    move.dgi_document_type_id = doc_type

    @api.depends("invoice_origin", "move_type")
    def _compute_dgi_is_from_sale(self):
        for move in self:
            # Solo bloquear facturas de cliente (out_invoice) que provengan de una orden de venta
            if move.move_type == 'out_invoice' and move.invoice_origin:
                move.dgi_is_from_sale = True
            else:
                move.dgi_is_from_sale = False

    @api.depends("partner_id", "fiscal_position_id")
    def _compute_dgi_show_retention_block(self):
        """
        Mostrar el bloque de retención/exento si el cliente tiene posición fiscal
        de retención o exento de impuestos.
        """
        for move in self:
            show = False
            if move.move_type in ('out_invoice', 'out_refund'):
                fp = move.fiscal_position_id
                if not fp and move.partner_id:
                    fp = move.partner_id.property_account_position_id
                if fp and 'retenci' in (fp.name or '').lower():
                    show = True
            move.dgi_show_retention_block = show

    @api.depends(
        "partner_id",
        "partner_id.l10n_pa_receptor_tipo",
        "partner_id.property_account_position_id",
        "fiscal_position_id",
        "move_type",
    )
    def _compute_dgi_retention_auto(self):
        """
        Auto-selecciona el tipo de retención según tipo de cliente + posición fiscal.
        Bloquea el campo si es Gobierno o Contribuyente con retención 50%.

        Las dependencias incluyen los campos internos del contacto
        (l10n_pa_receptor_tipo, property_account_position_id) porque el campo es
        almacenado: si solo se dependiera de partner_id, actualizar la
        configuración de retención de un cliente ya existente no recalcularía
        los documentos en borrador y quedarían con el valor viejo en la columna.
        """
        RetType = self.env["dgi.retention.type"]
        for move in self:
            # Solo aplica a facturas de cliente (out_invoice, out_refund)
            if move.move_type not in ('out_invoice', 'out_refund'):
                move.dgi_retention_readonly = False
                continue

            commercial = move.partner_id.commercial_partner_id or move.partner_id
            parent = move.partner_id.parent_id or commercial

            fp = move.fiscal_position_id
            if not fp:
                fp = move.partner_id.property_account_position_id or commercial.property_account_position_id or parent.property_account_position_id
            fp_name = (fp.name or '').lower() if fp else ''
            
            receptor = move.partner_id.l10n_pa_receptor_tipo or commercial.l10n_pa_receptor_tipo or parent.l10n_pa_receptor_tipo or ''

            if not fp or 'retenci' not in fp_name:
                move.dgi_retention_readonly = False
                continue

            # Detectar porcentaje de la posición fiscal
            is_100 = '100' in fp_name
            is_50 = '50' in fp_name

            if receptor == '03':  # Gobierno
                if is_100:
                    ret = RetType.search([('code', '=', '1'), ('receptor_type', '=', 'gobierno')], limit=1)
                elif is_50:
                    ret = RetType.search([('code', '=', '2'), ('receptor_type', '=', 'gobierno')], limit=1)
                else:
                    ret = False
                if ret and move.dgi_retention_type_id != ret:
                    move.dgi_retention_type_id = ret
                move.dgi_retention_readonly = True

            elif receptor == '01':  # Contribuyente
                # Auto-seleccionar código 4 (50%) para empresas retenedoras B2B
                ret = RetType.search([('code', '=', '4'), ('receptor_type', '=', 'contribuyente')], limit=1)
                if ret and move.dgi_retention_type_id != ret:
                    move.dgi_retention_type_id = ret
                move.dgi_retention_readonly = True

            else:
                move.dgi_retention_readonly = False

    @api.depends("partner_id")
    def _compute_dgi_retention_receptor_filter(self):
        """Mapea tipo receptor del partner al receptor_type del modelo dgi.retention.type."""
        MAPPING = {'01': 'contribuyente', '03': 'gobierno'}
        for move in self:
            commercial = move.partner_id.commercial_partner_id or move.partner_id
            parent = move.partner_id.parent_id or commercial
            receptor = move.partner_id.l10n_pa_receptor_tipo or commercial.l10n_pa_receptor_tipo or parent.l10n_pa_receptor_tipo or ''
            move.dgi_retention_receptor_filter = MAPPING.get(receptor, '')

    @api.depends("line_ids.balance", "line_ids.tax_line_id")
    def _compute_dgi_retention_amount(self):
        """
        Calcula el monto de retención desde las líneas de impuestos reales.
        Las retenciones son impuestos con amount negativo (ej: -50% del ITBMS).
        Non-stored para recalcular en tiempo real durante edición.
        """
        for move in self:
            if move.move_type not in ('out_invoice', 'out_refund'):
                move.dgi_retention_amount = 0.0
                continue

            # Buscar líneas de impuestos de retención (impuestos con amount < 0)
            retention_amount = 0.0
            for line in move.line_ids:
                if line.tax_line_id and line.tax_line_id.amount < 0:
                    retention_amount += abs(line.balance)
            move.dgi_retention_amount = retention_amount

    # Campos PAC y DGI genéricos
    l10n_pa_cufe = fields.Char(string="CUFE", copy=False, index=True, tracking=True)
    l10n_pa_qr_url = fields.Char(string="URL del Código QR", copy=False)
    l10n_pa_pac_status = fields.Selection([
        ('draft', 'No Enviado'),
        ('sent', 'Enviado'),
        ('accepted', 'Aceptado DGI'),
        ('cancelled', 'Anulado DGI'),
        ('error', 'Error / Rechazado'),
    ], string="Estado DGI/PAC", default='draft', copy=False, tracking=True)
    l10n_pa_pac_error = fields.Text(string="Error del PAC", copy=False)
    l10n_pa_pac_request = fields.Text(string="JSON Enviado (PAC)", copy=False)
    l10n_pa_pac_response = fields.Text(string="Respuesta PAC", copy=False)
    
    def action_l10n_pa_send_to_pac(self):
        """
        Método base que debe ser extendido por los conectores (HKA, Digifact, etc.).
        Deberá armar el payload (XML/JSON), enviarlo al PAC, e hidratar 
        l10n_pa_cufe y l10n_pa_qr_url.
        """
        self.ensure_one()
        raise NotImplementedError(_("Debe instalar un módulo conector PAC (Ej: mba_pa_edi_hka) para emitir la factura electrónica."))

    def _pa_next_numero(self):
        """
        Siguiente número fiscal para esta empresa/diario.
        Busca el MAX numérico entre todas las facturas HKA enviadas al PAC + 1.

        Se resuelve en una sola consulta SQL en vez de traer el 'name' de todas
        las facturas del diario a Python: la lógica es idéntica (se extraen los
        dígitos del nombre y se toma el máximo), pero el tiempo deja de crecer
        con el volumen histórico de facturas.

        NOTA: al ser SQL directo no ve escrituras pendientes en la caché del ORM,
        por eso el flush previo.

        Es intencional que el máximo NO sea "la última factura + 1": si el
        cliente se saltó un consecutivo, ese hueco queda libre para usarlo
        manualmente después desde el wizard.
        """
        self.ensure_one()

        self.env['account.move'].flush_model(
            ['name', 'l10n_pa_pac_status', 'journal_id', 'company_id', 'move_type']
        )

        self.env.cr.execute(
            r"""
            SELECT COALESCE(MAX(digits::bigint), 0)
              FROM (
                    SELECT NULLIF(regexp_replace(name, '\D', '', 'g'), '') AS digits
                      FROM account_move
                     WHERE company_id = %s
                       AND journal_id = %s
                       AND move_type IN ('out_invoice', 'out_refund')
                       AND l10n_pa_pac_status IN ('sent', 'accepted', 'cancelled', 'error')
                       AND name IS NOT NULL
                       AND name != '/'
                   ) sub
             WHERE digits IS NOT NULL
               AND length(digits) <= 18
            """,
            (self.company_id.id, self.journal_id.id),
        )
        max_num = self.env.cr.fetchone()[0] or 0

        return str(max_num + 1).zfill(10)

    def _pa_reserve_numero(self, numero=None):
        """
        Reserva el número fiscal escribiéndolo en la factura de forma atómica.

        Toma un advisory lock por diario antes de calcular el consecutivo, para
        que dos procesos simultáneos (dos cajas de POS, o el POS y un futuro cron
        de facturación recurrente) no lleguen al mismo MAX+1 y colisionen.

        El lock es de transacción: PostgreSQL lo libera solo al hacer commit o
        rollback, sin necesidad de liberarlo a mano. En la práctica se suelta en
        el primer commit dentro de action_l10n_pa_send_to_pac(), es decir antes
        de la llamada HTTP al PAC — de modo que no se retiene durante la espera
        de red, pero sí durante todo el tramo crítico de calcular y escribir.

        :param numero: número ya normalizado a usar. Si se omite, se calcula el
                       siguiente disponible. Permite que el flujo manual imponga
                       un consecutivo reservado y el automático tome el que sigue.
        """
        self.ensure_one()

        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            (PA_NUMERO_LOCK_NS, self.journal_id.id),
        )

        num = numero or self._pa_next_numero()
        self.write({'name': num})
        return num

    @api.onchange('partner_id')
    def _onchange_partner_dgi_validated(self):
        """
        Muestra advertencia con wizard amarillo si el contacto no ha sido validado con la DGI.
        Solo aplica a facturas de cliente (no a facturas de proveedor que son internas).
        También copia las notas complementarias del contacto al borrador.
        """
        if self.partner_id and self.move_type in ['out_invoice', 'out_refund']:
            partner_valid = self.partner_id.l10n_pa_is_dgi_validated
            if not partner_valid and self.partner_id.parent_id:
                partner_valid = self.partner_id.parent_id.l10n_pa_is_dgi_validated

            if not partner_valid:
                return {
                    'name': _("Contacto no Validado con DGI"),
                    'type': 'ir.actions.act_window',
                    'res_model': 'partner.dgi.warning.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_partner_name': self.partner_id.name,
                        'default_message_type': 'invoice',
                    }
                }

            # Copiar notas complementarias del contacto al borrador de factura
            partner = self.partner_id
            inv_partner_id = partner.address_get(['invoice']).get('invoice')
            if inv_partner_id:
                inv_partner = self.env['res.partner'].browse(inv_partner_id)
                notes = inv_partner.dgi_payment_notes or partner.dgi_payment_notes
            else:
                notes = partner.dgi_payment_notes
            if notes:
                self.dgi_payment_notes = notes

    @api.constrains('partner_id', 'move_type', 'state')
    def _check_partner_dgi_validated(self):
        """
        No bloquea la creación ni edición de facturas con contactos no validados por DGI.
        """
        pass

    def action_post(self):
        if self.env.context.get('skip_pac_send'):
            return super(AccountMove, self).action_post()
            
        for move in self:
            if move.move_type in ('out_invoice', 'out_refund') and move.company_id.account_fiscal_country_id.code == 'PA':
                # Return wizard action instead of posting directly
                return {
                    'name': _('Confirmar y Enviar Factura a DGI (PAC)'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'mba_pa_edi.confirmar.enviar.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {'default_move_id': move.id},
                }
        
        return super(AccountMove, self).action_post()


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _get_dgi_item_description(self):
        """
        Método agnóstico para obtener la descripción que se enviará al PAC/DGI.
        Si el producto está marcado como 'Es producto genérico DGI' (is_dgi_generic),
        se remueven automáticamente el prefijo [SKU] y el nombre del producto para dejar
        únicamente la descripción personalizada ingresada por el usuario.
        Ej: '[NO-STOCK] Articulo Genérico acrilico' -> 'acrilico'
        """
        self.ensure_one()
        prod = self.product_id
        is_generic = getattr(prod, "is_dgi_generic", False) if prod else True
        raw_name = (self.name or "").strip()

        if is_generic and prod:
            # 1. Quitar prefijo de código [SKU]
            if prod.default_code:
                code_prefix = f"[{prod.default_code.strip()}]"
                if raw_name.upper().startswith(code_prefix.upper()):
                    raw_name = raw_name[len(code_prefix):].strip()

            # 2. Quitar el nombre estático del producto del catálogo si antecede a la descripción
            prod_name = (prod.name or "").strip()
            if prod_name and raw_name.upper().startswith(prod_name.upper()):
                raw_name = raw_name[len(prod_name):].strip()

            return raw_name or prod_name

        return raw_name or (prod.name if prod else "Ítem")


