{
    "name": "Panamá - Facturación Electrónica Core (MBA Consultings)",
    "version": "19.0.1.0.22",
    "category": "Accounting/Localizations",
    "summary": "Módulo core de Facturación Electrónica DGI para Panamá (Sin PAC asignado). | MBA Consultings",
    "author": "MBA Consultings, Brooks Gonzalez",
    "website": "https://mbaconsultings.com",
    "license": "LGPL-3",
    "depends": [
        "account",
        "account_debit_note",
        "sale",
        "mba_pa_base",
        "mba_pa_products"
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/dgi_document_types.xml",
        "data/dgi_document_type_sequences_nc_order.xml",
        "data/dgi_payment_method_data.xml",
        "data/dgi_retention_type_data.xml",
        "views/res_partner_views.xml",
        "views/account_journal_views.xml",
        "views/account_move_views.xml",
        "wizard/confirmar_enviar_wizard_views.xml"
    ],
    "installable": True,
    "application": False,
    "assets": {
        "web.assets_backend": [
            "mba_pa_edi/static/src/css/l10n_pa_ribbon.css",
            "mba_pa_edi/static/src/js/account_move_dgi_check.js",
        ],
    },
}
