# -*- coding: utf-8 -*-
from odoo import models, fields, api

class MbaProductCatalogLine(models.Model):
    _name = 'mba.product.catalog.line'
    _description = 'Línea de Producto en Catálogo'
    _order = 'category_sequence, sequence, id'

    catalog_id = fields.Many2one(
        'mba.product.catalog',
        string="Catálogo",
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_tmpl_id = fields.Many2one(
        'product.template',
        string="Producto",
        required=True,
        ondelete='cascade',
    )
    category_id = fields.Many2one(
        'product.category',
        related='product_tmpl_id.categ_id',
        string="Categoría",
        store=True,
        readonly=True,
    )
    category_sequence = fields.Integer(
        string="Secuencia Categoría",
        default=10,
    )
    sequence = fields.Integer(
        string="Secuencia",
        default=10,
    )
    has_datasheet = fields.Boolean(
        string="Tiene Ficha",
        compute="_compute_datasheet_info",
    )
    datasheet_name = fields.Char(
        string="Ficha Técnica",
        compute="_compute_datasheet_info",
    )
    include_in_pdf = fields.Boolean(
        string="Incluir",
        default=True,
        help="Desmarcar si no se desea incluir este producto específico en el catálogo.",
    )

    @api.depends('product_tmpl_id', 'product_tmpl_id.catalog_datasheet_pdf')
    def _compute_datasheet_info(self):
        for line in self:
            datas, name = line.product_tmpl_id._get_catalog_datasheet()
            line.has_datasheet = bool(datas)
            line.datasheet_name = name or ""
