# -*- coding: utf-8 -*-
"""
Extensión del modelo ecf.api.provider de l10n_do_e_cf_tests para
soportar envío desde facturas con move_id.
"""
from odoo import api, fields, models, _

import logging
_logger = logging.getLogger(__name__)


class EcfApiProviderExtension(models.Model):
    """Extiende ecf.api.provider para soportar move_id."""
    _inherit = 'ecf.api.provider'

    def send_ecf_from_invoice(self, ecf_json, move, origin='invoice', validate_only=False):
        """
        Envía un e-CF desde una factura y guarda la relación en el log.

        Args:
            ecf_json: dict con el JSON del ECF
            move: record de account.move
            origin: tipo de origen (invoice, credit_note, debit_note)
            validate_only: si True, solo valida el formato sin consumir la
                secuencia de e-NCF ni enviar a DGII (solo MSeller).

        Returns:
            tuple: (success, response_data, track_id, error_message, raw_response, signed_xml)
        """
        self.ensure_one()

        # Llamar al método original
        result = self.send_ecf(
            ecf_json=ecf_json,
            rnc=move.company_id.vat,
            encf=move.encf,
            origin=origin,
            validate_only=validate_only,
        )

        # Buscar el log recién creado y asignar el move_id
        ApiLog = self.env['ecf.api.log']
        log = ApiLog.search([
            ('encf', '=', move.encf),
            ('provider_id', '=', self.id),
        ], order='create_date desc', limit=1)

        if log:
            log.write({'move_id': move.id})
            _logger.info(f"[API Provider] Log {log.id} asociado a factura {move.name}")

        return result
