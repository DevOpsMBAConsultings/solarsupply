# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_pa_sucursal_code = fields.Char(
        string="Código de Sucursal",
        size=4,
        help="Código de sucursal DGI (dSucEm). 0000 para casa matriz.",
    )
    
    l10n_pa_pto_fact_df = fields.Char(
        string="Punto de Facturación",
        size=3,
        help="Punto de Facturación DGI (dPtoFacDF). Ejemplo: 001. No puede ser 000.",
    )

    @api.constrains("l10n_pa_sucursal_code")
    def _check_l10n_pa_sucursal_code(self):
        for rec in self:
            if rec.l10n_pa_sucursal_code:
                code = rec.l10n_pa_sucursal_code.strip()
                if len(code) != 4:
                    raise ValidationError(_(
                        "El Código de Sucursal debe tener exactamente 4 caracteres."
                    ))

    @api.constrains("l10n_pa_pto_fact_df")
    def _check_l10n_pa_pto_fact_df(self):
        for rec in self:
            if rec.l10n_pa_pto_fact_df:
                pto = rec.l10n_pa_pto_fact_df.strip()
                if len(pto) != 3 or not pto.isdigit() or pto == "000":
                    raise ValidationError(_(
                        "El Punto de Facturación debe tener exactamente 3 dígitos numéricos y no puede ser '000'."
                    ))
