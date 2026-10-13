# Términos y Condiciones (`mba_terminos_condiciones`)

Módulo agnóstico para Odoo 19 Community. Agrega a la compañía una pestaña **Datos de pago**
(cheque a, beneficiario, # de cuenta, tipo de cuenta, SWIFT, direcciones del beneficiario y del banco)
y genera los **Términos y condiciones por defecto** (`res.company.invoice_terms`) como una tabla de
2 columnas, aprovechando todo el ancho de la cotización/factura.

- No contiene datos de ningún cliente. Los valores de cada cliente viven en un micro-módulo de datos
  aparte (ej. `solarsupply_terminos_data`), para que sobrevivan reinstalaciones o bases nuevas.
- `action_mba_generar_terminos()` escribe el texto en **todos los idiomas instalados** (el campo es traducible).
- Requiere activar en Ajustes > Facturación "Términos y condiciones predeterminados" con la opción "Agregar una nota".

## Dependencias
- `account`

## Licencia
LGPL-3.
