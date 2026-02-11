# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ==================== POS İLİŞKİLERİ ====================
    
    pos_transaction_ids = fields.Many2many('payment.transaction', string='POS İşlemleri')
    turkey_pos_order_id = fields.Many2one('turkey.pos.order', string='POS Siparişi')
    
    # Ödeme Bilgileri
    payment_provider_id = fields.Many2one('payment.provider', string='Ödeme Sağlayıcısı')
    is_pos_payment = fields.Boolean(string='POS Ödemesi', default=False)
    
    # Taksit Bilgileri
    installment_count = fields.Integer(related='turkey_pos_order_id.installment_count', 
                                        string='Taksit Sayısı', store=True)
    installment_amount = fields.Monetary(related='turkey_pos_order_id.installment_amount',
                                          string='Taksit Tutarı', store=True, currency_field='currency_id')
    
    # İade Bilgileri
    is_refund = fields.Boolean(string='İade', default=False)
    refund_date = fields.Date(string='İade Tarihi')
    original_invoice_id = fields.Many2one('account.move', string='Orijinal Fatura')
    
    # ==================== İŞ METOTLARI ====================
    
    def action_pos_refund(self):
        """POS iade işlemi yapar"""
        for move in self:
            if not move.is_pos_payment:
                continue
            
            if move.pos_transaction_ids:
                for tx in move.pos_transaction_ids:
                    if tx.state == 'done' and not tx.is_refunded:
                        tx.action_refund()
                        
                move.is_refund = True
                move.refund_date = fields.Date.today()

    def action_view_pos_transactions(self):
        """POS işlemlerini görüntüler"""
        self.ensure_one()
        return {
            'name': _('POS İşlemleri'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.transaction',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.pos_transaction_ids.ids)],
        }


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # POS Bilgileri
    is_pos_line = fields.Boolean(string='POS Satırı', default=False)
    pos_transaction_id = fields.Many2one('payment.transaction', string='POS İşlemi')
    
    # Komisyon
    is_commission = fields.Boolean(string='Komisyon Satırı', default=False)
    commission_rate = fields.Float(string='Komisyon Oranı (%)', digits=(5, 2))
