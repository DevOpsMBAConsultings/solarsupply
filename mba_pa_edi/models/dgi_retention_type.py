# -*- coding: utf-8 -*-
from odoo import fields, models


class DgiRetentionType(models.Model):
    _name = "dgi.retention.type"
    _description = "Tipo de retención DGI (objeto de retención)"

    name = fields.Char(string="Retención", required=True, translate=False)
    code = fields.Char(string="Código DGI", size=16, help="Código para el XML NUC si aplica.")
    receptor_type = fields.Selection(
        selection=[
            ("gobierno", "Gobierno"),
            ("contribuyente", "Contribuyente"),
        ],
        string="Tipo de receptor",
        required=True,
        help="Opciones para facturas a Gobierno (03) o a Contribuyente (01).",
    )
    percentage = fields.Float(
        string="Porcentaje",
        default=50.0,
        help="Porcentaje de retención sobre el impuesto (ITBMS) de la factura. Ej: 50 = 50%% del impuesto.",
    )
    sequence = fields.Integer(string="Secuencia", default=10, help="Orden en el desplegable.")

    _order = "receptor_type, sequence, id"
