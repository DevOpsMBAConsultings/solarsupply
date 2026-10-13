# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    mba_pago_cheque_a = fields.Char(string='Cheque a')
    mba_pago_beneficiario = fields.Char(string='Beneficiario')
    mba_pago_cuenta = fields.Char(string='# de cuenta')
    mba_pago_tipo_cuenta = fields.Selection(
        [('ahorros', 'Ahorros'), ('corriente', 'Corriente')],
        string='Tipo de cuenta',
    )
    mba_pago_swift = fields.Char(string='SWIFT')
    mba_pago_dir_beneficiario = fields.Text(string='Dirección del beneficiario')
    mba_pago_banco = fields.Char(string='Banco beneficiario')
    mba_pago_dir_banco = fields.Text(string='Dirección del banco')

    def _mba_render_terminos(self):
        """Arma la tabla de 2 columnas: pago/cuenta a la izquierda, direcciones a la derecha."""
        self.ensure_one()

        def fila(etiqueta, valor):
            return Markup('<strong>%s:</strong> %s<br/>') % (etiqueta, valor or '')

        tipo_cuenta = dict(self._fields['mba_pago_tipo_cuenta'].selection).get(
            self.mba_pago_tipo_cuenta)
        izquierda = (
            fila(_('Cheque a'), self.mba_pago_cheque_a)
            + fila(_('Beneficiario'), self.mba_pago_beneficiario)
            + fila(_('# de cuenta'), self.mba_pago_cuenta)
            + fila(_('Tipo de cuenta'), tipo_cuenta)
            + fila(_('SWIFT'), self.mba_pago_swift)
        )
        derecha = (
            fila(_('Dirección del beneficiario'), self.mba_pago_dir_beneficiario)
            + fila(_('Banco beneficiario'), self.mba_pago_banco)
            + fila(_('Dirección del banco'), self.mba_pago_dir_banco)
        )
        return Markup(
            '<table style="width:100%%; border-collapse:collapse;"><tr>'
            '<td style="width:50%%; vertical-align:top; padding-right:12px;">%s</td>'
            '<td style="width:50%%; vertical-align:top;">%s</td>'
            '</tr></table>'
        ) % (izquierda, derecha)

    def action_mba_generar_terminos(self):
        """Escribe la tabla en invoice_terms en TODOS los idiomas instalados.

        El campo es traducible: si solo se escribiera el valor base, una traducción
        previa (ej. editada en español desde Ajustes) taparía el valor nuevo.
        """
        langs = [code for code, _name in self.env['res.lang'].get_installed()]
        if 'en_US' in langs:
            langs.remove('en_US')
        langs.insert(0, 'en_US')  # el valor base primero
        for company in self:
            for code in langs:
                company_lang = company.with_context(lang=code)
                company_lang.invoice_terms = company_lang._mba_render_terminos()
        return True
