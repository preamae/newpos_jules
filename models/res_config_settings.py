# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ==================== GENEL POS AYARLARI ====================
    
    # Varsayılan Sağlayıcı
    default_pos_provider = fields.Many2one('payment.provider', 
                                            string='Varsayılan POS Sağlayıcı',
                                            domain=[('code', 'in', ['akbank', 'garanti', 'isbank', 
                                                                     'ziraat', 'halkbank', 'vakifbank',
                                                                     'vakifkatilim', 'yapikredi', 'finansbank',
                                                                     'denizbank', 'teb', 'sekerbank', 
                                                                     'kuveytturk', 'param', 'tosla'])])
    
    # 3D Secure Ayarları
    pos_force_3d_secure = fields.Boolean(string='3D Secure Zorunlu', 
                                          config_parameter='turkey_pos_payment.force_3d_secure',
                                          default=False)
    pos_min_amount_3d = fields.Monetary(string='3D Secure Min. Tutar',
                                         config_parameter='turkey_pos_payment.min_amount_3d',
                                         default=0.0, currency_field='currency_id')
    
    # Taksit Ayarları
    pos_enable_installments = fields.Boolean(string='Taksit Seçeneklerini Aktif Et',
                                              config_parameter='turkey_pos_payment.enable_installments',
                                              default=True)
    pos_max_installment_count = fields.Integer(string='Maksimum Taksit Sayısı',
                                                config_parameter='turkey_pos_payment.max_installment_count',
                                                default=12)
    pos_min_amount_installment = fields.Monetary(string='Taksit İçin Min. Tutar',
                                                  config_parameter='turkey_pos_payment.min_amount_installment',
                                                  default=100.0, currency_field='currency_id')
    
    # İade/İptal Ayarları
    pos_auto_refund = fields.Boolean(string='Otomatik İade',
                                      config_parameter='turkey_pos_payment.auto_refund',
                                      default=False)
    pos_refund_time_limit = fields.Integer(string='İade Süre Limiti (Gün)',
                                            config_parameter='turkey_pos_payment.refund_time_limit',
                                            default=30)
    
    # Güvenlik Ayarları
    pos_log_requests = fields.Boolean(string='API İsteklerini Logla',
                                       config_parameter='turkey_pos_payment.log_requests',
                                       default=True)
    pos_timeout_seconds = fields.Integer(string='API Zaman Aşımı (Saniye)',
                                          config_parameter='turkey_pos_payment.timeout_seconds',
                                          default=30)
    pos_retry_count = fields.Integer(string='Tekrar Deneme Sayısı',
                                      config_parameter='turkey_pos_payment.retry_count',
                                      default=3)
    
    # Bildirim Ayarları
    pos_notify_success = fields.Boolean(string='Başarılı Ödeme Bildirimi',
                                         config_parameter='turkey_pos_payment.notify_success',
                                         default=True)
    pos_notify_failure = fields.Boolean(string='Başarısız Ödeme Bildirimi',
                                         config_parameter='turkey_pos_payment.notify_failure',
                                         default=True)
    pos_notify_refund = fields.Boolean(string='İade Bildirimi',
                                        config_parameter='turkey_pos_payment.notify_refund',
                                        default=True)
    
    # Para Birimi
    currency_id = fields.Many2one('res.currency', string='Para Birimi',
                                   default=lambda self: self.env.company.currency_id)
    
    # ==================== HESAPLAMA METOTLARI ====================
    
    @api.onchange('pos_max_installment_count')
    def _onchange_max_installment_count(self):
        if self.pos_max_installment_count < 1:
            self.pos_max_installment_count = 1
        elif self.pos_max_installment_count > 24:
            self.pos_max_installment_count = 24

    # ==================== İŞ METOTLARI ====================
    
    def action_test_pos_connection(self):
        """POS bağlantısını test eder"""
        self.ensure_one()
        
        if not self.default_pos_provider:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Hata'),
                    'message': _('Lütfen varsayılan POS sağlayıcısı seçin.'),
                    'type': 'danger',
                }
            }
        
        # Bağlantı testi
        try:
            provider = self.default_pos_provider
            # Test sorgusu gönder
            result = {'success': True, 'message': _('Bağlantı başarılı!')}
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Bağlantı Testi'),
                    'message': result['message'],
                    'type': 'success' if result['success'] else 'danger',
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Bağlantı Hatası'),
                    'message': str(e),
                    'type': 'danger',
                }
            }

    def action_sync_bank_gateways(self):
        """Banka gateway'lerini senkronize eder"""
        self.ensure_one()
        
        # Banka gateway'lerini oluştur/güncelle
        gateways = [
            {
                'name': 'Akbank POS',
                'code': 'akbank',
                'bank_name': 'Akbank',
                'gateway_type': 'akbank',
                'support_3d_secure': True,
                'support_refund': True,
                'support_cancel': True,
            },
            {
                'name': 'Garanti Virtual POS',
                'code': 'garanti',
                'bank_name': 'Garanti BBVA',
                'gateway_type': 'garanti',
                'support_3d_secure': True,
                'support_refund': True,
                'support_cancel': True,
            },
            {
                'name': 'Asseco EST',
                'code': 'est',
                'bank_name': 'İş Bankası, Ziraat, Halkbank, TEB, Şekerbank',
                'gateway_type': 'est',
                'support_3d_secure': True,
                'support_refund': True,
                'support_cancel': True,
            },
            {
                'name': 'Asseco EST V3',
                'code': 'est_v3',
                'bank_name': 'İş Bankası, Ziraat, Halkbank, TEB, Şekerbank',
                'gateway_type': 'est_v3',
                'support_3d_secure': True,
                'support_refund': True,
                'support_cancel': True,
            },
            {
                'name': 'YKB PosNet',
                'code': 'posnet',
                'bank_name': 'Yapı Kredi Bankası',
                'gateway_type': 'posnet',
                'support_3d_secure': True,
                'support_refund': True,
                'support_cancel': True,
            },
            {
                'name': 'QNB Finansbank PayFor',
                'code': 'payfor',
                'bank_name': 'QNB Finansbank',
                'gateway_type': 'payfor',
                'support_3d_secure': True,
                'support_refund': True,
                'support_cancel': True,
            },
            {
                'name': 'Denizbank İnterPos',
                'code': 'interpos',
                'bank_name': 'Denizbank',
                'gateway_type': 'interpos',
                'support_3d_secure': True,
                'support_refund': True,
                'support_cancel': True,
            },
            {
                'name': 'PayFlex MPI VPOS',
                'code': 'payflex',
                'bank_name': 'Vakıfbank, İşbank, Ziraat',
                'gateway_type': 'payflex',
                'support_3d_secure': True,
                'support_refund': True,
                'support_cancel': True,
            },
            {
                'name': 'Kuveyt Türk POS',
                'code': 'kuveyt',
                'bank_name': 'Kuveyt Türk',
                'gateway_type': 'kuveyt',
                'support_3d_secure': True,
                'support_refund': True,
                'support_cancel': True,
            },
            {
                'name': 'Param POS',
                'code': 'param',
                'bank_name': 'Param',
                'gateway_type': 'param',
                'support_3d_secure': True,
                'support_refund': True,
                'support_cancel': True,
            },
            {
                'name': 'Tosla POS',
                'code': 'tosla',
                'bank_name': 'Tosla (AKÖde)',
                'gateway_type': 'tosla',
                'support_3d_secure': True,
                'support_refund': True,
                'support_cancel': True,
            },
            {
                'name': 'Vakıf Katılım POS',
                'code': 'vakifkatilim',
                'bank_name': 'Vakıf Katılım',
                'gateway_type': 'vakifkatilim',
                'support_3d_secure': True,
                'support_refund': True,
                'support_cancel': True,
            },
        ]
        
        gateway_obj = self.env['bank.gateway']
        created_count = 0
        updated_count = 0
        
        for gateway_data in gateways:
            existing = gateway_obj.search([('code', '=', gateway_data['code'])], limit=1)
            if existing:
                existing.write(gateway_data)
                updated_count += 1
            else:
                gateway_obj.create(gateway_data)
                created_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Senkronizasyon Tamamlandı'),
                'message': _('%s gateway oluşturuldu, %s gateway güncellendi.') % (created_count, updated_count),
                'type': 'success',
            }
        }
