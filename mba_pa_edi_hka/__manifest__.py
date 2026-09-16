{
    "name": "Panamá - FE Connector The Factory HKA (MBA Consultings)",
    "version": "19.0.1.0.18",
    "category": "Accounting/Localizations",
    "summary": "Conector API REST para el PAC The Factory HKA en Panamá. | MBA Consultings",
    "author": "MBA Consultings, Brooks Gonzalez",
    "website": "https://mbaconsultings.com",
    "license": "LGPL-3",
    "depends": [
        "mba_pa_edi",
        "mba_pa_sale"
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/res_company_views.xml",
        "views/account_move_views.xml",
        "wizard/hka_anular_factura_wizard_views.xml",
        "wizard/sale_order_credit_other_due_date_wizard_views.xml",
        "wizard/sale_order_payment_other_desc_wizard_views.xml"
    ],
    "installable": True,
    "application": False,
}
