# -*- coding: utf-8 -*-
{
    'name': 'Solar Supply - Datos de Términos y Condiciones (MBA Consultings)',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'summary': 'Datos de pago de Solar Supply para los términos y condiciones | MBA Consultings',
    'description': 'Micro-módulo de datos del cliente Solar Supply. Carga los datos de pago '
                   'y regenera los términos y condiciones en cada instalación/actualización.',
    'category': 'Accounting',
    'author': 'MBA Consultings, Brooks Gonzalez',
    'website': 'https://mbaconsultings.com',
    'depends': ['mba_terminos_condiciones'],
    'data': [
        'data/company_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
