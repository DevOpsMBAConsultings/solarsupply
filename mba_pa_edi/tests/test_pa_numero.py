# -*- coding: utf-8 -*-
"""
Pruebas de la numeración fiscal (_pa_next_numero / _pa_reserve_numero).

Estas pruebas documentan REGLAS DE NEGOCIO, no solo comportamiento del código.
La más importante: el consecutivo es "el número más alto + 1", NO "la última
factura + 1". Si el cliente se saltó un número, ese hueco queda libre para
usarlo manualmente después. Es intencional — no lo "arregles".

Cómo correrlas:

    odoo -d TU_BASE -u mba_pa_edi --test-enable --stop-after-init

Odoo levanta todo en una transacción y hace rollback al terminar: no queda
ningún registro en la base.
"""
from odoo.tests.common import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPaNumeroFiscal(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.diario = cls.company_data['default_journal_sale']
        cls.diario_sucursal = cls.env['account.journal'].create({
            'name': 'Ventas Sucursal',
            'code': 'VSUC',
            'type': 'sale',
            'company_id': cls.env.company.id,
        })

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _factura(self, name=None, status=None, journal=None):
        """
        Crea una factura de cliente en borrador.

        :param name:    número fiscal a forzar. Si se omite, Odoo pone el suyo.
        :param status:  estado PAC. Si se omite queda en 'draft', que es el
                        estado que el cálculo del consecutivo debe ignorar.
        :param journal: diario. Por defecto el de ventas de la compañía.
        """
        vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-01-15',
            'journal_id': (journal or self.diario).id,
        }
        if name:
            vals['name'] = name
        move = self.env['account.move'].create(vals)
        if status:
            move.l10n_pa_pac_status = status
        return move

    # ------------------------------------------------------------------
    # _pa_next_numero
    # ------------------------------------------------------------------

    def test_diario_sin_facturas_emitidas_arranca_en_uno(self):
        """Un diario donde nunca se ha emitido nada empieza en 0000000001."""
        nueva = self._factura()
        self.assertEqual(nueva._pa_next_numero(), '0000000001')

    def test_toma_el_mas_alto_no_el_ultimo_creado(self):
        """
        El consecutivo sale del número MÁS ALTO, no del último registro creado.
        Aquí la 7 se creó antes que la 3, y aun así el siguiente es el 8.
        """
        self._factura('0000000007', 'accepted')
        self._factura('0000000003', 'accepted')
        nueva = self._factura()
        self.assertEqual(nueva._pa_next_numero(), '0000000008')

    def test_hueco_saltado_queda_libre(self):
        """
        REGLA DE NEGOCIO: si el cliente se saltó la 51 y usó la 52, el siguiente
        sugerido es la 53 — NO la 51.

        La 51 queda libre a propósito, para que puedan emitirla a mano desde el
        wizard cuando les toque usar ese número reservado.
        """
        self._factura('0000000050', 'accepted')
        self._factura('0000000052', 'accepted')
        nueva = self._factura()
        self.assertEqual(nueva._pa_next_numero(), '0000000053')

    def test_factura_en_error_cuenta_como_numero_usado(self):
        """
        Una factura rechazada por el PAC conserva su número reservado, así que
        cuenta como usado. Si no, el siguiente intento chocaría contra ella.
        """
        self._factura('0000000007', 'error')
        nueva = self._factura()
        self.assertEqual(nueva._pa_next_numero(), '0000000008')

    def test_borrador_nunca_enviado_no_cuenta(self):
        """
        Un borrador que nunca se envió al PAC no consume número, aunque Odoo le
        haya puesto su propio nombre (INV/2026/00001 y similares).
        """
        self._factura()
        self._factura()
        nueva = self._factura()
        self.assertEqual(nueva._pa_next_numero(), '0000000001')

    def test_nombre_sin_digitos_no_rompe_el_calculo(self):
        """Un nombre sin dígitos se ignora en vez de reventar el cálculo."""
        self._factura('SIN NUMERO', 'accepted')
        self._factura('0000000004', 'accepted')
        nueva = self._factura()
        self.assertEqual(nueva._pa_next_numero(), '0000000005')

    def test_cada_diario_lleva_su_propio_consecutivo(self):
        """Lo emitido en un diario no corre el consecutivo de otro."""
        self._factura('0000000100', 'accepted', journal=self.diario)
        nueva = self._factura(journal=self.diario_sucursal)
        self.assertEqual(nueva._pa_next_numero(), '0000000001')

    def test_facturas_anuladas_siguen_ocupando_su_numero(self):
        """Anular en DGI no libera el número: ese consecutivo ya se usó."""
        self._factura('0000000020', 'cancelled')
        nueva = self._factura()
        self.assertEqual(nueva._pa_next_numero(), '0000000021')

    # ------------------------------------------------------------------
    # _pa_reserve_numero
    # ------------------------------------------------------------------

    def test_reservar_escribe_el_siguiente_numero(self):
        """Reservar sin argumento toma el siguiente y lo deja escrito."""
        self._factura('0000000050', 'accepted')
        nueva = self._factura()
        devuelto = nueva._pa_reserve_numero()
        self.assertEqual(devuelto, '0000000051')
        self.assertEqual(nueva.name, '0000000051')

    def test_reservar_respeta_un_numero_impuesto(self):
        """
        REGLA DE NEGOCIO: el flujo manual puede imponer un número reservado
        (el hueco que quedó libre) y la reserva debe respetarlo tal cual.
        """
        self._factura('0000000050', 'accepted')
        self._factura('0000000052', 'accepted')
        nueva = self._factura()
        nueva._pa_reserve_numero('0000000051')
        self.assertEqual(nueva.name, '0000000051')
