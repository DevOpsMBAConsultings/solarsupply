# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    catalog_datasheet_pdf = fields.Binary(
        string="Ficha Técnica (PDF)",
        attachment=True,
        help="Archivo PDF oficial con la ficha técnica o especificaciones del fabricante.",
    )
    catalog_datasheet_name = fields.Char(
        string="Nombre del Archivo PDF",
    )
    catalog_include = fields.Boolean(
        string="Incluir en Catálogos",
        default=True,
        help="Permite activar o desactivar este producto para la generación de catálogos.",
    )
    catalog_sequence = fields.Integer(
        string="Secuencia en Catálogo",
        default=10,
        help="Orden de aparición del producto dentro de su categoría en el catálogo.",
    )
    catalog_has_datasheet = fields.Boolean(
        string="Tiene Ficha Técnica",
        compute="_compute_catalog_has_datasheet",
        store=True,
    )

    def _get_catalog_datasheet(self):
        """
        Obtiene el PDF y nombre de la ficha técnica.
        Prioridad 1: Campo manual propio (catalog_datasheet_pdf).
        Prioridad 2: Documentos adjuntos nativos de Odoo (product.document).
        Prioridad 3: Archivo PDF en ir.attachment vinculado a este producto.
        """
        self.ensure_one()
        if self.catalog_datasheet_pdf:
            return self.catalog_datasheet_pdf, self.catalog_datasheet_name or "Ficha_Tecnica.pdf"

        # 2. Buscar en los documentos nativos (product.document)
        if hasattr(self, 'product_document_ids') and self.product_document_ids:
            pdf_docs = self.product_document_ids.filtered(
                lambda d: d.ir_attachment_id and (
                    d.ir_attachment_id.mimetype == 'application/pdf' or
                    (d.ir_attachment_id.name and d.ir_attachment_id.name.lower().endswith('.pdf'))
                )
            )
            if pdf_docs:
                doc = pdf_docs[0]
                return doc.ir_attachment_id.datas, doc.ir_attachment_id.name or "Ficha_Tecnica.pdf"

        # 3. Fallback directo en ir.attachment
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'product.template'),
            ('res_id', '=', self.id),
            ('mimetype', '=', 'application/pdf'),
        ], limit=1, order='id desc')
        if attachments and attachments.datas:
            return attachments.datas, attachments.name or "Ficha_Tecnica.pdf"

        return False, False

    @api.depends('catalog_datasheet_pdf')
    def _compute_catalog_has_datasheet(self):
        for record in self:
            datas, name = record._get_catalog_datasheet()
            record.catalog_has_datasheet = bool(datas)
