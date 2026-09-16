{
    "name": "Panamá - Catálogos Base (MBA Consultings)",
    "version": "19.0.1.0.3",
    "category": "Accounting/Localizations",
    "summary": "Catálogos base de la DGI y modificaciones a Contactos para Panamá. | MBA Consultings",
    "author": "MBA Consultings, Brooks Gonzalez",
    "website": "https://www.mbaconsultings.com",
    "license": "LGPL-3",
    "depends": [
        "base",
        "contacts"
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/partner_dgi_warning_wizard_views.xml",
        "data/dgi.provincia.csv",
        "data/dgi.distrito.csv",
        "data/dgi.corregimiento.csv",
        "views/res_partner_views.xml",
        "views/res_company_views.xml"
    ],
    "installable": True,
    "application": True,
}
