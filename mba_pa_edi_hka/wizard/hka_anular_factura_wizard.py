# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

class HKAAnularFacturaWizard(models.TransientModel):
    _name = "hka.anular.factura.wizard"
    _description = "Anulación de factura electrónica (HKA)"

    move_id = fields.Many2one(
        "account.move",
        string="Factura",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    cufe = fields.Char(
        string="Autorización (CUFE)",
        related="move_id.l10n_pa_cufe",
        readonly=True,
    )
    motivo = fields.Text(
        string="Motivo de anulación",
        required=True,
        help="Indique el motivo por el cual se anula este documento ante HKA/DGI.",
    )

    def action_anular(self):
        """Envía la anulación a HKA con el motivo indicado y cierra el asistente."""
        self.ensure_one()
        motivo = (self.motivo or "").strip()
        if not motivo:
            raise UserError(_("Debe indicar el motivo de anulación."))
        if len(motivo) < 15:
            raise UserError(_("El motivo de anulación debe tener al menos 15 caracteres (tiene %d).") % len(motivo))

        self.move_id.with_context(hka_anular_motivo=motivo).action_l10n_pa_anular_pac()
        return {"type": "ir.actions.act_window_close"}
