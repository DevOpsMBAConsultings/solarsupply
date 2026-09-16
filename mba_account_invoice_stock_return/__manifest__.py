{
    "name": "Devolución, Despacho, Exchange y Auto-Conciliación (MBA Consultings)",
    "version": "19.0.1.0.1",
    "category": "Inventory/Accounting",
    "summary": "Devolución desde NC y facturas anuladas, despacho directo, exchange, auto-conciliación y stat button de NCs | MBA Consultings",
    "author": "MBA Consultings, Brooks Gonzalez",
    "website": "https://mbaconsultings.com",
    "license": "LGPL-3",
    "depends": [
        "account",
        "stock",
        "sale_stock",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/account_invoice_stock_return_wizard_views.xml",
        "wizard/account_invoice_stock_delivery_wizard_views.xml",
        "wizard/account_invoice_stock_exchange_wizard_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
}
