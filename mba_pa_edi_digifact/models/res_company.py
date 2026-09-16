# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError

class ResCompany(models.Model):
    _inherit = 'res.company'

    df_fe_environment = fields.Selection([
        ('test', 'Pruebas'),
        ('prod', 'Producción'),
    ], string='Ambiente (Digifact)', default='test', required=True)
    df_fe_username = fields.Char(string='Usuario (Digifact)')
    df_fe_password = fields.Char(string='Contraseña (Digifact)')
    digifact_token = fields.Char(string='Token Digifact', readonly=True, help="Token de autenticación provisto por Digifact.")
    digifact_token_expires_at = fields.Datetime(string='Token Digifact Expira', readonly=True)
    digifact_api_base_url = fields.Char(
        string='URL Digifact',
        compute='_compute_digifact_api_base_url',
        readonly=True,
        help="URL base de la API de Digifact (se actualiza según el ambiente)",
    )

    @property
    def digifact_user(self):
        """Compatibilidad con métodos que invocan company.digifact_user"""
        return self.df_fe_username

    @api.depends('df_fe_environment')
    def _compute_digifact_api_base_url(self):
        for rec in self:
            if rec.df_fe_environment == 'prod':
                rec.digifact_api_base_url = "https://apinuc.digifact.com.pa/api"
            else:
                rec.digifact_api_base_url = "https://testnucpa.digifact.com/api"

    def action_get_ruc_details(self, partner=None):
        """ Override of base action to get RUC details from Digifact """
        self.ensure_one()
        # Ensure credentials
        if not self.df_fe_username or not self.df_fe_password:
            msg = "Por favor configure las credenciales de Digifact (Usuario y Contraseña) en la pestaña FE (DGI-ADMIN)."
            if partner:
                return partner._dgi_notification_error("Configuración faltante", msg)
            raise UserError(msg)

        target = partner if partner else self
        vat_value = target.vat or ""
        if not vat_value:
            msg = "Por favor ingrese el RUC en el campo NIF/VAT antes de obtener los detalles."
            if partner:
                return partner._dgi_notification_error("Validación incompleta", msg)
            raise UserError(msg)

        ruc = vat_value.strip()

        try:
            self.action_digifact_get_token()
            client = self.env["digifact.client"]
            
            data = None
            for tipo in [2, 1]:
                try:
                    status, payload = client.get_info_ruc(ruc=ruc, tipo=tipo, company=self)
                    if payload and payload.get("Ok") is True:
                        data = payload
                        break
                except Exception:
                    continue
            
            if not data:
                msg = f"El RUC {ruc} no fue encontrado o es inválido en Digifact."
                if partner:
                    return partner._dgi_notification_error("Error al consultar", msg)
                raise UserError(msg)
            
            dv = data.get("DV") or data.get("Dv") or data.get("dv") or data.get("DigitoVerificador")
            razon_social = data.get("RazonSocial") or data.get("Razon_Social") or data.get("RazonSocialFE") or data.get("Nombre") or data.get("name")
            tipo_ruc = str(data.get("TipoRuc") or data.get("TipoRUC") or data.get("TipoEmpresa") or "").strip()
            
            vals = {}
            if not partner:
                vals["l10n_pa_ruc"] = ruc
                
            if dv and str(dv).strip():
                import re
                digits = re.sub(r"\D", "", str(dv).strip())
                vals["l10n_pa_dv"] = digits.zfill(2)[-2:] if digits else False
            else:
                vals["l10n_pa_dv"] = False
            
            if tipo_ruc in ("1", "2"):
                vals["l10n_pa_tipo_contribuyente"] = tipo_ruc
                
            if razon_social:
                vals["l10n_pa_razon_social"] = str(razon_social).strip()
                
            if partner:
                vals["l10n_pa_is_dgi_validated"] = True
                
            if partner:
                partner.write(vals)
                tipo_str = "Persona Natural" if tipo_ruc == "1" else ("Persona Jurídica" if tipo_ruc == "2" else "Desconocido")
                partner.message_post(
                    body=f"✅ <b>Validación DGI completada mediante Digifact</b><br/>DV: {vals.get('l10n_pa_dv') or 'N/A'}<br/>Razón Social: {razon_social or 'No devuelta'}<br/>Tipo DGI: {tipo_str}<br/><i>ℹ️ Esta información ha sido guardada y será la que se utilice oficialmente al confirmar la factura.</i>",
                    message_type="comment",
                    subtype_xmlid="mail.mt_note",
                )
            else:
                self.partner_id.write(vals)

            tipo_str_notif = "Persona Natural" if tipo_ruc == "1" else ("Persona Jurídica" if tipo_ruc == "2" else "Desconocido")
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Éxito",
                    "message": f"Los detalles del RUC {ruc} se obtuvieron correctamente desde Digifact. Razón Social: {razon_social or 'No devuelta'} | Tipo DGI: {tipo_str_notif}",
                    "type": "success",
                    "sticky": False,
                },
            }
        except UserError:
            raise
        except Exception as e:
            msg = f"Error al obtener los detalles del RUC: {str(e)}"
            if partner:
                return partner._dgi_notification_error("Error", msg)
            raise UserError(msg)

    def action_digifact_get_token(self):
        self.ensure_one()
        if not self.df_fe_username or not self.df_fe_password:
            raise UserError("Por favor configure las credenciales de Digifact (Usuario y Contraseña).")
        
        try:
            client = self.env["digifact.client"]
            token_data = client.get_token(username=self.df_fe_username, password=self.df_fe_password, company=self)
            
            if not token_data:
                raise UserError("No se pudo obtener el token de Digifact. Verifique las credenciales.")
            
            self.write({
                "digifact_token": token_data.get("token"),
                "digifact_token_expires_at": token_data.get("expires_at"),
            })

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Éxito",
                    "message": "Token de Digifact obtenido correctamente.",
                    "type": "success",
                    "sticky": False,
                },
            }
        except Exception as e:
            raise UserError(f"Error al obtener el token: {str(e)}")

    def action_digifact_test_connection(self):
        self.ensure_one()
        self.action_digifact_get_token()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Conexión Exitosa",
                "message": "La conexión con Digifact se estableció correctamente.",
                "type": "success",
                "sticky": False,
            },
        }
