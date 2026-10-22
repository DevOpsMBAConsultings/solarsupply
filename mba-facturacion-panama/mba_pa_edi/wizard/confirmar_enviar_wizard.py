# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import re


class ConfirmarEnviarWizard(models.TransientModel):
    _name = 'mba_pa_edi.confirmar.enviar.wizard'
    _description = 'Wizard para Confirmar y Enviar Factura a DGI (PAC)'

    move_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    numero_df = fields.Char(
        string='Número de Documento Fiscal',
        size=10,
        help='Próximo número fiscal. Puede editarlo si es necesario antes de enviar.',
        required=True,
    )
    is_partner_unvalidated = fields.Boolean(
        string='Contacto no validado DGI',
        compute='_compute_is_partner_unvalidated',
    )

    @api.depends('move_id', 'move_id.partner_id')
    def _compute_is_partner_unvalidated(self):
        for wizard in self:
            partner = wizard.move_id.partner_id
            if partner:
                valid = getattr(partner, 'l10n_pa_is_dgi_validated', False)
                if not valid and partner.parent_id:
                    valid = getattr(partner.parent_id, 'l10n_pa_is_dgi_validated', False)
                wizard.is_partner_unvalidated = not valid
            else:
                wizard.is_partner_unvalidated = False

    # ----------------------------------------------------------
    # Default / Onchange
    # ----------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        move_id = self.env.context.get('default_move_id')
        if move_id and 'numero_df' in (fields_list or []):
            move = self.env['account.move'].browse(move_id)
            if move.exists() and move.move_type in ('out_invoice', 'out_refund'):
                # Si la factura ya tiene un número provisional (ej. reintento tras error o ya aceptada por PAC),
                # mostrarlo para que el usuario lo confirme o cambie.
                if (move.l10n_pa_pac_status in ('error', 'accepted')
                        and move.name and move.name != '/'):
                    res['numero_df'] = move.name
                else:
                    # Calcular el siguiente número disponible desde la BD
                    res['numero_df'] = move._pa_next_numero()
        return res

    @api.onchange('numero_df')
    def _onchange_numero_df(self):
        """Aviso visual si el número ya está en uso en el diario."""
        if not self.numero_df or not self.move_id:
            return
        num = self._normalize(self.numero_df)
        if not num:
            return
        existing = self.env['account.move'].search([
            ('id', '!=', self.move_id.id),
            ('journal_id', '=', self.move_id.journal_id.id),
            ('company_id', '=', self.move_id.company_id.id),
            ('name', '=', num),
        ], limit=1)
        if existing:
            return {
                'warning': {
                    'title': _('Número ya usado'),
                    'message': _(
                        'El número fiscal %s ya está en uso en la factura %s. '
                        'Elija otro número para evitar un error al confirmar.'
                    ) % (num, existing.name),
                }
            }

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def _normalize(self, value):
        """Extrae solo dígitos y rellena a 10 caracteres."""
        raw = re.sub(r'\D', '', str(value or ''))
        if not raw:
            return ''
        return raw[-10:].zfill(10)

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_enviar_factura(self):
        """
        Flujo correcto:
          1. Validar número disponible
          2. Escribir número en borrador (se revierte automáticamente si algo falla
             antes de que la factura sea persistida, al ser todo una sola transacción)
          3. Enviar al PAC PRIMERO (factura sigue en borrador)
             → Si falla → UserError → rollback → número libre, factura en borrador
          4. Si PAC OK → action_post() con skip_pac_send=True
        """
        self.ensure_one()
        move = self.move_id

        if move.state != 'draft':
            raise UserError(_('La factura ya está confirmada.'))

        num = self._normalize(self.numero_df)
        if not num or num == '0000000000':
            raise UserError(_('El número de documento fiscal no es válido.'))

        # Validación estricta de disponibilidad
        existing = self.env['account.move'].search([
            ('id', '!=', move.id),
            ('journal_id', '=', move.journal_id.id),
            ('company_id', '=', move.company_id.id),
            ('name', '=', num),
        ], limit=1)
        if existing:
            raise UserError(
                _('El número fiscal %s ya está en uso en la factura %s. '
                  'Elija otro número antes de continuar.') % (num, existing.name)
            )

        # Fecha de factura por defecto si no tiene
        if not move.invoice_date:
            move.invoice_date = fields.Date.context_today(self)

        # Reservar el número en el borrador.
        # Si action_l10n_pa_send_to_pac() falla, el ORM revierte esta escritura.
        move.write({'name': num})

        # ─── PAC PRIMERO ───────────────────────────────────────────────────────
        # Si ya fue aceptada previamente (y falló el post), no reenviar al PAC.
        if move.l10n_pa_pac_status != 'accepted':
            # Si lanza UserError o cualquier excepción, la transacción se revierte:
            # el número vuelve a '/' y la factura sigue en borrador.
            move.action_l10n_pa_send_to_pac()

        # ─── PUBLICAR EN ODOO (solo si el PAC aceptó) ──────────────────────────
        move.with_context(skip_pac_send=True).action_post()

        return {'type': 'ir.actions.act_window_close'}
