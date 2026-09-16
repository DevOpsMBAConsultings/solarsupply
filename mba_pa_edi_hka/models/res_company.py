# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError

class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_pa_hka_ambiente = fields.Selection([
        ('test', 'Pruebas'),
        ('prod', 'Producción'),
    ], string='Ambiente (HKA)', default='test', required=True)
    l10n_pa_hka_token = fields.Char(string='Token HKA', help="Token de autenticación provisto por The Factory HKA.")
    l10n_pa_hka_token_expires_at = fields.Datetime(string='Token HKA Expira')
    l10n_pa_hka_url = fields.Char(string='URL HKA', compute='_compute_l10n_pa_hka_url', help="URL base de la API de HKA (se actualiza según el ambiente)")
    
    l10n_pa_hka_user = fields.Char(string='Usuario (HKA)')
    l10n_pa_hka_password = fields.Char(string='Contraseña (HKA)')

    @api.depends('l10n_pa_hka_ambiente')
    def _compute_l10n_pa_hka_url(self):
        for rec in self:
            if rec.l10n_pa_hka_ambiente == 'prod':
                rec.l10n_pa_hka_url = "https://integracion.thefactoryhka.com.pa/api"
            else:
                rec.l10n_pa_hka_url = "https://demointegracion.thefactoryhka.com.pa/api"

    def action_hka_get_token(self, force=False):
        self.ensure_one()
        
        # Validación de expiración para evitar bloqueos:
        # Si tenemos token y aún le quedan más de 5 minutos de validez (y no es forzado), no renovamos.
        if not force and self.l10n_pa_hka_token and self.l10n_pa_hka_token_expires_at:
            from datetime import datetime, timedelta
            if self.l10n_pa_hka_token_expires_at > (datetime.now() + timedelta(minutes=5)):
                import logging
                logging.getLogger(__name__).debug("Token de HKA aún válido para compañía %s", self.name)
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Token Válido",
                        "message": "El token actual aún es válido y no necesita renovación.",
                        "type": "info",
                        "sticky": False,
                    },
                }

        if not self.l10n_pa_hka_user or not self.l10n_pa_hka_password:
            raise UserError("Por favor configure las credenciales de HKA (Usuario y Contraseña).")
        
        url = f"{self.l10n_pa_hka_url.rstrip('/')}/Autenticacion" if self.l10n_pa_hka_url else "https://testnucpa.thefactoryhka.com.pa/api/Autenticacion"
        
        try:
            import requests
            response = requests.post(url, json={
                "usuario": self.l10n_pa_hka_user,
                "clave": self.l10n_pa_hka_password
            }, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data and data.get("codigo") == "200" and data.get("token"):
                from datetime import datetime
                # Example: "2026-06-27T16:40:37.3804474Z"
                expires_str = data.get("expiracion", "")
                expires_at = False
                if expires_str:
                    try:
                        # Parsing ISO 8601 string safely
                        expires_at = datetime.fromisoformat(expires_str.replace('Z', '+00:00')).replace(tzinfo=None)
                    except ValueError:
                        expires_at = False

                self.write({
                    "l10n_pa_hka_token": data.get("token"),
                    "l10n_pa_hka_token_expires_at": expires_at
                })
                
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Éxito",
                        "message": "Token HKA obtenido correctamente.",
                        "type": "success",
                        "sticky": False,
                    },
                }
            else:
                raise UserError(f"Error obteniendo token: {data.get('mensaje', 'Desconocido')}")
        except Exception as e:
            raise UserError(f"Error al obtener el token de HKA: {str(e)}")

    def action_hka_test_connection(self):
        self.ensure_one()
        self.action_hka_get_token()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Conexión Exitosa",
                "message": "La conexión con The Factory HKA se estableció correctamente.",
                "type": "success",
                "sticky": False,
            },
        }

    def action_get_ruc_details(self, partner=None):
        """ Override of base action to get RUC details from HKA """
        self.ensure_one()
        import requests
        import re

        target = partner if partner else self
        vat_value = target.vat or ""
        if not vat_value:
            msg = "Por favor ingrese el RUC en el campo NIF/VAT antes de obtener los detalles."
            if partner:
                return partner._dgi_notification_error("Validación incompleta", msg)
            raise UserError(msg)
            
        ruc = vat_value.strip()

        if not self.l10n_pa_hka_user or not self.l10n_pa_hka_password:
            msg = "Por favor configure las credenciales de HKA (Usuario y Contraseña) en la pestaña FE (DGI-ADMIN) de la Compañía."
            if partner:
                return partner._dgi_notification_error("Configuración faltante", msg)
            raise UserError(msg)

        try:
            self.sudo().action_hka_get_token()
            
            url = f"{self.l10n_pa_hka_url}/ConsultaRucDv"
            headers = {
                'Authorization': f'Bearer {self.l10n_pa_hka_token}',
                'Content-Type': 'application/json'
            }
            
            last_error_msg = ""
            success_data = None
            
            # HKA requiere el tipoRuc en la consulta, pero no lo sabemos a priori.
            # Intentamos con 1 (Jurídico) y 2 (Natural)
            token_renewed = False
            for tipo in ("1", "2"):
                payload = {"ruc": ruc, "tipoRuc": tipo}
                try:
                    response = requests.post(url, json=payload, headers=headers, timeout=20)
                    if response.status_code == 200:
                        data = response.json()
                        codigo_resp = str(data.get("codigo", ""))
                        if codigo_resp == "212" and not token_renewed:
                            # Token expirado o revocado, renovar y reintentar
                            token_renewed = True
                            self.sudo().action_hka_get_token(force=True)
                            headers['Authorization'] = f'Bearer {self.l10n_pa_hka_token}'
                            response = requests.post(url, json=payload, headers=headers, timeout=20)
                            data = response.json()
                            codigo_resp = str(data.get("codigo", ""))

                        if codigo_resp == "200" and data.get("infoRuc"):
                            success_data = data["infoRuc"]
                            # Si funcionó con este tipo, usamos este tipo si no viene en la respuesta
                            if not success_data.get("tipoRuc"):
                                success_data["tipoRuc"] = tipo
                            break
                        else:
                            last_error_msg = data.get("mensaje", "Respuesta inválida o RUC no encontrado por HKA.")
                    elif response.status_code == 401 and not token_renewed:
                        token_renewed = True
                        self.sudo().action_hka_get_token(force=True)
                        headers['Authorization'] = f'Bearer {self.l10n_pa_hka_token}'
                        response = requests.post(url, json=payload, headers=headers, timeout=20)
                        if response.status_code == 200:
                            data = response.json()
                            if str(data.get("codigo")) == "200" and data.get("infoRuc"):
                                success_data = data["infoRuc"]
                                if not success_data.get("tipoRuc"):
                                    success_data["tipoRuc"] = tipo
                                break
                            else:
                                last_error_msg = data.get("mensaje", "Respuesta inválida o RUC no encontrado por HKA.")
                        else:
                            last_error_msg = f"Error HTTP {response.status_code}"
                    else:
                        last_error_msg = f"Error HTTP {response.status_code}"
                except requests.exceptions.RequestException as e:
                    last_error_msg = str(e)
            
            if not success_data:
                msg = f"No se pudo obtener la información del RUC. HKA respondió: {last_error_msg}"
                if partner:
                    return partner._dgi_notification_error("Error al consultar", msg)
                raise UserError(msg)
                
            dv = success_data.get("dv")
            razon_social = success_data.get("razonSocial")
            tipo_ruc = str(success_data.get("tipoRuc") or "").strip()
            
            vals = {}
            if not partner:
                vals["l10n_pa_ruc"] = ruc
                
            if dv is not None and str(dv).strip():
                digits = re.sub(r"\D", "", str(dv).strip())
                vals["l10n_pa_dv"] = digits.zfill(2)[-2:] if digits else False
            else:
                vals["l10n_pa_dv"] = False
                
            # Asignar tipo si la vista o modelo lo soporta, el partner base usa company_type, l10n_pa_tipo_contribuyente
            vals["l10n_pa_tipo_contribuyente"] = tipo_ruc if tipo_ruc in ("1", "2") else False
            
            if razon_social:
                vals["l10n_pa_razon_social"] = str(razon_social).strip()
            
            vals["l10n_pa_is_dgi_validated"] = True
            
            if partner:
                partner.write(vals)
            else:
                self.partner_id.write(vals)
            
            if partner:
                tipo_str = "Persona Natural" if tipo_ruc == "1" else ("Persona Jurídica" if tipo_ruc == "2" else "Desconocido")
                partner.message_post(
                    body=f"✅ <b>Validación DGI completada mediante HKA</b><br/>DV: {vals.get('l10n_pa_dv') or 'N/A'}<br/>Razón Social: {razon_social or 'No devuelta'}<br/>Tipo DGI: {tipo_str}<br/><i>ℹ️ Esta información ha sido guardada y será la que se utilice oficialmente al confirmar la factura.</i>",
                    message_type="comment",
                    subtype_xmlid="mail.mt_note",
                )
            
            # Use tipo_str for notification too, define it if partner was None
            tipo_str_notif = "Persona Natural" if tipo_ruc == "1" else ("Persona Jurídica" if tipo_ruc == "2" else "Desconocido")
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Éxito",
                    "message": f"Detalles actualizados correctamente. Razón Social: {razon_social or 'No devuelta'} | Tipo DGI: {tipo_str_notif}",
                    "type": "success",
                    "sticky": False,
                },
            }
            
        except requests.exceptions.RequestException as e:
            msg = f"Error de conexión con la API de HKA: {str(e)}"
            if partner:
                return partner._dgi_notification_error("Error de red", msg)
            raise UserError(msg)
