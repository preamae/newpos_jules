# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class BankGateway(models.Model):
    _name = 'bank.gateway'
    _description = 'Banka Sanal POS Gateway'
    _order = 'sequence, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ==================== TEMEL BİLGİLER ====================
    
    name = fields.Char(string='Gateway Adı', required=True)
    code = fields.Char(string='Gateway Kodu', required=True, index=True)
    bank_name = fields.Char(string='Banka Adı', required=True)
    bank_logo = fields.Binary(string='Banka Logosu')
    
    sequence = fields.Integer(string='Sıra', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    
    # Gateway Tipi
    gateway_type = fields.Selection([
        ('est', 'Asseco EST'),
        ('est_v3', 'Asseco EST V3 (SHA-512)'),
        ('garanti', 'Garanti Virtual POS'),
        ('posnet', 'YKB PosNet'),
        ('posnet_v1', 'YKB PosNet V1'),
        ('payfor', 'QNB Finansbank PayFor'),
        ('interpos', 'Denizbank İnterPos'),
        ('payflex', 'PayFlex MPI VPOS V4'),
        ('payflex_cp', 'PayFlex Common Payment V4'),
        ('akbank', 'Akbank POS'),
        ('kuveyt', 'Kuveyt Türk POS'),
        ('param', 'Param POS'),
        ('tosla', 'Tosla POS'),
        ('vakifkatilim', 'Vakıf Katılım POS'),
    ], string='Gateway Tipi', required=True)
    
    # ==================== DESTEKLENEN ÖZELLİKLER ====================
    
    support_3d_secure = fields.Boolean(string='3D Secure Desteği', default=True)
    support_3d_pay = fields.Boolean(string='3D Pay Desteği', default=True)
    support_non_secure = fields.Boolean(string='Non-Secure Desteği', default=True)
    support_3d_host = fields.Boolean(string='3D Host Desteği', default=False)
    support_recurring = fields.Boolean(string='Tekrarlanan Ödeme Desteği', default=False)
    
    support_refund = fields.Boolean(string='İade Desteği', default=True)
    support_cancel = fields.Boolean(string='İptal Desteği', default=True)
    support_status_query = fields.Boolean(string='Durum Sorgulama Desteği', default=True)
    support_order_history = fields.Boolean(string='Sipariş Tarihçesi Desteği', default=False)
    support_partial_refund = fields.Boolean(string='Kısmi İade Desteği', default=False)
    
    # ==================== KREDİ KARTI DESTEĞİ ====================
    
    supported_card_brands = fields.Many2many('bank.card.brand', string='Desteklenen Kart Markaları')
    supported_currencies = fields.Many2many('res.currency', string='Desteklenen Para Birimleri')
    
    # ==================== API URL'LERİ ====================
    
    # Test Ortamı
    test_api_url = fields.Char(string='Test API URL')
    test_3d_url = fields.Char(string='Test 3D URL')
    test_query_url = fields.Char(string='Test Sorgulama URL')
    
    # Canlı Ortam
    production_api_url = fields.Char(string='Canlı API URL')
    production_3d_url = fields.Char(string='Canlı 3D URL')
    production_query_url = fields.Char(string='Canlı Sorgulama URL')
    
    # ==================== DOKÜMANTASYON ====================
    
    documentation_url = fields.Char(string='Dokümantasyon URL')
    technical_contact = fields.Char(string='Teknik Destek İletişim')
    
    # ==================== AÇIKLAMA ====================
    
    description = fields.Text(string='Açıklama')
    setup_instructions = fields.Html(string='Kurulum Talimatları')
    
    # ==================== İSTATİSTİKLER ====================
    
    provider_count = fields.Integer(string='Bağlı Sağlayıcı Sayısı', compute='_compute_provider_count')
    transaction_count = fields.Integer(string='Toplam İşlem Sayısı', compute='_compute_statistics')
    success_rate = fields.Float(string='Başarı Oranı (%)', compute='_compute_statistics')
    
    # ==================== HESAPLAMA METOTLARI ====================
    
    @api.depends('provider_ids')
    def _compute_provider_count(self):
        for gateway in self:
            gateway.provider_count = len(gateway.provider_ids)

    @api.depends('provider_ids')
    def _compute_statistics(self):
        for gateway in self:
            total_tx = 0
            success_tx = 0
            for provider in gateway.provider_ids:
                txs = self.env['payment.transaction'].search([
                    ('provider_id', '=', provider.id),
                    ('state', 'in', ['done', 'error'])
                ])
                total_tx += len(txs)
                success_tx += len(txs.filtered(lambda t: t.state == 'done'))
            
            gateway.transaction_count = total_tx
            gateway.success_rate = (success_tx / total_tx * 100) if total_tx > 0 else 0.0

    # ==================== İLİŞKİLER ====================
    
    provider_ids = fields.One2many('payment.provider', 'gateway_id', string='Ödeme Sağlayıcıları')

    # ==================== KISITLAMALAR ====================
    
    _sql_constraints = [
        ('unique_code', 'UNIQUE(code)', 'Gateway kodu benzersiz olmalıdır!'),
    ]

    # ==================== BUTONLAR ====================
    
    def action_view_providers(self):
        """Bağlı sağlayıcıları görüntüler"""
        self.ensure_one()
        return {
            'name': _('Ödeme Sağlayıcıları'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.provider',
            'view_mode': 'list,form',
            'domain': [('gateway_id', '=', self.id)],
            'context': {'default_gateway_id': self.id, 'default_gateway_type': self.gateway_type},
        }


class BankCardBrand(models.Model):
    _name = 'bank.card.brand'
    _description = 'Kredi Kartı Markası'
    _order = 'sequence, name'

    name = fields.Char(string='Marka Adı', required=True)
    code = fields.Char(string='Marka Kodu', required=True)
    sequence = fields.Integer(string='Sıra', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    logo = fields.Binary(string='Logo')
    
    # BIN numaraları (ilk 6 hane)
    bin_prefixes = fields.Text(string='BIN Prefixleri', 
                               help='Her satıra bir BIN prefixi yazın. Örn: 454671')
    
    # Gateway ilişkisi
    gateway_ids = fields.Many2many('bank.gateway', string='Destekleyen Gatewayler')
