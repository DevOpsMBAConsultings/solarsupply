# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DGIUnidadMedida(models.Model):
    _name = "dgi.unidad.medida"
    _description = "DGI Unidad de Medida (CPBS)"
    _order = "code"

    code = fields.Char(
        string="Código (Símbolo CPBS)",
        required=True,
        index=True,
    )

    name = fields.Char(
        string="Nombre",
        required=True
    )

    system = fields.Char(
        string="Sistema"
    )

    measure = fields.Char(
        string="Tipo de Medida"
    )

    comment = fields.Text(
        string="Comentario / Descripción"
    )

    @api.constrains("code")
    def _check_code_unique(self):
        for rec in self:
            if self.search_count([("code", "=", rec.code), ("id", "!=", rec.id)]) > 0:
                raise ValidationError(_("El código de unidad de medida debe ser único."))