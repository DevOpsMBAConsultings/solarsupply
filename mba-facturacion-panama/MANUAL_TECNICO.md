# Manual Técnico - Sistema de Facturación Electrónica Panamá

## Arquitectura del Sistema
El sistema de facturación electrónica para Panamá está compuesto por 6 módulos principales que interactúan mediante una arquitectura en capas:

```
mba_pa_base → mba_pa_products → mba_pa_sale → mba_pa_edi → [mba_pa_edi_digifact | mba_pa_edi_hka]
```

### 1. mba_pa_base
**Lógica de Negocio:**
- Proporciona la base de datos maestra de ubicaciones (provincias, distritos, corregimientos)
- Extiende los modelos `ResCompany` y `ResPartner` con campos fiscales específicos de Panamá
- Implementa la validación de RUC mediante integración con APIs PAC
- Proporciona servicios de formato para teléfonos y direcciones según normas DGI

**Dependencias Técnicas:**
- Requiere `base`, `account`, `l10n_pa` (módulo contable base para Panamá)
- Debe instalarse primero ya que otros módulos dependen de sus estructuras de datos

**Flujos de Datos:**
1. Al crear/editar un partner:
   - Validación de tipo de receptor vs tipo de compañía
   - Formateo automático de teléfonos según país
   - Cálculo de código de ubicación (provincia-distrito-corregimiento)
2. Al validar RUC:
   - Llamada a `action_get_ruc_details` en `ResCompany`
   - Comunicación con API PAC según proveedor configurado
   - Actualización de datos de partner con respuesta

### 2. mba_pa_products
**Lógica de Negocio:**
- Gestiona catálogos DGI: familias CPBS, segmentos, unidades de medida
- Extiende `ProductTemplate` con campos requeridos para facturación electrónica
- Implementa validaciones de productos:
  - Consistencia entre segmento y familia CPBS
  - Longitud de códigos DGI
  - Asignación de impuestos para productos vendibles

**Dependencias Técnicas:**
- Requiere `mba_pa_base`, `product`, `sale`
- Debe instalarse antes de `mba_pa_sale` para tener productos validados

**Flujos de Datos:**
- Al crear/editar producto:
  - Validación de códigos CPBS
  - Cálculo de abreviatura automática
  - Verificación de impuestos asignados

### 3. mba_pa_sale
**Lógica de Negocio:**
- Extiende el flujo de ventas con validaciones fiscales
- Implementa restricciones para partners no validados
- Calcula retenciones automáticas basadas en posición fiscal
- Bloquea modificación de facturas generadas desde cotizaciones

**Dependencias Técnicas:**
- Requiere `mba_pa_base`, `mba_pa_products`, `sale`, `account`
- Debe instalarse antes de los módulos EDI

**Flujos de Datos:**
1. Al confirmar orden de venta:
   - Validación de partner con RUC verificado
   - Cálculo automático de retenciones
   - Generación de factura con datos fiscales
2. Al crear factura:
   - Copia notas de pago desde partner
   - Aplicación de retenciones automáticas
   - Bloqueo de campos si viene de cotización

### 4. mba_pa_edi
**Lógica de Negocio:**
- Proporciona la base común para integraciones PAC
- Extiende `AccountMove` con campos para facturación electrónica:
  - Estado PAC, CUFE, QR
  - Métodos de pago, retenciones, notas
- Implementa validación de partners para facturas de compra/venta
- Define la estructura base para generación de payloads

**Dependencias Técnicas:**
- Requiere `mba_pa_base`, `mba_pa_sale`, `account`
- Sirve como abstracción para los conectores PAC específicos

**Flujos de Datos:**
1. Al publicar factura:
   - Lanzamiento de wizard de confirmación
   - Validación de partner según tipo de factura
2. Al enviar a PAC:
   - Cálculo de número fiscal
   - Construcción de payload inicial
   - Delegación a conector específico

### 5. mba_pa_edi_digifact
**Lógica de Negocio:**
- Implementa conector para PAC Digifact
- Genera XML en formato NUC (Norma Única de Contribuyentes)
- Gestiona autenticación con tokens JWT
- Procesa respuestas de certificación y cancelación

**Dependencias Técnicas:**
- Requiere `mba_pa_edi`, `account`, `base`
- Utiliza `DigifactNUCBuilder` para generación XML

**Flujos de Datos:**
1. Autenticación:
   - `get_token` → Obtiene token de seguridad
   - `ensure_token` → Gestiona renovación automática
2. Certificación:
   - `certificate_fe_xml_tosign_v2` → Envía XML para certificación
   - Procesa respuesta → Actualiza CUFE/QR
3. Cancelación:
   - `cancel_fel` → Envía solicitud de anulación
   - Procesa respuesta → Actualiza estado

### 6. mba_pa_edi_hka
**Lógica de Negocio:**
- Implementa conector para PAC HKA
- Genera payloads JSON específicos
- Gestiona descarga de documentos (PDF, XML)
- Implementa flujos completos de anulación

**Dependencias Técnicas:**
- Requiere `mba_pa_edi`, `account`, `base`
- Utiliza `HKAClient` para comunicación API

**Flujos de Datos:**
1. Envío de factura:
   - `build_payload` → Construye JSON
   - `send_document` → Envía a API HKA
2. Descarga:
   - `download_document` → Obtiene PDF/XML
3. Anulación:
   - `anular_documento` → Gestiona anulación

## Flujo Completo de Facturación
1. Creación de orden de venta (mba_pa_sale)
2. Validación de partner (mba_pa_base)
3. Confirmación de orden → Generación de factura
4. Publicación de factura → Lanzamiento de wizard
5. Construcción de payload (mba_pa_edi)
6. Envío a PAC (conector específico)
7. Procesamiento de respuesta:
   - Éxito: Actualización CUFE/QR
   - Error: Registro en campo `l10n_pa_pac_error`
8. Descarga de documentos (solo HKA)
9. Anulación (si aplica)

## Estados del Documento
- `draft`: Borrador (no enviado)
- `sent`: Enviado al PAC (en proceso)
- `accepted`: Aceptado por DGI
- `cancelled`: Anulado por DGI
- `error`: Rechazado por DGI/PAC

## Validaciones Clave
1. RUC de partner:
   - Requerido para tipos 01 (Contribuyente) y 03 (Gobierno)
   - Validado mediante API PAC
2. Productos:
   - Códigos CPBS válidos
   - Impuestos asignados
3. Factura:
   - Partner validado
   - Diario configurado con sucursal/punto
   - Campos obligatorios completos

## Manejo de Errores
- Errores de validación: `UserError` con mensaje específico
- Errores PAC: Registrados en `l10n_pa_pac_error`
- Logs detallados: Modelo `digifact.log` (Digifact)
- Reintentos: Implementados en nivel API
