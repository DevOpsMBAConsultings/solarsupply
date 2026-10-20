# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductCategory(models.Model):
    _inherit = 'product.category'

    catalog_section_cover = fields.Binary(
        string="Portadilla de Categoría (PDF o Imagen)",
        attachment=True,
        help="Página de separación o carátula gráfica de la sección (ej. '01 MÓDULOS SOLARES'). Admite PDF o JPG/PNG.",
    )
    catalog_section_cover_name = fields.Char(
        string="Nombre Portadilla",
    )
    catalog_sequence = fields.Integer(
        string="Secuencia en Catálogo",
        default=10,
        help="Orden de aparición de esta categoría en el catálogo de productos.",
    )
