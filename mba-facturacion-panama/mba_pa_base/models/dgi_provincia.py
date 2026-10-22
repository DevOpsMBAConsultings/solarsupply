# -*- coding: utf-8 -*-
from odoo import models, fields


class DGIProvincia(models.Model):
    _name = "dgi.provincia"
    _description = "DGI Provincia"
    _order = "code, name"

    code = fields.Char(string="Código", required=True, index=True)
    name = fields.Char(string="Nombre", required=True)

    distrito_ids = fields.One2many(
        "dgi.distrito",
        "provincia_id",
        string="Distritos",
    )
