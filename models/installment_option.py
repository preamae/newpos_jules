# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class InstallmentOption(models.Model):
    _name = 'installment.option'
    _description = 'Taksit Seçeneği'
    _order = 'provider_id, installment_count'
    _inherit = ['mail.thread']

    # ==================== TEMEL BİLGİLER ====================
    
    name = fields.Char(string='Taksit Seçeneği', compute='_compute_name', store=True)
    provider_id = fields.Many2one('payment.provider', string='Ödeme Sağlayıcısı', required=True)
    gateway_type = fields.Selection(related='provider_id.gateway_type', string='Gateway Tipi', store=True)
    
    # Taksit Bilgileri
    installment_count = fields.Integer(string='Taksit Sayısı', required=True, default=1)
    is_active = fields.Boolean(string='Aktif', default=True)
    
    # Komisyon Oranları
    commission_rate = fields.Float(string='Komisyon Oranı (%)', default=0.0, digits=(5, 2))
    commission_amount = fields.Monetary(string='Komisyon Tutarı', compute='_compute_commission_amount', currency_field='currency_id')
    
    # Vade Farkı
    interest_rate = fields.Float(string='Vade Farkı Oranı (%)', default=0.0, digits=(5, 2))
    
    # Tutar Sınırları
    min_amount = fields.Monetary(string='Minimum Tutar', default=0.0, currency_field='currency_id')
    max_amount = fields.Monetary(string='Maksimum Tutar', default=999999.99, currency_field='currency_id')
    
    # Para Birimi
    currency_id = fields.Many2one(related='provider_id.main_currency_id', string='Para Birimi', store=True)
    
    # Açıklama
    description = fields.Text(string='Açıklama')
    
    # ==================== HESAPLAMA METOTLARI ====================
    
    @api.depends('installment_count', 'provider_id.name')
    def _compute_name(self):
        for option in self:
            if option.installment_count == 1:
                option.name = _('Tek Çekim')
            else:
                option.name = _('%s Taksit') % option.installment_count
            
            if option.provider_id:
                option.name = f"[{option.provider_id.name}] {option.name}"

    @api.depends('commission_rate', 'min_amount')
    def _compute_commission_amount(self):
        for option in self:
            option.commission_amount = (option.min_amount * option.commission_rate) / 100

    # ==================== KISITLAMALAR ====================
    
    @api.constrains('installment_count')
    def _check_installment_count(self):
        for option in self:
            if option.installment_count < 1:
                raise ValidationError(_('Taksit sayısı en az 1 olmalıdır.'))
            if option.installment_count > 24:
                raise ValidationError(_('Taksit sayısı en fazla 24 olabilir.'))

    @api.constrains('min_amount', 'max_amount')
    def _check_amounts(self):
        for option in self:
            if option.min_amount < 0:
                raise ValidationError(_('Minimum tutar negatif olamaz.'))
            if option.max_amount <= option.min_amount:
                raise ValidationError(_('Maksimum tutar minimum tutardan büyük olmalıdır.'))

    # ==================== İŞ METOTLARI ====================
    
    def calculate_installment_amount(self, total_amount):
        """Taksit tutarını hesaplar"""
        self.ensure_one()
        
        if self.installment_count <= 1:
            return {
                'installment_amount': total_amount,
                'total_amount': total_amount,
                'commission_amount': 0.0,
            }
        
        # Vade farkı hesapla
        if self.interest_rate > 0:
            total_with_interest = total_amount * (1 + (self.interest_rate / 100))
        else:
            total_with_interest = total_amount
        
        # Komisyon hesapla
        commission = (total_with_interest * self.commission_rate) / 100
        total_with_commission = total_with_interest + commission
        
        installment_amount = total_with_commission / self.installment_count
        
        return {
            'installment_amount': round(installment_amount, 2),
            'total_amount': round(total_with_commission, 2),
            'commission_amount': round(commission, 2),
        }

    def is_eligible(self, amount):
        """Verilen tutar için bu taksit seçeneği uygun mu?"""
        self.ensure_one()
        return self.is_active and self.min_amount <= amount <= self.max_amount


class ProductCategoryInstallment(models.Model):
    _name = 'product.category.installment'
    _description = 'Kategori Bazlı Taksit Seçeneği'
    _order = 'sequence, category_id'

    # İlişkiler
    category_id = fields.Many2one('product.category', string='Ürün Kategorisi', required=True)
    installment_option_id = fields.Many2one('installment.option', string='Taksit Seçeneği', required=True)
    provider_id = fields.Many2one(related='installment_option_id.provider_id', string='Sağlayıcı', store=True)
    
    # Sıralama
    sequence = fields.Integer(string='Sıra', default=10)
    
    # Özel Ayarlar
    custom_commission_rate = fields.Float(string='Özel Komisyon Oranı (%)', digits=(5, 2))
    custom_min_amount = fields.Monetary(string='Özel Minimum Tutar', currency_field='currency_id')
    
    # Para Birimi
    currency_id = fields.Many2one(related='installment_option_id.currency_id', string='Para Birimi')
    
    # Aktiflik
    is_active = fields.Boolean(string='Aktif', default=True)
    
    # Açıklama
    note = fields.Text(string='Not')

    # ==================== KISITLAMALAR ====================
    
    _sql_constraints = [
        ('unique_category_installment', 
         'UNIQUE(category_id, installment_option_id)', 
         'Bu kategori için bu taksit seçeneği zaten tanımlanmış!'),
    ]
