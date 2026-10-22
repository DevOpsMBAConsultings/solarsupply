# -*- coding: utf-8 -*-
{
    'name': 'Formato Cotización y Entregas (MBA Consultings)',
    'version': '19.0.1.0.7',
    'license': 'LGPL-3',
    'summary': 'Formato personalizado de cotización y albarán de entrega | Solar Supply / MBA Consultings',
    'description': 'Plantilla base reutilizable para reportes de cotización, pedidos de venta y albaranes de entrega/despacho.',
    'category': 'Sales',
    'author': 'MBA Consultings, Brooks Gonzalez',
    'website': 'https://mbaconsultings.com',
    'depends': ['sale', 'stock'],
    'data': [
        'views/report_saleorder.xml',
        'views/sale_order_views.xml',
        'views/report_picking.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
