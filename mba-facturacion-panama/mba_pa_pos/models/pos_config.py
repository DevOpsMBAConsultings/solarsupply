# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    @api.model
    def _load_pos_data_fields(self, config_id):
        """
        Expone 'l10n_pa_fiscal_printer' al frontend del POS (OWL).

        Sin esto, el JS del POS no tiene forma de saber si el punto de venta
        usa o no impresora fiscal: los campos custom en pos.config NO viajan
        al navegador automáticamente en Odoo 18, hay que declararlos aquí.
        Lo usa mba_pa_pos/static/.../payment_screen.js para forzar el toggle
        de "Factura" cuando no hay impresora fiscal (venta siempre facturada
        vía PAC/DGI).

        CAUSA RAIZ del KeyError use_pricelist / printer_ids (dos veces):
        en pos.load.mixin, '_load_pos_data_fields' devuelve [] por defecto,
        y en el ORM de Odoo 18 (BaseModel.check_field_access_rights,
        odoo/models.py) una lista de campos VACIA se trata exactamente
        igual que None: "leer TODOS los campos accesibles". Al hacer
        'pos_fields = super()...; pos_fields.append(...)' convertiamos esa
        lista vacia en una lista de UN solo campo, y Odoo dejaba de leer
        todo lo demas de pos.config (printer_ids, use_pricelist,
        payment_method_ids, etc.), rompiendo pos_printer.py y
        pos_config.py._load_pos_data que los dan por sentados.

        Por eso: si la lista base viene vacia, la dejamos vacia (= "leer
        todo"). Solo si viene con contenido explicito (otro modulo ya la
        restringio a una lista concreta) le agregamos nuestro campo.
        """
        pos_fields = super()._load_pos_data_fields(config_id)
        if not pos_fields:
            return pos_fields
        if "l10n_pa_fiscal_printer" not in pos_fields:
            pos_fields.append("l10n_pa_fiscal_printer")
        return pos_fields

    l10n_pa_fiscal_printer = fields.Boolean(
        string="Usa Impresora Fiscal",
        default=False,
        help=(
            "Si está activo, las facturas POS se manejan con la impresora fiscal "
            "y NO se envían al PAC (DGI). Si está desactivado, las facturas POS "
            "se generan como account.move en borrador con campos DGI para ser "
            "enviadas al PAC mediante el wizard de confirmación."
        ),
    )

    l10n_pa_dgi_document_type_id = fields.Many2one(
        "dgi.document.type",
        string="Tipo de Documento DGI (POS)",
        help="Tipo de documento fiscal por defecto para las facturas generadas desde este POS.",
    )

    l10n_pa_pos_journal_id = fields.Many2one(
        "account.journal",
        string="Diario DGI (POS)",
        domain=[("type", "=", "sale")],
        help=(
            "Diario contable específico para facturas DGI generadas desde este POS. "
            "Debe tener configurado el Código de Sucursal y Punto de Facturación DGI. "
            "Si se deja vacío, se usa el Diario de Facturas estándar del POS."
        ),
    )
