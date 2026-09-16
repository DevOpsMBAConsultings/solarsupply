# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    # Campos DGI heredados del contacto (partner_id)
    l10n_pa_ruc = fields.Char(related='partner_id.l10n_pa_ruc', readonly=False)
    l10n_pa_dv = fields.Char(related='partner_id.l10n_pa_dv', readonly=False)
    l10n_pa_tipo_contribuyente = fields.Selection(related='partner_id.l10n_pa_tipo_contribuyente', readonly=False)
    l10n_pa_razon_social = fields.Char(related='partner_id.l10n_pa_razon_social', readonly=True)
    l10n_pa_is_dgi_validated = fields.Boolean(related='partner_id.l10n_pa_is_dgi_validated', readonly=True)
    
    l10n_pa_provincia_id = fields.Many2one(related='partner_id.l10n_pa_provincia_id', readonly=False)
    l10n_pa_distrito_id = fields.Many2one(related='partner_id.l10n_pa_distrito_id', readonly=False)
    l10n_pa_corregimiento_id = fields.Many2one(related='partner_id.l10n_pa_corregimiento_id', readonly=False)

    l10n_pa_ambiente = fields.Selection([
        ('1', 'Producción'),
        ('2', 'Pruebas')
    ], string='Ambiente de Destino (DGI)', default='2', help='Seleccione el ambiente para la facturación electrónica DGI.')

    l10n_pa_sucursal_code = fields.Char(
        string="Código de Establecimiento (B071)",
        size=4,
        help="Código de establecimiento según DGI (B071) - alfanumérico de 4 caracteres",
    )
    
    l10n_pa_pto_fact = fields.Char(
        string="Punto de Facturación (AI05 / PtoFactDF)",
        size=3,
        help="Punto de facturación para el PAC (AI05 / PtoFactDF) - alfanumérico de 3 caracteres",
    )
    
    l10n_pa_coordem = fields.Char(
        string="Coordenadas Sucursal (Coordem)",
        help="Coordenadas de la sucursal (formato: +latitud,-longitud)",
    )

    l10n_pa_cod_ubi = fields.Char(
        string="Código de ubicación",
        compute="_compute_l10n_pa_cod_ubi",
        help="Código compuesto Provincia-Distrito-Corregimiento que se envía en el XML (CodUbi). Se obtiene del corregimiento seleccionado.",
    )

    @api.depends("l10n_pa_corregimiento_id", "l10n_pa_corregimiento_id.code")
    def _compute_l10n_pa_cod_ubi(self):
        for company in self:
            company.l10n_pa_cod_ubi = (
                (company.l10n_pa_corregimiento_id and company.l10n_pa_corregimiento_id.code)
                or ""
            )

    @api.constrains("l10n_pa_sucursal_code")
    def _check_l10n_pa_sucursal_code(self):
        """Valida que el código de establecimiento (B071) sea alfanumérico de 4 caracteres"""
        for rec in self:
            if rec.l10n_pa_sucursal_code:
                code = rec.l10n_pa_sucursal_code.strip()
                if len(code) != 4:
                    raise ValidationError(
                        "El Código de Establecimiento (B071) debe tener exactamente 4 caracteres alfanuméricos."
                    )
                if not code.isalnum():
                    raise ValidationError(
                        "El Código de Establecimiento (B071) debe ser alfanumérico (solo letras y números)."
                    )
    
    @api.constrains("l10n_pa_pto_fact")
    def _check_l10n_pa_pto_fact(self):
        """Valida que el punto de facturación (AI05) sea alfanumérico de 3 caracteres"""
        from odoo.exceptions import ValidationError
        for rec in self:
            if rec.l10n_pa_pto_fact:
                pto = rec.l10n_pa_pto_fact.strip()
                if len(pto) != 3:
                    raise ValidationError(
                        "El Punto de Facturación (AI05 / PtoFactDF) debe tener exactamente 3 caracteres alfanuméricos."
                    )
                if not pto.isalnum():
                    raise ValidationError(
                        "El Punto de Facturación (AI05 / PtoFactDF) debe ser alfanumérico (solo letras y números)."
                    )

    def action_get_ruc_details(self, partner=None):
        """ Base method for getting RUC details. To be overridden by PAC modules. """
        self.ensure_one()
        from odoo.exceptions import UserError
        raise UserError("La funcionalidad para obtener detalles del RUC requiere de un proveedor PAC (ej. Digifact o HKA) debidamente configurado.")
