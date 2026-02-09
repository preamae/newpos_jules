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


class ProductCategory(models.Model):
    _inherit = 'product.category'

    # Taksit Seçenekleri
    installment_line_ids = fields.One2many('product.category.installment', 'category_id', 
                                            string='Kategori Taksit Seçenekleri')
    
    # Varsayılan Taksit
    default_installment_id = fields.Many2one('installment.option', string='Varsayılan Taksit')
    
    # Taksit Aktifliği
    allow_installments = fields.Boolean(string='Taksit İzin Ver', default=True)
    max_installment_count = fields.Integer(string='Maksimum Taksit Sayısı', default=12)

    # ==================== İŞ METOTLARI ====================
    
    def get_available_installments(self, amount, provider_id=None):
        """Bu kategori için uygun taksit seçeneklerini döndürür"""
        self.ensure_one()
        
        if not self.allow_installments:
            return []
        
        domain = [('category_id', '=', self.id), ('is_active', '=', True)]
        if provider_id:
            domain.append(('provider_id', '=', provider_id))
        
        category_installments = self.env['product.category.installment'].search(domain)
        
        available_options = []
        for ci in category_installments:
            option = ci.installment_option_id
            if option.is_active and option.installment_count <= self.max_installment_count:
                if option.is_eligible(amount):
                    available_options.append({
                        'option_id': option.id,
                        'provider_id': option.provider_id.id,
                        'provider_name': option.provider_id.name,
                        'installment_count': option.installment_count,
                        'commission_rate': ci.custom_commission_rate or option.commission_rate,
                        'amounts': option.calculate_installment_amount(amount),
                    })
        
        return sorted(available_options, key=lambda x: x['installment_count'])


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


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # Kategori bazlı taksit
    category_installment_id = fields.Many2one('installment.option', string='Kategori Taksit Seçeneği')
    category_id = fields.Many2one('product.category', string='İlişkili Kategori')
