# -*- coding: utf-8 -*-

import logging
import hashlib
import hmac
import base64
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import urlencode, parse_qs, urlparse
from lxml import etree

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools.float_utils import float_round

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    # ==================== BANKA SEÇİMİ ====================
    code = fields.Selection(selection_add=[
        ('akbank', 'Akbank'),
        ('garanti', 'Garanti BBVA'),
        ('isbank', 'İş Bankası'),
        ('ziraat', 'Ziraat Bankası'),
        ('halkbank', 'Halkbank'),
        ('vakifbank', 'Vakıfbank'),
        ('vakifkatilim', 'Vakıf Katılım'),
        ('yapikredi', 'Yapı Kredi Bankası'),
        ('finansbank', 'QNB Finansbank'),
        ('denizbank', 'Denizbank'),
        ('teb', 'TEB'),
        ('sekerbank', 'Şekerbank'),
        ('kuveytturk', 'Kuveyt Türk'),
        ('param', 'Param POS'),
        ('tosla', 'Tosla (AKÖde)'),
    ], ondelete={
        'akbank': 'cascade',
        'garanti': 'cascade',
        'isbank': 'cascade',
        'ziraat': 'cascade',
        'halkbank': 'cascade',
        'vakifbank': 'cascade',
        'vakifkatilim': 'cascade',
        'yapikredi': 'cascade',
        'finansbank': 'cascade',
        'denizbank': 'cascade',
        'teb': 'cascade',
        'sekerbank': 'cascade',
        'kuveytturk': 'cascade',
        'param': 'cascade',
        'tosla': 'cascade',
    })

    # ==================== GATEWAY TİPİ ====================
    gateway_id = fields.Many2one('bank.gateway', string='Banka Gateway')
    gateway_type = fields.Selection([
        ('est', 'Asseco EST (İşbank, Ziraat, Halkbank, TEB, Şekerbank)'),
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
    ], string='Gateway Tipi', required=True, default='est')

    # ==================== API KONFİGÜRASYONU ====================
    # Temel API Bilgileri
    api_username = fields.Char(string='API Kullanıcı Adı')
    api_password = fields.Char(string='API Şifre')
    api_client_id = fields.Char(string='Müşteri ID / Terminal ID')
    api_merchant_id = fields.Char(string='Mağaza ID')
    api_store_key = fields.Char(string='Mağaza Anahtarı (Store Key)')
    api_provision_user = fields.Char(string='Provizyon Kullanıcısı')
    api_terminal_id = fields.Char(string='Terminal ID')
    
    # 3D Secure Ayarları
    use_3d_secure = fields.Boolean(string='3D Secure Kullan', default=True)
    force_3d_secure = fields.Boolean(string='3D Secure Zorunlu', default=False)
    allow_non_secure = fields.Boolean(string='Non-Secure İzin Ver', default=False)
    
    # Ortam Ayarları
    environment = fields.Selection([
        ('test', 'Test Ortamı'),
        ('production', 'Canlı Ortam'),
    ], string='Ortam', default='test', required=True)
    
    # API URL'leri
    api_url_test = fields.Char(string='Test API URL')
    api_url_production = fields.Char(string='Canlı API URL')
    api_3d_url_test = fields.Char(string='Test 3D URL')
    api_3d_url_production = fields.Char(string='Canlı 3D URL')
    
    # Hash Algoritması
    hash_algorithm = fields.Selection([
        ('sha256', 'SHA-256'),
        ('sha512', 'SHA-512'),
    ], string='Hash Algoritması', default='sha256')
    
    # Taksit Ayarları
    enable_installments = fields.Boolean(string='Taksit Seçeneklerini Aktif Et', default=True)
    max_installment_count = fields.Integer(string='Maksimum Taksit Sayısı', default=12)
    min_amount_for_installment = fields.Monetary(string='Taksit İçin Min. Tutar', default=100.0,
                                                 currency_field='main_currency_id')
    
    # İade ve İptal
    allow_refund = fields.Boolean(string='İade Yapılabilir', default=True)
    allow_cancel = fields.Boolean(string='İptal Yapılabilir', default=True)
    refund_time_limit_days = fields.Integer(string='İade Süre Limiti (Gün)', default=30)
    
    # İleri Seviye Ayarlar
    timeout_seconds = fields.Integer(string='API Zaman Aşımı (Saniye)', default=30)
    retry_count = fields.Integer(string='Tekrar Deneme Sayısı', default=3)
    log_requests = fields.Boolean(string='API İsteklerini Logla', default=True)
    
    # İstatistikler
    transaction_count = fields.Integer(string='İşlem Sayısı', compute='_compute_statistics')
    main_currency_id = fields.Many2one('res.currency', string='Ana Para Birimi', 
                                       default=lambda self: self.env.company.currency_id)
    total_volume = fields.Monetary(string='Toplam Hacim', compute='_compute_statistics',
                                   currency_field='main_currency_id')
    success_rate = fields.Float(string='Başarı Oranı (%)', compute='_compute_statistics')

    # ==================== HESAPLAMA METOTLARI ====================
    
    def _compute_statistics(self):
        for provider in self:
            transactions = self.env['payment.transaction'].search([
                ('provider_id', '=', provider.id),
                ('state', 'in', ['done', 'error', 'cancel'])
            ])
            provider.transaction_count = len(transactions)
            provider.total_volume = sum(transactions.filtered(lambda t: t.state == 'done').mapped('amount'))
            done_count = len(transactions.filtered(lambda t: t.state == 'done'))
            provider.success_rate = (done_count / len(transactions) * 100) if transactions else 0.0

    # ==================== KISITLAMALAR ====================
    
    @api.constrains('max_installment_count')
    def _check_max_installment(self):
        for record in self:
            if record.max_installment_count < 1 or record.max_installment_count > 24:
                raise ValidationError(_('Maksimum taksit sayısı 1-24 arasında olmalıdır.'))

    # ==================== HAZIRLIK METOTLARI ====================
    
    def _get_api_url(self, endpoint_type='api'):
        """Ortama göre API URL'sini döndürür"""
        self.ensure_one()
        if self.environment == 'test':
            return endpoint_type == '3d' and self.api_3d_url_test or self.api_url_test
        return endpoint_type == '3d' and self.api_3d_url_production or self.api_url_production

    def _generate_hash(self, data, hash_type='sha256'):
        """Hash oluşturur"""
        self.ensure_one()
        if hash_type == 'sha512':
            return hashlib.sha512(data.encode('utf-8')).hexdigest()
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

    def _generate_hmac(self, data, key):
        """HMAC hash oluşturur"""
        return hmac.new(key.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).hexdigest()

    def _get_currency_code(self, currency):
        """Para birimi kodunu döndürür"""
        currency_map = {
            'TRY': '949',
            'USD': '840',
            'EUR': '978',
            'GBP': '826',
        }
        return currency_map.get(currency.name, '949')

    # ==================== GATEWAY SPESİFİK METOTLAR ====================
    
    # ---- EST POS (Asseco) ----
    def _est_prepare_payment_data(self, transaction, card_data, return_url):
        """EST POS için ödeme verisi hazırlar"""
        self.ensure_one()
        order_id = f"{transaction.reference}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        data = {
            'clientid': self.api_client_id,
            'amount': str(transaction.amount),
            'oid': order_id,
            'okUrl': return_url,
            'failUrl': return_url,
            'islemtipi': 'Auth',
            'taksit': str(card_data.get('installment_count', 0)),
            'currency': self._get_currency_code(transaction.currency_id),
            'rnd': datetime.now().strftime('%Y%m%d%H%M%S'),
            'pan': card_data.get('card_number', ''),
            'Eavms_Emonth': card_data.get('expiry_month', ''),
            'Eavms_Eyear': card_data.get('expiry_year', ''),
            'cv2': card_data.get('cvv', ''),
        }
        
        # Hash oluştur
        hash_data = f"{data['clientid']}{data['oid']}{data['amount']}{data['okUrl']}{data['failUrl']}{data['islemtipi']}{data['taksit']}{data['rnd']}{self.api_store_key}"
        data['hash'] = self._generate_hash(hash_data, self.hash_algorithm)
        
        return data, order_id

    # ---- Garanti POS ----
    def _garanti_prepare_payment_data(self, transaction, card_data, return_url):
        """Garanti POS için ödeme verisi hazırlar"""
        self.ensure_one()
        order_id = f"{transaction.reference}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Güvenlik verisi oluştur
        terminal_id = self.api_terminal_id.zfill(9)
        provision_password = self.api_provision_user
        security_data = self._generate_hash(provision_password + terminal_id, 'sha256').upper()
        
        hash_data = f"{self.api_terminal_id}{order_id}{str(transaction.amount)}{security_data}"
        hash_value = self._generate_hash(hash_data, 'sha256').upper()
        
        data = {
            'secure3dsecuritylevel': '3D' if self.use_3d_secure else '3D_PAY',
            'mode': 'PROD' if self.environment == 'production' else 'TEST',
            'apiversion': '512',
            'terminalid': self.api_terminal_id,
            'terminalmerchantid': self.api_merchant_id,
            'terminaluserid': self.api_provision_user,
            'orderid': order_id,
            'customeremailaddress': transaction.partner_email or '',
            'customeripaddress': transaction.partner_ip_address or '127.0.0.1',
            'txnamount': str(int(transaction.amount * 100)),  # Kuruş cinsinden
            'txncurrencycode': self._get_currency_code(transaction.currency_id),
            'txninstallmentcount': str(card_data.get('installment_count', 0)),
            'successurl': return_url,
            'errorurl': return_url,
            'secure3dhash': hash_value,
            'cardnumber': card_data.get('card_number', ''),
            'cardexpiredatemonth': card_data.get('expiry_month', ''),
            'cardexpiredateyear': card_data.get('expiry_year', ''),
            'cardcvv2': card_data.get('cvv', ''),
        }
        
        return data, order_id

    # ---- YKB PosNet ----
    def _posnet_prepare_payment_data(self, transaction, card_data, return_url):
        """YKB PosNet için ödeme verisi hazırlar"""
        self.ensure_one()
        order_id = f"{transaction.reference}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        data = {
            'posnetID': self.api_client_id,
            'mid': self.api_merchant_id,
            'tranType': 'Sale',
            'amount': str(int(transaction.amount * 100)),
            'currencyCode': self._get_currency_code(transaction.currency_id),
            'installment': str(card_data.get('installment_count', 0)),
            'orderID': order_id[:24],  # PosNet max 24 karakter
            'lang': 'tr',
            'url': return_url,
            'cardNumber': card_data.get('card_number', ''),
            'expDate': f"{card_data.get('expiry_month', '')}{card_data.get('expiry_year', '')}",
            'cvc': card_data.get('cvv', ''),
        }
        
        return data, order_id

    # ---- PayFor (Finansbank) ----
    def _payfor_prepare_payment_data(self, transaction, card_data, return_url):
        """PayFor için ödeme verisi hazırlar"""
        self.ensure_one()
        order_id = f"{transaction.reference}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        data = {
            'MbrId': self.api_merchant_id,
            'MerchantId': self.api_client_id,
            'UserCode': self.api_username,
            'UserPass': self.api_password,
            'SecureType': '3DModel' if self.use_3d_secure else 'NonSecure',
            'TxnType': 'Auth',
            'PurchAmount': str(transaction.amount),
            'Currency': self._get_currency_code(transaction.currency_id),
            'InstallmentCount': str(card_data.get('installment_count', 0)),
            'OrderId': order_id,
            'OkUrl': return_url,
            'FailUrl': return_url,
            'CardNumber': card_data.get('card_number', ''),
            'ExpMonth': card_data.get('expiry_month', ''),
            'ExpYear': card_data.get('expiry_year', ''),
            'Cvv2': card_data.get('cvv', ''),
            'Rnd': datetime.now().strftime('%Y%m%d%H%M%S'),
        }
        
        # Hash oluştur
        hash_str = f"{data['MbrId']}{data['OrderId']}{data['PurchAmount']}{data['OkUrl']}{data['FailUrl']}{data['TxnType']}{data['InstallmentCount']}{data['Rnd']}{self.api_store_key}"
        data['Hash'] = self._generate_hash(hash_str, self.hash_algorithm)
        
        return data, order_id

    # ---- İnterPos (Denizbank) ----
    def _interpos_prepare_payment_data(self, transaction, card_data, return_url):
        """İnterPos için ödeme verisi hazırlar"""
        self.ensure_one()
        order_id = f"{transaction.reference}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        data = {
            'ShopCode': self.api_client_id,
            'UserCode': self.api_username,
            'UserPass': self.api_password,
            'SecureType': '3DModel' if self.use_3d_secure else 'NonSecure',
            'TxnType': 'Auth',
            'PurchAmount': str(transaction.amount),
            'Currency': self._get_currency_code(transaction.currency_id),
            'InstallmentCount': str(card_data.get('installment_count', 0)),
            'OrderId': order_id,
            'OkUrl': return_url,
            'FailUrl': return_url,
            'Rnd': datetime.now().strftime('%Y%m%d%H%M%S'),
            'CardNumber': card_data.get('card_number', ''),
            'ExpMonth': card_data.get('expiry_month', ''),
            'ExpYear': card_data.get('expiry_year', ''),
            'Cvv2': card_data.get('cvv', ''),
        }
        
        # Hash oluştur
        hash_str = f"{data['ShopCode']}{data['OrderId']}{data['PurchAmount']}{data['OkUrl']}{data['FailUrl']}{data['TxnType']}{data['InstallmentCount']}{data['Rnd']}{self.api_store_key}"
        data['Hash'] = self._generate_hash(hash_str, self.hash_algorithm)
        
        return data, order_id

    # ---- Kuveyt Türk ----
    def _kuveyt_prepare_payment_data(self, transaction, card_data, return_url):
        """Kuveyt Türk için ödeme verisi hazırlar"""
        self.ensure_one()
        order_id = f"{transaction.reference}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        data = {
            'MerchantId': self.api_merchant_id,
            'CustomerId': self.api_client_id,
            'UserName': self.api_username,
            'TransactionType': 'Sale',
            'InstallmentCount': str(card_data.get('installment_count', 0)),
            'Amount': str(int(transaction.amount * 100)),
            'DisplayAmount': str(int(transaction.amount * 100)),
            'CurrencyCode': self._get_currency_code(transaction.currency_id),
            'MerchantOrderId': order_id,
            'TransactionSecurity': '3' if self.use_3d_secure else '1',
            'OkUrl': return_url,
            'FailUrl': return_url,
            'CardNumber': card_data.get('card_number', ''),
            'ExpiryMonth': card_data.get('expiry_month', ''),
            'ExpiryYear': card_data.get('expiry_year', ''),
            'CVV2': card_data.get('cvv', ''),
        }
        
        # Hash oluştur
        hash_str = f"{self.api_merchant_id}{self.api_client_id}{data['Amount']}{order_id}{return_url}{return_url}{self.api_password}"
        data['HashData'] = self._generate_hash(hash_str, self.hash_algorithm).upper()
        
        return data, order_id

    # ---- Akbank ----
    def _akbank_prepare_payment_data(self, transaction, card_data, return_url):
        """Akbank için ödeme verisi hazırlar"""
        self.ensure_one()
        order_id = f"{transaction.reference}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        data = {
            'merchantId': self.api_merchant_id,
            'terminalId': self.api_terminal_id,
            'userId': self.api_username,
            'transactionType': 'sale',
            'amount': str(int(transaction.amount * 100)),
            'currency': self._get_currency_code(transaction.currency_id),
            'installmentCount': str(card_data.get('installment_count', 0)),
            'orderId': order_id,
            'successUrl': return_url,
            'failureUrl': return_url,
            'cardNumber': card_data.get('card_number', ''),
            'expireMonth': card_data.get('expiry_month', ''),
            'expireYear': card_data.get('expiry_year', ''),
            'cvv': card_data.get('cvv', ''),
        }
        
        return data, order_id

    # ---- Param POS ----
    def _param_prepare_payment_data(self, transaction, card_data, return_url):
        """Param POS için ödeme verisi hazırlar"""
        self.ensure_one()
        order_id = f"{transaction.reference}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        data = {
            'CLIENT_CODE': self.api_client_id,
            'CLIENT_USERNAME': self.api_username,
            'CLIENT_PASSWORD': self.api_password,
            'GUID': self.api_merchant_id,
            'ORDER_ID': order_id,
            'ORDER_AMOUNT': str(transaction.amount),
            'INSTALLMENT_COUNT': str(card_data.get('installment_count', 0)),
            'CURRENCY': self._get_currency_code(transaction.currency_id),
            'SUCCESS_URL': return_url,
            'ERROR_URL': return_url,
            'CARD_NO': card_data.get('card_number', ''),
            'EXP_MONTH': card_data.get('expiry_month', ''),
            'EXP_YEAR': card_data.get('expiry_year', ''),
            'CVV': card_data.get('cvv', ''),
        }
        
        return data, order_id

    # ---- Tosla ----
    def _tosla_prepare_payment_data(self, transaction, card_data, return_url):
        """Tosla için ödeme verisi hazırlar"""
        self.ensure_one()
        order_id = f"{transaction.reference}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        data = {
            'apiKey': self.api_client_id,
            'secretKey': self.api_store_key,
            'orderId': order_id,
            'amount': str(int(transaction.amount * 100)),
            'currency': self._get_currency_code(transaction.currency_id),
            'installment': str(card_data.get('installment_count', 0)),
            'successUrl': return_url,
            'failUrl': return_url,
            'cardNumber': card_data.get('card_number', ''),
            'expiryMonth': card_data.get('expiry_month', ''),
            'expiryYear': card_data.get('expiry_year', ''),
            'cvv': card_data.get('cvv', ''),
        }
        
        return data, order_id

    # ---- Vakıf Katılım ----
    def _vakifkatilim_prepare_payment_data(self, transaction, card_data, return_url):
        """Vakıf Katılım için ödeme verisi hazırlar"""
        self.ensure_one()
        order_id = f"{transaction.reference}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        data = {
            'MerchantId': self.api_merchant_id,
            'TerminalId': self.api_terminal_id,
            'UserName': self.api_username,
            'UserPassword': self.api_password,
            'OrderId': order_id,
            'Amount': str(int(transaction.amount * 100)),
            'CurrencyCode': self._get_currency_code(transaction.currency_id),
            'InstallmentCount': str(card_data.get('installment_count', 0)),
            'SuccessUrl': return_url,
            'FailUrl': return_url,
            'Pan': card_data.get('card_number', ''),
            'ExpiryDate': f"{card_data.get('expiry_year', '')}{card_data.get('expiry_month', '')}",
            'Cvv2': card_data.get('cvv', ''),
        }
        
        return data, order_id

    # ---- PayFlex ----
    def _payflex_prepare_payment_data(self, transaction, card_data, return_url):
        """PayFlex için ödeme verisi hazırlar"""
        self.ensure_one()
        order_id = f"{transaction.reference}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        data = {
            'MerchantId': self.api_merchant_id,
            'Password': self.api_password,
            'TerminalNo': self.api_terminal_id,
            'TransactionType': 'Sale',
            'OrderId': order_id,
            'CurrencyCode': self._get_currency_code(transaction.currency_id),
            'TransactionAmount': str(int(transaction.amount * 100)),
            'InstallmentCount': str(card_data.get('installment_count', 0)),
            'SuccessUrl': return_url,
            'FailUrl': return_url,
            'CardNumber': card_data.get('card_number', ''),
            'ExpirationMonth': card_data.get('expiry_month', ''),
            'ExpirationYear': card_data.get('expiry_year', ''),
            'CVV2': card_data.get('cvv', ''),
        }
        
        return data, order_id

    # ==================== GENEL ÖDEME METODU ====================
    
    def prepare_payment_data(self, transaction, card_data, return_url):
        """Gateway tipine göre ödeme verisi hazırlar"""
        self.ensure_one()
        
        method_map = {
            'est': self._est_prepare_payment_data,
            'est_v3': self._est_prepare_payment_data,
            'garanti': self._garanti_prepare_payment_data,
            'posnet': self._posnet_prepare_payment_data,
            'posnet_v1': self._posnet_prepare_payment_data,
            'payfor': self._payfor_prepare_payment_data,
            'interpos': self._interpos_prepare_payment_data,
            'kuveyt': self._kuveyt_prepare_payment_data,
            'akbank': self._akbank_prepare_payment_data,
            'param': self._param_prepare_payment_data,
            'tosla': self._tosla_prepare_payment_data,
            'vakifkatilim': self._vakifkatilim_prepare_payment_data,
            'payflex': self._payflex_prepare_payment_data,
            'payflex_cp': self._payflex_prepare_payment_data,
        }
        
        method = method_map.get(self.gateway_type)
        if not method:
            raise UserError(_('Desteklenmeyen gateway tipi: %s') % self.gateway_type)
        
        return method(transaction, card_data, return_url)

    # ==================== İADE METOTLARI ====================
    
    def process_refund(self, transaction, amount=None):
        """İade işlemi yapar"""
        self.ensure_one()
        
        if not self.allow_refund:
            raise UserError(_('Bu sağlayıcı için iade işlemi desteklenmiyor.'))
        
        if not amount:
            amount = transaction.amount
        
        # İade süre kontrolü
        if transaction.payment_date:
            days_diff = (fields.Date.today() - transaction.payment_date).days
            if days_diff > self.refund_time_limit_days:
                raise UserError(_('İade süresi dolmuş. Maksimum %s gün içinde iade yapılabilir.') % self.refund_time_limit_days)
        
        # Gateway'e göre iade işlemi
        refund_method = getattr(self, f'_{self.gateway_type}_refund', None)
        if refund_method:
            return refund_method(transaction, amount)
        
        raise UserError(_('Bu gateway için iade metodu henüz implement edilmemiş.'))

    # ---- Helper: XML Gönder ----
    def _send_xml_request(self, xml_data, headers=None):
        if not headers:
            headers = {'Content-Type': 'application/xml'}
        try:
            response = requests.post(
                self._get_api_url(),
                data=xml_data,
                headers=headers,
                timeout=self.timeout_seconds
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            _logger.error('XML Request Error: %s', e)
            return f'<Response><Error>{str(e)}</Error></Response>'

    # ---- EST İade ----
    def _est_refund(self, transaction, amount):
        """EST POS için iade"""
        root = etree.Element("CC5Request")
        etree.SubElement(root, "Name").text = self.api_username or ''
        etree.SubElement(root, "Password").text = self.api_password or ''
        etree.SubElement(root, "ClientId").text = self.api_client_id or ''
        etree.SubElement(root, "Type").text = "Credit"
        etree.SubElement(root, "OrderId").text = transaction.pos_order_id or ''
        etree.SubElement(root, "Total").text = str(amount)
        etree.SubElement(root, "Currency").text = self._get_currency_code(transaction.currency_id)
        
        xml_data = etree.tostring(root, encoding='ISO-8859-9', xml_declaration=True)
        response_text = self._send_xml_request(xml_data)
        return self._parse_est_response(response_text)

    # ---- Garanti İade ----
    def _garanti_refund(self, transaction, amount):
        """Garanti POS için iade"""
        terminal_id = self.api_terminal_id.zfill(9)
        provision_password = self.api_provision_user
        security_data = self._generate_hash(provision_password + terminal_id, 'sha256').upper()
        
        hash_data = f"{self.api_terminal_id}{transaction.pos_order_id}{str(int(amount * 100))}{security_data}"
        hash_value = self._generate_hash(hash_data, 'sha256').upper()
        
        root = etree.Element("GVPSRequest")
        etree.SubElement(root, "Mode").text = 'PROD' if self.environment == 'production' else 'TEST'
        etree.SubElement(root, "Version").text = "0.01"
        
        terminal = etree.SubElement(root, "Terminal")
        etree.SubElement(terminal, "ProvUserID").text = self.api_provision_user or ''
        etree.SubElement(terminal, "HashData").text = hash_value
        etree.SubElement(terminal, "UserID").text = self.api_username or ''
        etree.SubElement(terminal, "ID").text = self.api_terminal_id or ''
        etree.SubElement(terminal, "MerchantID").text = self.api_merchant_id or ''
        
        customer = etree.SubElement(root, "Customer")
        etree.SubElement(customer, "IPAddress").text = transaction.partner_ip_address or '127.0.0.1'
        etree.SubElement(customer, "EmailAddress").text = transaction.partner_email or ''
        
        order = etree.SubElement(root, "Order")
        etree.SubElement(order, "OrderID").text = transaction.pos_order_id or ''
        
        trans = etree.SubElement(root, "Transaction")
        etree.SubElement(trans, "Type").text = "refund"
        etree.SubElement(trans, "Amount").text = str(int(amount * 100))
        etree.SubElement(trans, "CurrencyCode").text = self._get_currency_code(transaction.currency_id)
        
        xml_data = etree.tostring(root, encoding='UTF-8', xml_declaration=True)
        response_text = self._send_xml_request(xml_data)
        return self._parse_garanti_response(response_text)

    # ==================== İPTAL METOTLARI ====================
    
    def process_cancel(self, transaction):
        """İptal işlemi yapar"""
        self.ensure_one()
        
        if not self.allow_cancel:
            raise UserError(_('Bu sağlayıcı için iptal işlemi desteklenmiyor.'))
        
        cancel_method = getattr(self, f'_{self.gateway_type}_cancel', None)
        if cancel_method:
            return cancel_method(transaction)
        
        raise UserError(_('Bu gateway için iptal metodu henüz implement edilmemiş.'))

    # ---- EST İptal ----
    def _est_cancel(self, transaction):
        """EST POS için iptal"""
        root = etree.Element("CC5Request")
        etree.SubElement(root, "Name").text = self.api_username or ''
        etree.SubElement(root, "Password").text = self.api_password or ''
        etree.SubElement(root, "ClientId").text = self.api_client_id or ''
        etree.SubElement(root, "Type").text = "Void"
        etree.SubElement(root, "OrderId").text = transaction.pos_order_id or ''
        
        xml_data = etree.tostring(root, encoding='ISO-8859-9', xml_declaration=True)
        response_text = self._send_xml_request(xml_data)
        return self._parse_est_response(response_text)

    # ==================== DURUM SORGULAMA ====================
    
    def query_status(self, transaction):
        """İşlem durumunu sorgular"""
        self.ensure_one()
        
        query_method = getattr(self, f'_{self.gateway_type}_query', None)
        if query_method:
            return query_method(transaction)
        
        raise UserError(_('Bu gateway için durum sorgulama metodu henüz implement edilmemiş.'))

    # ---- EST Durum Sorgulama ----
    def _est_query(self, transaction):
        """EST POS için durum sorgulama"""
        root = etree.Element("CC5Request")
        etree.SubElement(root, "Name").text = self.api_username or ''
        etree.SubElement(root, "Password").text = self.api_password or ''
        etree.SubElement(root, "ClientId").text = self.api_client_id or ''
        etree.SubElement(root, "Type").text = "OrderInq"
        etree.SubElement(root, "OrderId").text = transaction.pos_order_id or ''
        
        xml_data = etree.tostring(root, encoding='ISO-8859-9', xml_declaration=True)
        response_text = self._send_xml_request(xml_data)
        return self._parse_est_response(response_text)

    # ==================== YANIT AYRİŞTIRMA ====================
    
    def _parse_est_response(self, response_text):
        """EST yanıtını ayrıştırır"""
        try:
            root = ET.fromstring(response_text)
            result = {
                'success': False,
                'message': '',
                'code': '',
                'transaction_id': '',
            }
            
            for elem in root:
                if elem.tag == 'ProcReturnCode':
                    result['success'] = elem.text == '00'
                elif elem.tag == 'ErrMsg':
                    result['message'] = elem.text or ''
                elif elem.tag == 'TransId':
                    result['transaction_id'] = elem.text or ''
                elif elem.tag == 'Response':
                    result['code'] = elem.text or ''
            
            return result
        except Exception as e:
            _logger.error('EST response parsing error: %s', e)
            return {'success': False, 'message': str(e), 'code': 'PARSING_ERROR'}

    def _parse_garanti_response(self, response_text):
        """Garanti yanıtını ayrıştırır"""
        try:
            root = ET.fromstring(response_text)
            result = {
                'success': False,
                'message': '',
                'code': '',
                'transaction_id': '',
            }
            
            transaction = root.find('.//Transaction')
            if transaction is not None:
                response_elem = transaction.find('Response')
                if response_elem is not None:
                    result['code'] = response_elem.findtext('Code', '')
                    result['message'] = response_elem.findtext('Message', '')
                    result['success'] = result['code'] == '00'
                
                result['transaction_id'] = transaction.findtext('RetrefNum', '')
            
            return result
        except Exception as e:
            _logger.error('Garanti response parsing error: %s', e)
            return {'success': False, 'message': str(e), 'code': 'PARSING_ERROR'}

    # ==================== 3D DÖNÜŞ İŞLEME ====================
    
    def process_3d_return(self, post_data):
        """3D Secure dönüşünü işler"""
        self.ensure_one()
        
        process_method = getattr(self, f'_{self.gateway_type}_process_3d_return', None)
        if process_method:
            return process_method(post_data)
        
        raise UserError(_('Bu gateway için 3D dönüş işleme metodu henüz implement edilmemiş.'))

    # ---- EST 3D Dönüş ----
    def _est_process_3d_return(self, post_data):
        """EST 3D dönüşünü işler"""
        result = {
            'success': post_data.get('mdStatus') == '1',
            'message': post_data.get('mdErrorMsg', ''),
            'transaction_id': post_data.get('transId', ''),
            'auth_code': post_data.get('AuthCode', ''),
            'order_id': post_data.get('oid', ''),
        }
        
        # Hash doğrulama
        if result['success']:
            hash_params = post_data.get('HASHPARAMS', '')
            hash_params_val = post_data.get('HASHPARAMSVAL', '')
            hash = post_data.get('HASH', '')
            
            calculated_hash = self._generate_hash(hash_params_val + self.api_store_key, self.hash_algorithm)
            
            if calculated_hash.upper() != hash.upper():
                result['success'] = False
                result['message'] = _('Hash doğrulama başarısız.')
        
        return result

    # ---- Garanti 3D Dönüş ----
    def _garanti_process_3d_return(self, post_data):
        """Garanti 3D dönüşünü işler"""
        result = {
            'success': post_data.get('mdStatus') in ['1', '2', '3', '4'],
            'message': post_data.get('mdErrorMsg', ''),
            'transaction_id': post_data.get('transId', ''),
            'auth_code': post_data.get('authCode', ''),
            'order_id': post_data.get('orderId', ''),
        }
        
        # Hash doğrulama
        if result['success']:
            hash_params = f"{post_data.get('clientid', '')}{post_data.get('oid', '')}{post_data.get('authCode', '')}{post_data.get('procReturnCode', '')}{post_data.get('mdStatus', '')}"
            calculated_hash = self._generate_hash(hash_params + self.api_store_key, 'sha256').upper()
            
            if calculated_hash != post_data.get('HASH', ''):
                result['success'] = False
                result['message'] = _('Hash doğrulama başarısız.')
        
        return result
