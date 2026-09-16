# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re

class ResPartner(models.Model):
    _inherit = 'res.partner'

    # =========================================================
    # DGI – FORMA DE PAGO
    # =========================================================
    
    def _format_panama_phone(self, phone_str, country):
        """
        FE phone formatting ONLY:
        - If Panama: just remove +507 / 507 and keep the rest as-is.
        - If not Panama: return +<digits> (without modifying partner.phone/mobile).
        """
        if not phone_str:
            return False

        raw = (phone_str or "").strip()
        digits = re.sub(r"\D+", "", raw)
        if not digits:
            return raw

        # Panama logic
        if country and country.code == "PA":
            if raw.startswith("+507"):
                return raw.replace("+507", "", 1).strip()
            if raw.startswith("507"):
                return raw.replace("507", "", 1).strip()
            if digits.startswith("507"):
                return digits[3:]
            return raw

        # Non-Panama → keep international style
        if raw.startswith("+"):
            return raw
        return f"+{digits}"

    def _format_dgi_phone_any_country(self, phone_str):
        """
        Formats phone to one of:
        - 999-9999 (7)
        - 9999-9999 (8)
        - 999999-9999 (10)
        - 999999-999-9999 (13)
        - 999999-9999-9999 (14)
        """
        if not phone_str:
            return False

        digits = re.sub(r"\D+", "", (phone_str or "").strip())
        if not digits:
            return False

        # pad small inputs
        if len(digits) < 7:
            digits = digits.ljust(7, "0")

        # normalize length to supported buckets
        if len(digits) == 7:
            return f"{digits[:3]}-{digits[3:]}"
        if len(digits) == 8:
            return f"{digits[:4]}-{digits[4:]}"
        if len(digits) == 10:
            return f"{digits[:6]}-{digits[6:]}"
        if len(digits) == 13:
            return f"{digits[:6]}-{digits[6:9]}-{digits[9:]}"
        if len(digits) == 14:
            return f"{digits[:6]}-{digits[6:10]}-{digits[10:]}"

        # If 9 -> pad to 10, 11-12 -> pad to 13, >14 -> trim to 14
        if len(digits) == 9:
            digits = digits.ljust(10, "0")
            return f"{digits[:6]}-{digits[6:]}"
        if len(digits) in (11, 12):
            digits = digits.ljust(13, "0")
            return f"{digits[:6]}-{digits[6:9]}-{digits[9:]}"
        if len(digits) > 14:
            digits = digits[:14]
            return f"{digits[:6]}-{digits[6:10]}-{digits[10:]}"

        # fallback
        digits = digits[:7].ljust(7, "0")
        return f"{digits[:3]}-{digits[3:]}"
        
    dgi_payment_method_id = fields.Many2one(
        "dgi.payment.method", string="Método de Pago (DGI)",
        tracking=True,
        help="En blanco por defecto. Seleccione Términos de pago (Ventas y compras) o elija aquí.",
    )

    dgi_payment_method_code = fields.Char(
        related="dgi_payment_method_id.code",
        string="Código Método de Pago (DGI)",
        readonly=True,
    )

    dgi_payment_method_other_desc = fields.Char(
        string="Descripción de forma de pago",
        help="Obligatorio si la forma de pago es '99 - Otro'.",
        tracking=True,
    )

    dgi_payment_term_type = fields.Selection(
        selection=[("contado", "Contado"), ("credito", "Crédito/Plazo")],
        string="Plazos", required=False, tracking=True,
        help="En blanco por defecto. Seleccione Términos de pago (Ventas y compras) o elija aquí.",
    )

    dgi_plazo_option = fields.Selection(
        selection=[("30", "30 días"), ("60", "60 días"), ("90", "90 días"), ("other", "Otro")],
        string="Plazo", default="30", tracking=True,
    )

    dgi_payment_notes = fields.Text(string="Notas complementarias", tracking=True)

    def _dgi_payment_vals_from_payment_term(self, payment_term):
        """
        Map Odoo payment term (Ventas → Términos de pago) to DGI defaults.
        """
        if not payment_term or not payment_term.name:
            return None
        name = (payment_term.name or "").strip().lower()
        if not name:
            return None
            
        Method = self.env["dgi.payment.method"]
        
        if "efectivo" in name:
            m = Method.search([("code", "=", "02")], limit=1)
            return {"dgi_payment_term_type": "contado", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "30"}
        if "crédito a 30" in name or "credito a 30" in name or ("30 días" in name and "crédito" in name):
            m = Method.search([("code", "=", "01")], limit=1)
            return {"dgi_payment_term_type": "credito", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "30"}
        if "crédito a 60" in name or "credito a 60" in name or ("60 días" in name and "crédito" in name):
            m = Method.search([("code", "=", "01")], limit=1)
            return {"dgi_payment_term_type": "credito", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "60"}
        if "crédito a 90" in name or "credito a 90" in name or ("90 días" in name and "crédito" in name):
            m = Method.search([("code", "=", "01")], limit=1)
            return {"dgi_payment_term_type": "credito", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "90"}
        if "crédito otro" in name or "credito otro" in name:
            m = Method.search([("code", "=", "01")], limit=1)
            return {"dgi_payment_term_type": "credito", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "other"}
        if name == "otro" or ("otro" in name and "crédito" not in name and "credito" not in name):
            m = Method.search([("code", "=", "99")], limit=1)
            return {"dgi_payment_term_type": "contado", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "30"}
        if "tarjeta crédito" in name or "tarjeta credito" in name:
            m = Method.search([("code", "=", "03")], limit=1)
            return {"dgi_payment_term_type": "contado", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "30"}
        if "tarjeta débito" in name or "tarjeta debito" in name:
            m = Method.search([("code", "=", "04")], limit=1)
            return {"dgi_payment_term_type": "contado", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "30"}
        if "fidelización" in name or "fidelizacion" in name:
            m = Method.search([("code", "=", "05")], limit=1)
            return {"dgi_payment_term_type": "contado", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "30"}
        if "vale" in name and "tarjeta" not in name:
            m = Method.search([("code", "=", "06")], limit=1)
            return {"dgi_payment_term_type": "contado", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "30"}
        if "tarjeta de regalo" in name or "regalo" in name:
            m = Method.search([("code", "=", "07")], limit=1)
            return {"dgi_payment_term_type": "contado", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "30"}
        if "transf" in name or "depósito" in name or "deposito" in name or "bancaria" in name:
            m = Method.search([("code", "=", "08")], limit=1)
            return {"dgi_payment_term_type": "contado", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "30"}
        if "cheque" in name:
            m = Method.search([("code", "=", "09")], limit=1)
            return {"dgi_payment_term_type": "contado", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "30"}
        if "punto de pago" in name or "pago" in name and "punto" in name:
            m = Method.search([("code", "=", "10")], limit=1)
            return {"dgi_payment_term_type": "contado", "dgi_payment_method_id": m.id if m else False, "dgi_plazo_option": "30"}
        return None

    @api.onchange("property_payment_term_id")
    def _onchange_property_payment_term_id_dgi(self):
        """Al elegir Términos de pago (Ventas), rellenar Plazos y Método de pago DGI; al borrarlo, vaciarlos."""
        payment_term = getattr(self.with_company(self.env.company), "property_payment_term_id", None)
        if not payment_term:
            self.dgi_payment_term_type = False
            self.dgi_payment_method_id = False
            self.dgi_plazo_option = "30"
            return
        dgi_vals = self._dgi_payment_vals_from_payment_term(payment_term)
        if dgi_vals:
            self.dgi_payment_term_type = dgi_vals.get("dgi_payment_term_type")
            self.dgi_payment_method_id = dgi_vals.get("dgi_payment_method_id")
            self.dgi_plazo_option = dgi_vals.get("dgi_plazo_option", "30")

    def _sanitize_panama_vat(self, vat_raw):
        """
        Sanitiza y normaliza automáticamente cadenas de RUC / Cédula de Panamá:
        - Pasa a mayúsculas y quita espacios.
        - Si es un carnet/cédula tipo PN/PE/PI/N/E pegado sin guión (ej. PN0174213),
          le inserta el guión automáticamente (ej. PN-0174213).
        """
        if not vat_raw:
            return vat_raw
        raw = str(vat_raw).strip().upper().replace(" ", "")
        match_prefix = re.match(r"^(PN|PE|PI|N|E)(\d+)$", raw)
        if match_prefix:
            prefix, digits = match_prefix.groups()
            return f"{prefix}-{digits}"
        return raw

    @api.onchange("vat")
    def _onchange_vat_sanitize_pa(self):
        """Auto-sanitiza el RUC en tiempo real en la vista formulario."""
        if self.vat:
            self.vat = self._sanitize_panama_vat(self.vat)

    # =========================================================
    # REGLAS DE VALIDACIÓN DGI (Constrains)
    # =========================================================
    
    @api.constrains("l10n_pa_receptor_tipo", "company_type")
    def _check_df_receptor_tipo_matches_company_type(self):
        """
        Hard rule (DB-level validation):
        - Company: only 01 (Contribuyente), 03 (Gobierno)
        - Person: only 01, 02 (Consumidor Final), 04 (Extranjero)
        """
        for rec in self:
            if not rec.l10n_pa_receptor_tipo:
                continue

            if rec.company_type == "company" and rec.l10n_pa_receptor_tipo not in ("01", "03"):
                raise ValidationError(_("Para contactos tipo Empresa, el Tipo de Receptor (DGI) debe ser Contribuyente (01) o Gobierno (03)."))

            if rec.company_type == "person" and rec.l10n_pa_receptor_tipo not in ("01", "02", "04"):
                raise ValidationError(_("Para contactos tipo Persona, el Tipo de Receptor (DGI) debe ser Contribuyente (01), Consumidor Final (02) o Extranjero (04)."))

    @api.constrains(
        "l10n_pa_receptor_tipo",
        "l10n_pa_provincia_id",
        "l10n_pa_distrito_id",
        "l10n_pa_corregimiento_id",
    )
    def _check_dgi_address_required(self):
        """
        DGI rule:
        - Si es Contribuyente (01) o Gobierno (03), Provincia, Distrito y Corregimiento son obligatorios
        """
        for rec in self:
            if rec.env.context.get("skip_fe_validation"):
                continue

            if rec.l10n_pa_receptor_tipo in ("01", "03"):
                if not rec.l10n_pa_provincia_id or not rec.l10n_pa_distrito_id or not rec.l10n_pa_corregimiento_id:
                    raise ValidationError(_(
                        "Provincia, Distrito y Corregimiento son obligatorios "
                        "para Contribuyente y Gobierno (DGI)."
                    ))

    def action_validate_dgi(self):
        """ Core validation before getting RUC details. """
        self.ensure_one()
        
        # Mapear Términos de pago (Ventas y compras) → campos DGI si no se han rellenado
        payment_term = getattr(self.with_company(self.env.company), "property_payment_term_id", None)
        if payment_term:
            dgi_vals = self._dgi_payment_vals_from_payment_term(payment_term)
            if dgi_vals:
                self.with_context(skip_fe_validation=True).write({
                    "dgi_payment_term_type": dgi_vals.get("dgi_payment_term_type"),
                    "dgi_payment_method_id": dgi_vals.get("dgi_payment_method_id"),
                    "dgi_plazo_option": dgi_vals.get("dgi_plazo_option", "30"),
                })

        if not self.id:
            return self._dgi_notification_error(
                "Validación incompleta",
                "Guarde primero el contacto."
            )

        vat_value = self.vat or ""
        ruc = self._sanitize_panama_vat(vat_value.strip())
        if ruc and ruc != self.vat:
            self.with_context(skip_fe_validation=True).write({"vat": ruc})

        # Validaciones de campos obligatorios para DGI
        if not self.l10n_pa_receptor_tipo:
            return self._dgi_notification_error(
                "Validación incompleta",
                "Debe seleccionar el Tipo de Receptor (DGI) antes de validar."
            )
            
        if self.l10n_pa_receptor_tipo == '02' and self.company_type == 'company':
            return self._dgi_notification_error(
                "Validación de Tipo de Receptor",
                "No puedes declarar a una empresa (Persona Jurídica) como Consumidor Final."
            )

        if not ruc and self.l10n_pa_receptor_tipo != '02':
            return self._dgi_notification_error(
                "Validación incompleta", 
                "Por favor ingrese el RUC o Cédula en el campo correspondiente antes de validar."
            )
            
        if self.l10n_pa_receptor_tipo in ("01", "03"):
            if not self.l10n_pa_provincia_id or not self.l10n_pa_distrito_id or not self.l10n_pa_corregimiento_id:
                return self._dgi_notification_error(
                    "Validación incompleta",
                    "Provincia, Distrito y Corregimiento son obligatorios para Contribuyente y Gobierno (DGI)."
                )
            if not (self.street or self.street2 or self.city):
                return self._dgi_notification_error(
                    "Validación incompleta",
                    "Favor introducir una dirección en el contacto (Calle / Ciudad). Es requerida para facturar a Contribuyente/Gobierno."
                )
                
        self.invalidate_recordset()
        if not getattr(self, "dgi_payment_method_id", False):
            return self._dgi_notification_error(
                "Validación incompleta",
                "Debe seleccionar un Método de Pago (DGI) o Término de Pago antes de validar."
            )

        # Bypass API validation for Consumidor Final (02) and Extranjero (04)
        if self.l10n_pa_receptor_tipo == '02':
            vals = {
                "l10n_pa_is_dgi_validated": True,
            }
            if not ruc:
                vals["vat"] = "CF"

            raw_phone = (self.phone or "").strip()
            if self.country_id and self.country_id.code == "PA":
                formatted_phone = self._format_panama_phone(raw_phone, self.country_id) or False
            else:
                formatted_phone = self._format_dgi_phone_any_country(raw_phone) or False

            if formatted_phone:
                vals["phone"] = formatted_phone

            if self.street:
                vals["street"] = self.street[:100]

            self.with_context(skip_fe_validation=True).write(vals)
            self.message_post(
                body="✅ <b>Validación DGI completada (Interna)</b><br/>Tipo: Consumidor Final",
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Datos DGI validados",
                    "message": "Consumidor Final validado correctamente (Validación interna DGI).",
                    "type": "success",
                    "sticky": True,
                },
            }

        if self.l10n_pa_receptor_tipo == '04':
            vals = {
                "l10n_pa_is_dgi_validated": True,
            }

            raw_phone = (self.phone or "").strip()
            formatted_phone = self._format_dgi_phone_any_country(raw_phone) or False
            if formatted_phone:
                vals["phone"] = formatted_phone

            if self.street:
                vals["street"] = self.street[:100]

            self.with_context(skip_fe_validation=True).write(vals)
            self.message_post(
                body="✅ <b>Validación DGI completada (Interna)</b><br/>Tipo: Extranjero",
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Datos DGI validados",
                    "message": "Receptor Extranjero validado correctamente (Validación interna DGI).",
                    "type": "success",
                    "sticky": True,
                },
            }

        return self.env.company.action_get_ruc_details(partner=self)
