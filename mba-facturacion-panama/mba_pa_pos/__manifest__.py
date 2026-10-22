{
    "name": "Panamá - POS Facturación Electrónica (MBA Consultings)",
    "version": "19.0.1.0.15",
    "category": "Point of Sale",
    "summary": "Integración POS con Facturación Electrónica DGI Panamá. | MBA Consultings",
    "author": "MBA Consultings, Brooks Gonzalez",
    "website": "https://www.mbaconsultings.com",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "mba_pa_edi"
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_config_views.xml",
        "views/pos_order_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "mba_pa_pos/static/src/overrides/models.js",
            "mba_pa_pos/static/src/overrides/components/payment_screen/dgi_number_popup.js",
            "mba_pa_pos/static/src/overrides/components/payment_screen/dgi_number_popup.xml",
            "mba_pa_pos/static/src/overrides/components/payment_screen/payment_screen.js",
            "mba_pa_pos/static/src/overrides/components/receipt_screen/receipt_screen.js",
            "mba_pa_pos/static/src/overrides/components/receipt_screen/receipt_screen.xml",
        ],
    },
    "installable": True,
    "application": False,
}
