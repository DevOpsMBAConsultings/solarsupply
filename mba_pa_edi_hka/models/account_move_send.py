# -*- coding: utf-8 -*-
from odoo import models


class AccountMoveSend(models.AbstractModel):
    """
    Inyecta el PDF CAFE de la DGI (HKA) en el wizard de envío de correo
    en lugar del PDF generado por Odoo, cuando la factura está aceptada por el PAC.
    """
    _inherit = "account.move.send"

    def _get_invoice_extra_attachments(self, move):
        """
        Devuelve el adjunto CAFE PDF de HKA si la factura está aceptada.
        Este método es usado por Odoo para incluir adjuntos adicionales en el wizard de envío.
        """
        if (
            move.move_type in ("out_invoice", "out_refund")
            and getattr(move, "l10n_pa_pac_status", None) == "accepted"
        ):
            cafe_att = self.env["ir.attachment"].search([
                ("res_model", "=", "account.move"),
                ("res_id", "=", move.id),
                ("name", "ilike", "%_CAFE.pdf"),
            ], limit=1)
            if cafe_att:
                return cafe_att
        return super()._get_invoice_extra_attachments(move)

    def _get_placeholder_mail_attachments_data(self, move, **kwargs):
        """
        Evita que Odoo muestre un placeholder genérico de PDF cuando ya tenemos
        el CAFE PDF de HKA adjunto.

        Se aceptan **kwargs y se reenvían tal cual a super() para no romper el
        override si el core de Odoo 18 cambia la firma del método (p. ej. añade
        o quita 'pdf_report' entre versiones menores).
        """
        if (
            move.move_type in ("out_invoice", "out_refund")
            and getattr(move, "l10n_pa_pac_status", None) == "accepted"
        ):
            cafe_att = self.env["ir.attachment"].search([
                ("res_model", "=", "account.move"),
                ("res_id", "=", move.id),
                ("name", "ilike", "%_CAFE.pdf"),
            ], limit=1)
            if cafe_att:
                return []
        return super()._get_placeholder_mail_attachments_data(move, **kwargs)
