# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PosCancelWizard(models.TransientModel):
    _name = 'pos.cancel.wizard'
    _description = 'POS İptal Sihirbazı'

    # İlişkiler
    transaction_id = fields.Many2one('payment.transaction', string='İşlem', required=True)
    provider_id = fields.Many2one(related='transaction_id.provider_id', string='Sağlayıcı')
    
    # İşlem Bilgileri
    order_id = fields.Char(related='transaction_id.pos_order_id', string='Sipariş ID')
    amount = fields.Monetary(related='transaction_id.amount', string='Tutar', currency_field='currency_id')
    currency_id = fields.Many2one(related='transaction_id.currency_id', string='Para Birimi')
    payment_date = fields.Date(related='transaction_id.payment_date', string='Ödeme Tarihi')
    
    # İptal Nedeni
    cancel_reason = fields.Selection([
        ('customer_request', 'Müşteri Talebi'),
        ('technical_error', 'Teknik Hata'),
        ('duplicate_transaction', 'Çift İşlem'),
        ('fraud_suspected', 'Dolandırıcılık Şüphesi'),
        ('order_cancelled', 'Sipariş İptali'),
        ('other', 'Diğer'),
    ], string='İptal Nedeni', required=True, default='customer_request')
    
    cancel_note = fields.Text(string='İptal Notu')
    
    # Onay
    confirm_cancel = fields.Boolean(string='İptali Onaylıyorum', default=False)
    
    # Uyarı
    warning_message = fields.Text(string='Uyarı', compute='_compute_warning_message')

    # ==================== HESAPLAMA METOTLARI ====================
    
    @api.depends('payment_date')
    def _compute_warning_message(self):
        for wizard in self:
            if wizard.payment_date:
                from datetime import datetime, timedelta
                days_passed = (datetime.now() - wizard.payment_date).days
                if days_passed > 1:
                    wizard.warning_message = _(
                        'UYARI: Bu işlem üzerinden %s gün geçmiş. '
                        'İptal yerine iade işlemi yapmanız önerilir.'
                    ) % days_passed
                else:
                    wizard.warning_message = False
            else:
                wizard.warning_message = False

    # ==================== İŞ METOTLARI ====================
    
    def action_confirm_cancel(self):
        """İptal işlemini onaylar"""
        self.ensure_one()
        
        if not self.confirm_cancel:
            raise ValidationError(_('Lütfen iptali onaylayın.'))
        
        # İptal işlemini gerçekleştir
        result = self.transaction_id.action_cancel_transaction()
        
        # İptal notunu kaydet
        if self.cancel_note:
            self.transaction_id.message_post(
                body=_('İptal Notu: %s') % self.cancel_note
            )
        
        return result
