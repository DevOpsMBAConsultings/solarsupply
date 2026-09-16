# AGENTS.md — `implementaciones/19.0/solarsupply/`

Las reglas completas del workspace (protocolo de autorización, estructura, modelo de repos,
arquitectura de facturación electrónica, convenciones de código y UI, zonas de riesgo) viven en
**`../../../agents.md`** (raíz de `development/`). Este archivo es solo un puntero — no dupliques
reglas acá, actualizá el de la raíz.

Recordatorio rápido para este repo:
- Cliente en **modo independiente** desde 2026-09-16 (ver `../../../agents.md` §2.1) — no se corre
  `subtree pull`/`push` sobre este repo salvo autorización explícita y puntual de Brooks.
- Compone módulos propios y adaptados para Odoo 19 Community:
  - Facturación Electrónica Panamá (`mba_pa_base`, `mba_pa_edi`, `mba_pa_edi_hka`, `mba_pa_edi_digifact`, `mba_pa_hka_tools`, `mba_pa_pos`, `mba_pa_products`, `mba_pa_sale`, `mba_pa_sale_hitos`, `mba_account_invoice_stock_return`)
  - `mba_formato_cotizacion` (Reporte de cotización personalizado agnóstico)
- Nunca se edita directamente el código de Odoo Core ni de la OCA — se extiende con
  `_inherit` desde un módulo propio (ver `../../../agents.md` §8).
- Ningún cambio de código procede sin un "sí, procede" explícito de Brooks (ver `../../../agents.md`
  §3 y §3.1).
