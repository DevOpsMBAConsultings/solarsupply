# Manual de Usuario - Sistema de Facturación Electrónica Panamá

## 1. Configuración Inicial

### 1.1. Configuración de Empresa
**Propósito:** Registrar información fiscal requerida por la DGI  
**Ruta:** Contabilidad > Configuración > Compañías > Seleccionar compañía  
**Campos obligatorios:**
- RUC de la empresa (10 dígitos)
- Código de sucursal (4 dígitos)
- Punto de facturación (4 dígitos)
- Ambiente (Pruebas/Producción)
- Credenciales PAC (según proveedor)

**Notas técnicas:**
- Los códigos de sucursal/punto deben coincidir con los registrados en la DGI
- En ambiente de pruebas se usan certificados de prueba

### 1.2. Configuración de Diarios
**Propósito:** Asociar diarios contables con puntos de facturación  
**Ruta:** Contabilidad > Configuración > Diarios > Seleccionar diario  
**Campos obligatorios:**
- Código de sucursal (4 dígitos)
- Punto de facturación para facturas definitivas (4 dígitos)

**Notas técnicas:**
- Cada diario representa un punto de facturación físico
- Debe coincidir con la configuración en la DGI

## 2. Gestión de Contactos

### 2.1. Validación de Partners
**Propósito:** Garantizar que los partners cumplan con requisitos DGI  
**Pasos:**
1. Navegar a: Contactos > Seleccionar contacto
2. En pestaña "Información Fiscal":
   - Seleccionar tipo de receptor (01: Contribuyente, 02: CF, etc.)
   - Ingresar RUC (excepto Consumidor Final)
3. Hacer clic en "Validar RUC"
4. Revisar validación:
   - ✅ Alerta verde: Validación exitosa
   - ❌ Alerta roja: Corregir errores mostrados

**Validaciones automáticas:**
- Consumidor Final: RUC opcional
- Contribuyente/Gobierno: Requieren dirección completa
- Empresas: No pueden ser tipo Consumidor Final

## 3. Gestión de Productos

### 3.1. Creación de Productos
**Propósito:** Cumplir con requerimientos DGI para ítems facturados  
**Pasos:**
1. Navegar a: Productos > Crear nuevo producto
2. En pestaña "Información General":
   - Seleccionar familia y segmento CPBS
3. En pestaña "Facturación Electrónica":
   - Ingresar código CPBS (8 dígitos)
   - Especificar abreviatura (3 caracteres)
   - Seleccionar unidad de medida DGI
   - Asignar impuestos positivos

**Validaciones automáticas:**
- Consistencia entre familia/segmento CPBS
- Longitud de códigos DGI
- Impuestos asignados para productos vendibles

## 4. Proceso de Facturación

### 4.1. Emisión de Factura Electrónica
**Flujo completo:**
1. Crear orden de venta:
   - Seleccionar partner validado
   - Agregar productos con datos fiscales completos
2. Confirmar orden → Genera factura en borrador
3. Publicar factura:
   - Sistema lanza wizard de confirmación
   - Verificar datos fiscales en pestaña "Soporte Técnico DGI"
4. Hacer clic en "Enviar a PAC"
5. Monitorear estados:
   - Enviado: Factura recibida por PAC
   - Aceptado: DGI aprobó documento
   - Error: Revisar mensaje en pestaña DGI

### 4.2. Descarga de Documentos (Solo HKA)
**Pasos:**
1. Para facturas en estado "Aceptada":
2. Abrir factura → Botón "Descargar PDF"
3. El sistema descarga representación gráfica con QR
4. Botón "Descargar XML" obtiene documento electrónico

### 4.3. Anulación de Facturas
**Requisitos:**
- Factura en estado "Aceptada"
- Tiempo límite: 72 horas según normativa DGI

**Pasos:**
1. Seleccionar factura aceptada
2. Hacer clic en "Anular"
3. Ingresar motivo de anulación (mínimo 10 caracteres)
4. Confirmar operación
5. Verificar cambio de estado a "Anulada"

**Notas técnicas:**
- Anulaciones generan documento de reverso
- No reversible: Una vez anulada no puede reactivarse
- Requiere conexión con PAC para transmisión

## 5. Manejo de Errores Comunes

### 5.1. Validación de Partner
**Síntoma:** No permite guardar factura  
**Solución:**
- Verificar que partner tenga "Validación DGI" exitosa
- Completar dirección para tipos 01/03
- Asignar método de pago DGI

### 5.2. Rechazo por PAC
**Síntoma:** Estado "Error" en factura  
**Solución:**
- Revisar mensaje en pestaña "Soporte Técnico DGI"
- Verificar consistencia de datos:
  - RUC emisor/receptor
  - Totales
  - Códigos de producto
- Reenviar después de correcciones

### 5.3. Error de Conexión
**Síntoma:** Tiempo de espera agotado  
**Solución:**
- Verificar credenciales PAC
- Comprobar acceso a internet
- Validar certificados digitales
