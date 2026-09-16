from odoo import models, fields

class DGICPBSSegment(models.Model):
    _name = "dgi.cpbs.segment"
    _description = "DGI CPBS Segment"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)