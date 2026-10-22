{
    "name": "Panamá - Catálogo de Productos (MBA Consultings)",
    "version": "19.0.1.0.1",
    "category": "Accounting/Localizations",
    "summary": "Manejo de códigos CPBS y Unidades de Medida DGI en productos. | MBA Consultings",
    "author": "MBA Consultings, Brooks Gonzalez",
    "website": "https://www.mbaconsultings.com",
    "license": "LGPL-3",
    "depends": [
        "mba_pa_base",
        "product"
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/dgi.unidad.medida.csv",
        "data/dgi.cpbs.segment.csv",
        "data/dgi.cpbs.family.csv",
        "views/product_template_views.xml"
    ],
    "installable": True,
    "application": False,
}
