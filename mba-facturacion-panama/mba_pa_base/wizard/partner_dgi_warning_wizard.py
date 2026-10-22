# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class PartnerDgiWarningWizard(models.TransientModel):
    _name = 'partner.dgi.warning.wizard'
    _description = 'Advertencia de Contacto no Validado con DGI'

    partner_name = fields.Char(string='Nombre del Contacto')
    message_type = fields.Selection([
        ('sale', 'Cotización'),
        ('invoice', 'Factura')
    ], default='sale')

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}
