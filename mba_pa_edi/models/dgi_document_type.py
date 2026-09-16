# -*- coding: utf-8 -*-
from odoo import api, fields, models


# Código de etiqueta para mostrar en listas (ej. "01 - Factura de Operación Interna")
DOC_TYPE_DISPLAY_CODE = {
    "factura_operacion_interna": "01",
    "factura_exportacion": "02",
    "factura_zona_franca": "03",
    "factura_operacion_extranjera": "10",
    "nc_referenciada_fe": "04",
    "nd_referenciada_fe": "05",
    "nc_generica": "06",
    "nd_generica": "07",
    "reembolso": "08",
    "factura_importacion": "02",  # por si se usa
}


class DgiDocumentType(models.Model):
    _name = "dgi.document.type"
    _description = "DGI Document Type"
    _order = "sequence, name"

    sequence = fields.Integer(default=10, help="Order in FE (DGI) tab dropdowns: Factura types first, then Nota de crédito/débito.")
    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    rule_ids = fields.One2many(
        "dgi.document.type.rule",
        "doc_type_id",
        string="Receptor Rules",
    )

    @api.depends('code', 'name')
    def _compute_display_name(self):
        """Mostrar etiqueta con número de documento, ej. 01 - Factura de Operación Interna."""
        for rec in self:
            display_code = DOC_TYPE_DISPLAY_CODE.get((rec.code or "").strip())
            name = (rec.name or "").strip()
            if display_code:
                rec.display_name = f"{display_code} - {name}"
            else:
                rec.display_name = name or rec.code or ""

    @property
    def dgi_numeric_code(self):
        self.ensure_one()
        return DOC_TYPE_DISPLAY_CODE.get((self.code or "").strip(), "01")


class DgiDocumentTypeRule(models.Model):
    _name = "dgi.document.type.rule"
    _description = "DGI Document Type Rule"

    doc_type_id = fields.Many2one(
        "dgi.document.type",
        required=True,
        ondelete="cascade",
    )

    receptor_type = fields.Selection(
        selection=[
            ("consumidor_final", "Consumidor final"),
            ("contribuyente", "Contribuyente"),
            ("extranjero", "Extranjero"),
            ("gobierno", "Gobierno"),
        ],
        required=True,
        index=True,
    )