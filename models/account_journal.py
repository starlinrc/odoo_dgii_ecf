# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    """Extensión del modelo account.journal para agregar campos DGII."""
    _inherit = 'account.journal'

    # ========== TIPOS DE COMPROBANTE FISCAL ELECTRÓNICO (MÚLTIPLES) ==========
    dgii_tipo_ecf_ids = fields.Many2many(
        'dgii.ecf.tipo',
        'dgii_journal_tipo_ecf_rel',
        'journal_id',
        'tipo_id',
        string='Tipos e-CF',
        help='Tipos de Comprobantes Fiscales Electrónicos que puede emitir este diario según normativa DGII'
    )

    # Campo legacy mantenido por compatibilidad (deprecado)
    dgii_tipo_ecf = fields.Selection(
        selection=[
            ('31', '31 – Factura de Crédito Fiscal Electrónica'),
            ('32', '32 – Factura de Consumo Electrónica'),
            ('33', '33 – Nota de Débito Electrónica'),
            ('34', '34 – Nota de Crédito Electrónica'),
            ('41', '41 – Comprobante Electrónico de Compras'),
            ('43', '43 – Comprobante Electrónico para Gastos Menores'),
            ('44', '44 – Comprobante Electrónico para Regímenes Especiales'),
            ('45', '45 – Comprobante Electrónico Gubernamental'),
            ('46', '46 – Comprobante Electrónico para Exportaciones'),
            ('47', '47 – Comprobante Electrónico para Pagos al Exterior'),
        ],
        string='Tipo e-CF (Deprecado)',
        help='[DEPRECADO] Use dgii_tipo_ecf_ids en su lugar. Campo mantenido por compatibilidad.'
    )

    # ========== IDENTIFICACIÓN DEL EMISOR ==========
    dgii_establecimiento = fields.Char(
        string='Establecimiento DGII',
        size=3,
        help='Código de establecimiento (3 dígitos numéricos) según DGII'
    )

    dgii_punto_emision = fields.Char(
        string='Punto de Emisión DGII',
        size=3,
        help='Código de punto de emisión (3 dígitos numéricos) según DGII'
    )

    # ========== RELACIÓN CON RANGOS DE SECUENCIAS ==========
    dgii_ecf_range_ids = fields.Many2many(
        'dgii.ecf.sequence.range',
        'dgii_ecf_range_journal_rel',
        'journal_id',
        'range_id',
        string='Rangos e-NCF',
        help='Rangos de secuencias e-NCF disponibles para este diario'
    )

    # ========== CAMPO COMPUTADO PARA MOSTRAR RANGOS ACTIVOS ==========
    dgii_active_range_count = fields.Integer(
        string='Rangos Activos',
        compute='_compute_active_range_count',
        help='Cantidad de rangos activos disponibles'
    )

    # ========== MÉTODOS COMPUTADOS ==========
    @api.depends('dgii_ecf_range_ids', 'dgii_ecf_range_ids.estado')
    def _compute_active_range_count(self):
        """Cuenta la cantidad de rangos activos asociados al diario."""
        for journal in self:
            journal.dgii_active_range_count = len(
                journal.dgii_ecf_range_ids.filtered(lambda r: r.estado == 'activo')
            )

    # ========== VALIDACIONES ==========
    @api.constrains('dgii_establecimiento')
    def _check_dgii_establecimiento(self):
        """Valida que el establecimiento tenga exactamente 3 dígitos numéricos."""
        for journal in self:
            if journal.dgii_establecimiento:
                if len(journal.dgii_establecimiento) != 3:
                    raise ValidationError(_(
                        'El código de establecimiento DGII debe tener exactamente 3 dígitos.'
                    ))
                if not journal.dgii_establecimiento.isdigit():
                    raise ValidationError(_(
                        'El código de establecimiento DGII debe contener solo dígitos numéricos.'
                    ))

    @api.constrains('dgii_punto_emision')
    def _check_dgii_punto_emision(self):
        """Valida que el punto de emisión tenga exactamente 3 dígitos numéricos."""
        for journal in self:
            if journal.dgii_punto_emision:
                if len(journal.dgii_punto_emision) != 3:
                    raise ValidationError(_(
                        'El código de punto de emisión DGII debe tener exactamente 3 dígitos.'
                    ))
                if not journal.dgii_punto_emision.isdigit():
                    raise ValidationError(_(
                        'El código de punto de emisión DGII debe contener solo dígitos numéricos.'
                    ))

    # ========== MÉTODOS DE NEGOCIO ==========
    def get_available_ecf_range(self, tipo_ecf=None):
        """
        Obtiene el rango de e-NCF válido y disponible para este diario y tipo específico.

        Args:
            tipo_ecf (str): Código del tipo de e-CF (ej: '31', '32').
                           Si no se especifica, usa el primer tipo configurado.

        Returns:
            dgii.ecf.sequence.range: Rango válido o False si no hay disponible

        Raises:
            UserError: Si el diario no está configurado correctamente
        """
        self.ensure_one()

        # Determinar el tipo a usar
        if not tipo_ecf:
            # Si hay tipos nuevos configurados, usar el primero
            if self.dgii_tipo_ecf_ids:
                tipo_ecf = self.dgii_tipo_ecf_ids[0].codigo
            # Si no, intentar usar el campo legacy
            elif self.dgii_tipo_ecf:
                tipo_ecf = self.dgii_tipo_ecf
            else:
                return False

        if not self.dgii_establecimiento or not self.dgii_punto_emision:
            return False

        # Buscar rango válido
        # Nota: No podemos usar secuencia_actual < secuencia_hasta directamente en el search
        # porque no se pueden comparar campos entre sí en dominios de Odoo.
        # En su lugar, buscamos rangos activos y luego filtramos en Python.
        domain = [
            ('tipo_ecf', '=', tipo_ecf),
            ('establecimiento', '=', self.dgii_establecimiento),
            ('punto_emision', '=', self.dgii_punto_emision),
            ('estado', '=', 'activo'),
            ('company_id', '=', self.company_id.id),
        ]

        # Tipo 34 (NC) no tiene fecha de vencimiento según normativa DGII
        if tipo_ecf != '34':
            domain.append(('fecha_vencimiento', '>=', fields.Date.today()))
        else:
            # Para tipo 34, aceptar rangos sin fecha o con fecha válida
            domain += ['|', ('fecha_vencimiento', '=', False), ('fecha_vencimiento', '>=', fields.Date.today())]

        ranges = self.env['dgii.ecf.sequence.range'].search(domain, order='secuencia_actual asc')

        # Filtrar rangos que aún tienen secuencias disponibles
        valid_range = ranges.filtered(lambda r: r.secuencia_actual < r.secuencia_hasta)

        return valid_range[0] if valid_range else False

    def get_tipo_ecf_for_invoice(self, invoice):
        """
        Determina inteligentemente el tipo de e-CF a usar según el contexto de la factura.

        Regla principal para facturas de venta:
        - Cliente SIN RNC o RNC NO validado → Tipo 32 (Consumo Final)
        - Cliente CON RNC validado → Tipo 31 (Crédito Fiscal) u otro según tipo

        Args:
            invoice (account.move): Factura para la cual determinar el tipo

        Returns:
            str: Código del tipo de e-CF a usar (ej: '31', '32')
        """
        self.ensure_one()

        # Si solo tiene un tipo configurado, usarlo
        if len(self.dgii_tipo_ecf_ids) == 1:
            return self.dgii_tipo_ecf_ids[0].codigo

        # Si no tiene tipos configurados, usar legacy
        if not self.dgii_tipo_ecf_ids and self.dgii_tipo_ecf:
            return self.dgii_tipo_ecf

        # Lógica inteligente de selección
        move_type = invoice.move_type
        partner = invoice.partner_id

        # Notas de crédito
        if move_type in ['out_refund', 'in_refund']:
            nota_credito = self.dgii_tipo_ecf_ids.filtered(lambda t: t.es_nota_credito)
            if nota_credito:
                return nota_credito[0].codigo

        # Facturas de venta
        if move_type == 'out_invoice':
            # Determinar tipo según el campo "Tipo de Contribuyente" del cliente
            tipo_contribuyente = getattr(partner, 'x_tipo_contribuyente', 'consumo_final')

            # Mapeo de tipo de contribuyente a código de e-CF
            if tipo_contribuyente == 'consumo_final':
                # Consumidor Final → Tipo 32
                consumo = self.dgii_tipo_ecf_ids.filtered(lambda t: t.codigo == '32')
                if consumo:
                    return consumo[0].codigo

            elif tipo_contribuyente == 'credito_fiscal':
                # Crédito Fiscal → Tipo 31 (requiere RNC validado)
                credito_fiscal = self.dgii_tipo_ecf_ids.filtered(lambda t: t.codigo == '31')
                if credito_fiscal:
                    return credito_fiscal[0].codigo

            elif tipo_contribuyente == 'gubernamental':
                # Gubernamental → Tipo 45 (requiere RNC validado)
                gubernamental = self.dgii_tipo_ecf_ids.filtered(lambda t: t.codigo == '45')
                if gubernamental:
                    return gubernamental[0].codigo
                # Si no tiene tipo 45 configurado, usar tipo 31
                credito_fiscal = self.dgii_tipo_ecf_ids.filtered(lambda t: t.codigo == '31')
                if credito_fiscal:
                    return credito_fiscal[0].codigo

            elif tipo_contribuyente == 'regimen_especial':
                # Régimen Especial → Tipo 44
                regimen_especial = self.dgii_tipo_ecf_ids.filtered(lambda t: t.codigo == '44')
                if regimen_especial:
                    return regimen_especial[0].codigo

            # Si no se pudo determinar, intentar usar consumo por defecto
            consumo = self.dgii_tipo_ecf_ids.filtered(lambda t: t.codigo == '32')
            if consumo:
                return consumo[0].codigo

        # Facturas de compra
        if move_type == 'in_invoice':
            compra = self.dgii_tipo_ecf_ids.filtered(lambda t: t.es_compra and t.codigo == '41')
            if compra:
                return compra[0].codigo

        # Por defecto, usar el primero disponible
        if self.dgii_tipo_ecf_ids:
            return self.dgii_tipo_ecf_ids[0].codigo

        return False

    def action_view_ecf_ranges(self):
        """Acción para ver los rangos e-NCF asociados a este diario."""
        self.ensure_one()
        return {
            'name': _('Rangos e-NCF'),
            'type': 'ir.actions.act_window',
            'res_model': 'dgii.ecf.sequence.range',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.dgii_ecf_range_ids.ids)],
            'context': {
                'default_tipo_ecf': self.dgii_tipo_ecf,
                'default_establecimiento': self.dgii_establecimiento,
                'default_punto_emision': self.dgii_punto_emision,
                'default_company_id': self.company_id.id,
            },
        }
