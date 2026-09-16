# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase

class TestSaleOrderInvoiceDGI(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Cliente Pruebas DGI',
            'l10n_pa_receptor_tipo': '02',
            'l10n_pa_ruc': '8-888-8888',
            'l10n_pa_dv': '88',
        })
        self.sale_order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'dgi_payment_notes': 'Nota especial de entrega',
        })

    def test_prepare_invoice_includes_quote_reference(self):
        vals = self.sale_order._prepare_invoice()
        self.assertIn(f"Cotización: {self.sale_order.name}", vals.get('dgi_payment_notes', ''))
        self.assertIn("Nota especial de entrega", vals.get('dgi_payment_notes', ''))
