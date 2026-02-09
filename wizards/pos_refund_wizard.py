# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PosRefundWizard(models.TransientModel):
    _name = 'pos.refund.wizard'
    _description = 'POS İade Sihirbazı'

    # İlişkiler
    transaction_id = fields.Many2one('payment.transaction', string='İşlem', required=True)
    provider_id = fields.Many2one(related='transaction_id.provider_id', string='Sağlayıcı')
    
    # Tutar Bilgileri
    original_amount = fields.Monetary(related='transaction_id.amount', string='Orijinal Tutar', currency_field='currency_id')
    already_refunded = fields.Monetary(related='transaction_id.refund_amount', string='Önceki İadeler', currency_field='currency_id')
    max_amount = fields.Monetary(string='Maksimum İade Tutarı', compute='_compute_max_amount', currency_field='currency_id')
    refund_amount = fields.Monetary(string='İade Tutarı', required=True, currency_field='currency_id')
    
    # Para Birimi
    currency_id = fields.Many2one(related='transaction_id.currency_id', string='Para Birimi')
    
    # İade Nedeni
    refund_reason = fields.Selection([
        ('customer_request', 'Müşteri Talebi'),
        ('duplicate_charge', 'Çift Tahsilat'),
        ('fraud', 'Dolandırıcılık'),
        ('product_return', 'Ürün İadesi'),
        ('service_issue', 'Hizmet Sorunu'),
        ('other', 'Diğer'),
    ], string='İade Nedeni', required=True, default='customer_request')
    
    refund_note = fields.Text(string='İade Notu')
    
    # Onay
    confirm_refund = fields.Boolean(string='İadeyi Onaylıyorum', default=False)

    # ==================== HESAPLAMA METOTLARI ====================
    
    @api.depends('original_amount', 'already_refunded')
    def _compute_max_amount(self):
        for wizard in self:
            wizard.max_amount = wizard.original_amount - wizard.already_refunded

    # ==================== KISITLAMALAR ====================
    
    @api.constrains('refund_amount', 'max_amount')
    def _check_refund_amount(self):
        for wizard in self:
            if wizard.refund_amount <= 0:
                raise ValidationError(_('İade tutarı sıfırdan büyük olmalıdır.'))
            if wizard.refund_amount > wizard.max_amount:
                raise ValidationError(_('İade tutarı maksimum tutardan büyük olamaz.'))

    # ==================== İŞ METOTLARI ====================
    
    def action_confirm_refund(self):
        """İade işlemini onaylar"""
        self.ensure_one()
        
        if not self.confirm_refund:
            raise ValidationError(_('Lütfen iadeyi onaylayın.'))
        
        # İade işlemini gerçekleştir
        result = self.transaction_id.action_refund(self.refund_amount)
        
        # İade notunu kaydet
        if self.refund_note:
            self.transaction_id.message_post(
                body=_('İade Notu: %s') % self.refund_note
            )
        
        return result
