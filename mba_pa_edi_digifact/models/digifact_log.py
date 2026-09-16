# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DigifactLog(models.Model):
    _name = "digifact.log"
    _description = "Digifact Log"
    _order = "create_date desc, id desc"

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        index=True,
        readonly=True,
        default=lambda self: self.env.company,
    )

    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Invoice",
        required=False,
        ondelete="cascade",
        index=True,
    )

    operation = fields.Char(string="Operation", required=True, index=True)
    success = fields.Boolean(string="Success", default=False, index=True)
    http_status = fields.Integer(string="HTTP Status")

    request_payload = fields.Text(string="Request Payload")
    response_payload = fields.Text(string="Response Payload")
    error_message = fields.Text(string="Error Message")

    @api.model
    def create_log(
        self,
        operation,
        move=None,
        company=None,
        request_payload="",
        response_payload="",
        http_status=0,
        success=False,
        error_message="",
    ):
        """
        Central helper to log Digifact operations safely.

        NOTE:
        - `company` is optional; defaults to env.company
        - This matches how we want to call it from account.move actions.
        """
        company = company or self.env.company
        vals = {
            "company_id": company.id,
            "move_id": move.id if move else False,
            "operation": operation,
            "request_payload": request_payload or "",
            "response_payload": response_payload or "",
            "http_status": int(http_status or 0),
            "success": bool(success),
            "error_message": error_message or "",
        }
        return self.sudo().create(vals)