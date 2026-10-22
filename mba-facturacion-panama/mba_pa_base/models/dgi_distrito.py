# -*- coding: utf-8 -*-
from odoo import models, fields


class DGIDistrito(models.Model):
    _name = "dgi.distrito"
    _description = "DGI Distrito"
    _order = "code, name"

    code = fields.Char(string="Código", required=True, index=True)
    name = fields.Char(string="Nombre", required=True)

    provincia_id = fields.Many2one(
        "dgi.provincia",
        string="Provincia",
        required=True,
        ondelete="cascade",
        index=True,
    )

    corregimiento_ids = fields.One2many(
        "dgi.corregimiento",
        "distrito_id",
        string="Corregimientos",
    )
