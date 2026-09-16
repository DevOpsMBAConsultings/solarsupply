# -*- coding: utf-8 -*-
import base64
import json
import logging
from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = "account.move"

    digifact_numero_df = fields.Char(string="Número Fiscal (DF)", copy=False, readonly=True)
    digifact_codigo_seguridad = fields.Char(string="Código de Seguridad (DF)", copy=False, readonly=True)
    digifact_pto_fact_df = fields.Char(string="Punto de Facturación (DF)", copy=False, readonly=True)

    def action_l10n_pa_send_to_pac(self):
        """
        Implementación del método de envío para Digifact.
        Recopila los datos, llama al cliente XML (NUC) y procesa la respuesta.
        """
        self.ensure_one()
        
        company = self.company_id
        if not company.df_fe_username or not company.df_fe_password:
            raise UserError(_("Debe configurar el Usuario y Contraseña de Digifact en los ajustes de la compañía."))
        
        builder = self.env["digifact.nuc.builder"]
        client = self.env["digifact.client"]
        
        # Generar XML NUC
        try:
            xml_bytes = builder.build_nuc_xml(self, allow_draft=True)
        except Exception as e:
            err_detail = str(e)
            _logger.error("Error generating NUC XML: %s", err_detail)
            self.write({
                "l10n_pa_pac_status": "error",
                "l10n_pa_pac_error": "Error al generar XML NUC: " + err_detail,
            })
            raise UserError(_("Error al generar el XML de factura electrónica: %s") % err_detail)

        # Enviar a Digifact
        self.write({
            "l10n_pa_pac_status": "error",
            "l10n_pa_pac_error": False,
            "l10n_pa_pac_response": False,
        })
        self._cr.commit()
        
        try:
            status, response = client.certificate_fe_xml_tosign_v2(
                xml_bytes,
                company=company,
                fmt="XML|PDF|HTML",
            )
        except Exception as e:
            err_detail = str(e)
            _logger.error("Error communicating with Digifact: %s", err_detail)
            self.write({
                "l10n_pa_pac_status": "error",
                "l10n_pa_pac_error": "Error de comunicación con Digifact: " + err_detail,
            })
            raise UserError(_("Error al enviar XML a Digifact: %s") % err_detail)

        # Parsear respuesta
        code = response.get("code")
        is_error = False
        if code is not None:
            try:
                is_error = int(code) != 1
            except (ValueError, TypeError):
                is_error = True
        elif response.get("Ok") is False:
            is_error = True

        response_text = ""
        try:
            response_text = json.dumps(response, indent=2, ensure_ascii=False) if isinstance(response, dict) else str(response)
        except Exception:
            response_text = str(response)

        if is_error:
            err_msg = response.get("mensaje") or response.get("message") or response.get("description") or "Error desconocido de Digifact"
            _logger.error("Digifact rejected XML. Code: %s, Message: %s, Response: %s", code, err_msg, response_text[:500])
            self.write({
                "l10n_pa_pac_status": "error",
                "l10n_pa_pac_error": err_msg,
                "l10n_pa_pac_response": response_text[:5000],
            })
            raise UserError(_("Digifact rechazó el XML: %s") % err_msg)

        # Éxito: Extraer CUFE, QR
        cufe = response.get("authNumber") or response.get("CUFE") or response.get("cufe")
        qr_url = response.get("url") or response.get("QRUrl")
        
        self.write({
            "l10n_pa_pac_status": "accepted",
            "l10n_pa_pac_error": False,
            "l10n_pa_cufe": cufe or self.l10n_pa_cufe,
            "l10n_pa_qr_url": qr_url or self.l10n_pa_qr_url,
            "l10n_pa_pac_response": response_text[:5000],
        })
        self._cr.commit()

        # Extraer Attachments
        Attachment = self.env["ir.attachment"].sudo()
        created_attachments = []
        pdf_att_id = False
        attachment_map = (
            ("responseData1", "Digifact FE XML", ".xml"),
            ("responseData2", "Digifact FE HTML", ".html"),
            ("responseData3", "Digifact FE PDF", ".pdf"),
        )
        
        for key, name, ext in attachment_map:
            data = response.get(key) or response.get(key.replace("Data", "data"))
            if not data:
                data = response.get("XML" if "xml" in ext else "PDF" if "pdf" in ext else "HTML")
            if not data:
                continue
            if isinstance(data, str) and data.startswith("data:"):
                data = data.split(",", 1)[-1] if "," in data else None
            if isinstance(data, str):
                try:
                    data = base64.b64decode(data)
                except Exception:
                    continue
            if not data:
                continue
            
            att = Attachment.create({
                "name": "%s %s%s" % (name, self.name or self.id, ext),
                "datas": base64.b64encode(data) if isinstance(data, bytes) else data,
                "res_model": self._name,
                "res_id": self.id,
                "res_field": "invoice_pdf_report_file" if ext == ".pdf" else False,
                "type": "binary",
                "mimetype": "application/xml" if ext == ".xml" else "application/pdf" if ext == ".pdf" else "text/html",
            })
            created_attachments.append(att.id)
            if ext == ".pdf":
                pdf_att_id = att.id

        if pdf_att_id:
            self.message_main_attachment_id = pdf_att_id
            self.invalidate_recordset(fnames=["invoice_pdf_report_id", "invoice_pdf_report_file"])

        if created_attachments:
            self.message_post(
                body=_("Factura autorizada exitosamente por Digifact (DGI). Adjuntos: PDF y XML."),
                attachment_ids=created_attachments,
            )

        return True
