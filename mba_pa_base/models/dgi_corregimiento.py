# -*- coding: utf-8 -*-
from odoo import models, fields


class DGICorregimiento(models.Model):
    _name = "dgi.corregimiento"
    _description = "DGI Corregimiento"
    _order = "code, name"

    code = fields.Char(string="Código", required=True, index=True)
    name = fields.Char(string="Nombre", required=True)

    distrito_id = fields.Many2one(
        "dgi.distrito",
        string="Distrito",
        required=True,
        ondelete="cascade",
        index=True,
    )

    provincia_id = fields.Many2one(
        "dgi.provincia",
        string="Provincia",
        related="distrito_id.provincia_id",
        store=True,
        readonly=True,
    )
