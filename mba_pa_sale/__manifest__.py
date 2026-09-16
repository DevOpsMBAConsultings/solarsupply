{
    "name": "Panamá - Integración con Ventas (MBA Consultings)",
    "version": "19.0.1.0.33",
    "category": "Sales",
    "summary": "Extensión de cotizaciones y ventas para Panamá (DGI). | MBA Consultings",
    "author": "MBA Consultings, Brooks Gonzalez",
    "website": "https://www.mbaconsultings.com",
    "license": "LGPL-3",
    "depends": [
        "sale",
        "mba_pa_base",
        "mba_pa_edi"
    ],
    "data": [
        "security/mba_pa_sale_security.xml",
        "security/ir.model.access.csv",
        "wizard/sale_order_dgi_warning_wizard_views.xml",
        "views/sale_order_views.xml"
    ],
    "assets": {
        "web.assets_backend": [
            "mba_pa_sale/static/src/js/sale_order_dgi_check.js"
        ]
    },
    "installable": True,
    "application": False,
}
