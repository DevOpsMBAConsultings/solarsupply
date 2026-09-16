# Devolución, Despacho, Exchange y Auto-Conciliación (MBA Consultings)

![Odoo](https://img.shields.io/badge/Odoo-18.0%20Community-71639e?logo=odoo&logoColor=white)
![Versi%C3%B3n](https://img.shields.io/badge/versi%C3%B3n-18.0.1.5.2-blue)
![Licencia](https://img.shields.io/badge/licencia-LGPL--3-green)
![Autor](https://img.shields.io/badge/MBA%20Consultings-Brooks%20Gonzalez-orange)
![Website](https://img.shields.io/badge/web-mbaconsultings.com-lightgrey?link=https%3A%2F%2Fmbaconsultings.com)

Módulo para **Odoo 18 Community** que conecta Facturación (`account`) con Inventario (`stock`) sin
obligar a pasar por el flujo completo de Ventas. Permite ejecutar operaciones de almacén —devoluciones,
despachos directos e intercambios de mercancía— directamente desde la factura o la nota de crédito, y
automatiza el cruce contable de las notas de crédito con su factura original.

---

## Tabla de Contenidos

- [Funcionalidades](#funcionalidades)
  - [1. Devolución de Productos a Bodega](#1-devolución-de-productos-a-bodega)
  - [2. Despacho Directo desde Factura](#2-despacho-directo-desde-factura)
  - [3. Exchange / Cambio de Mercancía](#3-exchange--cambio-de-mercancía)
  - [4. Auto-Conciliación de Notas de Crédito](#4-auto-conciliación-de-notas-de-crédito)
  - [5. Semáforo Informativo de Conciliación](#5-semáforo-informativo-de-conciliación)
  - [6. Smart Button de Notas de Crédito](#6-smart-button-de-notas-de-crédito)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Guía de Uso](#guía-de-uso)
- [Estructura Técnica](#estructura-técnica)
- [Seguridad y Permisos](#seguridad-y-permisos)
- [Consideraciones y Limitaciones](#consideraciones-y-limitaciones)
- [Roadmap](#roadmap)
- [Autor y Soporte](#autor-y-soporte)
- [Licencia](#licencia)

---

## Funcionalidades

### 1. Devolución de Productos a Bodega

Genera el movimiento de **entrada a almacén** directamente desde una **Nota de Crédito** (publicada)
o una **Factura anulada**, y lo valida automáticamente a estado `Hecho`.

- **Escenario A — Existe despacho previo:** detecta el albarán de salida de la venta original (ya sea
  el despacho directo generado por este módulo o el picking de la orden de venta) y utiliza el
  asistente nativo `stock.return.picking` de Odoo, pre-cargando las cantidades del documento fiscal.
- **Escenario B — Sin despacho previo:** crea un albarán de recepción directo desde la ubicación del
  cliente hacia la bodega seleccionada.
- Vincula el albarán resultante en el campo **Devolución de Inventario** del documento y deja una
  tarjeta visual con el detalle de productos en el chatter.

### 2. Despacho Directo desde Factura

Para **facturas directas** (emitidas sin orden de venta previa), genera el movimiento de **salida de
almacén** con un clic, validado automáticamente.

- El botón solo aparece si la factura **no** proviene de una orden de venta (detección automática por
  líneas de venta vinculadas o por el campo `Origen de la factura`), para no duplicar entregas del
  flujo estándar de Ventas.
- Vincula el albarán en el campo **Despacho de Inventario** de la factura y registra la tarjeta visual
  en el chatter.

### 3. Exchange / Cambio de Mercancía

Procesa en una sola operación el **ingreso a bodega de los productos devueltos por el cliente** y la
**salida de los productos sustitutos**, sin alterar la factura fiscal original.

- Dos listas editables: *Productos que regresa el cliente (Entrada)* y *Nuevos productos que se
  entregan (Salida)*, con precios unitarios editables (los de salida se pre-cargan con el precio de
  lista del producto).
- Calcula en vivo **Total Devuelto**, **Total Entregado** y la **Diferencia** monetaria
  (positiva: el cliente debe pagar la diferencia; negativa: saldo a favor).
- Genera uno o dos albaranes validados (según haya entrada, salida o ambas) y deja en el chatter una
  tarjeta consolidada con el detalle y la diferencia económica.

### 4. Auto-Conciliación de Notas de Crédito

Al **publicar** una Nota de Crédito cuya factura original aún tiene saldo pendiente, el módulo cruza
automáticamente las cuentas por cobrar de ambos documentos (`account.move.line` con
`account_type = asset_receivable`), dejando ambas saldadas. Si el cruce falla por cualquier motivo,
la publicación de la NC no se interrumpe.

### 5. Semáforo Informativo de Conciliación

Banner en la parte superior de la Nota de Crédito que informa su estado de aplicación:

| Estado | Banner | Significado |
|---|---|---|
| ✅ **Cruzada Automáticamente** | Verde | La NC se aplicó contra la factura original; ambas cuentas quedan saldadas en B/. 0.00. |
| ℹ️ **Saldo a Favor del Cliente** | Amarillo | La factura original ya estaba pagada; la NC queda como crédito disponible para futuras compras o reembolso. |
| ⚡ **Pendiente de Cruzar** | Azul | La factura original tiene saldo por saldar. Incluye el botón **Cruzar Saldo Ahora** para ejecutar la conciliación manual. |

### 6. Smart Button de Notas de Crédito

Botón inteligente en el formulario de la factura de cliente que muestra la **cantidad de Notas de
Crédito vinculadas** y permite navegar a ellas (vista formulario si hay una sola, lista si hay varias).

---

## Requisitos

- **Odoo 18.0 Community**
- Módulos base: `account`, `stock`, `sale_stock`
- Sin dependencias externas de Python.

## Instalación

1. Clona este repositorio en el directorio de addons de tu instancia:

   ```bash
   git clone -b 18.0 https://github.com/DevOpsMBAConsultings/mba_account_invoice_stock_return.git
   ```

2. Actualiza la lista de aplicaciones en Odoo (*Apps → Update Apps List*).
3. Busca **"Devolución, Despacho, Exchange y Auto-Conciliación"** e instala.

> **Actualización:** basta con `git pull` + reiniciar el servicio de Odoo y actualizar el módulo
> (`-u mba_account_invoice_stock_return`) cuando el cambio incluya nuevos campos o registros XML.

## Guía de Uso

**Devolver productos a bodega**
1. Abre la Nota de Crédito (publicada) o la Factura anulada.
2. Clic en el botón del encabezado **"Devolver a Bodega"** (o el smart button *Regresar a Bodega*).
3. Verifica bodega de recepción y cantidades a devolver → **"Sí, Procesar Devolución a Bodega"**.
4. El sistema crea y valida el albarán de entrada, y lo abre en pantalla.

**Despachar una factura directa**
1. Abre la factura publicada (sin orden de venta).
2. Clic en **"Despachar de Bodega"**.
3. Verifica bodega de salida y cantidades → **"Sí, Procesar Despacho"** — queda validado a `Hecho`.

**Procesar un Exchange**
1. Abre la factura publicada → botón **"Exchange / Cambio"**.
2. En la pestaña *1. Productos que Regresa el Cliente*, ajusta cantidades devueltas.
3. En la pestaña *2. Nuevos Productos que se Entregan*, agrega los sustitutos.
4. Revisa la **Diferencia** calculada → **"Sí, Procesar Exchange de Mercancía"**.

## Estructura Técnica

```
mba_account_invoice_stock_return/
├── models/
│   └── account_move.py                              # Campos, computes, auto-conciliación y apertura de wizards
├── wizard/
│   ├── account_invoice_stock_return_wizard.py       # Escenario A/B de devolución y validación DONE
│   ├── account_invoice_stock_delivery_wizard.py     # Despacho directo validado
│   ├── account_invoice_stock_exchange_wizard.py     # Entrada + Salida simultáneas y diferencia monetaria
│   └── *_views.xml                                  # Formularios de los 3 asistentes
├── views/
│   └── account_move_views.xml                       # Botones header, smart buttons y semáforo
├── security/
│   └── ir.model.access.csv                          # Acceso a los 7 modelos transient
└── static/description/icon.png
```

**Modelos agregados** (todos `TransientModel`):

| Modelo | Propósito |
|---|---|
| `account.invoice.stock.return.wizard` (+ `.line`) | Asistente de devolución a bodega |
| `account.invoice.stock.delivery.wizard` (+ `.line`) | Asistente de despacho directo |
| `account.invoice.stock.exchange.wizard` | Asistente de intercambio |
| `account.invoice.stock.exchange.return.line` | Líneas de entrada del exchange |
| `account.invoice.stock.exchange.delivery.line` | Líneas de salida del exchange |

**Campos agregados a `account.move`:**

| Campo | Tipo | Descripción |
|---|---|---|
| `stock_return_picking_id` | Many2one → `stock.picking` | Albarán de recepción generado por la devolución |
| `stock_delivery_picking_id` | Many2one → `stock.picking` | Albarán de salida generado por el despacho directo |
| `has_sale_order` | Boolean (compute, stored) | Detecta si la factura proviene de una orden de venta |
| `reconciliation_alert_type` | Selection (compute) | Estado del semáforo de conciliación de la NC |
| `credit_note_count` | Integer (compute) | Cantidad de NCs vinculadas a la factura |

## Seguridad y Permisos

Los 7 modelos transient otorgan acceso completo (lectura/escritura/creación/eliminación) al grupo
**Usuario interno** (`base.group_user`). No se agregan grupos nuevos ni reglas de registro.

## Consideraciones y Limitaciones

- Los albaranes generados se **validan inmediatamente a estado `Hecho`** con la cantidad completa de
  cada línea (`skip_sanity_check`). El módulo asume disponibilidad de stock; no está pensado para
  flujos de reserva, backorder o entregas parciales diferidas.
- La auto-conciliación al publicar la NC se ejecuta dentro de un bloque protegido: si el cruce falla,
  la NC queda publicada igualmente y el semáforo permitirá cruzarla después de forma manual.
- En devoluciones con despacho previo se delega al asistente nativo `stock.return.picking`; el
  resultado puede diferir levemente del escenario directo (respetando la trazabilidad nativa de Odoo).
- Actualmente todo el flujo se gatilla desde documentos de cliente (`out_invoice` / `out_refund`);
  no cubre facturas de proveedor.

## Roadmap

- [ ] Recolección de métricas de uso por operación (devolución / despacho / exchange).
- [ ] Extender el flujo a documentos de proveedor (`in_invoice` / `in_refund`).

## Autor y Soporte

**MBA Consultings — Brooks Gonzalez**
🌐 [https://mbaconsultings.com](https://mbaconsultings.com)

## Licencia

Este módulo se distribuye bajo la licencia **LGPL-3**.
