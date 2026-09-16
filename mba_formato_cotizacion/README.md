# Formato Cotización (`mba_formato_cotizacion`)

Plantilla base agnóstica y reutilizable para el reporte PDF de cotizaciones y pedidos de venta en Odoo 19 Community.

## Qué hace

Sobreescribe el reporte estándar de cotización/pedido de venta (`sale.report_saleorder_document`) de Odoo con un diseño limpio, profesional y corporativo:
- Cabecera y logotipos corporativos dinámicos de la compañía (`res_company.logo` vía `image_data_uri`).
- Paleta visual armónica inspirada en estándares solares e industriales (Azul Profundo `#102B66` y Acento Dorado Eléctrico `#F39C12`).
- Compatibilidad nativa con Odoo 19 (`doc.tax_totals`, `web.basic_layout`).
- Soporte agnóstico para campos DGI de Facturación Panamá si el módulo `mba_pa_sale` está instalado (`_get_dgi_item_description`, `_get_dgi_line_tax`, `dgi_show_retention_block`).

## Dependencias

- `sale`

## Licencia

LGPL-3.
