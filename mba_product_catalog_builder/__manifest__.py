# -*- coding: utf-8 -*-
{
    'name': 'Generador de Catálogos de Productos (MBA Consultings)',
    'version': '19.0.1.1.0',
    'license': 'LGPL-3',
    'summary': 'Ensamblador y compilador de catálogos comerciales con fichas técnicas oficiales (PDF) y portadillas por categoría.',
    'description': """
Generador de Catálogos de Productos en PDF (Solar Supply / MBA Consultings)
==========================================================================
Permite ensamblar y compilar catálogos corporativos profesionales a partir de:
- Carátula institucional (Portada)
- Páginas de introducción (Índice, Quiénes somos, Aliados, Sucursales)
- Portadillas / Separadores gráficos por cada Categoría
- Fichas técnicas oficiales (Datasheets PDF del fabricante) de cada producto seleccionado
- Contraportada institucional con contactos y QR

Características:
- Cero sobrecarga de wkhtmltopdf: fusión binaria nativa de PDFs ultrarrápida.
- Máxima fidelidad y resolución vectorial de las fichas de producto originales.
- Soporte para adjuntos en PDF e imágenes (conversión automática a página PDF).
- Selección y ordenamiento flexible de categorías y productos.
- Opción de numeración correlativa de páginas.
    """,
    'category': 'Sales/Products',
    'author': 'MBA Consultings, Brooks Gonzalez',
    'website': 'https://mbaconsultings.com',
    'depends': ['product', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/product_category_views.xml',
        'views/product_catalog_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
