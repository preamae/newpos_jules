# -*- coding: utf-8 -*-

import logging
import requests
from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class TurkeyPosPaymentController(http.Controller):
    """Ödeme işlemleri controller'ı"""

    @http.route('/payment/turkey_pos/process', type='http', auth='public', website=True, csrf=True)
    def process_payment(self, **post):
        """Ödeme işlemini başlatır"""
        _logger.info('Processing payment with data: %s', post)
        
        try:
            # Gerekli alanları kontrol et
            required_fields = ['provider_id', 'amount', 'reference', 'card_number', 
                              'expiry_month', 'expiry_year', 'cvv']
            for field in required_fields:
                if not post.get(field):
                    return request.render('turkey_pos_payment.payment_error', {
                        'error_message': _('Missing required field: %s') % field
                    })
            
            provider_id = int(post.get('provider_id'))
            provider = request.env['payment.provider'].sudo().browse(provider_id)
            
            if not provider.exists():
                return request.render('turkey_pos_payment.payment_error', {
                    'error_message': _('Payment provider not found')
                })
            
            # İşlem oluştur
            transaction_vals = {
                'provider_id': provider.id,
                'reference': post.get('reference'),
                'amount': float(post.get('amount')),
                'currency_id': request.env.company.currency_id.id,
                'partner_id': request.env.user.partner_id.id if request.env.user else None,
                'partner_email': post.get('email'),
                'partner_ip_address': request.httprequest.remote_addr,
                'installment_count': int(post.get('installment_count', 1)),
            }
            
            transaction = request.env['payment.transaction'].sudo().create(transaction_vals)
            
            # Kart verilerini hazırla
            card_data = {
                'card_number': post.get('card_number').replace(' ', '').replace('-', ''),
                'expiry_month': post.get('expiry_month'),
                'expiry_year': post.get('expiry_year'),
                'cvv': post.get('cvv'),
                'installment_count': int(post.get('installment_count', 1)),
            }
            
            # Dönüş URL'sini oluştur
            return_url = request.httprequest.host_url.rstrip('/') + '/payment/turkey_pos/3d_return/' + str(provider.id)
            
            # Ödeme verisini hazırla
            payment_data, order_id = provider.prepare_payment_data(transaction, card_data, return_url)
            transaction.pos_order_id = order_id
            
            # 3D Secure kullanılacaksa
            if provider.use_3d_secure:
                # 3D formunu render et
                return request.render('turkey_pos_payment.redirect_3d_form', {
                    'action_url': provider._get_api_url('3d'),
                    'data': payment_data,
                })
            else:
                # Non-secure ödeme
                # API isteği gönder
                response = requests.post(
                    provider._get_api_url(),
                    data=payment_data,
                    timeout=provider.timeout_seconds
                )
                
                # Yanıtı işle
                result = provider._parse_est_response(response.text) if 'est' in provider.gateway_type else provider._parse_garanti_response(response.text)
                result['processed'] = True
                
                if result.get('success'):
                    transaction._process_notification_data(result)
                    return request.redirect('/payment/confirmation')
                else:
                    return request.render('turkey_pos_payment.payment_error', {
                        'error_message': result.get('message', _('Payment failed'))
                    })
            
        except Exception as e:
            _logger.exception('Payment processing error: %s', e)
            return request.render('turkey_pos_payment.payment_error', {
                'error_message': str(e)
            })

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
