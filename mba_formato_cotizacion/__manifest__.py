# -*- coding: utf-8 -*-
{
    'name': 'Formato Cotización (MBA Consultings)',
    'version': '19.0.1.0.3',
    'license': 'LGPL-3',
    'summary': 'Formato personalizado y agnóstico de cotización | MBA Consultings',
    'description': 'Plantilla base reutilizable y agnóstica para reportes de cotización y pedidos de venta.',
    'category': 'Sales',
    'author': 'MBA Consultings, Brooks Gonzalez',
    'website': 'https://mbaconsultings.com',
    'depends': ['sale'],
    'data': [
        'views/report_saleorder.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
