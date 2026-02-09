# -*- coding: utf-8 -*-

import logging
import json
from datetime import datetime

from odoo import http, _, fields
from odoo.http import request
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class TurkeyPosController(http.Controller):
    """Türkiye Sanal POS Controller"""

    # ==================== 3D SECURE DÖNÜŞ URL'LERİ ====================

    @http.route('/payment/turkey_pos/3d_return/<int:provider_id>', 
                type='http', auth='public', csrf=False, methods=['POST', 'GET'])
    def turkey_pos_3d_return(self, provider_id, **post):
        """3D Secure dönüşünü işler"""
        _logger.info('3D Return received for provider ID: %s, data: %s', provider_id, post)
        
        try:
            # Sağlayıcıyı bul
            provider = request.env['payment.provider'].sudo().browse(provider_id)
            
            if not provider or not provider.exists():
                _logger.error('Provider not found: %s', provider_id)
                return request.redirect('/payment/error')
            
            # İşlem referansını bul
            order_id = post.get('oid') or post.get('orderId') or post.get('OrderId') or post.get('MERCHANT_ORDER_ID') or post.get('posnet_order_id')
            if not order_id:
                _logger.error('Order ID not found in 3D return data')
                return request.redirect('/payment/error')
            
            # İşlemi bul
            transaction = request.env['payment.transaction'].sudo().search([
                ('pos_order_id', 'like', order_id.split('_')[0] if '_' in order_id else order_id)
            ], limit=1)
            
            if not transaction:
                _logger.error('Transaction not found for order: %s', order_id)
                return request.redirect('/payment/error')
            
            # 3D dönüşünü işle ve sonucu al
            result = transaction._process_notification_data(post)
            
            if result and result.get('success'):
                return request.redirect('/payment/confirmation')
            else:
                return request.redirect('/payment/error')
                
        except Exception as e:
            _logger.exception('Error processing 3D return: %s', e)
            return request.redirect('/payment/error')

    # ==================== ÖDEME İŞLEMLERİ ====================

    @http.route('/payment/turkey_pos/payment', type='http', auth='public', website=True, csrf=True)
    def turkey_pos_payment_page(self, **kwargs):
        """Ödeme sayfasını gösterir"""
        sale_order_id = kwargs.get('order_id')
        amount = kwargs.get('amount')
        reference = kwargs.get('reference')
        
        if not all([sale_order_id, amount, reference]):
            return request.redirect('/shop/cart')
        
        sale_order = request.env['sale.order'].sudo().browse(int(sale_order_id))
        if not sale_order.exists():
            return request.redirect('/shop/cart')
        
        # Aktif sağlayıcıları al
        providers = request.env['payment.provider'].sudo().search([
            ('state', 'in', ['enabled', 'test']),
            ('code', 'in', ['akbank', 'garanti', 'isbank', 'ziraat', 'halkbank',
                           'vakifbank', 'vakifkatilim', 'yapikredi', 'finansbank',
                           'denizbank', 'teb', 'sekerbank', 'kuveytturk', 'param', 'tosla'])
        ])
        
        # Kategori bazlı taksit seçeneklerini al
        installment_options = sale_order.get_category_based_installments()
        
        values = {
            'sale_order': sale_order,
            'amount': float(amount),
            'reference': reference,
            'providers': providers,
            'installment_options': installment_options,
            'default_installment': 1,
        }
        
        return request.render('turkey_pos_payment.payment_page', values)

    # ==================== ÜRÜN TAKSİT ENDPOINT'LERİ ====================

    @http.route('/payment/turkey_pos/get_product_installments', type='json', auth='public', csrf=True)
    def get_product_installments(self, bank_code, amount, product_id=None, **kwargs):
        """Ürün için banka bazlı taksit seçeneklerini döndürür"""
        try:
            # Banka sağlayıcısını bul
            provider = request.env['payment.provider'].sudo().search([
                ('code', '=', bank_code),
                ('state', 'in', ['enabled', 'test'])
            ], limit=1)
            
            if not provider:
                return {'success': False, 'message': 'Banka bulunamadı'}
            
            # Taksit seçeneklerini al
            options = request.env['installment.option'].sudo().search([
                ('provider_id', '=', provider.id),
                ('is_active', '=', True),
                ('min_amount', '<=', amount),
                ('max_amount', '>=', amount),
            ])
            
            installments = []
            for opt in options:
                calc = opt.calculate_installment_amount(amount)
                installments.append({
                    'count': opt.installment_count,
                    'monthly_amount': calc['installment_amount'],
                    'total_amount': calc['total_amount'],
                    'commission_rate': opt.commission_rate,
                    'commission_amount': calc['commission_amount'],
                })
            
            return {
                'success': True,
                'bank': provider.name,
                'installments': installments
            }
            
        except Exception as e:
            _logger.error('Product installments error: %s', e)
            return {'success': False, 'message': str(e)}

    @http.route('/payment/turkey_pos/get_default_installments', type='json', auth='public', csrf=True)
    def get_default_installments(self, amount, **kwargs):
        """Varsayılan banka için taksit seçeneklerini döndürür"""
        try:
            # Varsayılan sağlayıcıyı al
            provider_id = request.env['ir.config_parameter'].sudo().get_param(
                'turkey_pos_payment.default_pos_provider'
            )
            
            if provider_id:
                provider = request.env['payment.provider'].sudo().browse(int(provider_id))
            else:
                # İlk aktif sağlayıcıyı al
                provider = request.env['payment.provider'].sudo().search([
                    ('state', 'in', ['enabled', 'test']),
                    ('code', 'in', ['akbank', 'garanti', 'isbank', 'ziraat', 'halkbank',
                                   'vakifbank', 'vakifkatilim', 'yapikredi', 'finansbank',
                                   'denizbank', 'teb', 'sekerbank', 'kuveytturk', 'param', 'tosla'])
                ], limit=1)
            
            if not provider:
                return {'success': False, 'message': 'Varsayılan banka bulunamadı'}
            
            # Taksit seçeneklerini al
            options = request.env['installment.option'].sudo().search([
                ('provider_id', '=', provider.id),
                ('is_active', '=', True),
                ('min_amount', '<=', amount),
                ('max_amount', '>=', amount),
            ])
            
            installments = []
            for opt in options:
                calc = opt.calculate_installment_amount(amount)
                installments.append({
                    'count': opt.installment_count,
                    'monthly_amount': calc['installment_amount'],
                    'total_amount': calc['total_amount'],
                    'commission_rate': opt.commission_rate,
                    'commission_amount': calc['commission_amount'],
                })
            
            return {
                'success': True,
                'bank': provider.name,
                'installments': installments
            }
            
        except Exception as e:
            _logger.error('Default installments error: %s', e)
            return {'success': False, 'message': str(e)}

    @http.route('/payment/turkey_pos/get_default_provider', type='json', auth='public', csrf=True)
    def get_default_provider(self, **kwargs):
        """Varsayılan POS sağlayıcısını döndürür"""
        try:
            provider_id = request.env['ir.config_parameter'].sudo().get_param(
                'turkey_pos_payment.default_pos_provider'
            )
            
            if provider_id:
                return {'provider_id': int(provider_id)}
            
            # İlk aktif sağlayıcıyı bul
            provider = request.env['payment.provider'].sudo().search([
                ('state', 'in', ['enabled', 'test']),
                ('code', 'in', ['akbank', 'garanti', 'isbank', 'ziraat', 'halkbank',
                               'vakifbank', 'vakifkatilim', 'yapikredi', 'finansbank',
                               'denizbank', 'teb', 'sekerbank', 'kuveytturk', 'param', 'tosla'])
            ], limit=1)
            
            if provider:
                return {'provider_id': provider.id}
            
            return {'provider_id': None}
            
        except Exception as e:
            _logger.error('Get default provider error: %s', e)
            return {'provider_id': None}

    # ==================== TAKSİT HESAPLAMA ====================

    @http.route('/payment/turkey_pos/calculate_installment', type='json', auth='public', csrf=True)
    def calculate_installment(self, amount, installment_count, provider_id, **kwargs):
        """Taksit tutarını hesaplar"""
        try:
            provider = request.env['payment.provider'].sudo().browse(int(provider_id))
            if not provider.exists():
                return {'error': _('Provider not found')}
            
            # Taksit seçeneğini bul
            installment_option = request.env['installment.option'].sudo().search([
                ('provider_id', '=', provider.id),
                ('installment_count', '=', int(installment_count)),
                ('is_active', '=', True),
            ], limit=1)
            
            if not installment_option:
                # Varsayılan hesaplama
                return {
                    'installment_count': int(installment_count),
                    'installment_amount': round(float(amount) / int(installment_count), 2),
                    'total_amount': float(amount),
                    'commission_amount': 0.0,
                }
            
            result = installment_option.calculate_installment_amount(float(amount))
            return {
                'installment_count': installment_option.installment_count,
                'installment_amount': result['installment_amount'],
                'total_amount': result['total_amount'],
                'commission_amount': result['commission_amount'],
            }
            
        except Exception as e:
            _logger.error('Installment calculation error: %s', e)
            return {'error': str(e)}

    @http.route('/payment/turkey_pos/installment_options', type='json', auth='public', csrf=True)
    def get_installment_options(self, amount, provider_id=None, **kwargs):
        """Taksit seçeneklerini döndürür"""
        try:
            amount = float(amount)
            
            domain = [
                ('is_active', '=', True),
                ('min_amount', '<=', amount),
                ('max_amount', '>=', amount),
            ]
            
            if provider_id:
                domain.append(('provider_id', '=', int(provider_id)))
            
            options = request.env['installment.option'].sudo().search(domain)
            
            result = []
            for opt in options:
                calc = opt.calculate_installment_amount(amount)
                result.append({
                    'id': opt.id,
                    'installment_count': opt.installment_count,
                    'provider_name': opt.provider_id.name,
                    'monthly_amount': calc['installment_amount'],
                    'total_amount': calc['total_amount'],
                    'commission_amount': calc['commission_amount'],
                    'commission_rate': opt.commission_rate,
                })
            
            return {'success': True, 'options': result}
            
        except Exception as e:
            _logger.error('Get installment options error: %s', e)
            return {'success': False, 'error': str(e)}

    @http.route('/payment/turkey_pos/category_installments', type='json', auth='public', csrf=True)
    def get_category_installments(self, order_id, **kwargs):
        """Sipariş için kategori bazlı taksit seçeneklerini döndürür"""
        try:
            sale_order = request.env['sale.order'].sudo().browse(int(order_id))
            if not sale_order.exists():
                return {'success': False, 'error': _('Order not found')}
            
            installments = sale_order.get_category_based_installments()
            
            return {'success': True, 'installments': installments}
            
        except Exception as e:
            _logger.error('Get category installments error: %s', e)
            return {'success': False, 'error': str(e)}

    # ==================== KART BİLGİSİ DOĞRULAMA ====================

    @http.route('/payment/turkey_pos/validate_card', type='json', auth='public', csrf=True)
    def validate_card(self, card_number, **kwargs):
        """Kart bilgisini doğrular ve markasını tespit eder"""
        try:
            # Luhn algoritması ile doğrulama
            def luhn_check(card_num):
                digits = [int(d) for d in str(card_num) if d.isdigit()]
                odd_digits = digits[-1::-2]
                even_digits = digits[-2::-2]
                checksum = sum(odd_digits)
                for d in even_digits:
                    checksum += sum(divmod(d * 2, 10))
                return checksum % 10 == 0

            is_valid = luhn_check(card_number)
            
            # Kart markasını tespit et
            card_brand = self._detect_card_brand(card_number)
            
            # Bankayı tespit et
            bank = self._detect_bank_from_card(card_number)
            
            return {
                'valid': is_valid,
                'brand': card_brand,
                'bank': bank,
                'masked': self._mask_card_number(card_number),
            }
            
        except Exception as e:
            _logger.error('Card validation error: %s', e)
            return {'error': str(e)}

    def _detect_card_brand(self, card_number):
        """Kart markasını tespit eder"""
        card_number = str(card_number).replace(' ', '').replace('-', '')
        
        # Visa
        if card_number.startswith('4'):
            return 'visa'
        # Mastercard
        elif card_number[:2] in ['51', '52', '53', '54', '55'] or \
             (222100 <= int(card_number[:6]) <= 272099):
            return 'mastercard'
        # American Express
        elif card_number[:2] in ['34', '37']:
            return 'amex'
        # Troy
        elif card_number[:4] in ['9792', '9793'] or card_number[:6] in ['65']:
            return 'troy'
        # Discover
        elif card_number[:4] == '6011' or card_number[:2] == '65':
            return 'discover'
        # JCB
        elif 3528 <= int(card_number[:4]) <= 3589:
            return 'jcb'
        
        return 'unknown'

    def _detect_bank_from_card(self, card_number):
        """Kart numarasından banka tespiti"""
        card_bin_ranges = {
            'akbank': ['454671', '454672', '413252', '520932'],
            'garanti': ['514915', '540036', '540037', '541865'],
            'isbank': ['450803', '540667', '540668', '541078'],
            'ziraat': ['454671', '540130', '541865'],
            'halkbank': ['522241', '540435', '543081'],
            'vakifbank': ['411724', '411726', '425669'],
            'yapikredi': ['545103', '545616', '547564'],
            'finansbank': ['525312', '540963', '542404'],
            'denizbank': ['552096', '554567', '676366'],
            'teb': ['450918', '540638', '543738'],
            'sekerbank': ['402275', '402276', '403814'],
            'kuveytturk': ['402589', '402590', '410555'],
        }
        
        bin_num = card_number.replace(' ', '').replace('-', '')[:6]
        
        for bank, bins in card_bin_ranges.items():
            if bin_num in bins:
                return bank
        return None

    def _mask_card_number(self, card_number):
        """Kart numarasını maskele"""
        card_number = str(card_number).replace(' ', '').replace('-', '')
        if len(card_number) >= 4:
            return '*' * (len(card_number) - 4) + card_number[-4:]
        return card_number

    # ==================== İŞLEM SORGULAMA ====================

    @http.route('/payment/turkey_pos/query_transaction', type='json', auth='user', csrf=True)
    def query_transaction(self, transaction_id, **kwargs):
        """İşlem durumunu sorgular"""
        try:
            transaction = request.env['payment.transaction'].browse(int(transaction_id))
            if not transaction.exists():
                return {'error': _('Transaction not found')}
            
            # Yetki kontrolü
            if transaction.partner_id != request.env.user.partner_id and \
               not request.env.user.has_group('base.group_system'):
                return {'error': _('Access denied')}
            
            result = transaction.provider_id.query_status(transaction)
            return result
            
        except Exception as e:
            _logger.error('Transaction query error: %s', e)
            return {'error': str(e)}

    # ==================== WEBHOOK ====================

    @http.route('/payment/turkey_pos/webhook/<string:provider_code>', 
                type='json', auth='public', csrf=False, methods=['POST'])
    def turkey_pos_webhook(self, provider_code, **kwargs):
        """Webhook bildirimlerini işler"""
        _logger.info('Webhook received for provider: %s', provider_code)
        
        try:
            # Sağlayıcıyı bul
            provider = request.env['payment.provider'].sudo().search([
                ('code', '=', provider_code)
            ], limit=1)
            
            if not provider:
                return {'status': 'error', 'message': 'Provider not found'}
            
            # Webhook verilerini işle
            data = request.jsonrequest
            _logger.info('Webhook data: %s', data)
            
            # İşlemi güncelle
            # ... webhook işleme mantığı ...
            
            return {'status': 'success'}
            
        except Exception as e:
            _logger.exception('Webhook error: %s', e)
            return {'status': 'error', 'message': str(e)}

    # ==================== API ENDPOINTLERİ ====================

    @http.route('/api/v1/pos/providers', type='json', auth='public', methods=['GET'])
    def api_get_providers(self, **kwargs):
        """Aktif sağlayıcıları döndürür"""
        providers = request.env['payment.provider'].sudo().search([
            ('state', 'in', ['enabled', 'test']),
            ('code', 'in', ['akbank', 'garanti', 'isbank', 'ziraat', 'halkbank',
                           'vakifbank', 'vakifkatilim', 'yapikredi', 'finansbank',
                           'denizbank', 'teb', 'sekerbank', 'kuveytturk', 'param', 'tosla'])
        ])
        
        return {
            'providers': [{
                'id': p.id,
                'name': p.name,
                'code': p.code,
                'gateway_type': p.gateway_type,
                'support_3d_secure': p.use_3d_secure,
                'support_installments': p.enable_installments,
            } for p in providers]
        }

    @http.route('/api/v1/pos/installments', type='json', auth='public', methods=['POST'])
    def api_get_installments(self, amount, provider_id=None, category_id=None, **kwargs):
        """Taksit seçeneklerini döndürür"""
        try:
            domain = [('is_active', '=', True)]
            if provider_id:
                domain.append(('provider_id', '=', int(provider_id)))
            
            options = request.env['installment.option'].sudo().search(domain)
            
            result = []
            for opt in options:
                calc = opt.calculate_installment_amount(float(amount))
                result.append({
                    'id': opt.id,
                    'provider_id': opt.provider_id.id,
                    'provider_name': opt.provider_id.name,
                    'installment_count': opt.installment_count,
                    'commission_rate': opt.commission_rate,
                    'monthly_amount': calc['installment_amount'],
                    'total_amount': calc['total_amount'],
                })
            
            return {'installments': result}
            
        except Exception as e:
            _logger.error('API installments error: %s', e)
            return {'error': str(e)}

    @http.route('/api/v1/pos/transaction/status', type='json', auth='user', methods=['POST'])
    def api_get_transaction_status(self, reference, **kwargs):
        """İşlem durumunu döndürür"""
        transaction = request.env['payment.transaction'].search([
            ('reference', '=', reference)
        ], limit=1)
        
        if not transaction:
            return {'error': _('Transaction not found')}
        
        return {
            'reference': transaction.reference,
            'state': transaction.state,
            'pos_state': transaction.pos_state,
            'amount': transaction.amount,
            'installment_count': transaction.installment_count,
            'is_3d_secure': transaction.is_3d_secure,
            'payment_date': transaction.payment_date.isoformat() if transaction.payment_date else None,
        }
