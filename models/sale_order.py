# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Taksit Bilgileri
    installment_option_id = fields.Many2one('installment.option', string='Seçilen Taksit')
    installment_count = fields.Integer(related='installment_option_id.installment_count', 
                                        string='Taksit Sayısı', store=True)
    installment_amount = fields.Monetary(string='Taksit Tutarı', compute='_compute_installment_amount', currency_field='currency_id')
    commission_amount = fields.Monetary(string='Komisyon Tutarı', compute='_compute_installment_amount', currency_field='currency_id')

    # ==================== HESAPLAMA METOTLARI ====================
    
    @api.depends('amount_total', 'installment_option_id')
    def _compute_installment_amount(self):
        for order in self:
            if order.installment_option_id and order.amount_total > 0:
                amounts = order.installment_option_id.calculate_installment_amount(order.amount_total)
                order.installment_amount = amounts['installment_amount']
                order.commission_amount = amounts['commission_amount']
            else:
                order.installment_amount = order.amount_total
                order.commission_amount = 0.0

    # ==================== İŞ METOTLARI ====================
    
    def get_category_based_installments(self, provider_id=None):
        """Siparişteki ürünlere göre taksit seçeneklerini döndürür"""
        self.ensure_one()
        
        # Tüm kategorileri topla
        categories = self.order_line.mapped('product_id.categ_id')
        
        if not categories:
            return []
        
        # En kısıtlayıcı kategoriyi bul (en düşük max_installment_count)
        restrictive_category = min(categories, key=lambda c: c.max_installment_count)
        
        return restrictive_category.get_available_installments(self.amount_total, provider_id)
