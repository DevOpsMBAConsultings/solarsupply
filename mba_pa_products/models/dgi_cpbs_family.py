from odoo import models, fields

class DGICPBSFamily(models.Model):
    _name = "dgi.cpbs.family"
    _description = "DGI CPBS Family"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    segment_id = fields.Many2one(
        "dgi.cpbs.segment",
        string="Segment",
        required=True,
        ondelete="restrict",
    )