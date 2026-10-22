# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError
import logging
from .hka_client import HKAClient

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = "account.move"

    def action_l10n_pa_send_to_pac(self):
        """
        Envía la factura a HKA.
        El JSON enviado y el error siempre quedan guardados en el tab FE (DGI)
        incluso cuando la factura queda en borrador (usando _cr.commit antes del raise).
        """
        self.ensure_one()

        company = self.company_id
        company.sudo().action_hka_get_token()
        if not company.l10n_pa_hka_url or not company.l10n_pa_hka_token:
            raise UserError(_("Debe configurar la URL y el Token de HKA en los ajustes de la compañía."))

        client = HKAClient(company.l10n_pa_hka_url, company.l10n_pa_hka_token)

        # 1. Construir JSON
        import json as _json
        try:
            payload = client.build_payload(self)
            payload_str = _json.dumps(payload, indent=2, ensure_ascii=False)
            _logger.info("HKA payload para factura %s:\n%s", self.name, payload_str)
        except UserError:
            raise
        except Exception as e:
            err_detail = str(e)
            _logger.error("Error al construir payload HKA para %s: %s", self.name, err_detail)
            raise UserError(_("Error al construir el JSON para HKA:\n%s") % err_detail)

        # 2. Guardar payload en el tab FE antes de enviar.
        #    _cr.commit() garantiza que queda en BD incluso si hay error después.
        self.write({
            "l10n_pa_pac_request": payload_str,
            "l10n_pa_pac_status": "error",
            "l10n_pa_pac_error": False,
            "l10n_pa_pac_response": False,
        })
        self._cr.commit()

        # 3. Enviar a HKA (con reintento automático si el token expiró/fue revocado: Código 212)
        try:
            response = client.send_document(payload)
            _logger.info("HKA response para factura %s:\n%s", self.name, response.get("raw_response", "(sin raw)"))
            
            # Si HKA devuelve código 212 (Token inválido o expirado), forzamos regeneración y reintentamos 1 vez
            if not response.get("success") and (
                response.get("error_code") == "212" or "212" in str(response.get("error_message") or "")
            ):
                _logger.warning(
                    "HKA devolvió Código 212 (token inválido/expirado) para factura %s. Forzando renovación y reintentando...",
                    self.name
                )
                company.sudo().action_hka_get_token(force=True)
                client = HKAClient(company.l10n_pa_hka_url, company.l10n_pa_hka_token)
                response = client.send_document(payload)
                _logger.info("HKA response reintento para factura %s:\n%s", self.name, response.get("raw_response", "(sin raw)"))
        except Exception as e:
            err_detail = str(e)
            _logger.error("Error de comunicación HKA para %s: %s", self.name, err_detail)
            self.write({
                "l10n_pa_pac_status": "error",
                "l10n_pa_pac_error": "Error de comunicación con HKA: " + err_detail,
            })
            self._cr.commit()
            raise UserError(_("Error al comunicarse con HKA: %s") % err_detail)

        # 4. Parsear respuesta
        raw_resp = response.get("raw_response", "")

        if not response.get("success"):
            error_msg = response.get("error_message", "Error desconocido de HKA")
            _logger.warning("HKA rechazó factura %s: %s | raw: %s", self.name, error_msg, raw_resp[:500])
            self.write({
                "l10n_pa_pac_status": "error",
                "l10n_pa_pac_error": error_msg,
                "l10n_pa_pac_response": raw_resp[:5000],
            })
            self._cr.commit()
            raise UserError(_("Error de HKA: %s") % error_msg)

        # 5. Éxito — escribir resultado
        self.write({
            "l10n_pa_pac_status": "accepted",
            "l10n_pa_pac_error": False,
            "l10n_pa_cufe": response.get("cufe"),
            "l10n_pa_qr_url": response.get("qr"),
            "l10n_pa_pac_response": raw_resp[:5000],
            "l10n_pa_pac_request": payload_str,
        })
        self._cr.commit()

        import re as _re
        attachment_ids = []

        # Descargar PDF (CAFE)
        pdf_res = client.download_document(self.l10n_pa_cufe, tipo_archivo="pdf")
        if pdf_res.get("success") and pdf_res.get("base64"):
            pdf_att = self.env["ir.attachment"].sudo().create({
                "name": f"{self.name}_CAFE.pdf",
                "type": "binary",
                "datas": pdf_res.get("base64"),
                "res_model": "account.move",
                "res_id": self.id,
                "res_field": "invoice_pdf_report_file",
                "mimetype": "application/pdf",
            })
            attachment_ids.append(pdf_att.id)
            self.message_main_attachment_id = pdf_att.id

            # IMPORTANTE: 'invoice_pdf_report_id' es un campo computado que
            # busca un ir.attachment por (res_model, res_id, res_field). El
            # ORM no sabe automaticamente que acabamos de crear ese adjunto
            # "por fuera" (no via el pipeline normal de account_move_send),
            # asi que su cache queda desactualizado en este mismo request.
            # Si algo despues (p.ej. pos_order.py -> _generate_and_send())
            # revisa 'invoice_pdf_report_id' antes de que se invalide, lo ve
            # vacio y genera un PDF generico de respaldo que termina
            # "ganandole" al CAFE real. Odoo mismo hace este invalidate en
            # su propio flujo equivalente (account_move_send.py,
            # _link_invoice_documents, linea ~444) justo por esta razon.
            self.invalidate_recordset(fnames=["invoice_pdf_report_id", "invoice_pdf_report_file"])
        else:
            _logger.warning("No se pudo descargar PDF CAFE para %s: %s", self.name, pdf_res.get("error_message"))

        # Descargar XML
        xml_res = client.download_document(self.l10n_pa_cufe, tipo_archivo="xml")
        if xml_res.get("success") and xml_res.get("base64"):
            xml_att = self.env["ir.attachment"].sudo().create({
                "name": f"{self.name}_CAFE.xml",
                "type": "binary",
                "datas": xml_res.get("base64"),
                "res_model": "account.move",
                "res_id": self.id,
                "mimetype": "application/xml",
            })
            attachment_ids.append(xml_att.id)
        else:
            _logger.warning("No se pudo descargar XML CAFE para %s: %s", self.name, xml_res.get("error_message"))

        if attachment_ids:
            self.message_post(
                body=_("Factura enviada exitosamente a HKA. Adjuntos: PDF y XML."),
                attachment_ids=attachment_ids,
            )

        return True

    def action_l10n_pa_download_hka_files(self):
        self.ensure_one()
        if self.l10n_pa_pac_status != 'accepted' or not self.l10n_pa_cufe:
            raise UserError(_("La factura debe estar aceptada por HKA y tener un CUFE para descargar los archivos."))
            
        company = self.company_id
        company.sudo().action_hka_get_token()
        if not company.l10n_pa_hka_url or not company.l10n_pa_hka_token:
            raise UserError(_("Debe configurar la URL y el Token de HKA en los ajustes de la compañía."))
            
        client = HKAClient(company.l10n_pa_hka_url, company.l10n_pa_hka_token)
        attachment_ids = []
        
        # Intentar PDF
        pdf_res = client.download_document(self.l10n_pa_cufe, "pdf")
        if not pdf_res.get("success") and (pdf_res.get("error_code") == "212" or "212" in str(pdf_res.get("error_message") or "")):
            company.sudo().action_hka_get_token(force=True)
            client = HKAClient(company.l10n_pa_hka_url, company.l10n_pa_hka_token)
            pdf_res = client.download_document(self.l10n_pa_cufe, "pdf")

        if pdf_res.get("success") and pdf_res.get("base64"):
            pdf_att = self.env['ir.attachment'].create({
                'name': f"{self.name}_CAFE.pdf",
                'type': 'binary',
                'datas': pdf_res.get("base64"),
                'res_model': 'account.move',
                'res_id': self.id,
                'res_field': 'invoice_pdf_report_file',
                'mimetype': 'application/pdf'
            })
            attachment_ids.append(pdf_att.id)
        else:
            raise UserError(_("Error al descargar PDF: %s") % pdf_res.get('error_message'))
            
        # Intentar XML
        xml_res = client.download_document(self.l10n_pa_cufe, "xml")
        if not xml_res.get("success") and (xml_res.get("error_code") == "212" or "212" in str(xml_res.get("error_message") or "")):
            company.sudo().action_hka_get_token(force=True)
            client = HKAClient(company.l10n_pa_hka_url, company.l10n_pa_hka_token)
            xml_res = client.download_document(self.l10n_pa_cufe, "xml")

        if xml_res.get("success") and xml_res.get("base64"):
            xml_att = self.env['ir.attachment'].create({
                'name': f"{self.name}_CAFE.xml",
                'type': 'binary',
                'datas': xml_res.get("base64"),
                'res_model': 'account.move',
                'res_id': self.id,
                'mimetype': 'application/xml'
            })
            attachment_ids.append(xml_att.id)
            
        if attachment_ids:
            self.message_post(
                body=_("Archivos descargados manualmente desde HKA."),
                attachment_ids=attachment_ids
            )
            
    def action_open_anular_wizard(self):
        self.ensure_one()
        return {
            "name": _("Anular Factura"),
            "type": "ir.actions.act_window",
            "res_model": "hka.anular.factura.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_move_id": self.id},
        }

    def action_l10n_pa_anular_pac(self):
        """
        Envía la anulación de la factura a HKA y descarga el PDF cancelado (con sello Anulado).
        """
        self.ensure_one()
        motivo = self.env.context.get("hka_anular_motivo", "Anulacion generica")

        company = self.company_id
        company.sudo().action_hka_get_token()
        if not company.l10n_pa_hka_url or not company.l10n_pa_hka_token:
            raise UserError(_(u"Debe configurar la URL y el Token de HKA en los ajustes de la compania."))

        client = HKAClient(company.l10n_pa_hka_url, company.l10n_pa_hka_token)
        response = client.anular_documento(motivo, self)
        if not response.get("success") and (response.get("error_code") == "212" or "212" in str(response.get("error_message") or "")):
            _logger.warning("HKA devolvió Código 212 en anulación. Forzando renovación de token y reintentando...")
            company.sudo().action_hka_get_token(force=True)
            client = HKAClient(company.l10n_pa_hka_url, company.l10n_pa_hka_token)
            response = client.anular_documento(motivo, self)

        if response.get("success"):
            self.l10n_pa_pac_status = 'cancelled'

            # Cancelar en Odoo (estado cancelado)
            if self.state == 'posted':
                self.button_cancel()

            attachment_ids = []

            # Descargar el PDF anulado (HKA ya incluye el sello "Anulado")
            if self.l10n_pa_cufe:
                pdf_res = client.download_document(self.l10n_pa_cufe, tipo_archivo="pdf")
                if pdf_res.get("success") and pdf_res.get("base64"):
                    # Renombrar el PDF original para que no confunda
                    old_cafes = self.env['ir.attachment'].search([
                        ('res_model', '=', 'account.move'),
                        ('res_id', '=', self.id),
                        ('name', 'ilike', '%_CAFE.pdf'),
                    ])
                    for old in old_cafes:
                        old.name = old.name.replace('_CAFE.pdf', '_CAFE_original.pdf')

                    # Adjunto del PDF cancelado como adjunto principal
                    cancelled_att = self.env['ir.attachment'].create({
                        'name': f"{self.name}_CAFE_ANULADO.pdf",
                        'type': 'binary',
                        'datas': pdf_res.get("base64"),
                        'res_model': 'account.move',
                        'res_id': self.id,
                        'mimetype': 'application/pdf',
                    })
                    attachment_ids.append(cancelled_att.id)
                    self.message_main_attachment_id = cancelled_att.id
                else:
                    _logger.warning(
                        "No se pudo descargar el PDF anulado de HKA para %s: %s",
                        self.name, pdf_res.get('error_message')
                    )

            self.message_post(
                body=_(u"Factura anulada en HKA/DGI. Motivo: %s") % motivo,
                attachment_ids=attachment_ids,
            )
        else:
            raise UserError(_(u"Error anulando en HKA: %s") % response.get("error_message"))

        return True

    def action_l10n_pa_send_email_with_cafe(self):
        """
        Abre el asistente de envío de correo con el PDF CAFE de la DGI/HKA
        en lugar del PDF generado por Odoo.
        """
        self.ensure_one()

        # Buscar el adjunto CAFE PDF de HKA
        cafe_att = self.env['ir.attachment'].search([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', self.id),
            ('name', 'ilike', '%_CAFE.pdf')
        ], limit=1)

        if not cafe_att:
            raise UserError(_(
                "No se encontró el PDF CAFE adjunto a esta factura. "
                "Por favor use el botón 'Descargar Archivos HKA' primero."
            ))

        # Obtener plantilla de correo estándar de Odoo
        template = self.env.ref('account.email_template_edi_invoice', raise_if_not_found=False)

        compose_ctx = {
            'default_model': 'account.move',
            'default_res_ids': self.ids,
            'default_composition_mode': 'comment',
            'default_email_layout_xmlid': 'mail.mail_notification_light',
            'force_email': True,
            'default_attachment_ids': [cafe_att.id],
            'mark_invoice_as_sent': True,
        }
        if template:
            compose_ctx['default_template_id'] = template.id

        return {
            'type': 'ir.actions.act_window',
            'name': _('Enviar Factura'),
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': compose_ctx,
        }

    def action_l10n_pa_send_anulado(self):
        """
        Abre el wizard de correo con el PDF CAFE ANULADO adjunto.
        Permite al usuario enviar por correo la factura anulada al cliente.
        """
        self.ensure_one()

        # Buscar el PDF anulado (guardado durante el proceso de anulación)
        anulado_att = self.env['ir.attachment'].search([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', self.id),
            ('mimetype', '=', 'application/pdf'),
            ('name', 'ilike', '%_CAFE_ANULADO%'),
        ], limit=1, order='id desc')

        # Si no hay uno específico, usar el adjunto principal PDF
        if not anulado_att:
            anulado_att = self.env['ir.attachment'].search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', self.id),
                ('mimetype', '=', 'application/pdf'),
                ('name', 'not ilike', '_CAFE_original%'),
            ], limit=1, order='id desc')

        if not anulado_att:
            raise UserError(_(
                "No se encontró el PDF de la factura anulada. "
                "Es posible que la descarga desde HKA haya fallado al momento de anular."
            ))

        template = self.env.ref('account.email_template_edi_invoice', raise_if_not_found=False)

        compose_ctx = {
            'default_model': 'account.move',
            'default_res_ids': self.ids,
            'default_composition_mode': 'comment',
            'default_email_layout_xmlid': 'mail.mail_notification_light',
            'force_email': True,
            'default_attachment_ids': [anulado_att.id],
            'mark_invoice_as_sent': False,
        }
        if template:
            compose_ctx['default_template_id'] = template.id

        return {
            'type': 'ir.actions.act_window',
            'name': _('Enviar Factura Anulada'),
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': compose_ctx,
        }

    def action_l10n_pa_print_anulado(self):
        """
        Descarga o previsualiza el PDF CAFE ANULADO directamente.
        """
        self.ensure_one()

        # Buscar el PDF anulado
        anulado_att = self.env['ir.attachment'].search([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', self.id),
            ('mimetype', '=', 'application/pdf'),
            ('name', 'ilike', '%_CAFE_ANULADO%'),
        ], limit=1, order='id desc')

        # Fallback al último PDF no-original
        if not anulado_att:
            anulado_att = self.env['ir.attachment'].search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', self.id),
                ('mimetype', '=', 'application/pdf'),
                ('name', 'not ilike', '_CAFE_original%'),
            ], limit=1, order='id desc')

        if not anulado_att:
            raise UserError(_(
                "No se encontró el PDF de la factura anulada. "
                "Es posible que la descarga desde HKA haya fallado al momento de anular."
            ))

        # Abrir el PDF en nueva pestaña (puede imprimirse desde el navegador)
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{anulado_att.id}?download=false',
            'target': 'new',
        }
