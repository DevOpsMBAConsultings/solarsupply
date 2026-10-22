# -*- coding: utf-8 -*-
{
    'name': 'MBA - HKA Tools Importador (MBA Consultings)',
    'version': '19.0.1.0.6',
    'category': 'Accounting/Localizations',
    'summary': 'Utilidades para consultar folios restantes y descargar/importar facturas electrónicas desde HKA.',
    'author': 'MBA Consultings, Brooks González',
    'website': 'https://mbaconsultings.com',
    'depends': ['account', 'mba_pa_edi_hka'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/hka_folios_wizard_views.xml',
        'wizard/hka_import_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
}
