# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ProductCategory(models.Model):
    _inherit = 'product.category'

    # ==================== TAKSİT AYARLARI ====================
    
    # Temel Taksit Ayarları
    allow_installments = fields.Boolean(string='Taksit İzin Ver', default=True,
                                        help='Bu kategorideki ürünler için taksit seçenekleri aktif olacak')
    max_installment_count = fields.Integer(string='Maksimum Taksit Sayısı', default=12,
                                           help='Bu kategori için izin verilen maksimum taksit sayısı')
    currency_id = fields.Many2one('res.currency', string='Para Birimi', 
                                  default=lambda self: self.env.company.currency_id)
    min_amount_for_installment = fields.Monetary(string='Taksit İçin Min. Tutar', default=100.0,
                                                 help='Taksit uygulanabilmesi için minimum sepet tutarı',
                                                 currency_field='currency_id')
    
    # Komisyon Ayarları
    commission_type = fields.Selection([
        ('fixed', 'Sabit Oran'),
        ('tiered', 'Kademeli Oran'),
        ('category_based', 'Kategori Bazlı'),
    ], string='Komisyon Tipi', default='fixed')
    
    default_commission_rate = fields.Float(string='Varsayılan Komisyon Oranı (%)', 
                                           default=0.0, digits=(5, 2))
    
    # ==================== KATEGORİ TAKSİT SEÇENEKLERİ ====================
    
    installment_line_ids = fields.One2many('product.category.installment', 'category_id',
                                           string='Özel Taksit Tanımları')
    
    # ==================== BANKA ÖZEL TAKSİTLER ====================
    
    bank_installment_ids = fields.One2many('product.category.bank.installment', 'category_id',
                                           string='Banka Bazlı Taksitler')
    
    # ==================== KAMPANYA TAKSİTLERİ ====================
    
    campaign_installment_ids = fields.One2many('product.category.campaign', 'category_id',
                                               string='Kampanya Taksitleri')
    
    # ==================== HESAPLAMA METOTLARI ====================
    
    @api.constrains('max_installment_count')
    def _check_max_installment(self):
        for category in self:
            if category.max_installment_count < 1:
                category.max_installment_count = 1
            elif category.max_installment_count > 24:
                category.max_installment_count = 24

    # ==================== İŞ METOTLARI ====================
    
    def get_installment_options(self, amount, provider_id=None, card_brand=None):
        """Bu kategori için uygun taksit seçeneklerini döndürür"""
        self.ensure_one()
        
        if not self.allow_installments:
            return []
        
        if amount < self.min_amount_for_installment:
            return []
        
        # Temel taksit seçeneklerini al
        options = []
        
        # 1. Kampanya taksitlerini kontrol et
        campaign_options = self._get_campaign_options(amount, provider_id, card_brand)
        options.extend(campaign_options)
        
        # 2. Banka özel taksitleri kontrol et
        bank_options = self._get_bank_options(amount, provider_id, card_brand)
        options.extend(bank_options)
        
        # 3. Genel taksit seçeneklerini ekle
        general_options = self._get_general_options(amount, provider_id)
        options.extend(general_options)
        
        # Tekrarları kaldır ve sırala
        unique_options = {opt['installment_count']: opt for opt in options}
        sorted_options = sorted(unique_options.values(), key=lambda x: x['installment_count'])
        
        return sorted_options

    def _get_campaign_options(self, amount, provider_id, card_brand):
        """Kampanya taksitlerini döndürür"""
        self.ensure_one()
        
        today = fields.Date.today()
        campaigns = self.campaign_installment_ids.filtered(
            lambda c: c.is_active and 
                      c.date_start <= today <= c.date_end and
                      c.min_amount <= amount <= c.max_amount
        )
        
        if provider_id:
            campaigns = campaigns.filtered(lambda c: c.provider_id.id == provider_id)
        
        options = []
        for campaign in campaigns:
            amounts = self._calculate_installment_amounts(
                amount, 
                campaign.installment_count, 
                campaign.commission_rate,
                campaign.interest_rate
            )
            options.append({
                'type': 'campaign',
                'campaign_id': campaign.id,
                'campaign_name': campaign.name,
                'installment_count': campaign.installment_count,
                'commission_rate': campaign.commission_rate,
                'interest_rate': campaign.interest_rate,
                'provider_id': campaign.provider_id.id,
                'provider_name': campaign.provider_id.name,
                'monthly_amount': amounts['monthly_amount'],
                'total_amount': amounts['total_amount'],
                'commission_amount': amounts['commission_amount'],
                'label': campaign.display_name,
            })
        
        return options

    def _get_bank_options(self, amount, provider_id, card_brand):
        """Banka özel taksitleri döndürür"""
        self.ensure_one()
        
        domain = [('is_active', '=', True), ('min_amount', '<=', amount), ('max_amount', '>=', amount)]
        if provider_id:
            domain.append(('provider_id', '=', provider_id))
        
        bank_installments = self.bank_installment_ids.search(domain)
        
        options = []
        for bi in bank_installments:
            if bi.installment_count > self.max_installment_count:
                continue
            
            amounts = self._calculate_installment_amounts(
                amount,
                bi.installment_count,
                bi.commission_rate,
                bi.interest_rate
            )
            options.append({
                'type': 'bank',
                'installment_count': bi.installment_count,
                'commission_rate': bi.commission_rate,
                'interest_rate': bi.interest_rate,
                'provider_id': bi.provider_id.id,
                'provider_name': bi.provider_id.name,
                'monthly_amount': amounts['monthly_amount'],
                'total_amount': amounts['total_amount'],
                'commission_amount': amounts['commission_amount'],
                'label': f"{bi.installment_count} Taksit - {bi.provider_id.name}",
            })
        
        return options

    def _get_general_options(self, amount, provider_id):
        """Genel taksit seçeneklerini döndürür"""
        self.ensure_one()
        
        # Kategori özel tanımları kontrol et
        domain = [('category_id', '=', self.id), ('is_active', '=', True)]
        if provider_id:
            domain.append(('provider_id', '=', provider_id))
        
        category_installments = self.env['product.category.installment'].search(domain)
        
        options = []
        for ci in category_installments:
            if ci.installment_option_id.installment_count > self.max_installment_count:
                continue
            
            commission_rate = ci.custom_commission_rate or ci.installment_option_id.commission_rate
            
            amounts = self._calculate_installment_amounts(
                amount,
                ci.installment_option_id.installment_count,
                commission_rate,
                ci.installment_option_id.interest_rate
            )
            options.append({
                'type': 'general',
                'installment_count': ci.installment_option_id.installment_count,
                'commission_rate': commission_rate,
                'interest_rate': ci.installment_option_id.interest_rate,
                'provider_id': ci.provider_id.id,
                'provider_name': ci.provider_id.name,
                'monthly_amount': amounts['monthly_amount'],
                'total_amount': amounts['total_amount'],
                'commission_amount': amounts['commission_amount'],
                'label': f"{ci.installment_option_id.installment_count} Taksit",
            })
        
        return options

    def _calculate_installment_amounts(self, amount, installment_count, commission_rate, interest_rate):
        """Taksit tutarlarını hesaplar"""
        # Vade farkı ekle
        if interest_rate > 0:
            amount_with_interest = amount * (1 + interest_rate / 100)
        else:
            amount_with_interest = amount
        
        # Komisyon ekle
        commission_amount = amount_with_interest * (commission_rate / 100)
        total_amount = amount_with_interest + commission_amount
        
        monthly_amount = total_amount / installment_count if installment_count > 0 else total_amount
        
        return {
            'monthly_amount': round(monthly_amount, 2),
            'total_amount': round(total_amount, 2),
            'commission_amount': round(commission_amount, 2),
        }


class ProductCategoryBankInstallment(models.Model):
    _name = 'product.category.bank.installment'
    _description = 'Kategori - Banka Taksit Tanımı'
    _order = 'sequence, installment_count'

    category_id = fields.Many2one('product.category', string='Kategori', required=True, ondelete='cascade')
    provider_id = fields.Many2one('payment.provider', string='Ödeme Sağlayıcısı', required=True)
    
    installment_count = fields.Integer(string='Taksit Sayısı', required=True)
    commission_rate = fields.Float(string='Komisyon Oranı (%)', default=0.0, digits=(5, 2))
    interest_rate = fields.Float(string='Vade Farkı (%)', default=0.0, digits=(5, 2))
    
    min_amount = fields.Monetary(string='Minimum Tutar', default=0.0, currency_field='currency_id')
    max_amount = fields.Monetary(string='Maksimum Tutar', default=999999.99, currency_field='currency_id')
    currency_id = fields.Many2one(related='provider_id.main_currency_id', string='Para Birimi')
    
    is_active = fields.Boolean(string='Aktif', default=True)
    sequence = fields.Integer(string='Sıra', default=10)
    note = fields.Text(string='Not')


class ProductCategoryCampaign(models.Model):
    _name = 'product.category.campaign'
    _description = 'Kategori Kampanya Taksiti'
    _order = 'date_start desc'

    category_id = fields.Many2one('product.category', string='Kategori', required=True, ondelete='cascade')
    name = fields.Char(string='Kampanya Adı', required=True)
    
    # Tarih Aralığı
    date_start = fields.Date(string='Başlangıç Tarihi', required=True)
    date_end = fields.Date(string='Bitiş Tarihi', required=True)
    
    # Taksit Bilgileri
    provider_id = fields.Many2one('payment.provider', string='Ödeme Sağlayıcısı', required=True)
    installment_count = fields.Integer(string='Taksit Sayısı', required=True)
    commission_rate = fields.Float(string='Komisyon Oranı (%)', default=0.0, digits=(5, 2))
    interest_rate = fields.Float(string='Vade Farkı (%)', default=0.0, digits=(5, 2))
    
    # Tutar Sınırları
    min_amount = fields.Monetary(string='Minimum Tutar', default=0.0, currency_field='currency_id')
    max_amount = fields.Monetary(string='Maksimum Tutar', default=999999.99, currency_field='currency_id')
    currency_id = fields.Many2one(related='provider_id.main_currency_id', string='Para Birimi')
    
    # Kart Markası
    card_brand_id = fields.Many2one('bank.card.brand', string='Kart Markası')
    
    # Durum
    is_active = fields.Boolean(string='Aktif', default=True)
    
    # Gösterim
    display_name = fields.Char(string='Görünen Ad', compute='_compute_display_name')
    
    @api.depends('name', 'installment_count', 'provider_id')
    def _compute_display_name(self):
        for campaign in self:
            campaign.display_name = f"[{campaign.provider_id.name}] {campaign.name} - {campaign.installment_count} Taksit"

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for campaign in self:
            if campaign.date_end < campaign.date_start:
                raise ValidationError(_('Bitiş tarihi başlangıç tarihinden önce olamaz.'))
