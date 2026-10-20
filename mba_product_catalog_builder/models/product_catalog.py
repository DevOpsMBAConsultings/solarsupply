# -*- coding: utf-8 -*-
import base64
import hashlib
import io
import logging
import os
import shutil
import subprocess
import tempfile
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from odoo.tools.pdf import merge_pdf, PdfFileReader, PdfFileWriter
except ImportError:
    from PyPDF2 import PdfFileReader, PdfFileWriter
    def merge_pdf(pdf_data):
        writer = PdfFileWriter()
        for doc in pdf_data:
            reader = PdfFileReader(io.BytesIO(doc), strict=False)
            for page in range(reader.getNumPages()):
                writer.addPage(reader.getPage(page))
        with io.BytesIO() as buf:
            writer.write(buf)
            return buf.getvalue()

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
except ImportError:
    canvas = None


class MbaProductCatalog(models.Model):
    _name = 'mba.product.catalog'
    _description = 'Catálogo de Productos (PDF Builder)'
    _order = 'id desc'

    name = fields.Char(
        string="Nombre del Catálogo",
        required=True,
        default="Catálogo de Productos 2026",
    )
    date = fields.Date(
        string="Fecha",
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        'res.company',
        string="Compañía",
        default=lambda self: self.env.company,
        required=True,
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('ready', 'Listo para Generar'),
        ('done', 'Generado'),
    ], default='draft', string="Estado")

    # 1. Portada y Páginas Institucionales
    cover_pdf = fields.Binary(
        string="Portada Principal (PDF o Imagen)",
        attachment=True,
        help="Carátula frontal del catálogo. Admite PDF o JPG/PNG a página completa.",
    )
    cover_name = fields.Char(string="Nombre Portada")

    intro_pdf = fields.Binary(
        string="Introducción / Índice / Institucional (PDF)",
        attachment=True,
        help="Documento PDF con las páginas iniciales (ej. Índice, Quiénes somos, Bodegas, Aliados).",
    )
    intro_name = fields.Char(string="Nombre Intro")

    back_cover_pdf = fields.Binary(
        string="Contraportada / Cierre (PDF o Imagen)",
        attachment=True,
        help="Página de cierre institucional con datos de contacto, QR y sucursales.",
    )
    back_cover_name = fields.Char(string="Nombre Contraportada")

    # 2. Filtros y selección
    category_ids = fields.Many2many(
        'product.category',
        string="Categorías a Incluir",
        help="Filtrar por categorías específicas. Si se deja vacío, incluye todas las que tengan productos activos.",
    )
    only_with_datasheet = fields.Boolean(
        string="Cargar solo productos con ficha técnica",
        default=True,
        help="Si está marcado, solo se agregarán productos que tengan ficha técnica en PDF (sea en el catálogo o en el botón Documentos).",
    )
    paginate_pages = fields.Boolean(
        string="Numerar páginas consecutivamente",
        default=False,
        help="Estampa el número correlativo en el pie de página de cada hoja del PDF compilado.",
    )
    page_number_start = fields.Integer(
        string="Página inicial para numerar",
        default=1,
    )
    deduplicate_datasheets = fields.Boolean(
        string="Deduplicar Fichas Técnicas",
        default=True,
        help="Si varios productos comparten la misma ficha técnica (mismo archivo PDF, común en familias de inversores o baterías), solo se incluirá una vez en el catálogo.",
    )
    pdf_compression = fields.Selection([
        ('300', '300 DPI — Alta Fidelidad / Imprenta (Recomendado)'),
        ('200', '200 DPI — Comercial / Balanceado'),
        ('150', '150 DPI — Ligero / Email'),
        ('none', 'Sin compresión (Original / Máxima resolución bruta)'),
    ], default='300', string="Resolución y Calidad PDF",
    help="Permite optimizar el peso del PDF manteniendo la nitidez de logos, textos y fichas técnicas según la resolución elegida.")

    # 3. Líneas de productos
    line_ids = fields.One2many(
        'mba.product.catalog.line',
        'catalog_id',
        string="Productos del Catálogo",
    )

    # 4. Resultado y métricas
    generated_pdf = fields.Binary(
        string="Catálogo PDF Generado",
        readonly=True,
        attachment=True,
    )
    generated_pdf_name = fields.Char(
        string="Nombre del Archivo Generado",
        readonly=True,
    )
    generated_pdf_size = fields.Char(
        string="Tamaño del Archivo",
        readonly=True,
    )
    generated_date = fields.Datetime(
        string="Fecha de Generación",
        readonly=True,
    )
    total_pages = fields.Integer(
        string="Total de Páginas",
        readonly=True,
    )
    total_products = fields.Integer(
        string="Total de Productos",
        compute="_compute_totals",
    )

    @api.depends('line_ids', 'line_ids.include_in_pdf')
    def _compute_totals(self):
        for record in self:
            record.total_products = len(record.line_ids.filtered(lambda l: l.include_in_pdf))

    def _file_to_pdf_bytes(self, binary_data, filename=""):
        """ Convierte datos binarios en bytes PDF. """
        if not binary_data:
            return None
        raw_bytes = base64.b64decode(binary_data)
        if raw_bytes.startswith(b'%PDF-'):
            return raw_bytes

        # Intentar convertir imagen con PIL si no es PDF
        if Image:
            try:
                img = Image.open(io.BytesIO(raw_bytes))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="PDF", resolution=300.0)
                return buf.getvalue()
            except Exception as e:
                _logger.warning("No se pudo convertir la imagen a PDF (%s): %s", filename, e)
                raise UserError(_("El archivo '%s' no es un PDF válido ni una imagen procesable.", filename or 'desconocido'))
        else:
            raise UserError(_("El archivo '%s' debe ser un formato PDF válido.", filename or 'desconocido'))

    def _stamp_page_numbers(self, pdf_bytes, start_page=1):
        """ Estampa números correlativos en el pie de página de cada hoja. """
        if not canvas:
            return pdf_bytes

        reader = PdfFileReader(io.BytesIO(pdf_bytes), strict=False)
        writer = PdfFileWriter()
        total = reader.getNumPages()

        for idx in range(total):
            page = reader.getPage(idx)
            current_num = start_page + idx
            w = float(page.mediaBox.getWidth())
            h = float(page.mediaBox.getHeight())

            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(w, h))
            can.setFont("Helvetica", 9)
            can.setFillColor(HexColor("#555555"))
            can.drawRightString(w - 36, 20, str(current_num))
            can.save()
            packet.seek(0)

            overlay_reader = PdfFileReader(packet)
            page.mergePage(overlay_reader.getPage(0))
            writer.addPage(page)

        with io.BytesIO() as out:
            writer.write(out)
            return out.getvalue()

    def _compress_pdf(self, pdf_bytes, level='300'):
        """
        Comprime y optimiza el PDF usando Ghostscript si está disponible.
        Usa AutoFilterColorImages=true para garantizar que logotipos, tipografías
        y elementos vectoriales permanezcan 100% nítidos sin artefactos JPEG.
        """
        if level == 'none' or not pdf_bytes:
            return pdf_bytes

        if not shutil.which('gs'):
            _logger.info("Ghostscript (gs) no está disponible en el sistema. Omitiendo compresión.")
            return pdf_bytes

        # Parámetros según la resolución solicitada
        if level == '300':
            preset = '-dPDFSETTINGS=/printer'
            dpi = '300'
            quality = '95'
        elif level == '200':
            preset = '-dPDFSETTINGS=/prepress'
            dpi = '200'
            quality = '88'
        elif level == '150':
            preset = '-dPDFSETTINGS=/ebook'
            dpi = '150'
            quality = '80'
        else:
            preset = '-dPDFSETTINGS=/printer'
            dpi = '300'
            quality = '95'

        in_name = None
        out_name = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f_in, \
                 tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f_out:
                f_in.write(pdf_bytes)
                f_in.flush()
                in_name = f_in.name
                out_name = f_out.name

            cmd = [
                'gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
                preset,
                '-dDownsampleColorImages=true', '-dColorImageDownsampleType=/Bicubic', f'-dColorImageResolution={dpi}',
                '-dDownsampleGrayImages=true', '-dGrayImageDownsampleType=/Bicubic', f'-dGrayImageResolution={dpi}',
                '-dAutoFilterColorImages=true',
                '-dAutoFilterGrayImages=true',
                f'-dJPEGQ={quality}',
                '-dNOPAUSE', '-dQUIET', '-dBATCH',
                f'-sOutputFile={out_name}', in_name
            ]
            res = subprocess.run(cmd, capture_output=True, timeout=90)
            if res.returncode == 0 and os.path.exists(out_name) and os.path.getsize(out_name) > 0:
                with open(out_name, 'rb') as f:
                    compressed_bytes = f.read()
                if len(compressed_bytes) < len(pdf_bytes):
                    return compressed_bytes
            else:
                _logger.warning("Ghostscript retorno no exitoso: %s", res.stderr)
        except Exception as e:
            _logger.warning("Error durante compresión Ghostscript: %s", e)
        finally:
            for p in (in_name, out_name):
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except Exception:
                        pass

        return pdf_bytes

    def action_load_products(self):
        """ Busca y carga los productos en las líneas del catálogo. """
        self.ensure_one()
        domain = [('sale_ok', '=', True), ('catalog_include', '=', True)]

        if self.category_ids:
            domain.append(('categ_id', 'child_of', self.category_ids.ids))

        products = self.env['product.template'].search(domain, order='categ_id, catalog_sequence, name')

        # Filtrar solo los que tienen ficha técnica si la opción está activa
        if self.only_with_datasheet:
            products = products.filtered(lambda p: bool(p._get_catalog_datasheet()[0]))

        self.line_ids.unlink()

        lines_vals = []
        for prod in products:
            lines_vals.append({
                'catalog_id': self.id,
                'product_tmpl_id': prod.id,
                'category_sequence': prod.categ_id.catalog_sequence or 10,
                'sequence': prod.catalog_sequence or 10,
                'include_in_pdf': True,
            })

        if lines_vals:
            self.env['mba.product.catalog.line'].create(lines_vals)

        self.write({'state': 'ready' if lines_vals else 'draft'})
        return True

    def action_generate_catalog_pdf(self):
        """ Ensambla todas las piezas en un único PDF final de alta calidad y lo optimiza. """
        self.ensure_one()

        if not self.line_ids:
            self.action_load_products()

        selected_lines = self.line_ids.filtered(
            lambda l: l.include_in_pdf and bool(l.product_tmpl_id._get_catalog_datasheet()[0])
        )
        if not selected_lines:
            raise UserError(_("No hay productos con ficha técnica seleccionados para incluir en el catálogo."))

        pdf_collection = []

        # 1. Portada principal
        if self.cover_pdf:
            cover_bytes = self._file_to_pdf_bytes(self.cover_pdf, self.cover_name)
            if cover_bytes:
                pdf_collection.append(cover_bytes)

        # 2. Páginas de Introducción / Índice
        if self.intro_pdf:
            intro_bytes = self._file_to_pdf_bytes(self.intro_pdf, self.intro_name)
            if intro_bytes:
                pdf_collection.append(intro_bytes)

        # 3. Ordenar líneas por categoría y secuencia
        sorted_lines = selected_lines.sorted(
            key=lambda l: (l.category_sequence, l.category_id.name or '', l.sequence, l.product_tmpl_id.name or '')
        )

        # 4. Agrupar por categoría agregando separador de sección y fichas técnicas
        processed_categories = set()
        processed_datasheet_hashes = set()
        for line in sorted_lines:
            category = line.category_id
            if category and category.id not in processed_categories:
                processed_categories.add(category.id)
                if category.catalog_section_cover:
                    section_bytes = self._file_to_pdf_bytes(category.catalog_section_cover, category.catalog_section_cover_name)
                    if section_bytes:
                        pdf_collection.append(section_bytes)

            datasheet_data, datasheet_name = line.product_tmpl_id._get_catalog_datasheet()
            datasheet_bytes = self._file_to_pdf_bytes(datasheet_data, datasheet_name)
            if datasheet_bytes:
                if self.deduplicate_datasheets:
                    content_hash = hashlib.sha256(datasheet_bytes).hexdigest()
                    if content_hash in processed_datasheet_hashes:
                        _logger.info(
                            "Omitiendo ficha técnica repetida (%s) para el producto '%s' en catálogo '%s'",
                            datasheet_name, line.product_tmpl_id.display_name, self.name
                        )
                        continue
                    processed_datasheet_hashes.add(content_hash)

                pdf_collection.append(datasheet_bytes)

        # 5. Contraportada / Cierre
        if self.back_cover_pdf:
            back_bytes = self._file_to_pdf_bytes(self.back_cover_pdf, self.back_cover_name)
            if back_bytes:
                pdf_collection.append(back_bytes)

        if not pdf_collection:
            raise UserError(_("No se encontraron documentos PDF válidos para ensamblar el catálogo."))

        # 6. Fusionar todo con el motor binario de Odoo
        try:
            merged_pdf_bytes = merge_pdf(pdf_collection)
        except Exception as e:
            _logger.error("Error al fusionar PDFs del catálogo: %s", e)
            raise UserError(_("Ocurrió un error al fusionar los documentos PDF: %s", e))

        # 7. Numerar páginas si está activo
        if self.paginate_pages:
            try:
                merged_pdf_bytes = self._stamp_page_numbers(merged_pdf_bytes, self.page_number_start)
            except Exception as e:
                _logger.warning("No se pudo estampar la numeración de páginas: %s", e)

        # 8. Comprimir PDF si está configurado (por defecto 300 DPI con AutoFilter sin pérdida para logos)
        if self.pdf_compression != 'none':
            try:
                merged_pdf_bytes = self._compress_pdf(merged_pdf_bytes, self.pdf_compression)
            except Exception as e:
                _logger.warning("No se pudo comprimir el PDF con Ghostscript: %s", e)

        # 9. Contar páginas y calcular tamaño legible
        reader = PdfFileReader(io.BytesIO(merged_pdf_bytes), strict=False)
        total_pages = reader.getNumPages()

        file_size_bytes = len(merged_pdf_bytes)
        if file_size_bytes < 1024 * 1024:
            size_str = f"{round(file_size_bytes / 1024, 1)} KB"
        else:
            size_str = f"{round(file_size_bytes / (1024 * 1024), 2)} MB"

        # 10. Guardar y lanzar descarga
        clean_name = self.name.strip().replace(' ', '_').replace('/', '_')
        filename = f"{clean_name}.pdf"
        self.write({
            'generated_pdf': base64.b64encode(merged_pdf_bytes),
            'generated_pdf_name': filename,
            'generated_pdf_size': size_str,
            'generated_date': fields.Datetime.now(),
            'total_pages': total_pages,
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model=mba.product.catalog&id={self.id}&field=generated_pdf&filename={filename}&download=true',
            'target': 'self',
        }
