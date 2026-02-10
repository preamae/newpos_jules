# -*- coding: utf-8 -*-

import logging
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_round

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # ==================== POS SPESİFİK ALANLAR ====================
    
    # POS İşlem Bilgileri
    pos_order_id = fields.Char(string='POS Sipariş ID', index=True)
    pos_transaction_id = fields.Char(string='POS İşlem ID', index=True)
    pos_auth_code = fields.Char(string='POS Onay Kodu')
    pos_batch_num = fields.Char(string='POS Batch Numarası')
    pos_stan = fields.Char(string='POS STAN')
    pos_rrn = fields.Char(string='POS RRN (Referans No)')
    
    # 3D Secure Bilgileri
    is_3d_secure = fields.Boolean(string='3D Secure İşlem', default=False)
    md_status = fields.Char(string='3D Durum Kodu')
    md_error_message = fields.Text(string='3D Hata Mesajı')
    
    # Taksit Bilgileri
    installment_count = fields.Integer(string='Taksit Sayısı', default=0)
    installment_amount = fields.Monetary(string='Taksitli Tutar', currency_field='currency_id', compute='_compute_installment_amount', store=True)
    commission_amount = fields.Monetary(string='Komisyon Tutarı', currency_field='currency_id')
    
    # İade/İptal Bilgileri
    is_refunded = fields.Boolean(string='İade Edildi', default=False)
    refund_amount = fields.Monetary(string='İade Tutarı', default=0.0, currency_field='currency_id')
    refund_date = fields.Datetime(string='İade Tarihi')
    refund_transaction_id = fields.Char(string='İade İşlem ID')
    
    is_cancelled = fields.Boolean(string='İptal Edildi', default=False)
    cancel_date = fields.Datetime(string='İptal Tarihi')
    cancel_transaction_id = fields.Char(string='İptal İşlem ID')
    
    # İşlem Detayları
    request_data = fields.Text(string='İstek Verisi')
    response_data = fields.Text(string='Yanıt Verisi')
    error_code = fields.Char(string='Hata Kodu')
    error_message = fields.Text(string='Hata Mesajı')
    
    # Kart Bilgileri (Maskelenmiş)
    card_number_masked = fields.Char(string='Maskelenmiş Kart No')
    card_brand = fields.Char(string='Kart Markası')
    card_type = fields.Selection([
        ('credit', 'Kredi Kartı'),
        ('debit', 'Banka Kartı'),
        ('prepaid', 'Ön Ödemeli Kart'),
    ], string='Kart Tipi')
    
    # İşlem Tarihçesi
    history_ids = fields.One2many('payment.transaction.history', 'transaction_id', string='İşlem Tarihçesi')
    
    # Kategori Bazlı Taksit
    category_installment_id = fields.Many2one('installment.option', string='Kategori Taksit Seçeneği')
    
    # İşlem Durumu
    pos_state = fields.Selection([
        ('pending', 'Bekliyor'),
        ('processing', 'İşleniyor'),
        ('authorized', 'Onaylandı'),
        ('captured', 'Tahsil Edildi'),
        ('refunded', 'İade Edildi'),
        ('partial_refunded', 'Kısmi İade'),
        ('cancelled', 'İptal Edildi'),
        ('failed', 'Başarısız'),
    ], string='POS Durumu', default='pending')
    
    # Ödeme Tarihi
    payment_date = fields.Date(string='Ödeme Tarihi')

    # ==================== HESAPLAMA METOTLARI ====================
    
    @api.depends('amount', 'installment_count')
    def _compute_installment_amount(self):
        for tx in self:
            if tx.installment_count > 1:
                tx.installment_amount = tx.amount / tx.installment_count
            else:
                tx.installment_amount = tx.amount

    # ==================== İŞLEM METOTLARI ====================
    
    def _send_payment_request(self):
        """Ödeme isteği gönderir"""
        self.ensure_one()
        
        if self.provider_code not in ['akbank', 'garanti', 'isbank', 'ziraat', 'halkbank', 
                                       'vakifbank', 'vakifkatilim', 'yapikredi', 'finansbank',
                                       'denizbank', 'teb', 'sekerbank', 'kuveytturk', 'param', 'tosla']:
            return super(PaymentTransaction, self)._send_payment_request()
        
        try:
            # POS sipariş ID oluştur
            self.pos_order_id = f"ODOO_{self.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # İşlem durumunu güncelle
            self.pos_state = 'processing'
            
            # İşlem tarihçesine kaydet
            self._add_history_entry('processing', _('Ödeme işlemi başlatıldı'))
            
            _logger.info('Payment request sent for transaction %s', self.reference)
            return {'success': True}
            
        except Exception as e:
            _logger.error('Payment request error: %s', e)
            self.pos_state = 'failed'
            self.error_message = str(e)
            self._add_history_entry('failed', str(e))
            return {'success': False, 'error': str(e)}

    def _process_notification_data(self, data):
        """Bildirim verilerini işler"""
        self.ensure_one()
        
        if self.provider_code not in ['akbank', 'garanti', 'isbank', 'ziraat', 'halkbank',
                                       'vakifbank', 'vakifkatilim', 'yapikredi', 'finansbank',
                                       'denizbank', 'teb', 'sekerbank', 'kuveytturk', 'param', 'tosla']:
            return super(PaymentTransaction, self)._process_notification_data(data)
        
        try:
            # Eğer veri zaten işlenmişse (success anahtarı varsa) direkt kullan
            if isinstance(data, dict) and 'success' in data and 'processed' in data:
                result = data
            else:
                # 3D dönüş verilerini işle
                provider = self.provider_id
                result = provider.process_3d_return(data)
            
            self.response_data = str(data)
            
            if result.get('success'):
                self.pos_state = 'authorized'
                self.pos_auth_code = result.get('auth_code', '')
                self.pos_transaction_id = result.get('transaction_id', '')
                self.state = 'done'
                self.payment_date = fields.Date.today()
                self.is_3d_secure = True
                self.md_status = data.get('mdStatus', '')
                
                self._add_history_entry('authorized', 
                    _('Ödeme başarılı. Onay Kodu: %s') % self.pos_auth_code)
                
                # POS Siparişi Oluştur
                self._create_pos_order()
                
                # Faturayı ödendi olarak işaretle
                self._reconcile_after_done()
            else:
                self.pos_state = 'failed'
                self.state = 'error'
                self.error_message = result.get('message', _('Ödeme başarısız'))
                self.md_error_message = result.get('message', '')
                
                self._add_history_entry('failed', self.error_message)
            
            return result
            
        except Exception as e:
            _logger.error('Notification processing error: %s', e)
            self.pos_state = 'failed'
            self.state = 'error'
            self.error_message = str(e)
            self._add_history_entry('failed', str(e))
            return {'success': False, 'error': str(e)}

    def _create_pos_order(self):
        """İşlem başarılı olduğunda POS siparişi oluşturur"""
        self.ensure_one()
        pos_order_model = self.env['pos.order'].sudo()
        
        # Eğer zaten varsa oluşturma
        existing_order = pos_order_model.search([('transaction_id', '=', self.id)], limit=1)
        if existing_order:
            return existing_order
            
        order_vals = {
            'transaction_id': self.id,
            'state': 'done',
            'payment_date': datetime.now(),
        }
        
        # Sale Order linkleme
        if hasattr(self, 'sale_order_ids') and self.sale_order_ids:
            order_vals['sale_order_id'] = self.sale_order_ids[0].id
        elif self.reference:
            so_name = self.reference.split('_')[0]
            sale_order = self.env['sale.order'].sudo().search([('name', '=', so_name)], limit=1)
            if sale_order:
                order_vals['sale_order_id'] = sale_order.id
        
        order = pos_order_model.create(order_vals)
        return order

    def _add_history_entry(self, state, message):
        """İşlem tarihçesine kayıt ekler"""
        self.ensure_one()
        self.env['payment.transaction.history'].create({
            'transaction_id': self.id,
            'state': state,
            'message': message,
            'date': datetime.now(),
        })

    # ==================== İADE METOTLARI ====================
    
    def action_refund(self, amount=None):
        """İade işlemi yapar"""
        self.ensure_one()
        
        if self.state != 'done':
            raise UserError(_('Sadece tamamlanmış işlemler için iade yapılabilir.'))
        
        if self.is_refunded and not amount:
            raise UserError(_('Bu işlem zaten iade edilmiş.'))
        
        if not amount:
            amount = self.amount - self.refund_amount
        
        if amount <= 0:
            raise UserError(_('İade tutarı sıfırdan büyük olmalıdır.'))
        
        if amount > (self.amount - self.refund_amount):
            raise UserError(_('İade tutarı kalan tutardan büyük olamaz.'))
        
        try:
            provider = self.provider_id
            result = provider.process_refund(self, amount)
            
            if result['success']:
                self.refund_amount += amount
                self.refund_date = datetime.now()
                self.refund_transaction_id = result.get('transaction_id', '')
                
                if self.refund_amount >= self.amount:
                    self.is_refunded = True
                    self.pos_state = 'refunded'
                    self.state = 'cancel'
                else:
                    self.pos_state = 'partial_refunded'
                
                self._add_history_entry('refunded', 
                    _('İade yapıldı. Tutar: %s, İade ID: %s') % (amount, self.refund_transaction_id))
                
                # İade kaydı oluştur
                self._create_refund_move(amount)
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Başarılı'),
                        'message': _('İade işlemi başarıyla tamamlandı.'),
                        'type': 'success',
                    }
                }
            else:
                raise UserError(result.get('message', _('İade işlemi başarısız')))
                
        except Exception as e:
            _logger.error('Refund error: %s', e)
            raise UserError(_('İade işlemi sırasında hata: %s') % str(e))

    def _create_refund_move(self, amount):
        """İade muhasebe kaydı oluşturur"""
        self.ensure_one()
        if not self.invoice_ids:
            return
        
        invoice = self.invoice_ids[0]
        if invoice.state != 'posted':
            return
            
        # Kredi notu oluştur
        refund_wizard = self.env['account.move.reversal'].with_context(
            active_model='account.move',
            active_ids=invoice.ids
        ).create({
            'date': fields.Date.today(),
            'reason': _('POS Refund: %s') % self.reference,
            'journal_id': invoice.journal_id.id,
        })
        
        res = refund_wizard.refund_moves()
        refund_move = self.env['account.move'].browse(res['res_id'])
        refund_move.action_post()
        
        # POS siparişini güncelle
        pos_order = self.env['pos.order'].search([('transaction_id', '=', self.id)], limit=1)
        if pos_order:
            pos_order.invoice_id = refund_move.id

    # ==================== İPTAL METOTLARI ====================
    
    def action_cancel_transaction(self):
        """İşlemi iptal eder"""
        self.ensure_one()
        
        if self.state != 'done':
            raise UserError(_('Sadece tamamlanmış işlemler iptal edilebilir.'))
        
        if self.is_cancelled:
            raise UserError(_('Bu işlem zaten iptal edilmiş.'))
        
        try:
            provider = self.provider_id
            result = provider.process_cancel(self)
            
            if result['success']:
                self.is_cancelled = True
                self.cancel_date = datetime.now()
                self.cancel_transaction_id = result.get('transaction_id', '')
                self.pos_state = 'cancelled'
                self.state = 'cancel'
                
                self._add_history_entry('cancelled', 
                    _('İptal edildi. İptal ID: %s') % self.cancel_transaction_id)
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Başarılı'),
                        'message': _('İptal işlemi başarıyla tamamlandı.'),
                        'type': 'success',
                    }
                }
            else:
                raise UserError(result.get('message', _('İptal işlemi başarısız')))
                
        except Exception as e:
            _logger.error('Cancel error: %s', e)
            raise UserError(_('İptal işlemi sırasında hata: %s') % str(e))

    # ==================== DURUM SORGULAMA ====================
    
    def action_query_status(self):
        """İşlem durumunu sorgular"""
        self.ensure_one()
        
        if not self.pos_order_id:
            raise UserError(_('POS sipariş ID bulunamadı.'))
        
        try:
            provider = self.provider_id
            result = provider.query_status(self)
            
            if result['success']:
                self._add_history_entry('query', 
                    _('Durum sorgulama: %s') % result.get('message', ''))
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Durum Sorgulama'),
                        'message': result.get('message', _('İşlem başarılı')),
                        'type': 'info',
                    }
                }
            else:
                raise UserError(result.get('message', _('Durum sorgulama başarısız')))
                
        except Exception as e:
            _logger.error('Status query error: %s', e)
            raise UserError(_('Durum sorgulama sırasında hata: %s') % str(e))

    # ==================== BUTONLAR ====================
    
    def action_open_refund_wizard(self):
        """İade sihirbazını açar"""
        self.ensure_one()
        
        return {
            'name': _('İade İşlemi'),
            'type': 'ir.actions.act_window',
            'res_model': 'pos.refund.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_transaction_id': self.id,
                'default_max_amount': self.amount - self.refund_amount,
            }
        }

    def action_open_cancel_wizard(self):
        """İptal sihirbazını açar"""
        self.ensure_one()
        
        return {
            'name': _('İptal İşlemi'),
            'type': 'ir.actions.act_window',
            'res_model': 'pos.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_transaction_id': self.id,
            }
        }

    def action_view_history(self):
        """İşlem tarihçesini görüntüler"""
        self.ensure_one()
        
        return {
            'name': _('İşlem Tarihçesi'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.transaction.history',
            'view_mode': 'list,form',
            'domain': [('transaction_id', '=', self.id)],
            'context': {'default_transaction_id': self.id},
        }


class PaymentTransactionHistory(models.Model):
    _name = 'payment.transaction.history'
    _description = 'Ödeme İşlem Tarihçesi'
    _order = 'date desc'

    transaction_id = fields.Many2one('payment.transaction', string='İşlem', required=True, ondelete='cascade')
    state = fields.Selection([
        ('pending', 'Bekliyor'),
        ('processing', 'İşleniyor'),
        ('authorized', 'Onaylandı'),
        ('captured', 'Tahsil Edildi'),
        ('refunded', 'İade Edildi'),
        ('partial_refunded', 'Kısmi İade'),
        ('cancelled', 'İptal Edildi'),
        ('failed', 'Başarısız'),
        ('query', 'Sorgulama'),
    ], string='Durum', required=True)
    
    message = fields.Text(string='Mesaj')
    date = fields.Datetime(string='Tarih', default=lambda self: datetime.now())
    user_id = fields.Many2one('res.users', string='Kullanıcı', default=lambda self: self.env.user)
