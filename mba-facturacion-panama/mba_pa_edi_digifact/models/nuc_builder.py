# -*- coding: utf-8 -*-
from odoo import models

import re
import logging
import random
import time
import unicodedata
from datetime import date, datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring

_logger = logging.getLogger(__name__)


def _nuc_sanitize_text(value):
    """
    Normalize text for NUC XML so it passes DGI schema validation.
    Many schemas only allow ASCII or reject certain Unicode; tildes and ñ often cause
    'Falló la validación de XML contra su esquema'. We strip accents and ñ -> n.
    """
    if value is None or not isinstance(value, str):
        return ""
    s = value.strip()
    if not s:
        return ""
    # NFD decompose then drop combining characters (accents, etc.)
    nfd = unicodedata.normalize("NFD", s)
    out = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    # ñ is a single code point; NFD gives n + combining tilde, so the above may already fix it
    # Explicit map for Spanish if needed (e.g. ñ not decomposed on some systems)
    for a, b in (("ñ", "n"), ("Ñ", "N")):
        out = out.replace(a, b)
    return out.strip() or ""


def _indent_xml(elem, level=0):
    """Pretty-print XML: add newlines and indentation so the file is readable (like Digifact examples)."""
    indent = "\n" + level * "    "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "    "
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
        for child in elem:
            _indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent


def _get(obj, field_name, default=None):
    return getattr(obj, field_name, default)


def _get_company_fe(company, *candidates, default=None):
    """Get first available value from company (x_fe_* or digifact_*)."""
    for name in candidates:
        val = getattr(company, name, None)
        if val is not None and str(val).strip() != "":
            return val
    return default


def _digits_only(value):
    return re.sub(r"\D+", "", value or "")


def _fmt_phone_b0611(value):
    """
    Format phone for NUC B0611/C0711: 7-12 characters; patterns 999-9999, 9999-9999, etc.
    Doc NUC 2.0.7: B0611 Phone (7-12 caracteres; formatos 999-9999, 9999-9999, etc.).
    Contacts store +507 for Panama (future development); NUC requires LOCAL number only (no country code).
    """
    s = (value or "").strip()
    # Strip Panama country code so we send local number only (7-12 chars per schema)
    for prefix in ("+507", "+507 ", "507", "507 "):
        if s.lower().startswith(prefix) or s.startswith(prefix):
            s = s[len(prefix) :].strip()
            break
    digits = re.sub(r"\D+", "", s)
    if not digits or len(digits) < 7:
        return "000-0000"
    digits = digits[:12]
    n = len(digits)
    if n == 7:
        return "%s-%s" % (digits[:3], digits[3:])
    if n == 8:
        return "%s-%s" % (digits[:4], digits[4:])
    if n == 9:
        return "%s-%s" % (digits[:5], digits[5:])
    if n == 10:
        return "%s-%s" % (digits[:5], digits[5:])
    if n == 11:
        return "%s-%s-%s" % (digits[:6], digits[6:9], digits[9:])
    return "%s-%s-%s" % (digits[:6], digits[6:10], digits[10:])


def _fmt_dt_panama():
    # Panama is UTC-5, no DST. Digifact examples use whole seconds only (no milliseconds), e.g. 2022-09-16T19:42:00-05:00
    tz = timezone(timedelta(hours=-5))
    return datetime.now(tz).isoformat(timespec="seconds")


def _fmt_amount(value, decimals=6):
    try:
        return f"{float(value or 0.0):.{decimals}f}"
    except Exception:
        return f"{0.0:.{decimals}f}"


def _add_info(parent, name, value):
    # Always write as attributes (Digifact schema expects Info nodes)
    SubElement(parent, "Info", {"Name": str(name), "Value": str(value)})


def _str_clean(v):
    """Return non-None/False values as stripped string; never return 'False' (Odoo empty Many2one can be False)."""
    if v is None or v is False:
        return ""
    s = (str(v).strip() if v is not None else "").strip()
    return "" if s == "False" else s


def _strip_reference_from_description(name, default_code):
    """Quita prefijo [referencia] de la descripción y formatea saltos de línea entre nombre y descripción."""
    s = (name or "").strip()
    if not s:
        return ""
    if default_code:
        prefix = "[" + str(default_code).strip() + "]"
        if s.upper().startswith(prefix.upper()):
            s = s[len(prefix) :].strip()
    # Reemplazar saltos de línea entre el nombre y la descripción por un separador limpio
    cleaned = re.sub(r'[\r\n]+', ' - ', s)
    # Comprimir espacios múltiples
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
    return cleaned


def _fmt_branch_code(value, length=4):
    """dSucEm: esquema DGI exige patrón (ej. 4 caracteres). Rellena con ceros a la izquierda."""
    s = _str_clean(value) or "1"
    digits = re.sub(r"\D+", "", s)
    if not digits:
        digits = "1"
    return digits.zfill(length)[-length:] if len(digits) >= length else digits.zfill(length)


# Códigos de unidad que aparecen en ejemplos Digifact (NUC 1, 4, 15, 20: und, bit, cm, m). "Caja" y similares suelen fallar esquema
_NUC_SAFE_UNIT_CODES = frozenset(
    ("und", "bit", "cm", "m", "mm", "kg", "g", "l", "ml", "lb", "oz", "ft", "in", "km", "ha", "m2", "dm", "dam", "hm")
)


def _nuc_safe_unit_code(value):
    """Return unit code for NUC; use as-is if in Digifact examples / safe set, else 'und' to avoid schema rejection."""
    s = (_str_clean(value) or "").strip()
    if not s:
        return "und"
    if s in _NUC_SAFE_UNIT_CODES:
        return s
    # Lowercase 2–5 char alphanumeric often accepted (e.g. docena -> try as-is; long names -> und)
    if len(s) <= 5 and s.isalnum():
        return s
    return "und"


def _fmt_numero_df(value):
    """AI04 NumeroDF: exactamente 10 dígitos, ceros a la izquierda (esquema NUC)."""
    digits = _digits_only(value)
    if not digits:
        digits = "1"
    return digits.zfill(10)[-10:] if len(digits) >= 10 else digits.zfill(10)


def _fmt_codigo_seguridad(value):
    """AI06 CodigoSeguridad: exactamente 9 dígitos, ceros a la izquierda (esquema NUC)."""
    digits = _digits_only(value)
    if not digits:
        digits = "1"
    return digits.zfill(9)[-9:] if len(digits) >= 9 else digits.zfill(9)


def _fmt_digito_verificador(value):
    """
    BI01/CI02 DigitoVerificador: exactamente 2 dígitos (norma DGI). Nunca 1.
    Ceros a la izquierda si hace falta (ej: "6" -> "06"). Si hay más de 2 dígitos, últimos 2.
    """
    if value is None or value is False:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    digits = re.sub(r"\D+", "", s)
    if not digits:
        return ""
    # Siempre 2 caracteres: rellenar con 0 a la izquierda o tomar los últimos 2
    return digits.zfill(2)[-2:]


def _safe_money(v):
    try:
        return float(v or 0.0)
    except Exception:
        return 0.0


def _safe_get_phone(obj):
    """
    Safely get phone number from a record (company or partner).
    Returns phone or mobile if available, using getattr to avoid AttributeError
    if mobile field doesn't exist (some Odoo installations don't have mobile field).
    """
    if not obj:
        return ""
    phone = getattr(obj, "phone", None) or ""
    if not phone:
        phone = getattr(obj, "mobile", None) or ""
    return phone or ""


# E0911/E0912 (DGI): Código y nombre del impuesto en Items/Taxes.
# E0912: Description solo puede ser ITBMS | ISC | OTI (nunca "EXENTO" ni "7%").
# Referencia: NUC 4 - Tasa ITBMS 0%.xml → Code 00, Description ITBMS, Amount 00.00
_TAX_NOMBRE_ALLOWED = ("ITBMS", "ISC", "OTI")


def _tax_nombre_impuesto(tax_obj):
    """
    E0912: Nombre del impuesto = ITBMS | ISC | OTI (nunca "7%" ni nombre libre).
    Se busca en descripción y en nombre del impuesto de Odoo (ambos sirven).
    """
    out = "ITBMS"
    if tax_obj:
        rec = tax_obj[:1] if hasattr(tax_obj, "__len__") and len(tax_obj) else tax_obj
        if rec:
            desc = _str_clean(getattr(rec, "description", None) or "")
            name = _str_clean(getattr(rec, "name", None) or "")
            raw = " ".join([desc, name]).upper()
            if not raw and getattr(rec, "display_name", None):
                raw = _str_clean(rec.display_name).upper()
            if "ITBMS" in raw or "ITMBS" in raw:
                out = "ITBMS"
            elif "ISC" in raw:
                out = "ISC"
            elif "OTI" in raw:
                out = "OTI"
            else:
                dgi = _str_clean(getattr(rec, "digifact_tax_desc", None))
                if dgi and dgi.upper() in _TAX_NOMBRE_ALLOWED:
                    out = dgi.upper()
    return out if out in _TAX_NOMBRE_ALLOWED else "ITBMS"


class DigifactNUCBuilder(models.AbstractModel):
    """
    Builder dinámico de XML NUC (Panamá FE). Una sola ruta de código: todo se lee del move
    (y company/partner); no hay una rama por cada “combinación” de facturación.

    Dimensiones que maneja (todas desde datos del move):
    - Tipo de documento: 01–10 (move.dgi_document_type_id.code → doc_type_map).
    - Tipo de receptor: 01 Contribuyente, 02 CF, 03 Gobierno, 04 Extranjero (campos Buyer/DV/cedula/pasaporte según tipo).
    - Impuestos por ítem: line.tax_ids + compute_all; Code/Description/Amount desde account.tax (digifact_tax_*) o 00/ITBMS/0.
    - Pagos: contado (código método) o crédito (PLAZO 30/60/90 u otra fecha).
    - Retención: CodRetenc/ValRetenc solo si move tiene dgi_retention_type_id y dgi_retention_amount != 0.
    - NC/ND: con o sin documentos referenciados (CUFE); TotalCharges (Acarreo/Seguro/Otros) desde líneas con dgi_charge_type.
    """
    _name = "digifact.nuc.builder"
    _description = "Digifact NUC XML Builder (Panama FE)"

    def build_nuc_xml(self, move, allow_draft=False):
        """
        Build a minimal-but-valid NUC XML from an account.move (customer invoice).
        When allow_draft=True and the document is in draft:
        - If NumeroDF/CodigoSeguridad/PtoFactDF are set (fiscal number reserved), they are used.
        - If any is missing, placeholder values are used so the XML can be generated for preview only.
        Posted documents always use the move's fiscal data.
        """

        # --- Guards ---
        if not move:
            raise ValueError("move is required")
        if move.move_type not in ("out_invoice", "out_refund"):
            raise ValueError("Only customer invoices and credit/debit notes are supported")
        if move.state not in ("posted", "draft"):
            raise ValueError("Document must be draft or posted")
        if move.state == "draft" and not allow_draft:
            raise ValueError("Document must be posted before generating NUC XML (or use allow_draft=True for preview)")
        if move.dgi_document_type_id and move.dgi_document_type_id.code in ("nc_referenciada_fe", "nd_referenciada_fe"):
            refs = getattr(move, "dgi_referenced_fe_ids", None)
            has_ref = bool(refs and any(getattr(r, "cufe", None) for r in refs))
            has_origin = bool((move.debit_origin_id and move.debit_origin_id.l10n_pa_cufe) or (move.reversed_entry_id and move.reversed_entry_id.l10n_pa_cufe))
            if not (has_ref or has_origin):
                raise ValueError("NC/ND referenciada FE debe tener al menos un documento fiscal referenciado con CUFE.")

        company = move.company_id
        partner = move.partner_id
        if not company:
            raise ValueError(
                "La factura no tiene compañía asignada. Asigne la compañía en la factura."
            )
        if not _str_clean(company.vat):
            raise ValueError(
                "La compañía (emisor) no tiene RUC configurado. "
                "Indique el NIF/VAT de la compañía en Configuración / Información de la empresa o en Facturación Electrónica (DGI) / Configuración de la empresa."
            )
        if not partner:
            raise ValueError("La factura no tiene cliente (contacto) asignado.")

        # Effective fiscal header values:
        # Prioridad 1: campos específicos digifact_* si están poblados
        # Prioridad 2: si está en draft con allow_draft=True (wizard PAC Primero) o posted,
        # usar move.name (10 dígitos) y generar/obtener código de seguridad y pto_fact.
        numero_from_name = _digits_only(move.name) if move.name and move.name != '/' else ""
        if numero_from_name and len(numero_from_name) >= 10:
            numero_from_name = numero_from_name[-10:]
        elif numero_from_name:
            numero_from_name = numero_from_name.zfill(10)

        effective_numero_df = (
            move.digifact_numero_df
            or (numero_from_name if numero_from_name else False)
            or ("0000000001" if allow_draft else "0000000001")
        )

        pto_raw = (
            move.digifact_pto_fact_df
            or getattr(move.journal_id, "l10n_pa_pto_fact_df", None)
            or getattr(company, "l10n_pa_pto_fact", None)
            or getattr(company, "x_fe_ptofact_code", None)
            or getattr(company, "digifact_ptofact_code", None)
            or "001"
        )
        effective_pto_fact = (_digits_only(pto_raw) or "1").strip()[:3].zfill(3)
        if len(effective_pto_fact) > 3:
            effective_pto_fact = effective_pto_fact[-3:]

        if move.digifact_codigo_seguridad:
            effective_codigo_seg = move.digifact_codigo_seguridad
        else:
            # Generar código de seguridad DGI de 9 dígitos no nulo y distinto al número DF
            num_digits = _digits_only(effective_numero_df)[:9]
            candidate = "000000001"
            for _ in range(30):
                rnd = str(random.randint(1, 999999999)).zfill(9)
                if rnd != num_digits and rnd != "000000000":
                    candidate = rnd
                    break
            effective_codigo_seg = candidate

        # --- Root ---
        root = Element("Root")
        SubElement(root, "Version").text = "1.00"
        SubElement(root, "CountryCode").text = "PA"

        # --- Header ---
        header = SubElement(root, "Header")
        # A02 DocType (DGI): 01=FE Operación Interna, 02=Importación, 03=Exportación,
        # 04=NC Referente a una o Varias FE (con CUFE), 05=ND Referente FE,
        # 06=NC Genérica (flujo Facturación → Nota de crédito, sin referencia), 07=ND Genérica,
        # 08=Zona Franca, 09=Reembolso, 10=Operación Extranjera
        doc_type_map = {
            "factura_operacion_interna": "01",
            "factura_importacion": "02",
            "factura_exportacion": "03",
            "nc_referenciada_fe": "04",   # Nota de Crédito referenciando CUFE
            "nd_referenciada_fe": "05",
            "nc_generica": "06",          # Nota de Crédito Genérica (sin referencia)
            "nd_generica": "07",
            "factura_zona_franca": "08",
            "reembolso": "09",
            "factura_operacion_extranjera": "10",
        }
        doc_type_code = "01"
        if move.dgi_document_type_id and move.dgi_document_type_id.code:
            doc_type_code = doc_type_map.get(
                str(move.dgi_document_type_id.code).strip(),
                "01",
            )
        SubElement(header, "DocType").text = doc_type_code
        SubElement(header, "IssuedDateTime").text = _fmt_dt_panama()
        ambiente = _get_company_fe(company, "digifact_ambiente", default="2")
        SubElement(header, "AdditionalIssueType").text = _str_clean(ambiente) or "2"

        add = SubElement(header, "AdditionalIssueDocInfo")
        _add_info(add, "TipoEmision", "01")
        _add_info(add, "NumeroDF", _fmt_numero_df(effective_numero_df))
        pto_fact = _digits_only(effective_pto_fact) or "1"
        _add_info(add, "PtoFactDF", pto_fact.zfill(3)[-3:] if len(pto_fact) >= 3 else pto_fact.zfill(3))
        _add_info(add, "CodigoSeguridad", _fmt_codigo_seguridad(effective_codigo_seg))
        # AI08: DGI valid values 01,02,03,04,05,10,11,12,13,14,20,21. "11" = Devolución (we stored "06" historically).
        nat_raw = _str_clean(getattr(move, "dgi_naturaleza_operacion", None)) or "01"
        nat_xml = "11" if nat_raw == "06" else nat_raw
        _add_info(add, "NaturalezaOperacion", nat_xml)
        _add_info(add, "TipoOperacion", _str_clean(getattr(move, "dgi_tipo_operacion", None)) or "1")
        _add_info(add, "DestinoOperacion", "1")
        _add_info(add, "FormatoGeneracion", "1")
        _add_info(add, "ManeraEntrega", "1")
        _add_info(add, "EnvioContenedor", "1")
        _add_info(add, "ProcesoGeneracion", "1")
        _add_info(add, "TipoTransaccion", "1")
        _add_info(add, "TipoSucursal", "2")
        # AI17 InfoInteres: notas complementarias (máx. 200 caracteres; opcional)
        info_interes = _nuc_sanitize_text(_str_clean(getattr(move, "dgi_payment_notes", None) or "")[:200])
        if info_interes:
            _add_info(add, "InfoInteres", info_interes)

        # --- Seller (from company + company.partner_id for address) ---
        seller = SubElement(root, "Seller")
        SubElement(seller, "TaxID").text = _str_clean(company.vat) or ""
        SubElement(seller, "TaxIDType").text = "2"  # Jurídico typical for company

        seller_tax_add = SubElement(seller, "TaxIDAdditionalInfo")
        dv_emisor = (
            _get_company_fe(company, "dgi_dv", "x_fe_dgi_dv", "digifact_dv", "l10n_pa_dv", default="")
            or getattr(company.partner_id, "l10n_pa_dv", None)
            or getattr(company.partner_id, "dgi_dv", None)
            or ""
        )
        # BI01 DigitoVerificador: obligatorio para el emisor; norma DGI exige exactamente 2 dígitos (no 1).
        dv_emisor_formatted = _fmt_digito_verificador(dv_emisor)
        if not dv_emisor_formatted:
            raise ValueError(
                "El dígito verificador (DV) del emisor es obligatorio en el NUC. "
                "Configure el DV de la compañía en Facturación Electrónica (DGI) / Configuración de la empresa."
            )
        if len(dv_emisor_formatted) != 2:
            raise ValueError(
                "El DV del emisor debe ser exactamente 2 dígitos en el NUC (norma DGI). "
                "Valor formateado obtenido: '%s' (longitud %s). Configure el DV en la compañía (Obtener detalles RUC)."
                % (dv_emisor_formatted, len(dv_emisor_formatted))
            )
        _add_info(seller_tax_add, "DigitoVerificador", dv_emisor_formatted)

        # DGI: if A04 (Ambiente) = 2 (Pruebas), Seller/Name must be the test literal
        if _str_clean(ambiente) == "2":
            seller_name = "FE generada en ambiente de pruebas - sin valor comercial ni fiscal"
        else:
            seller_name = (company.name or "N/A").strip()
        SubElement(seller, "Name").text = _nuc_sanitize_text(seller_name)

        contact = SubElement(seller, "Contact")
        phones = SubElement(contact, "PhoneList")
        # Control: norma exige 1 teléfono para el emisor (no enviar placeholder)
        comp_phone = _safe_get_phone(company) or (company.partner_id and _safe_get_phone(company.partner_id) or "") or ""
        if not comp_phone or not comp_phone.strip():
            raise ValueError(
                "El emisor (compañía) debe tener un número de teléfono configurado. "
                "Indique el Teléfono en la compañía o en su dirección de contacto."
            )
        SubElement(phones, "Phone").text = _fmt_phone_b0611(comp_phone)

        branch = SubElement(seller, "BranchInfo")
        # dSucEm: esquema DGI exige 4 caracteres.
        # User request: allow 0000 if configured (do not force 0001).
        branch_code = _get_company_fe(company, "dgi_sucursal_code", "x_fe_branch_code", "digifact_branch_code", default="001")
        code_4 = _fmt_branch_code(branch_code)
        # Removed hardcoded check for 0000 -> 0001
        SubElement(branch, "Code").text = code_4

        comp_partner = company.partner_id or company
        addr = SubElement(branch, "AddressInfo")
        SubElement(addr, "Address").text = _nuc_sanitize_text(_str_clean(getattr(comp_partner, "street", None) or getattr(company, "street", None)) or "N/A")
        # Seller: City/District/State = ubicación DGI (corregimiento, distrito, provincia), NOT contact city
        correg_seller = (
            getattr(company, "dgi_corregimiento_id", None) and company.dgi_corregimiento_id.name
            or getattr(company, "x_fe_corregimiento_id", None) and company.x_fe_corregimiento_id.name
        ) or "Panama"
        distrito_seller = (
            getattr(company, "dgi_distrito_id", None) and company.dgi_distrito_id.name
            or getattr(company, "x_fe_distrito_id", None) and company.x_fe_distrito_id.name
        ) or "Panama"
        provincia_seller = (
            getattr(company, "dgi_provincia_id", None) and company.dgi_provincia_id.name
            or getattr(company, "x_fe_provincia_id", None) and company.x_fe_provincia_id.name
        ) or "Panama"
        SubElement(addr, "City").text = _nuc_sanitize_text(_str_clean(correg_seller) or "Panama")
        SubElement(addr, "District").text = _nuc_sanitize_text(_str_clean(distrito_seller) or "Panama")
        SubElement(addr, "State").text = _nuc_sanitize_text(_str_clean(provincia_seller) or "Panama")
        SubElement(addr, "Country").text = "PA"

        abi = SubElement(branch, "AdditionalBranchInfo")
        coordem = _get_company_fe(company, "x_fe_coordem", "digifact_coordem", default="+8.9213,-79.7068")
        _add_info(abi, "CoordEm", _str_clean(coordem) or "+8.9213,-79.7068")
        cod_ubi = _get_company_fe(
            company,
            "dgi_cod_ubi",
            "x_fe_cod_ubi",
            "digifact_codubi",
            default="1-1-1",
        )
        _add_info(abi, "CodUbi", _str_clean(cod_ubi) or "1-1-1")

        # --- Buyer (from move snapshot dgi_partner_*) - structure aligned with NUC 17 (extranjero) ---
        buyer = SubElement(root, "Buyer")
        commercial_partner = move.commercial_partner_id or partner
        tipo_receptor = commercial_partner.l10n_pa_receptor_tipo if hasattr(commercial_partner, "l10n_pa_receptor_tipo") else (move._df_receptor_tipo_code() if hasattr(move, "_df_receptor_tipo_code") else "01")
        receptor_type = getattr(move, "dgi_receptor_type", None) or ""
        
        # Priority: commercial_partner.l10n_pa_ruc -> commercial_partner.vat -> move snapshot
        buyer_ruc = _str_clean(getattr(commercial_partner, "l10n_pa_ruc", "")) or _str_clean(commercial_partner.vat) or _str_clean(getattr(move, "dgi_partner_ruc", "")) or ""
        # El comentario de abajo dice "enviar TaxID vacío si no hay RUC real", pero _str_clean("CF")
        # devuelve "CF" y terminaba enviándose al XSD (error 3010). Lo normalizamos aquí de verdad:
        # "CF" (o cualquier placeholder no numérico en CF/02) → "" para que <TaxID> vaya vacío.
        is_clean_numeric_ruc = bool(re.match(r"^(\d{1,2}-\d{1,5}-\d{1,6}|\d{1,2}-NT-\d{1,5}-\d{1,6}|\d{7,15})$", buyer_ruc))
        if buyer_ruc.upper() == "CF" or (tipo_receptor == "02" and not is_clean_numeric_ruc):
            buyer_ruc = ""
        if tipo_receptor == "04":
            buyer_ruc = "EXTRANJERO"

        # TaxID / dRuc:
        #   • Contribuyente (01) / Gobierno (03): obligatorio, enviar RUC.
        #   • Extranjero (04): enviar literal "EXTRANJERO".
        #   • Consumidor Final (02):
        #       - DGI XSD rechaza el valor literal "CF" (Pattern constraint, error 3010).
        #       - Digifact NUC schema exige que el nodo TaxID esté presente (posición antes de TaxIDAdditionalInfo).
        #       - Solución: enviar TaxID vacío si no hay RUC/cédula real.
        #         Digifact pasa el nodo vacío a DGI que lo acepta (patrón permite cadena vacía).
        #       - Si hay cédula real (vat / dgi_partner_ruc), enviarla como valor.
        if tipo_receptor == "02":
            SubElement(buyer, "TaxID").text = buyer_ruc or ""
        else:
            SubElement(buyer, "TaxID").text = buyer_ruc or ""

        # Priority: move snapshot -> commercial_partner.l10n_pa_tipo_contribuyente -> company_type
        taxpayer_val = getattr(move, "dgi_partner_taxpayer_type", None) or getattr(commercial_partner, "l10n_pa_tipo_contribuyente", None) or ("2" if commercial_partner.company_type == "company" else "1")
        tax_type = "2" if str(taxpayer_val) == "2" or str(taxpayer_val).strip().lower() == "juridico" else "1"
        if tipo_receptor not in ("02", "04"):
            SubElement(buyer, "TaxIDType").text = tax_type

        buyer_tax_add = SubElement(buyer, "TaxIDAdditionalInfo")
        _add_info(buyer_tax_add, "TipoReceptor", _str_clean(tipo_receptor) or "01")
        # REGLA NORMA: Lo obligatorio lo enviamos. Lo no obligatorio lo enviamos solo si el usuario lo brinda. No obligamos.
        # CI02: obligatorio solo 01 y 03. Para 02 y 04: opcional; enviamos solo si hay dato.
        buyer_dv_raw = _str_clean(getattr(commercial_partner, "l10n_pa_dv", "")) or _str_clean(getattr(commercial_partner, "df_dv", "")) or _str_clean(getattr(move, "dgi_partner_dv", "")) or ""
        buyer_dv_formatted = _fmt_digito_verificador(buyer_dv_raw)
        if tipo_receptor in ("01", "03"):
            if not buyer_dv_formatted:
                raise ValueError(
                    "Para receptor Contribuyente (01) o Gobierno (03) el DV es obligatorio. "
                    "Use «Validar datos DGI» en el contacto para obtener el DV desde la DGI."
                )
            if len(buyer_dv_formatted) != 2:
                raise ValueError(
                    "El DV del receptor (CI02) debe ser exactamente 2 dígitos. Corrija en el contacto (Validar datos DGI)."
                )
            _add_info(buyer_tax_add, "DigitoVerificador", buyer_dv_formatted)
        elif buyer_dv_formatted and tipo_receptor == "02":
            # CF: CI02 no obligatorio; enviamos solo si el usuario lo brindó (2 dígitos).
            _add_info(buyer_tax_add, "DigitoVerificador", buyer_dv_formatted.zfill(2)[-2:])
        # 02 (CF): CedulaCF no obligatorio; enviamos solo si el usuario lo brindó.
        if tipo_receptor == "02":
            cedula_cf = _str_clean(getattr(move, "dgi_partner_cedula", None)) or _str_clean(getattr(commercial_partner, "df_cedula", None)) or ""
            if cedula_cf:
                _add_info(buyer_tax_add, "CedulaCF", cedula_cf)
        # 04 (Extranjero): CI02 no obligatorio. NumPasaporte/PaisExt solo si el usuario lo brindó.
        if tipo_receptor == "04":
            num_pasaporte = _str_clean(getattr(commercial_partner, "l10n_pa_tipo_identificacion", None)) or _str_clean(getattr(move, "dgi_partner_id_pasaporte", None)) or _str_clean(getattr(commercial_partner, "df_id_pasaporte", None)) or ""
            pais_ext = (commercial_partner.country_id and commercial_partner.country_id.code) or ""
            if num_pasaporte:
                _add_info(buyer_tax_add, "NumPasaporte", num_pasaporte)
            if pais_ext:
                _add_info(buyer_tax_add, "PaisExt", _str_clean(pais_ext))
        # Address Logic Preparation (Moved up to decide on CodUbi)
        # ---------------------------------------------------------
        # 1. Harvest values (from the contact person, not commercial partner)
        val_street = _nuc_sanitize_text(_str_clean(getattr(move, "dgi_partner_address_text", "")) or (partner.street or ""))
        
        taxpayer_natural = tax_type == "1"
        skip_buyer_ubicacion = receptor_type in ("consumidor_final", "extranjero") or taxpayer_natural or tipo_receptor in ("02", "04")
        
        # 2. Decide validation strictness (AddressInfo)
        # skip_buyer_ubicacion is True for CF (02) / Extranjero (04) / Natural
        should_send_address = True
        if skip_buyer_ubicacion:
            # Only send if we have at least a street address
            # Strict validation in res.partner now ensures that if we have location, we also have street.
            if not val_street:
                should_send_address = False

        # CI04 (CodUbi): Digifact requirements
        # - Mandatory if AddressInfo (C08) is present (User feedback & Docs).
        # - Mandatory if Receptor is Contribuyente (01) or Gobierno (03) (Implied by skip_buyer_ubicacion=False).
        # - Optional if Receptor 02/04 AND No AddressInfo.
        
        buyer_cod_ubi = ""
        # Priority to commercial_partner or partner corregimiento code
        correg_obj = (
            getattr(commercial_partner, "l10n_pa_corregimiento_id", False)
            or getattr(partner, "l10n_pa_corregimiento_id", False)
        )
        if correg_obj and getattr(correg_obj, "code", False):
            buyer_cod_ubi = _str_clean(correg_obj.code)
        
        # Only add CodUbi if we are sending address OR if we are in strict mode (01/03)
        # Use '1-1-1' as fallback only if we MUST send it.
        if should_send_address or not skip_buyer_ubicacion:
             _add_info(buyer_tax_add, "CodUbi", buyer_cod_ubi or "1-1-1")

        buyer_name = (getattr(move, "dgi_partner_name", "") or commercial_partner.name or "CONSUMIDOR FINAL").strip()
        if buyer_name:
            SubElement(buyer, "Name").text = _nuc_sanitize_text(buyer_name)

        addinfo = SubElement(buyer, "AdditionlInfo")
        buyer_country = (commercial_partner.country_id and commercial_partner.country_id.code) or "PA"
        _add_info(addinfo, "PaisReceptorFE", _str_clean(buyer_country) or "PA")

        # AddressInfo Block
        # -----------------
        
        # City/District/State logic
        # If we have linked DGI locations on the partner, use them. Else fallback to standard Odoo fields.
        val_city = ""
        val_district = ""
        val_state = ""

        correg = getattr(partner, "l10n_pa_corregimiento_id", None) or getattr(commercial_partner, "l10n_pa_corregimiento_id", None)
        if correg:
            val_city = correg.name
        else:
            val_city = partner.city or ""

        distrito = getattr(partner, "l10n_pa_distrito_id", None) or getattr(commercial_partner, "l10n_pa_distrito_id", None)
        if distrito:
            val_district = distrito.name
        else:
            val_district = partner.city or "" # Fallback if no district field

        provincia = getattr(partner, "l10n_pa_provincia_id", None) or getattr(commercial_partner, "l10n_pa_provincia_id", None)
        if provincia:
            val_state = provincia.name
        elif partner.state_id:
            val_state = partner.state_id.name
        
        val_city = _nuc_sanitize_text(_str_clean(val_city))
        val_district = _nuc_sanitize_text(_str_clean(val_district))
        val_state = _nuc_sanitize_text(_str_clean(val_state))
        
        # 3. Build XML
        if should_send_address:
            addr_b = SubElement(buyer, "AddressInfo")
            # Address: Always required if AddressInfo exists
            SubElement(addr_b, "Address").text = val_street or "N/A"
            
            # For mandatory types, we force defaults. For optional, we only send if present (or if schema forces it).
            # Schema usually requires City/District/State/Country if AddressInfo is present.
            # To be safe and compliant with "force validation for 01/03 but use real data for 02":
            
            if not skip_buyer_ubicacion:
                # Mandatory: Force N/A if missing
                SubElement(addr_b, "City").text = val_city or "Panama"
                SubElement(addr_b, "District").text = val_district or "Panama"
                SubElement(addr_b, "State").text = val_state or "Panama"
            else:
                # Optional (CF): User request "if not mandatory and not there, don't send".
                # However, XSD likely enforces minOccurs=1 for City inside AddressInfo.
                # We will send them if we have them. If empty, we might have to send something or omit.
                # NUC spec typically: AddressInfo -> Sequence { Address, City, District, State, Country }
                # If XSD says minOccurs=1 for these, we MUST send them if we send AddressInfo.
                # Assuming standard DGI schema structure which usually mandates full address block if partial.
                # The user's specific complaint was "N/A" and forcing "Panama".
                # We will try to send empty or skip? Skipping is safer if XSD allows optional children.
                # But typically DGI schemas require the 5 fields.
                # Solution: if we have Street, we probably should fill others with "Panama" or at least not "N/A" if possible,
                # BUT user explicitly said "if client is in Chiriqui... we are forcing Panama?".
                # So we MUST use `val_state` (e.g. Chiriqui) if available.
                
                # We use the harvested values. If missing, we might have to fallback to something to avoid XSD error *if* we are sending the block.
                # Let's send what we have. If blank, let's try sending blank or not sending.
                # Based on user request, let's Try sending real values. If blank, send tag with empty? Or omit?
                # Safest bet meeting user goal: Use real values. If state is empty, don't force "Panama" unless necessary.
                # But wait, logic above `val_state = partner.state_id.name`. If user set Chiriqui, it will be Chiriqui.
                # Previously it was hardcoded: `SubElement(addr_b, "State").text = ... or "N/A" ... default_state`
                
                if val_city:
                    SubElement(addr_b, "City").text = val_city
                else: 
                     SubElement(addr_b, "City").text = "Panama" # Fallback likely needed for schema
                     
                if val_district:
                    SubElement(addr_b, "District").text = val_district
                else:
                    SubElement(addr_b, "District").text = "Panama"

                if val_state:
                    SubElement(addr_b, "State").text = val_state
                else:
                    SubElement(addr_b, "State").text = "Panama"

            SubElement(addr_b, "Country").text = buyer_country

        # El esquema NUC de Digifact no admite Contact como hijo de Buyer (error 3010: "invalid child element 'Contact'").
        # Los samples oficiales (NUC 15 - CF, NUC1 referencia) no incluyen Contact en Buyer. No añadirlo.

        # --- Items ---
        items = SubElement(root, "Items")

        all_billable = move.invoice_line_ids.filtered(
            lambda l: l.display_type not in ("line_section", "line_note")
        )
        # F03 TotalCharges: Acarreo, Seguro, Otros Gastos no van como ítem (no aplica CPBS). Se suman todas las líneas del mismo tipo y se envía UN TotalCharge por tipo (F0311 Description, F0312 Amount).
        charge_type_map = {"acarreo": "FACTURA", "seguro": "SEGURO", "otros_gastos": "OTROS_GASTOS"}
        item_lines = all_billable.filtered(
            lambda l: not l.product_id
            or not getattr(l.product_id.product_tmpl_id, "dgi_charge_type", None)
            or l.product_id.product_tmpl_id.dgi_charge_type not in charge_type_map
        )
        charge_lines = all_billable.filtered(
            lambda l: l.product_id
            and getattr(l.product_id.product_tmpl_id, "dgi_charge_type", None)
            and l.product_id.product_tmpl_id.dgi_charge_type in charge_type_map
        )

        if not item_lines:
            # Help debug: show line counts (move may have been invalidated after action_post)
            n_total = len(all_billable)
            n_charges = len(charge_lines)
            raise ValueError(
                "Invoice has no billable item lines (total lines=%s, charge-only lines=%s). "
                "Lines with products marked as Acarreo/Seguro/Otros Gastos are sent as TotalCharges (F03), "
                "not as items; add at least one normal product line."
                % (n_total, n_charges)
            )

        # For GrandTotal calculation: sum of positive taxes (excluding retention)
        total_taxes_gross_accum = 0.0

        for line in item_lines:
            it = SubElement(items, "Item")

            # Codes: same complete block for all customers (gov + others): CodigoProd, CodCPBSabr, CodCPBScmp, UnidadCPBS
            code_pairs = []
            prod = line.product_id
            prod_tmpl = prod.product_tmpl_id if prod else None  # CPBS fields are on template
            if prod and prod.default_code:
                # EI01 CodigoProd: DGI exige alfanumérico (letras, números, guiones, guiones bajos), máx 20 chars.
                # Se sanitiza automáticamente aquí en lugar de rechazar al guardar el producto,
                # para no bloquear instalación de módulos Odoo que crean productos con caracteres especiales.
                raw_code = (prod.default_code or "").strip()
                sanitized_code = re.sub(r'[^a-zA-Z0-9_-]', '-', raw_code)[:20]
                if sanitized_code:
                    code_pairs.append(("CodigoProd", sanitized_code))
            # CodCPBSabr: digits only (e.g. "13"); never "False" (Odoo empty rel can be False)
            cod_cpbs_abrev = ""
            if prod_tmpl:
                cod_cpbs_abrev = _str_clean(getattr(prod_tmpl, "dgi_cpbs_abrev", None))
                if not cod_cpbs_abrev and prod_tmpl.dgi_cpbs_segment_id:
                    cod_cpbs_abrev = _str_clean(prod_tmpl.dgi_cpbs_segment_id.code)
                if not cod_cpbs_abrev and prod_tmpl.dgi_cpbs_family_id:
                    cod_cpbs_abrev = _str_clean(prod_tmpl.dgi_cpbs_family_id.code)
            cod_cpbs_abrev = _digits_only(cod_cpbs_abrev) or "00"  # ensure digits only
            if prod:
                code_pairs.append(("CodCPBSabr", cod_cpbs_abrev))
            # CodCPBScmp: full CPBS digits (e.g. "1310"); only add when we have real digits
            cod_cpbs_cmp = ""
            if prod_tmpl:
                cod_cpbs_cmp = _str_clean(getattr(prod_tmpl, "dgi_cpbs_codigo", None))
                if not cod_cpbs_cmp and prod_tmpl.dgi_cpbs_family_id:
                    cod_cpbs_cmp = _str_clean(prod_tmpl.dgi_cpbs_family_id.code)
            cod_cpbs_cmp = _digits_only(cod_cpbs_cmp)
            if cod_cpbs_cmp:
                code_pairs.append(("CodCPBScmp", cod_cpbs_cmp))
            # UnidadCPBS: DGI unit code. Esquema suele aceptar códigos cortos (und, bit, cm, m); nombres largos como "Caja" pueden fallar
            uom_cpbs = ""
            if prod_tmpl and getattr(prod_tmpl, "dgi_unidad_medida_id", None) and prod_tmpl.dgi_unidad_medida_id:
                uom_cpbs = _str_clean(prod_tmpl.dgi_unidad_medida_id.code)
            uom_cpbs = _nuc_safe_unit_code(uom_cpbs)
            if uom_cpbs:
                code_pairs.append(("UnidadCPBS", uom_cpbs))

            # E03 Codes: para receptor Gobierno (03) son obligatorios al menos CodigoProd o CPBS por ítem
            if tipo_receptor == "03" and not code_pairs:
                prod_name = (line.product_id and line.product_id.display_name) or (line.name or "ítem")
                raise ValueError(
                    "Para facturar a Gobierno (Tipo de Receptor 03) cada ítem debe tener código de producto (referencia interna) o códigos CPBS. "
                    "Falta en: %s. Configure el producto o la línea."
                    % (prod_name[:80],)
                )
            if code_pairs:
                codes = SubElement(it, "Codes")
                for name, value in code_pairs:
                    SubElement(codes, "Code", {"Name": str(name), "Value": str(value)})

            # Basic fields (descripción respetando si el producto es genérico DGI)
            raw_item_desc = line._get_dgi_item_description() if hasattr(line, "_get_dgi_item_description") else line.name
            item_desc = _strip_reference_from_description(raw_item_desc, prod.default_code if prod else None)
            SubElement(it, "Description").text = _nuc_sanitize_text(item_desc or "ITEM")
            SubElement(it, "Qty").text = _fmt_amount(line.quantity, 2)
            # E06 UnitOfMeasure: opcional (Ocu 0-1) según DGI NUC-XML V2.0.7.
            # Solo se emite cuando el producto tiene el campo "Unidad de medida (DGI)" configurado
            # con un código válido del Catálogo de Unidades de Medida DGI.
            # NUNCA se usa la unidad de Odoo (e.g. "Galón") como fallback: no está en la
            # enumeración DGI y causa error de esquema 3010.
            uom_dgi = ""
            if prod_tmpl and getattr(prod_tmpl, "dgi_unidad_medida_id", None) and prod_tmpl.dgi_unidad_medida_id:
                uom_dgi = _nuc_safe_unit_code(_str_clean(prod_tmpl.dgi_unidad_medida_id.code))
            if uom_dgi:
                SubElement(it, "UnitOfMeasure").text = uom_dgi
            SubElement(it, "Price").text = _fmt_amount(line.price_unit, 6)

            # E08 Discounts (per item): DGI expects Amount (total discount in currency); % or fixed in Odoo we convert to amount
            line_discount_pct = _safe_money(getattr(line, "discount", 0) or 0)
            line_discount_amount = (line.quantity * line.price_unit) * (line_discount_pct / 100.0) if line_discount_pct else 0.0
            if line_discount_amount and abs(line_discount_amount) >= 0.00001:
                discounts_node = SubElement(it, "Discounts")
                disc = SubElement(discounts_node, "Discount")
                SubElement(disc, "Amount").text = _fmt_amount(line_discount_amount, 6)

            # --- Taxes (PER ITEM) ---
            taxes_node = SubElement(it, "Taxes")

            # Cliente exento (posición fiscal Exento en contacto): líneas sin impuesto o 0%.
            # DGI exige Code 00, Description ITBMS, Amount 0.00 (NUC 4; E0912 no permite "EXENTO").
            # Sin impuestos en línea → <Tax><Code>00</Code><Description>ITBMS</Description><Amount>0.00</Amount></Tax>
            if not line.tax_ids:
                # No taxes on line (exempt via fiscal position or no taxes assigned)
                tax = SubElement(taxes_node, "Tax")
                SubElement(tax, "Code").text = "00"
                SubElement(tax, "Description").text = "ITBMS"
                SubElement(tax, "Amount").text = _fmt_amount(0.0, 2)
            else:
                # Base for tax: after line discount so XML tax amounts match Odoo (price_subtotal / quantity)
                unit_after_discount = (line.price_subtotal / line.quantity) if line.quantity else line.price_unit

                # [FE-TAX-ROUNDING-FIX] Derive the expected total positive tax from Odoo's
                # confirmed line amounts. When a line has exactly ONE positive tax (typical Panama
                # ITBMS-only invoice), we use this value instead of compute_all()'s result to
                # guarantee that TotalBTaxes + Tax.Amount == TotalWTaxes in the XML.
                # Without this fix, Python floating-point rounding in compute_all() can produce
                # amounts that differ by 0.01 from Odoo's stored value (e.g. 0.87 vs 0.88
                # for 12.50 × 7%), causing per-item cuadrature errors at the DGI.
                odoo_line_tax_total = _safe_money(line.price_total) - _safe_money(line.price_subtotal)

                # IMPORTANT: When fiscal position is applied, line.tax_ids already contains the mapped taxes
                # (set by account_move_line._compute_tax_ids). compute_all will compute amounts for these taxes.
                # The partner passed to compute_all should have the fiscal position set for proper computation,
                # but since line.tax_ids already has mapped taxes, compute_all should work correctly.
                tax_res = line.tax_ids.compute_all(
                    unit_after_discount,
                    currency=move.currency_id,
                    quantity=line.quantity,
                    product=line.product_id,
                    partner=partner,
                )
                tax_lines = tax_res.get("taxes", []) or []
                # Count positive taxes to decide whether to apply the Odoo-confirmed amount
                positive_tax_count = sum(1 for t in tax_lines if _safe_money(t.get("amount", 0)) >= 0)
                # Detect retention: if ANY tax is negative, the line has retention alongside ITBMS.
                # In that case, odoo_line_tax_total is the NET (ITBMS - retention), not the gross ITBMS,
                # so we must NOT use it as a substitute — we need compute_all's gross individual amounts.
                has_negative_taxes = any(_safe_money(t.get("amount", 0)) < 0 for t in tax_lines)
                if not tax_lines:
                    # compute_all returned no taxes (exempt via fiscal position)
                    tax = SubElement(taxes_node, "Tax")
                    SubElement(tax, "Code").text = "00"
                    SubElement(tax, "Description").text = "ITBMS"
                    SubElement(tax, "Amount").text = _fmt_amount(0.0, 2)
                else:
                    # Keep track if we added any tax to the XML
                    added_tax_xml = False
                    for t in tax_lines:
                        tax_id = t.get("id")
                        # Find the tax object for Digifact code/description mapping
                        # IMPORTANT: When fiscal position is applied, line.tax_ids contains the mapped taxes
                        # (set by account_move_line._compute_tax_ids). The tax_id from compute_all should match
                        # one of the taxes in line.tax_ids. If not found, browse it directly.
                        tax_obj = self.env["account.tax"]
                        if tax_id:
                            # First try to find in line.tax_ids (these are the mapped taxes after fiscal position)
                            tax_obj = line.tax_ids.filtered(lambda x: x.id == tax_id)[:1]
                            # If not found in line.tax_ids, browse it directly (shouldn't happen normally)
                            if not tax_obj:
                                tax_obj = self.env["account.tax"].browse(tax_id)
                                # If tax doesn't exist, use empty tax_obj (will use defaults)
                                if not tax_obj.exists():
                                    tax_obj = self.env["account.tax"]
                        
                        amount_raw = _safe_money(t.get("amount"))
                        # [FE-TAX-ROUNDING-FIX] Odoo is the source of truth for tax amounts.
                        # When there is exactly ONE positive tax and NO negative taxes (retention),
                        # use Odoo's confirmed difference (price_total - price_subtotal) to avoid
                        # floating-point drift from compute_all() line-by-line accumulation.
                        # EXCEPTION: when retention taxes are also on the line, price_total is NET
                        # (ITBMS gross - retention), so odoo_line_tax_total would give the net amount
                        # instead of the gross ITBMS. In that case use compute_all's gross value directly.
                        if positive_tax_count == 1 and amount_raw >= 0 and not has_negative_taxes:
                            amount = max(0.0, odoo_line_tax_total)
                        else:
                            amount = amount_raw

                        # Defaults by computed amount:
                        # - 0.00 => treat as ITBMS 0% or exento depending on mapping
                        # - >0 => ITBMS normal
                        if abs(amount) < 0.00001:
                            default_code = "00"
                            default_desc = "ITBMS"
                        else:
                            default_code = "01"
                            default_desc = "ITBMS"

                        code = (_str_clean(_get(tax_obj, "digifact_tax_code", "")) or default_code) if tax_obj else default_code
                        # E0912 Description = only ITBMS, ISC or OTI (never tax name like "7%")
                        desc = _tax_nombre_impuesto(tax_obj) if tax_obj else default_desc
                        if desc not in _TAX_NOMBRE_ALLOWED:
                            desc = "ITBMS"

                        # [FE-TAX-RETENTION] Skip ANY negative tax (retention) from item-level XML <Taxes> node.
                        # The DGI schema only allows positive values in this tag.
                        if amount < 0:
                            continue

                        # Accumulate gross tax for GrandTotal (ignoring retention)
                        total_taxes_gross_accum += amount
                        
                        if tax_obj and (not _str_clean(_get(tax_obj, "digifact_tax_code", "")) or not _str_clean(_get(tax_obj, "digifact_tax_desc", ""))):
                            _logger.warning("Tax %s has no Digifact mapping; default applied", tax_obj.name)

                        # Create the XML element ONLY if not skipped
                        tax = SubElement(taxes_node, "Tax")
                        SubElement(tax, "Code").text = code
                        SubElement(tax, "Description").text = desc
                        SubElement(tax, "Amount").text = _fmt_amount(amount, 2)
                        added_tax_xml = True

                    # If all taxes were skipped (e.g. only retention?), ensure at least one Tax node exists (00 Exempt)
                    # to match schema requirements if Taxes node is present.
                    if not added_tax_xml:
                         tax = SubElement(taxes_node, "Tax")
                         SubElement(tax, "Code").text = "00"
                         SubElement(tax, "Description").text = "ITBMS"
                         SubElement(tax, "Amount").text = _fmt_amount(0.0, 2)

            # Totals per item (NUC 1 / NUC 12: with discount send TotalBDiscount/TotalWDiscount; always TotalBTaxes, TotalWTaxes, SpecificTotal, TotalItem)
            totals = SubElement(it, "Totals")
            subtotal_line = _safe_money(line.price_subtotal)
            total_line = _safe_money(line.price_total)
            if line_discount_amount and abs(line_discount_amount) >= 0.00001:
                subtotal_before_disc = line.quantity * line.price_unit
                SubElement(totals, "TotalBDiscount").text = _fmt_amount(subtotal_before_disc, 5)
                SubElement(totals, "TotalWDiscount").text = _fmt_amount(subtotal_line, 5)
            SubElement(totals, "TotalBTaxes").text = _fmt_amount(subtotal_line, 5)
            SubElement(totals, "TotalWTaxes").text = _fmt_amount(total_line, 5)
            SubElement(totals, "SpecificTotal").text = _fmt_amount(total_line, 6)
            SubElement(totals, "TotalItem").text = _fmt_amount(total_line, 6)

        # --- Totals (NUC 1/12/13: QtyItems, F03 TotalCharges, F04 TotalDiscounts, F05 GrandTotal) ---
        totals_root = SubElement(root, "Totals")
        SubElement(totals_root, "QtyItems").text = str(len(item_lines))
        # F03 TotalCharges: una sola línea por tipo (suma de todas las líneas Acarreo → FACTURA, Seguro → SEGURO, Otros → OTROS_GASTOS). Nada de CPBS aplica.
        if charge_lines:
            charges_by_desc = {}
            for cl in charge_lines:
                ctype = getattr(cl.product_id.product_tmpl_id, "dgi_charge_type", None)
                desc = charge_type_map.get(ctype)
                if desc:
                    charges_by_desc[desc] = charges_by_desc.get(desc, 0.0) + _safe_money(cl.price_total)
            if charges_by_desc:
                total_charges_node = SubElement(totals_root, "TotalCharges")
                for desc in ("FACTURA", "SEGURO", "OTROS_GASTOS"):
                    amount = charges_by_desc.get(desc, 0.0)
                    if amount and abs(amount) >= 0.00001:
                        tc = SubElement(total_charges_node, "TotalCharge")
                        SubElement(tc, "Description").text = desc
                        SubElement(tc, "Amount").text = _fmt_amount(amount, 2)
        # F04 TotalDiscounts: solo descuentos a nivel de documento (campo dgi_total_discount).
        # Los descuentos por línea ya están declarados dentro de cada <Item><Discounts> y
        # ya están reflejados en line.price_subtotal (Odoo los resta ahí).
        # NO se vuelven a sumar aquí: hacerlo causaría que la DGI los reste dos veces
        # del total global, disparando el error 2504 (descuento invalida el valor total).
        total_discount_amount = 0.0
        doc_discount = _safe_money(getattr(move, "dgi_total_discount", 0) or 0)
        if doc_discount and abs(doc_discount) >= 0.00001:
            total_discount_amount = doc_discount
        if total_discount_amount and abs(total_discount_amount) >= 0.00001:
            total_discounts_node = SubElement(totals_root, "TotalDiscounts")
            disc_node = SubElement(total_discounts_node, "Discount")
            SubElement(disc_node, "Description").text = _nuc_sanitize_text(_str_clean(getattr(move, "dgi_total_discount_description", None)) or "Descuento")
            SubElement(disc_node, "Amount").text = _fmt_amount(total_discount_amount, 6)
        # Monto retención (HI101 ValRetenc): mismo valor que va en AditionalInfo; Ficha DGI ubica gRetenc dentro de gTot para el CAFE/PDF
        val_retenc_grand = 0.0
        show_ret = getattr(move, "dgi_show_retention_block", False)
        # Leer retención directamente del move (usuario puede haberla cambiado en borrador)
        rt = move.dgi_retention_type_id
        ra = getattr(move, "dgi_retention_amount", None)
        if show_ret and rt:
            # [FE-TAX-RETENTION] Use the stored retention amount which is now strictly calculated from journal items
            # to match Odoo's internal rounding (avoiding 1-cent discrepancies).
            val_retenc_grand = _safe_money(getattr(move, "dgi_retention_amount", 0.0))
            
            # Fallback if 0 (e.g. not computed yet), try simple percentage estimation or 0
            if val_retenc_grand == 0.0 and rt.percentage:
                 # Estimate based on taxes if needed, but ideally the field is correct.
                 # For now, let's trust the field 100% as we fixed the compute method.
                 pass
        # GrandTotal: el esquema NUC solo permite TotalBDiscounts, TotalWDiscounts, ExplicitTotal, InvoiceTotal (no Retencion)
        # [FE-ROUNDING-FIX] Para InvoiceTotal se usa move.amount_total de Odoo directamente
        # cuando no hay retención, evitando diferencias de redondeo causadas por acumular
        # compute_all() línea por línea. Con retención, move.amount_total ya tiene la retención
        # deducida, así que mantenemos el cálculo bruto con total_taxes_gross_accum
        # (que solo acumula impuestos positivos, excluyendo retenciones negativas).
        if show_ret and rt and val_retenc_grand:
            # Con retención: reconstruir total bruto (antes de retención)
            grand_total_amount = move.amount_untaxed + total_taxes_gross_accum
        else:
            # Sin retención: usar directamente el total de Odoo (evita drift de redondeo)
            grand_total_amount = move.amount_total

        grand = SubElement(totals_root, "GrandTotal")
        SubElement(grand, "TotalBTaxes").text = _fmt_amount(move.amount_untaxed, 2)
        SubElement(grand, "TotalWTaxes").text = _fmt_amount(grand_total_amount, 2)
        if total_discount_amount and abs(total_discount_amount) >= 0.00001:
            SubElement(grand, "TotalBDiscounts").text = _fmt_amount(move.amount_untaxed + total_discount_amount, 2)
            SubElement(grand, "TotalWDiscounts").text = _fmt_amount(move.amount_untaxed, 2)
        SubElement(grand, "InvoiceTotal").text = _fmt_amount(grand_total_amount, 2)

        # --- Payments: alineado con samples/NUC 20 - pago a plazos 30.xml (igual para 60, 90, otro). ---
        # Es UN solo pago. Contado: 1 nodo = forma de pago (01 o método) + total.
        # Crédito: 2 nodos describen ese único pago — (1) forma = crédito (01), (2) plazo = 1 cuota a 30/60/90 días o a fecha (PLAZO).
        pays = SubElement(root, "Payments")
        is_credito = (getattr(move, "dgi_payment_term_type", None) or "contado") == "credito"

        # Primero: forma de pago (iFormaPago). Contado = 01 o código método; crédito = 01 (crédito a plazo).
        pay_code = "01"
        if not is_credito and move.dgi_payment_method_id and getattr(move.dgi_payment_method_id, "code", None):
            pay_code = _str_clean(move.dgi_payment_method_id.code) or "01"
        elif not is_credito:
            pay_code = _str_clean(_get(company, "digifact_forma_pago", None)) or "01"
        pay01 = SubElement(pays, "Payment")
        SubElement(pay01, "Type").text = pay_code
        # DGI 2601: cuando la forma de pago es 99 (Otro) es obligatoria la descripción (dInfFormaPago)
        if pay_code == "99":
            desc_otro = _nuc_sanitize_text(
                _str_clean(getattr(move, "dgi_payment_method_other_desc", None)) or ""
            ).strip()
            if not desc_otro:
                desc_otro = "Otro"
            SubElement(pay01, "Description").text = desc_otro
        SubElement(pay01, "Amount").text = _fmt_amount(grand_total_amount, 2)

        if is_credito:
            # Segundo: plazo del crédito (gPagPlazo). 1 solo pago del total: 30/60/90 = emisión + N días; "otro" = fecha que indica el usuario.
            due_date = getattr(move, "dgi_plazo_due_date", None)
            if not due_date and hasattr(move, "_df_compute_due_date_from_plazo"):
                due_date = move._df_compute_due_date_from_plazo()
            if not due_date:
                due_date = getattr(move, "invoice_date_due", None) or getattr(move, "invoice_date", None)
            if not due_date or not hasattr(due_date, "strftime"):
                due_date = date.today()
            pay_plazo = SubElement(pays, "Payment")
            SubElement(pay_plazo, "Type").text = "PLAZO"
            # DGI schema requires MinLength on dInfPagPlazo (Description); "Pago a plazo" alone is too short
            if getattr(move, "dgi_plazo_option", None) in ("30", "60", "90"):
                desc = "Pago a plazo %s dias" % move.dgi_plazo_option
            else:
                # "Otro": incluir fecha para cumplir MinLength y que sea claro
                desc = "Pago a plazo a fecha indicada (vencimiento %s)" % due_date.strftime("%Y-%m-%d")
            SubElement(pay_plazo, "Description").text = _nuc_sanitize_text(_str_clean(desc) or "Pago a plazo a fecha indicada")
            SubElement(pay_plazo, "Date").text = due_date.strftime("%Y-%m-%dT09:00:00-05:00")
            SubElement(pay_plazo, "Amount").text = _fmt_amount(grand_total_amount, 2)

        # --- AdditionalDocumentInfo (NUC 2: Documento Fiscal Referenciado + TiempoPago) ---
        add_doc = SubElement(root, "AdditionalDocumentInfo")
        add_info = SubElement(add_doc, "AdditionalInfo")  # single wrapper per NUC 2
        ref_fe_ids = getattr(move, "dgi_referenced_fe_ids", None)
        if move.move_type == "out_refund" and ref_fe_ids:
            # AditionalData: one Data per referenced FE (NUC 2 - Notas de credito.xml)
            aditional_data = SubElement(add_info, "AditionalData")
            for ref in ref_fe_ids:
                if not ref.cufe:
                    continue
                data_node = SubElement(aditional_data, "Data")  # no Name attribute per NUC 2
                _add_info(data_node, "NombEmRef", _nuc_sanitize_text(_str_clean(ref.issuer_name) or ""))
                issue_dt = ref.issue_date
                if issue_dt:
                    # FechaDFRef: ISO with timezone -05:00 (Panama) per NUC 2
                    fecha_val = issue_dt.strftime("%Y-%m-%dT00:00:00-05:00") if hasattr(issue_dt, "strftime") else str(issue_dt)
                    _add_info(data_node, "FechaDFRef", fecha_val)
                _add_info(data_node, "CUFERef", _str_clean(ref.cufe) or "")
        # TiempoPago: 1=Contado, 2=Crédito (required by schema)
        aditional_info = SubElement(add_info, "AditionalInfo")
        tiempo_pago = "1" if (getattr(move, "dgi_payment_term_type", None) or "contado") == "contado" else "2"
        _add_info(aditional_info, "TiempoPago", tiempo_pago)
        # [FE-TAX-RETENTION] Add retention info to AditionalInfo (HI10 CodRetenc, HI101 ValRetenc)
        # User requirement: identify customer as tax retention -> send CodRetenc
        if show_ret and rt and rt.code:
            _add_info(aditional_info, "CodRetenc", _str_clean(rt.code))
            if val_retenc_grand and abs(val_retenc_grand) >= 0.00001:
                _add_info(aditional_info, "ValRetenc", _fmt_amount(val_retenc_grand, 2))

        # Pretty-print so the XML opens in editors (e.g. VS Code) with structure like Digifact examples
        _indent_xml(root)
        xml_bytes = tostring(root, encoding="utf-8", method="xml")
        # Match Digifact examples: no space before /> in self-closing tags (e.g. <Info ... /> not <Info ... />)
        xml_str = (b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes).decode("utf-8")
        xml_str = xml_str.replace(" />", "/>")
        return xml_str.encode("utf-8")