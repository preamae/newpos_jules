# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class PosStatusQueryWizard(models.TransientModel):
    _name = 'pos.status.query.wizard'
    _description = 'POS Durum Sorgulama Sihirbazı'

    # Sorgu Tipi
    query_type = fields.Selection([
        ('transaction', 'İşlem ID ile'),
        ('order', 'Sipariş ID ile'),
        ('date_range', 'Tarih Aralığı ile'),
    ], string='Sorgu Tipi', required=True, default='transaction')
    
    # İşlem ID ile sorgu
    transaction_id = fields.Many2one('payment.transaction', string='İşlem')
    
    # Sipariş ID ile sorgu
    order_id = fields.Char(string='Sipariş ID')
    
    # Tarih aralığı ile sorgu
    date_from = fields.Date(string='Başlangıç Tarihi')
    date_to = fields.Date(string='Bitiş Tarihi')
    provider_id = fields.Many2one('payment.provider', string='Sağlayıcı')
    
    # Sonuçlar
    result_ids = fields.Many2many('payment.transaction', string='Sonuçlar', compute='_compute_results')
    result_count = fields.Integer(string='Sonuç Sayısı', compute='_compute_results')

    # ==================== HESAPLAMA METOTLARI ====================
    
    @api.depends('query_type', 'transaction_id', 'order_id', 'date_from', 'date_to', 'provider_id')
    def _compute_results(self):
        for wizard in self:
            domain = []
            
            if wizard.query_type == 'transaction' and wizard.transaction_id:
                domain.append(('id', '=', wizard.transaction_id.id))
            elif wizard.query_type == 'order' and wizard.order_id:
                domain.append(('pos_order_id', 'ilike', wizard.order_id))
            elif wizard.query_type == 'date_range':
                if wizard.date_from:
                    domain.append(('payment_date', '>=', wizard.date_from))
                if wizard.date_to:
                    domain.append(('payment_date', '<=', wizard.date_to))
                if wizard.provider_id:
                    domain.append(('provider_id', '=', wizard.provider_id.id))
            
            if domain:
                transactions = self.env['payment.transaction'].search(domain)
                wizard.result_ids = [(6, 0, transactions.ids)]
                wizard.result_count = len(transactions)
            else:
                wizard.result_ids = [(5, 0, 0)]
                wizard.result_count = 0

    # ==================== İŞ METOTLARI ====================
    
    def action_query(self):
        """Sorguyu çalıştırır"""
        self.ensure_one()
        
        if self.query_type == 'transaction' and self.transaction_id:
            # Tek işlem sorgula
            result = self.transaction_id.action_query_status()
            return result
        
        elif self.result_ids:
            # Sonuçları göster
            return {
                'name': _('Sorgu Sonuçları'),
                'type': 'ir.actions.act_window',
                'res_model': 'payment.transaction',
                'view_mode': 'list,form',
                'domain': [('id', 'in', self.result_ids.ids)],
            }
        
        return {'type': 'ir.actions.act_window_close'}
