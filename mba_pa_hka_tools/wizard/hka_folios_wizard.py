# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.mba_pa_edi_hka.models.hka_client import HKAClient



class HKAFoliosWizard(models.TransientModel):
    _name = 'hka.folios.wizard'
    _description = 'Consulta de Folios Restantes HKA'

    status_message = fields.Char(string='Estado Conexión', readonly=True)
    is_success = fields.Boolean(string='Consulta Exitosa', readonly=True)
    licencia = fields.Char(string='Licencia', readonly=True)
    fecha_licencia = fields.Char(string='Vencimiento Licencia', readonly=True)
    ciclo = fields.Char(string='Ciclo', readonly=True)
    fecha_ciclo = fields.Char(string='Fecha Ciclo', readonly=True)
    folios_totales_disponibles = fields.Char(string='Folios Totales Disponibles', readonly=True)
    folios_disponibles_ciclo = fields.Char(string='Folios Disponibles en Ciclo', readonly=True)
    folios_utilizados_ciclo = fields.Char(string='Folios Utilizados en Ciclo', readonly=True)
    folios_totales_ciclo = fields.Char(string='Folios Totales del Ciclo', readonly=True)
    folios_totales = fields.Char(string='Folios Totales', readonly=True)
    error_message = fields.Text(string='Detalle de Error', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        try:
            company.action_hka_get_token()
            if not company.l10n_pa_hka_url or not company.l10n_pa_hka_token:
                res.update({
                    'is_success': False,
                    'status_message': _('Error: URL o Token de HKA no configurados en los Ajustes de la Empresa.'),
                    'error_message': _('Debe configurar las credenciales de HKA Panamá en los ajustes de la empresa.')
                })
                return res

            client = HKAClient(company.l10n_pa_hka_url, company.l10n_pa_hka_token)
            result = client.get_folios_restantes()

            if result.get('success'):
                res.update({
                    'is_success': True,
                    'status_message': _('Consulta realizada exitosamente.'),
                    'licencia': result.get('licencia'),
                    'fecha_licencia': result.get('fecha_licencia'),
                    'ciclo': result.get('ciclo'),
                    'fecha_ciclo': result.get('fecha_ciclo'),
                    'folios_totales_disponibles': result.get('folios_totales_disponibles'),
                    'folios_disponibles_ciclo': result.get('folios_disponibles_ciclo'),
                    'folios_utilizados_ciclo': result.get('folios_utilizados_ciclo'),
                    'folios_totales_ciclo': result.get('folios_totales_ciclo'),
                    'folios_totales': result.get('folios_totales'),
                })
            else:
                res.update({
                    'is_success': False,
                    'status_message': _('Respuesta de error emitida por HKA.'),
                    'error_message': result.get('error_message'),
                })
        except Exception as e:
            res.update({
                'is_success': False,
                'status_message': _('Error al conectar con HKA.'),
                'error_message': str(e),
            })

        return res

    def action_refresh(self):
        self.ensure_one()
        company = self.env.company
        try:
            company.action_hka_get_token()
            if not company.l10n_pa_hka_url or not company.l10n_pa_hka_token:
                self.write({
                    'is_success': False,
                    'status_message': _('Error: URL o Token de HKA no configurados en los Ajustes de la Empresa.'),
                    'error_message': _('Debe configurar las credenciales de HKA Panamá en los ajustes de la empresa.')
                })
            else:
                client = HKAClient(company.l10n_pa_hka_url, company.l10n_pa_hka_token)
                result = client.get_folios_restantes()

                if result.get('success'):
                    self.write({
                        'is_success': True,
                        'status_message': _('Consulta actualizada exitosamente.'),
                        'licencia': result.get('licencia'),
                        'fecha_licencia': result.get('fecha_licencia'),
                        'ciclo': result.get('ciclo'),
                        'fecha_ciclo': result.get('fecha_ciclo'),
                        'folios_totales_disponibles': result.get('folios_totales_disponibles'),
                        'folios_disponibles_ciclo': result.get('folios_disponibles_ciclo'),
                        'folios_utilizados_ciclo': result.get('folios_utilizados_ciclo'),
                        'folios_totales_ciclo': result.get('folios_totales_ciclo'),
                        'folios_totales': result.get('folios_totales'),
                        'error_message': False,
                    })
                else:
                    self.write({
                        'is_success': False,
                        'status_message': _('Respuesta de error emitida por HKA.'),
                        'error_message': result.get('error_message'),
                    })
        except Exception as e:
            self.write({
                'is_success': False,
                'status_message': _('Error al conectar con HKA.'),
                'error_message': str(e),
            })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hka.folios.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
