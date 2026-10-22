# -*- coding: utf-8 -*-
import json
import logging
import requests
import base64
from datetime import datetime, timedelta
from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DigifactClient(models.AbstractModel):
    """
    Cliente para interactuar con la API de Digifact Panamá.
    Maneja autenticación, consulta de RUC y certificación de documentos.
    """
    _name = "digifact.client"
    _description = "Digifact API Client (Panama)"

    def get_token(self, username, password, company):
        """
        Obtiene un token de autenticación de Digifact.
        
        Según la documentación de Digifact Panamá, el username debe ser:
        PA.<RUC>.<NombreUsuario>
        
        Args:
            username (str): Nombre de usuario de Digifact (sin el prefijo PA.RUC.)
            password (str): Contraseña de Digifact
            company (res.company): Compañía para guardar el token (debe tener RUC en VAT)
        
        Returns:
            dict: Datos del token (token, expires_at, etc.)
        """
        if not company or not company.digifact_api_base_url:
            raise UserError(_("URL base de API Digifact no configurada en la compañía."))
        
        # Obtener RUC de la compañía
        if not company.vat:
            raise UserError(_("Por favor configure el RUC en el campo NIF/VAT de la información general de la compañía antes de obtener el token."))
        
        # Usar el VAT completo (puede venir como "155704849-2-2021" o "155704849")
        # Según Postman que funciona, el formato debe ser PA.155704849-2-2021.Usuario
        # No extraer solo los dígitos, usar el formato completo del VAT
        vat_clean = (company.vat or "").strip()
        if not vat_clean:
            raise UserError(_("No se pudo obtener el RUC del campo NIF/VAT. Por favor verifique el formato (ej: 155704849-2-2021 o 155704849)."))
        
        # Limpiar username también (eliminar espacios)
        username_clean = (username or "").strip()
        if not username_clean:
            raise UserError(_("El nombre de usuario de Digifact no puede estar vacío."))
        
        # Construir username según formato de Digifact Panamá: PA.<RUC completo>.<NombreUsuario>
        # El username que viene ya es solo el nombre de usuario, necesitamos agregar PA. y el RUC completo
        digifact_username = f"PA.{vat_clean}.{username_clean}"
        
        # Log para verificar el formato exacto
        _logger.info("Construyendo username Digifact - VAT: '%s', Usuario: '%s'", vat_clean, username_clean)
        _logger.info("Username completo resultante: '%s'", digifact_username)
        
        # Construir URL del endpoint
        base_url = company.digifact_api_base_url.rstrip('/')
        url = f"{base_url}/login/get_token"
        
        # Payload de autenticación - según Postman que funciona, usa minúscula
        # El formato debe ser: username (PA.RUC.Usuario) y password (en minúscula)
        payload = {
            "username": digifact_username,
            "password": password
        }
        
        # Headers
        headers = {
            "Content-Type": "application/json",
        }
        
        try:
            _logger.info("Obteniendo token de Digifact - URL: %s, VAT: %s, Usuario: %s", url, vat_clean, username)
            _logger.info("Username completo (PA.VAT.Usuario): %s", digifact_username)
            _logger.debug("Payload: %s", json.dumps(payload))
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            status_code = response.status_code
            
            _logger.info("Respuesta HTTP status: %s", status_code)
            _logger.debug("Respuesta completa: %s", response.text[:500])
            
            # Intentar parsear respuesta JSON
            try:
                response_data = response.json()
                _logger.debug("Respuesta JSON parseada: %s", json.dumps(response_data)[:500])
            except json.JSONDecodeError as e:
                _logger.error("Error parseando JSON: %s. Respuesta: %s", str(e), response.text[:500])
                raise UserError(_("Respuesta inválida del servidor Digifact (no es JSON válido). Status: %s, Respuesta: %s") % 
                              (status_code, response.text[:200]))
            
            # Verificar status HTTP
            if status_code != 200:
                error_msg = response_data.get("Error") or response_data.get("Mensaje") or response_data.get("message") or response.text[:200]
                _logger.error("Error HTTP %s: %s", status_code, error_msg)
                raise UserError(_("Error al obtener token de Digifact (HTTP %s): %s") % (status_code, error_msg))
            
            # Verificar si la respuesta indica éxito
            # La API puede retornar Ok=True o simplemente el token directamente
            ok = response_data.get("Ok")
            if ok is False:
                error_msg = response_data.get("Error") or response_data.get("Mensaje") or response_data.get("message") or "Error desconocido"
                _logger.error("API retornó Ok=False: %s", error_msg)
                raise UserError(_("Error al obtener token de Digifact: %s") % error_msg)
            
            # Extraer token y datos de expiración
            # El token puede venir en diferentes campos según la versión de la API
            token = response_data.get("Token") or response_data.get("token") or response_data.get("TokenValue")
            if not token:
                _logger.error("No se encontró token en la respuesta: %s", json.dumps(response_data))
                raise UserError(_("No se recibió token en la respuesta de Digifact. Respuesta: %s") % 
                              json.dumps(response_data)[:200])
            
            # Calcular fecha de expiración
            # La API puede retornar "expira_en" como string de fecha o "ExpiresIn" como segundos
            expires_at = None
            expires_in = None
            
            # Intentar obtener expira_en como string de fecha (formato: "2/25/2026 6:17:39 PM")
            expira_en_str = response_data.get("expira_en")
            if expira_en_str:
                try:
                    # Parsear fecha en formato "M/D/YYYY H:MM:SS AM/PM" (formato de Panamá)
                    # Intentar con strptime primero
                    try:
                        expires_at = datetime.strptime(expira_en_str, "%m/%d/%Y %I:%M:%S %p")
                    except ValueError:
                        # Si falla, intentar con dateutil si está disponible
                        try:
                            from dateutil import parser
                            expires_at = parser.parse(expira_en_str)
                        except ImportError:
                            # Si dateutil no está disponible, usar formato alternativo
                            expires_at = datetime.strptime(expira_en_str, "%d/%m/%Y %I:%M:%S %p")
                    
                    expires_in = int((expires_at - datetime.now()).total_seconds())
                    _logger.info("Fecha de expiración parseada desde expira_en: %s", expires_at)
                except Exception as e:
                    _logger.warning("Error parseando expira_en '%s': %s", expira_en_str, str(e))
            
            # Si no se pudo obtener de expira_en, intentar ExpiresIn (segundos)
            if not expires_at:
                expires_in = response_data.get("ExpiresIn") or response_data.get("expires_in") or 86400  # Default 24 horas
                expires_at = datetime.now() + timedelta(seconds=int(expires_in))
                _logger.info("Fecha de expiración calculada desde ExpiresIn: %s", expires_at)
            
            _logger.info("Token obtenido exitosamente, expira en: %s", expires_at)
            
            return {
                "token": token,
                "expires_at": expires_at,
                "expires_in": expires_in,
            }
            
        except UserError:
            # Re-lanzar UserError sin modificar
            raise
        except requests.exceptions.Timeout:
            _logger.error("Timeout al obtener token de Digifact")
            raise UserError(_("Timeout al conectar con Digifact. Verifique su conexión a internet."))
        except requests.exceptions.ConnectionError as e:
            _logger.error("Error de conexión: %s", str(e))
            raise UserError(_("Error de conexión con Digifact. Verifique la URL y su conexión a internet: %s") % str(e))
        except requests.exceptions.RequestException as e:
            _logger.error("Error en petición get_token: %s", str(e), exc_info=True)
            raise UserError(_("Error de conexión con Digifact: %s") % str(e))
        except Exception as e:
            _logger.error("Error inesperado al obtener token: %s", str(e), exc_info=True)
            raise UserError(_("Error inesperado al obtener token de Digifact: %s") % str(e))

    def ensure_token(self, company):
        """
        Asegura que la compañía tiene un token válido de Digifact.
        Si no existe o está expirado, obtiene uno nuevo.
        """
        if not company:
            raise UserError(_("Compañía no especificada para obtener token de Digifact."))
        
        # Verificar si el token existe y no está expirado
        if company.digifact_token and company.digifact_token_expires_at:
            expires_at = company.digifact_token_expires_at
            # Si el token expira en más de 5 minutos, está válido
            if expires_at > (datetime.now() + timedelta(minutes=5)):
                _logger.debug("Token de Digifact aún válido para compañía %s", company.name)
                return
        
        # Obtener nuevo token.
        # Usamos sudo() SOLO para la escritura del token en res.company porque
        # cualquier usuario con permisos de facturación puede disparar el refresh
        # automáticamente al enviar un documento, pero res.company solo es
        # modificable por Administradores.  Las credenciales (user/password)
        # ya están en el objeto `company` que viene del contexto original.
        _logger.info("Obteniendo nuevo token de Digifact para compañía %s", company.name)
        company.sudo().action_digifact_get_token()

    def get_info_ruc(self, ruc, tipo, company):
        """
        Obtiene información de un RUC desde la API de Digifact.
        
        Args:
            ruc (str): RUC a consultar (sin DV)
            tipo (int): Tipo de RUC (1=Natural, 2=Jurídica)
            company (res.company): Compañía con credenciales configuradas
        
        Returns:
            tuple: (http_status, payload_dict)
        """
        if not company or not company.digifact_api_base_url:
            raise UserError(_("URL base de API Digifact no configurada en la compañía."))
        
        # Asegurar token válido
        self.ensure_token(company)
        
        # Construir URL del endpoint - según referencia usa GetInfoRuc (sin FE/FacturaElectronica)
        base_url = company.digifact_api_base_url.rstrip('/')
        url = f"{base_url}/GetInfoRuc?RUC={ruc}&TIPO={int(tipo)}"
        
        # Headers - según referencia, Authorization es solo el token, no "Bearer {token}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": company.digifact_token,
        }
        
        try:
            _logger.info("Consultando RUC %s (tipo %s) en Digifact", ruc, tipo)
            response = requests.get(url, headers=headers, timeout=30)
            status_code = response.status_code
            
            # Intentar parsear respuesta JSON
            try:
                payload = response.json()
            except json.JSONDecodeError:
                payload = {"Ok": False, "Error": f"Respuesta no válida: {response.text[:200]}"}
            
            _logger.info("Respuesta GetInfoRUC: status=%s, Ok=%s", status_code, payload.get("Ok"))
            
            return (status_code, payload)
            
        except requests.exceptions.RequestException as e:
            _logger.error("Error en petición GetInfoRUC: %s", str(e))
            return (0, {"Ok": False, "Error": str(e)})

    def certificate_fe_xml_tosign_v2(self, xml_bytes, company, fmt="XML|PDF|HTML"):
        """
        Certifica un documento XML NUC en Digifact.
        
        Args:
            xml_bytes (bytes): XML NUC a certificar
            company (res.company): Compañía con credenciales configuradas
            fmt (str): Formatos de respuesta deseados (ej: "XML|PDF|HTML")
        
        Returns:
            tuple: (http_status, response_dict)
        """
        if not company or not company.digifact_api_base_url:
            raise UserError(_("URL base de API Digifact no configurada en la compañía."))
        
        # Asegurar token válido
        self.ensure_token(company)
        
        # Construir URL del endpoint - según referencia usa v2/transform/nuc con parámetros en query
        base_url = company.digifact_api_base_url.rstrip('/')
        
        # TAXID y USERNAME deben usar el mismo formato que en get_token (VAT completo)
        # Si usamos solo dígitos, Digifact devuelve 401 porque el token se emitió para PA.155704849-2-2021.Usuario
        vat_clean = (company.vat or "").strip()
        if not vat_clean:
            raise UserError(_("RUC no disponible en la compañía para certificar el documento. Configure NIF/VAT (ej: 155704849-2-2021)."))
        
        digifact_username = f"PA.{vat_clean}.{company.digifact_user}" if company.digifact_user else ""
        if not digifact_username:
            raise UserError(_("Usuario Digifact no configurado en la compañía."))
        
        # Convertir XML a bytes si es necesario
        if isinstance(xml_bytes, str):
            xml_bytes = xml_bytes.encode('utf-8')
        
        # Construir URL con parámetros según referencia (TAXID = VAT completo, igual que en get_token)
        url = f"{base_url}/v2/transform/nuc?TAXID={vat_clean}&USERNAME={digifact_username}&FORMAT={fmt}"
        
        # Headers: charset=utf-8 so server correctly interprets ñ/tildes in XML body
        headers = {
            "Content-Type": "application/xml; charset=utf-8",
            "Authorization": company.digifact_token,
        }
        
        try:
            _logger.info("Certificando XML NUC en Digifact (tamaño: %d bytes, TAXID: %s)", len(xml_bytes), vat_clean)
            # Enviar XML directamente como body, no como JSON con base64
            response = requests.post(url, data=xml_bytes, headers=headers, timeout=60)
            status_code = response.status_code
            
            # Intentar parsear respuesta JSON
            try:
                response_data = response.json()
            except json.JSONDecodeError as e:
                raw = (response.text or "").strip()
                content_type = response.headers.get("Content-Type", "")
                detail = (
                    f"Status HTTP: {status_code}, Content-Type: {content_type}. "
                    f"Cuerpo (primeros 1000 caracteres): {raw[:1000]!r}"
                )
                _logger.error(
                    "Digifact no devolvió JSON válido. %s Cuerpo completo (primeros 2000 chars): %s",
                    detail, raw[:2000]
                )
                response_data = {
                    "Ok": False,
                    "Error": f"Respuesta no válida (no es JSON): {detail}",
                    "RawResponse": raw[:5000],
                    "HttpStatus": status_code,
                    "ContentType": content_type,
                }
            
            _logger.info("Respuesta Certificate_FE_XML_TOSIGN_V2: status=%s, Ok=%s", 
                        status_code, response_data.get("Ok"))
            
            code = response_data.get("code")
            try:
                code_ok = code is None or int(code) == 1
            except (ValueError, TypeError):
                code_ok = False
            # Log full response for debugging (especially errors)
            if not response_data.get("Ok") or not code_ok:
                _logger.error("Digifact rechazó el XML. Status: %s, Code: %s, Response: %s", 
                            status_code, code, json.dumps(response_data, ensure_ascii=False)[:1000])
            
            return (status_code, response_data)
            
        except requests.exceptions.RequestException as e:
            _logger.error("Error en petición Certificate_FE_XML_TOSIGN_V2: %s", str(e))
            # Include more details in error response
            error_detail = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_detail += f" | Response: {e.response.text[:500]}"
                except:
                    pass
            return (0, {"Ok": False, "Error": error_detail, "HttpStatus": getattr(e, "status_code", 0)})

    def cancel_fel(self, move, company=None, motivo=None):
        """
        Anula una factura electrónica ya certificada en Digifact (API 2.1.5 CANCEL FEL).

        Documentación: Documentacion Tecnica API Digifact Panama V2.0.3, Tabla 5 y 6.
        Test: https://testnucpa.digifact.com/api/CancelFePA
        Productivo: https://apinuc.digifact.com.pa/api/CancelFePA

        Body: Taxid (RUC emisor), Cufe (CUFE del documento), Motivo, Username.
        Respuesta: Codigo, Anulado (booleano), Mensaje.

        Args:
            move: account.move (factura certificada con digifact_cufe).
            company: res.company con credenciales (default: move.company_id).
            motivo: descripción del motivo de anulación (opcional; si no se indica se usa un texto por defecto).

        Returns:
            tuple: (http_status, response_dict)
        """
        company = company or move.company_id
        if not company or not company.digifact_api_base_url:
            raise UserError(_("URL base de API Digifact no configurada en la compañía."))

        self.ensure_token(company)

        base_url = company.digifact_api_base_url.rstrip("/")
        url = f"{base_url}/CancelFePA"

        vat_clean = (company.vat or "").strip()
        if not vat_clean:
            raise UserError(_("RUC no configurado en la compañía."))

        cufe = getattr(move, "digifact_cufe", None) and (move.digifact_cufe or "").strip()
        if not cufe:
            raise UserError(_(
                "Para anular en Digifact se requiere el CUFE de la factura. "
                "Esta factura no tiene CUFE guardado (certifique primero la factura)."
            ))

        username = (company.digifact_user or "").strip()
        if not username:
            raise UserError(_("Usuario Digifact no configurado en la compañía."))

        motivo_text = (motivo or "").strip() or _("Anulación solicitada desde sistema.")

        body = {
            "Taxid": vat_clean,
            "Cufe": cufe,
            "Motivo": motivo_text,
            "Username": username,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": company.digifact_token,
        }

        try:
            _logger.info("Anulando FEL en Digifact (CANCEL FEL): CUFE=%s", cufe[:50] + "..." if len(cufe) > 50 else cufe)
            response = requests.post(url, json=body, headers=headers, timeout=30)
            status_code = response.status_code

            try:
                response_data = response.json()
            except json.JSONDecodeError:
                raw = (response.text or "").strip()
                response_data = {
                    "Anulado": False,
                    "Codigo": 0,
                    "Mensaje": f"Respuesta no JSON. HTTP {status_code}: {raw[:500]}",
                    "RawResponse": raw[:2000],
                    "HttpStatus": status_code,
                }

            _logger.info("Respuesta CancelFePA: status=%s, Anulado=%s", status_code, response_data.get("Anulado"))
            return (status_code, response_data)

        except requests.exceptions.RequestException as e:
            _logger.error("Error en petición CancelFePA: %s", str(e))
            return (0, {"Anulado": False, "Codigo": 0, "Mensaje": str(e)})

    def get_dte_status(self, move, company=None):
        """
        Consulta en Digifact/DGI el estado de un DTE por CUFE.

        Referencia: Documentación Técnica API Digifact Panamá V2.0.3 (sección consulta estado DTE).
        Endpoint y formato de respuesta deben coincidir con dicha documentación.

        Args:
            move: account.move con digifact_cufe (factura ya enviada/certificada).
            company: res.company (default: move.company_id).

        Returns:
            tuple: (http_status, response_dict).
            response_dict puede contener: Codigo, Estado, Anulado, Mensaje, u otros según la API.
        """
        company = company or move.company_id
        if not company or not company.digifact_api_base_url:
            raise UserError(_("URL base de API Digifact no configurada en la compañía."))

        self.ensure_token(company)

        base_url = company.digifact_api_base_url.rstrip("/")
        # Nombre del endpoint según Documentación Técnica API Digifact Panamá V2.0.3 (consulta estado)
        url = f"{base_url}/GetStatusFePA"

        vat_clean = (company.vat or "").strip()
        if not vat_clean:
            raise UserError(_("RUC no configurado en la compañía."))

        cufe = getattr(move, "digifact_cufe", None) and (move.digifact_cufe or "").strip()
        if not cufe:
            raise UserError(_(
                "Para consultar el estado en Digifact se requiere el CUFE de la factura. "
                "Esta factura no tiene CUFE guardado."
            ))

        body = {
            "Taxid": vat_clean,
            "Cufe": cufe,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": company.digifact_token,
        }

        try:
            _logger.info("Consultando estado DTE en Digifact: CUFE=%s", cufe[:50] + "..." if len(cufe) > 50 else cufe)
            response = requests.post(url, json=body, headers=headers, timeout=30)
            status_code = response.status_code

            try:
                response_data = response.json()
            except json.JSONDecodeError:
                raw = (response.text or "").strip()
                response_data = {
                    "Codigo": -1,
                    "Mensaje": f"Respuesta no JSON. HTTP {status_code}: {raw[:500]}",
                    "HttpStatus": status_code,
                }

            _logger.info("Respuesta GetStatusFePA: status=%s, data=%s", status_code, response_data)
            return (status_code, response_data)

        except requests.exceptions.RequestException as e:
            _logger.error("Error en petición GetStatusFePA: %s", str(e))
            return (0, {"Codigo": -1, "Mensaje": str(e)})

    def get_dte_status_by_cufe(self, company, cufe):
        """
        Consulta en Digifact/DGI el estado (y datos si vienen) de un DTE por CUFE.
        Útil para "Nota de crédito referente a una o varias FE": validar CUFE y opcionalmente
        obtener Fecha emisión, RUC emisor, Nombre emisor si la API los devuelve.

        Args:
            company: res.company con digifact_api_base_url y credenciales.
            cufe: str, CUFE a consultar.

        Returns:
            tuple: (http_status, response_dict).
        """
        if not company or not company.digifact_api_base_url:
            raise UserError(_("URL base de API Digifact no configurada en la compañía."))
        self.ensure_token(company)
        base_url = company.digifact_api_base_url.rstrip("/")
        url = f"{base_url}/GetStatusFePA"
        vat_clean = (company.vat or "").strip()
        if not vat_clean:
            raise UserError(_("RUC no configurado en la compañía."))
        cufe = (cufe or "").strip()
        if not cufe:
            raise UserError(_("Indique el CUFE a consultar."))
        body = {"Taxid": vat_clean, "Cufe": cufe}
        headers = {"Content-Type": "application/json", "Authorization": company.digifact_token}
        try:
            _logger.info("Consultando DTE por CUFE en Digifact (primeros 50 chars): %s...", cufe[:50])
            response = requests.post(url, json=body, headers=headers, timeout=30)
            status_code = response.status_code
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                raw = (response.text or "").strip()
                response_data = {"Codigo": -1, "Mensaje": f"Respuesta no JSON. HTTP {status_code}: {raw[:500]}"}
            return (status_code, response_data)
        except requests.exceptions.RequestException as e:
            _logger.error("Error en petición GetStatusFePA (by CUFE): %s", str(e))
            return (0, {"Codigo": -1, "Mensaje": str(e)})

    def get_document(self, move, company=None, fmt="PDF"):
        """
        Descarga un documento electrónico certificado (o anulado) desde Digifact por CUFE.
        API 2.1.7 GET DOCUMENT.

        Test:       https://testnucpa.digifact.com/api/GetDocument
        Productivo: https://apinuc.digifact.com.pa/api/GetDocument

        Parámetros (query string):
            CUFE     - Código único de factura electrónica
            RUC      - RUC del emisor  (ej. 155704849-2-2021)
            FORMAT   - Formatos separados por pipeline: XML | HTML | PDF
            USERNAME - Nombre de usuario Digifact (sin prefijo PA.RUC.)

        Respuesta JSON:
            {
              "REQUEST_DATA": [{...}],
              "RESPONSE": [{"ResponseData1": <b64 XML>, "ResponseData2": <b64 HTML>, "ResponseData3": <b64 PDF>}]
            }
        Si el documento aún no está disponible en el servidor: "RESPONSE": []

        Args:
            move:    account.move con digifact_cufe.
            company: res.company con credenciales (default: move.company_id).
            fmt:     Formatos deseados, ej. "PDF" o "PDF|HTML" o "XML|HTML|PDF".

        Returns:
            tuple: (http_status, response_dict)
        """
        company = company or move.company_id
        if not company or not company.digifact_api_base_url:
            raise UserError(_("URL base de API Digifact no configurada en la compañía."))

        self.ensure_token(company)

        base_url = company.digifact_api_base_url.rstrip("/")
        url = f"{base_url}/GetDocument"

        vat_clean = (company.vat or "").strip()
        if not vat_clean:
            raise UserError(_("RUC no configurado en la compañía."))

        cufe = getattr(move, "digifact_cufe", None) and (move.digifact_cufe or "").strip()
        if not cufe:
            raise UserError(_(
                "Para obtener el documento se requiere el CUFE. "
                "Esta factura no tiene CUFE guardado."
            ))

        username = (company.digifact_user or "").strip()
        if not username:
            raise UserError(_("Usuario Digifact no configurado en la compañía."))

        params = {
            "CUFE": cufe,
            "RUC": vat_clean,
            "FORMAT": fmt,
            "USERNAME": username,
        }

        headers = {
            "Authorization": company.digifact_token,
        }

        try:
            _logger.info(
                "GetDocument Digifact (API 2.1.7): CUFE=%s..., FORMAT=%s",
                cufe[:50],
                fmt,
            )
            response = requests.get(url, params=params, headers=headers, timeout=30)
            status_code = response.status_code

            try:
                response_data = response.json()
            except json.JSONDecodeError:
                raw = (response.text or "").strip()
                _logger.warning("GetDocument: respuesta no JSON. HTTP %s: %s", status_code, raw[:500])
                response_data = {
                    "REQUEST_DATA": [],
                    "RESPONSE": [],
                    "_raw": raw[:2000],
                    "HttpStatus": status_code,
                }

            _logger.info(
                "GetDocument respuesta: HTTP %s, RESPONSE items=%s",
                status_code,
                len(response_data.get("RESPONSE") or []),
            )
            return (status_code, response_data)

        except requests.exceptions.Timeout:
            _logger.error("GetDocument: timeout para CUFE %s", cufe[:50])
            return (0, {"REQUEST_DATA": [], "RESPONSE": [], "Mensaje": "Timeout al conectar con Digifact."})
        except requests.exceptions.RequestException as e:
            _logger.error("GetDocument: error de conexión: %s", str(e))
            return (0, {"REQUEST_DATA": [], "RESPONSE": [], "Mensaje": str(e)})
