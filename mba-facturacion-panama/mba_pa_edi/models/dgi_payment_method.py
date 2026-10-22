# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DgiPaymentMethod(models.Model):
    _name = "dgi.payment.method"
    _description = "DGI – Formas de Pago"
    _order = "code, id"

    code = fields.Char(
        string="Código DGI",
        required=True,
        size=2,
        index=True,
        help="Código de forma de pago DGI (01–99). Se envía tal cual al XML.",
    )
    name = fields.Char(string="Descripción", required=True)
    active = fields.Boolean(default=True)

    @api.constrains("code")
    def _check_code_format(self):
        for rec in self:
            if rec.code and (len(rec.code) != 2 or not rec.code.isdigit()):
                raise ValidationError(_("El Código DGI debe tener 2 dígitos (ej: 01, 02, ... 99)."))

    @api.constrains("code")
    def _check_unique_code(self):
        for rec in self:
            if rec.code and self.search_count([("id", "!=", rec.id), ("code", "=", rec.code)]):
                raise ValidationError(_("Código DGI duplicado: %s") % rec.code)