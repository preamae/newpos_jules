# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _name = 'turkey.pos.order'
    _description = 'POS Sipariş Kaydı'
    _order = 'date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ==================== TEMEL BİLGİLER ====================
    
    name = fields.Char(string='Sipariş No', required=True, index=True, copy=False, default='/')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('turkey.pos.order') or '/'
        return super().create(vals_list)
    
    # İlişkiler
    transaction_id = fields.Many2one('payment.transaction', string='Ödeme İşlemi', required=True)
    provider_id = fields.Many2one(related='transaction_id.provider_id', string='Sağlayıcı', store=True)
    partner_id = fields.Many2one(related='transaction_id.partner_id', string='Müşteri', store=True)
    sale_order_id = fields.Many2one('sale.order', string='Satış Siparişi')
    invoice_id = fields.Many2one('account.move', string='Fatura')
    
    # Tutar Bilgileri
    amount = fields.Monetary(related='transaction_id.amount', string='Tutar', store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='transaction_id.currency_id', string='Para Birimi', store=True)
    
    # POS Bilgileri
    pos_order_id = fields.Char(related='transaction_id.pos_order_id', string='POS Sipariş ID', store=True)
    pos_transaction_id = fields.Char(related='transaction_id.pos_transaction_id', 
                                      string='POS İşlem ID', store=True)
    pos_auth_code = fields.Char(related='transaction_id.pos_auth_code', string='Onay Kodu', store=True)
    
    # Taksit Bilgileri
    installment_count = fields.Integer(related='transaction_id.installment_count', 
                                        string='Taksit Sayısı', store=True)
    installment_amount = fields.Monetary(related='transaction_id.installment_amount', 
                                          string='Taksit Tutarı', store=True, 
                                          currency_field='currency_id')
    
    # Durum
    state = fields.Selection([
        ('draft', 'Taslak'),
        ('pending', 'Bekliyor'),
        ('authorized', 'Onaylandı'),
        ('done', 'Tamamlandı'),
        ('refunded', 'İade Edildi'),
        ('partial_refunded', 'Kısmi İade'),
        ('cancelled', 'İptal Edildi'),
        ('failed', 'Başarısız'),
        ('disputed', 'İtiraz Edildi'),
    ], string='Durum', default='draft', tracking=True)
    
    # Tarihler
    date = fields.Datetime(string='Sipariş Tarihi', default=lambda self: datetime.now())
    payment_date = fields.Datetime(string='Ödeme Tarihi')
    refund_date = fields.Datetime(string='İade Tarihi')
    cancel_date = fields.Datetime(string='İptal Tarihi')
    
    # 3D Secure
    is_3d_secure = fields.Boolean(related='transaction_id.is_3d_secure', string='3D Secure', store=True)
    md_status = fields.Char(related='transaction_id.md_status', string='3D Durum', store=True)
    
    # İade Bilgileri
    refund_amount = fields.Monetary(related='transaction_id.refund_amount', string='İade Tutarı', store=True, currency_field='currency_id')
    is_refunded = fields.Boolean(related='transaction_id.is_refunded', string='İade Edildi', store=True)
    
    # İptal Bilgileri
    is_cancelled = fields.Boolean(related='transaction_id.is_cancelled', string='İptal Edildi', store=True)
    
    # Notlar
    note = fields.Text(string='Not')
    internal_note = fields.Text(string='Dahili Not')
    
    # ==================== İŞ METOTLARI ====================
    
    def action_confirm(self):
        """Siparişi onaylar"""
        for order in self:
            if order.state == 'draft':
                order.state = 'pending'
                order.message_post(body=_('Sipariş onaylandı ve işleme alındı.'))

    def action_complete(self):
        """Siparişi tamamlar"""
        for order in self:
            if order.state in ['pending', 'authorized']:
                order.state = 'done'
                order.payment_date = datetime.now()
                order.message_post(body=_('Sipariş tamamlandı.'))

    def action_refund(self, amount=None):
        """Siparişi iade eder"""
        for order in self:
            if order.state != 'done':
                raise UserError(_('Sadece tamamlanmış siparişler iade edilebilir.'))
            
            # İşlemi iade et
            result = order.transaction_id.action_refund(amount)
            
            # Durumu güncelle
            if order.transaction_id.is_refunded:
                order.state = 'refunded'
                order.refund_date = datetime.now()
            elif order.transaction_id.refund_amount > 0:
                order.state = 'partial_refunded'
                order.refund_date = datetime.now()
            
            return result

    def action_cancel(self):
        """Siparişi iptal eder"""
        for order in self:
            if order.state not in ['draft', 'pending', 'authorized']:
                raise UserError(_('Bu durumdaki sipariş iptal edilemez.'))
            
            # İşlemi iptal et
            order.transaction_id.action_cancel_transaction()
            
            order.state = 'cancelled'
            order.cancel_date = datetime.now()
            order.message_post(body=_('Sipariş iptal edildi.'))

    # ==================== GÖRÜNÜM METOTLARI ====================
    
    def action_view_transaction(self):
        """Ödeme işlemini görüntüler"""
        self.ensure_one()
        return {
            'name': _('Ödeme İşlemi'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.transaction',
            'res_id': self.transaction_id.id,
            'view_mode': 'form',
        }

    def action_view_invoice(self):
        """Faturayı görüntüler"""
        self.ensure_one()
        if self.invoice_id:
            return {
                'name': _('Fatura'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': self.invoice_id.id,
                'view_mode': 'form',
            }
        return {'type': 'ir.actions.act_window_close'}

    def action_view_sale_order(self):
        """Satış siparişini görüntüler"""
        self.ensure_one()
        if self.sale_order_id:
            return {
                'name': _('Satış Siparişi'),
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'res_id': self.sale_order_id.id,
                'view_mode': 'form',
            }
        return {'type': 'ir.actions.act_window_close'}


class PosOrderLine(models.Model):
    _name = 'turkey.pos.order.line'
    _description = 'POS Sipariş Satırı'

    order_id = fields.Many2one('turkey.pos.order', string='Sipariş', required=True, ondelete='cascade')
    
    # Ürün Bilgileri
    product_id = fields.Many2one('product.product', string='Ürün', required=True)
    name = fields.Char(string='Açıklama')
    
    # Miktar ve Fiyat
    quantity = fields.Float(string='Miktar', default=1.0)
    price_unit = fields.Monetary(string='Birim Fiyat', currency_field='currency_id')
    discount = fields.Float(string='İndirim (%)', default=0.0)
    
    # Tutarlar
    price_subtotal = fields.Monetary(string='Ara Toplam', compute='_compute_amounts', store=True, currency_field='currency_id')
    price_total = fields.Monetary(string='Toplam', compute='_compute_amounts', store=True, currency_field='currency_id')
    
    # Para Birimi
    currency_id = fields.Many2one(related='order_id.currency_id', string='Para Birimi')
    
    # Taksit
    installment_count = fields.Integer(string='Taksit Sayısı', default=1)
    
    @api.depends('quantity', 'price_unit', 'discount')
    def _compute_amounts(self):
        for line in self:
            subtotal = line.quantity * line.price_unit
            discount_amount = subtotal * (line.discount / 100)
            line.price_subtotal = subtotal - discount_amount
            line.price_total = line.price_subtotal

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.name
            self.price_unit = self.product_id.lst_price


class PosReconciliation(models.Model):
    _name = 'pos.reconciliation'
    _description = 'POS Mutabakat'
    _order = 'date desc'

    name = fields.Char(string='Mutabakat No', required=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('pos.reconciliation'))
    
    # Dönem
    date_start = fields.Date(string='Başlangıç Tarihi', required=True)
    date_end = fields.Date(string='Bitiş Tarihi', required=True)
    
    # Sağlayıcı
    provider_id = fields.Many2one('payment.provider', string='Ödeme Sağlayıcısı', required=True)
    
    # Durum
    state = fields.Selection([
        ('draft', 'Taslak'),
        ('in_progress', 'İşleniyor'),
        ('done', 'Tamamlandı'),
        ('cancelled', 'İptal Edildi'),
    ], string='Durum', default='draft')
    
    # İstatistikler
    total_transaction_count = fields.Integer(string='Toplam İşlem', compute='_compute_statistics')
    total_amount = fields.Monetary(string='Toplam Tutar', compute='_compute_statistics', currency_field='currency_id')
    total_commission = fields.Monetary(string='Toplam Komisyon', compute='_compute_statistics', currency_field='currency_id')
    net_amount = fields.Monetary(string='Net Tutar', compute='_compute_statistics', currency_field='currency_id')
    
    # Para Birimi
    currency_id = fields.Many2one(related='provider_id.main_currency_id', string='Para Birimi')
    
    # İlişkiler
    order_ids = fields.Many2many('turkey.pos.order', string='Siparişler')
    transaction_ids = fields.Many2many('payment.transaction', string='İşlemler')
    
    @api.depends('order_ids')
    def _compute_statistics(self):
        for rec in self:
            rec.total_transaction_count = len(rec.order_ids)
            rec.total_amount = sum(rec.order_ids.mapped('amount'))
            rec.total_commission = sum(rec.order_ids.mapped('transaction_id.commission_amount'))
            rec.net_amount = rec.total_amount - rec.total_commission

    def action_load_transactions(self):
        """İşlemleri yükler"""
        for rec in self:
            domain = [
                ('provider_id', '=', rec.provider_id.id),
                ('payment_date', '>=', rec.date_start),
                ('payment_date', '<=', rec.date_end),
                ('state', '=', 'done'),
            ]
            transactions = self.env['payment.transaction'].search(domain)
            rec.transaction_ids = [(6, 0, transactions.ids)]
            
            # İlgili siparişleri bul
            orders = self.env['turkey.pos.order'].search([
                ('transaction_id', 'in', transactions.ids)
            ])
            rec.order_ids = [(6, 0, orders.ids)]

    def action_confirm(self):
        """Mutabakatı onaylar"""
        for rec in self:
            rec.state = 'done'

    def action_cancel(self):
        """Mutabakatı iptal eder"""
        for rec in self:
            rec.state = 'cancelled'

    @api.model
    def _cron_daily_reconciliation(self):
        """Günlük mutabakat raporu oluştur"""
        yesterday = datetime.now() - timedelta(days=1)
        providers = self.env['payment.provider'].search([
            ('code', 'in', ['akbank', 'garanti', 'isbank', 'ziraat', 'halkbank',
                            'vakifbank', 'vakifkatilim', 'yapikredi', 'finansbank',
                            'denizbank', 'teb', 'sekerbank', 'kuveytturk', 'param', 'tosla']),
            ('state', '=', 'enabled')
        ])

        for provider in providers:
            reconciliation = self.create({
                'name': "MUT/%s/%s" % (yesterday.strftime('%Y%m%d'), provider.code.upper()),
                'date_start': yesterday.date(),
                'date_end': yesterday.date(),
                'provider_id': provider.id,
            })
            reconciliation.action_load_transactions()
