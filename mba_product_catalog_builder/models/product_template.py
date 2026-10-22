# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = "product.template"

    catalog_datasheet_pdf = fields.Binary(
        string="Ficha Técnica (PDF)",
        attachment=True,
        help="Archivo PDF oficial con la ficha técnica o especificaciones del fabricante. Sincronizado automáticamente con el botón Documentos.",
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

    @api.depends("catalog_datasheet_pdf", "product_document_ids", "product_document_ids.ir_attachment_id")
    def _compute_catalog_has_datasheet(self):
        for record in self:
            datas, name = record._get_catalog_datasheet()
            record.catalog_has_datasheet = bool(datas)

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
        if hasattr(self, "product_document_ids") and self.product_document_ids:
            pdf_docs = self.product_document_ids.filtered(
                lambda d: d.ir_attachment_id and (
                    d.ir_attachment_id.mimetype == "application/pdf" or
                    (d.ir_attachment_id.name and d.ir_attachment_id.name.lower().endswith(".pdf"))
                )
            )
            if pdf_docs:
                doc = pdf_docs[0]
                return doc.ir_attachment_id.datas, doc.ir_attachment_id.name or "Ficha_Tecnica.pdf"

        # 3. Fallback directo en ir.attachment
        attachments = self.env["ir.attachment"].search([
            ("res_model", "=", "product.template"),
            ("res_id", "=", self.id),
            ("mimetype", "=", "application/pdf"),
        ], limit=1, order="id desc")
        if attachments and attachments.datas:
            return attachments.datas, attachments.name or "Ficha_Tecnica.pdf"

        return False, False

    def _sync_datasheet_to_product_document(self):
        """Sincroniza la ficha técnica con product.document para reflejarse en el smart button Documentos."""
        for record in self:
            att = self.env["ir.attachment"].sudo().search([
                ("res_model", "=", "product.template"),
                ("res_id", "=", record.id),
                ("res_field", "=", "catalog_datasheet_pdf"),
            ], limit=1, order="id desc")

            if not record.catalog_datasheet_pdf:
                if record.catalog_datasheet_name:
                    record.catalog_datasheet_name = False
                if att:
                    self.env["product.document"].sudo().search([
                        ("ir_attachment_id", "=", att.id)
                    ]).unlink()
                continue

            if att:
                file_name = record.catalog_datasheet_name or f"Ficha_Tecnica_{record.default_code or record.id}.pdf"
                if att.name != file_name:
                    att.write({"name": file_name})

                # Verificar si ya existe en product.document para no duplicar
                existing_doc = self.env["product.document"].sudo().search([
                    ("res_model", "=", "product.template"),
                    ("res_id", "=", record.id),
                ]).filtered(lambda d: d.ir_attachment_id.id == att.id or (att.checksum and d.ir_attachment_id.checksum == att.checksum))

                if not existing_doc:
                    self.env["product.document"].sudo().create({
                        "ir_attachment_id": att.id,
                    })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.catalog_datasheet_pdf:
                record._sync_datasheet_to_product_document()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "catalog_datasheet_pdf" in vals or "catalog_datasheet_name" in vals:
            self._sync_datasheet_to_product_document()
        return res
