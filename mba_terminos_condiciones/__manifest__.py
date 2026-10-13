# -*- coding: utf-8 -*-
{
    'name': 'Términos y Condiciones (MBA Consultings)',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'summary': 'Datos de pago en 2 columnas para los términos y condiciones | MBA Consultings',
    'description': 'Módulo agnóstico: agrega los datos de pago a la compañía y genera '
                   'los términos y condiciones por defecto como tabla de 2 columnas.',
    'category': 'Accounting',
    'author': 'MBA Consultings, Brooks Gonzalez',
    'website': 'https://mbaconsultings.com',
    'depends': ['account'],
    'data': [
        'views/res_company_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
