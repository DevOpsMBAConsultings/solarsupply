# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class ProductTemplate(models.Model):
    _inherit = "product.template"

    dgi_unidad_medida_id = fields.Many2one(
        "dgi.unidad.medida",
        string="Unidad de medida (DGI)",
        ondelete="restrict",
    )

    dgi_cpbs_segment_id = fields.Many2one(
        "dgi.cpbs.segment",
        string="Clasificación bienes/servicios (DGI)",
        ondelete="restrict",
    )

    dgi_cpbs_family_id = fields.Many2one(
        "dgi.cpbs.family",
        string="Subclasificación bienes/servicios (DGI)",
        ondelete="restrict",
        domain="[('segment_id', '=', dgi_cpbs_segment_id)]",
    )

    dgi_cpbs_abrev = fields.Char(
        string="Código CPBMS abreviado",
        help="Código abreviado CPBMS (según catálogo DGI).",
    )

    dgi_cpbs_codigo = fields.Char(
        string="Código codificación panameña del ítem",
        help="Código oficial de la codificación panameña (según catálogo DGI).",
    )

    dgi_charge_type = fields.Selection(
        [
            ("", "Ninguno (ítem normal)"),
            ("acarreo", "Acarreo (FACTURA)"),
            ("seguro", "Seguro (SEGURO)"),
            ("otros_gastos", "Otros Gastos (OTROS_GASTOS)"),
        ],
        string="Cargo DGI (F03)",
        default="",
        help="Si se selecciona, las líneas con este producto no se envían como ítem normal; "
        "se agregan a TotalCharges (F03) con la descripción indicada.",
    )

    is_dgi_generic = fields.Boolean(
        string="Es Producto Genérico (DGI)",
        default=False,
        help="Si se marca, en la facturación electrónica ante la DGI se enviará el texto de la 'Descripción' "
        "modificado por el usuario en la línea de la factura, en lugar del nombre estático del producto del catálogo.",
    )

    @api.onchange("dgi_cpbs_segment_id")
    def _onchange_dgi_cpbs_segment_id(self):
        for rec in self:
            if rec.dgi_cpbs_family_id and rec.dgi_cpbs_family_id.segment_id != rec.dgi_cpbs_segment_id:
                rec.dgi_cpbs_family_id = False

    @api.constrains("dgi_cpbs_segment_id", "dgi_cpbs_family_id")
    def _check_segment_family_consistency(self):
        for rec in self:
            if rec.dgi_cpbs_family_id and rec.dgi_cpbs_segment_id:
                if rec.dgi_cpbs_family_id.segment_id != rec.dgi_cpbs_segment_id:
                    raise ValidationError(_("La Familia (DGI) no pertenece al Segmento seleccionado."))

    @api.constrains("dgi_cpbs_abrev", "dgi_cpbs_codigo")
    def _check_dgi_codes_length(self):
        for rec in self:
            if rec.dgi_cpbs_abrev and len(rec.dgi_cpbs_abrev.strip()) > 50:
                raise ValidationError(_("El Código CPBMS abreviado excede 50 caracteres."))
            if rec.dgi_cpbs_codigo and len(rec.dgi_cpbs_codigo.strip()) > 50:
                raise ValidationError(_("El Código de codificación panameña excede 50 caracteres."))

    @api.constrains("taxes_id", "sale_ok", "dgi_charge_type")
    def _check_taxes_assigned(self):
        """
        Validación: Todos los productos vendibles deben tener al menos un impuesto positivo asignado
        para la Facturación Electrónica en Panamá.
        """
        # Omitir validación durante instalación/actualización automática de módulos
        if self.env.context.get('install_mode'):
            return

        for rec in self:
            if rec.sale_ok:
                if rec.dgi_charge_type in ["acarreo", "seguro", "otros_gastos"]:
                    continue

                def is_retention(tax):
                    if getattr(tax, 'dgi_is_retention', False):
                        return True
                    if tax.amount < 0:
                        return True
                    name = (tax.name or "").lower()
                    group_name = (tax.tax_group_id.name or "").lower() if tax.tax_group_id else ""
                    return "retenc" in name or "retenc" in group_name or "reten" in name or "reten" in group_name
                    
                if not rec.taxes_id or all(is_retention(tax) for tax in rec.taxes_id):
                    # Solo es una advertencia o log en implementaciones limpias,
                    # para no romper otras dependencias de odoo, pero como estaba en constrains, lo mantenemos:
                    raise ValidationError(
                        _("No se puede guardar el producto '%s': debe tener al menos un impuesto positivo "
                          "(ITBMS, incluyendo 0%%) asignado en los 'Impuestos de venta'.\n\n"
                          "La DGI exige que todos los productos facturables declaren un impuesto base. "
                          "Las retenciones por sí solas no son suficientes.") % rec.name
                    )
