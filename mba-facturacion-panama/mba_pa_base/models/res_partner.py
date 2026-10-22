# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_pa_tipo_contribuyente = fields.Selection([
        ('1', 'Natural'),
        ('2', 'Jurídico')
    ], string='Tipo de Contribuyente (DGI)')
    
    l10n_pa_receptor_tipo = fields.Selection(
        selection=[
            ("02", "Consumidor Final"),
            ("01", "Contribuyente"),
            ("04", "Extranjero"),
            ("03", "Gobierno"),
        ],
        string="Tipo de Receptor (DGI)",
    )

    # UI-only selectors (to show only the valid options per company_type)
    l10n_pa_receptor_tipo_company_ui = fields.Selection(
        selection=[("01", "Contribuyente"), ("03", "Gobierno"), ("04", "Extranjero")],
        string="Tipo de Receptor (DGI)",
        compute="_compute_receptor_ui",
        inverse="_inverse_receptor_company_ui",
        store=False,
    )

    l10n_pa_receptor_tipo_person_ui = fields.Selection(
        selection=[
            ("01", "Contribuyente"),
            ("02", "Consumidor Final"),
            ("04", "Extranjero"),
        ],
        string="Tipo de Receptor (DGI)",
        compute="_compute_receptor_ui",
        inverse="_inverse_receptor_person_ui",
        store=False,
    )

    @api.depends("l10n_pa_receptor_tipo", "company_type")
    def _compute_receptor_ui(self):
        for rec in self:
            rec.l10n_pa_receptor_tipo_company_ui = False
            rec.l10n_pa_receptor_tipo_person_ui = False

            if rec.company_type == "company" and rec.l10n_pa_receptor_tipo in ("01", "03", "04"):
                rec.l10n_pa_receptor_tipo_company_ui = rec.l10n_pa_receptor_tipo
            elif rec.company_type == "person" and rec.l10n_pa_receptor_tipo in ("01", "02", "04"):
                rec.l10n_pa_receptor_tipo_person_ui = rec.l10n_pa_receptor_tipo

    def _inverse_receptor_company_ui(self):
        for rec in self:
            if rec.l10n_pa_receptor_tipo_company_ui:
                rec.l10n_pa_receptor_tipo = rec.l10n_pa_receptor_tipo_company_ui
                
    def _inverse_receptor_person_ui(self):
        for rec in self:
            if rec.l10n_pa_receptor_tipo_person_ui:
                rec.l10n_pa_receptor_tipo = rec.l10n_pa_receptor_tipo_person_ui
                    
    @api.onchange("company_type")
    def _onchange_company_type_reset_receptor(self):
        """
        When toggling Person/Company, reset CI01 so user must pick again.
        Also clear UI helpers so the displayed dropdown matches cleanly.
        Preserves Extranjero (04) if country is foreign or already 04.
        """
        for rec in self:
            if rec.l10n_pa_receptor_tipo == "04" or (rec.country_id and rec.country_id.code != "PA"):
                rec.l10n_pa_receptor_tipo = "04"
                if rec.company_type == "company":
                    rec.l10n_pa_receptor_tipo_company_ui = "04"
                else:
                    rec.l10n_pa_receptor_tipo_person_ui = "04"
                continue
            rec.l10n_pa_receptor_tipo = False
            rec.l10n_pa_receptor_tipo_company_ui = False
            rec.l10n_pa_receptor_tipo_person_ui = False

    @api.onchange("country_id")
    def _onchange_country_id_receptor(self):
        """
        When country changes:
        - If NOT Panama: set to Extranjero (04) and clear Panama location fields.
        - If Panama: default back to Contribuyente (01) for company or Consumidor Final (02) for person.
        """
        for rec in self:
            if rec.country_id and rec.country_id.code != "PA":
                rec.l10n_pa_receptor_tipo = "04"
                rec.l10n_pa_receptor_tipo_company_ui = "04"
                rec.l10n_pa_receptor_tipo_person_ui = "04"
                rec.l10n_pa_provincia_id = False
                rec.l10n_pa_distrito_id = False
                rec.l10n_pa_corregimiento_id = False
            elif rec.country_id and rec.country_id.code == "PA":
                if rec.l10n_pa_receptor_tipo == "04":
                    default_rec = "01" if rec.company_type == "company" else "02"
                    rec.l10n_pa_receptor_tipo = default_rec
                    rec.l10n_pa_receptor_tipo_company_ui = default_rec if rec.company_type == "company" else False
                    rec.l10n_pa_receptor_tipo_person_ui = default_rec if rec.company_type == "person" else False

    @api.onchange("l10n_pa_receptor_tipo_company_ui", "l10n_pa_receptor_tipo_person_ui")
    def _onchange_receptor_ui_clear_panama(self):
        for rec in self:
            selected = rec.l10n_pa_receptor_tipo_company_ui if rec.company_type == "company" else rec.l10n_pa_receptor_tipo_person_ui
            if selected == "04":
                rec.l10n_pa_provincia_id = False
                rec.l10n_pa_distrito_id = False
                rec.l10n_pa_corregimiento_id = False

    l10n_pa_ruc = fields.Char(string='RUC / Cédula (DGI)', help='Número de identificación fiscal de la DGI.')
    l10n_pa_razon_social = fields.Char(string='Razón Social (DGI)', readonly=True, help='Nombre legal o razón social validado por la DGI.')
    l10n_pa_dv = fields.Char(string='Dígito Verificador (DV)', size=2)

    l10n_pa_provincia_id = fields.Many2one('dgi.provincia', string='Provincia')
    l10n_pa_distrito_id = fields.Many2one('dgi.distrito', string='Distrito')
    l10n_pa_corregimiento_id = fields.Many2one('dgi.corregimiento', string='Corregimiento')

    # Campo técnico para saber si ya se procesaron los datos DGI de este contacto
    l10n_pa_is_dgi_validated = fields.Boolean(string="Validado por DGI", default=False)

    def _dgi_notification_error(self, title, message):
        """Unified error feedback: sticky notification, red (danger), no reload."""
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": "danger",
                "sticky": True,
            },
        }

    def action_validate_dgi(self):
        return self._dgi_notification_error(
            'Conector faltante',
            'Para validar los datos con la DGI debe instalar y configurar el módulo de Facturación Electrónica con el conector de su proveedor PAC (Ej. The Factory HKA o Digifact).'
        )
