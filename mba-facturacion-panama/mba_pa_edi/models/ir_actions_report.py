import io
from collections import OrderedDict

from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        """
        Intercepción agnóstica de impresión:
        Si el documento (Factura, NC, ND) fue aceptado ante la DGI por cualquier PAC
        (l10n_pa_pac_status == 'accepted'), entrega directamente el PDF oficial (CAFE)
        almacenado en invoice_pdf_report_id / adjuntos en lugar del reporte estándar.
        """
        report = self._get_report(report_ref)
        if report.report_name in ('account.report_invoice_with_payments', 'account.report_invoice') and res_ids:
            moves = self.env['account.move'].browse(res_ids)
            collected_streams = OrderedDict()
            for move in moves:
                if getattr(move, 'l10n_pa_pac_status', False) == 'accepted':
                    att = move.invoice_pdf_report_id or self.env['ir.attachment'].search([
                        ('res_model', '=', 'account.move'),
                        ('res_id', '=', move.id),
                        ('name', 'ilike', '%_CAFE.pdf')
                    ], limit=1)
                    if att and att.raw:
                        collected_streams[move.id] = {
                            'stream': io.BytesIO(att.raw),
                            'attachment': att,
                        }
            if len(collected_streams) == len(moves):
                return collected_streams

        return super()._render_qweb_pdf_prepare_streams(report_ref, data, res_ids=res_ids)
