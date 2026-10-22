# -*- coding: utf-8 -*-
from odoo import api, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.onchange('fiscal_position_id')
    def _onchange_fiscal_position_recompute_taxes(self):
        """
        Recalcula impuestos de las líneas cuando cambia la posición fiscal.
        Si se quita la FP, restaura los impuestos originales del producto.
        """
        for line in self.order_line:
            if not line.product_id:
                continue
            original_taxes = line.product_id.taxes_id.filtered(
                lambda t: t.company_id == self.company_id
            )
            if self.fiscal_position_id:
                new_taxes = self.fiscal_position_id.map_tax(original_taxes)
            else:
                new_taxes = original_taxes
            if new_taxes != line.tax_ids:
                line.tax_ids = new_taxes
