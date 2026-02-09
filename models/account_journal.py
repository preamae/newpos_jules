# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    # POS Banka Bilgileri
    is_pos_journal = fields.Boolean(string='POS Günlüğü', default=False)
    pos_provider_id = fields.Many2one('payment.provider', string='POS Sağlayıcısı')
    bank_code = fields.Char(string='Banka Kodu', compute='_compute_bank_code', store=True)

    @api.depends('pos_provider_id.code')
    def _compute_bank_code(self):
        for journal in self:
            journal.bank_code = journal.pos_provider_id.code
    
    # Hesap Bilgileri
    pos_commission_account_id = fields.Many2one('account.account', string='POS Komisyon Hesabı')
    pos_expense_account_id = fields.Many2one('account.account', string='POS Gider Hesabı')
    pos_receivable_account_id = fields.Many2one('account.account', string='POS Alacak Hesabı')
    
    # Taksit Farkı Hesabı
    pos_installment_fee_account_id = fields.Many2one('account.account', string='Taksit Farkı Hesabı')
    
    # Mutabakat Hesabı
    pos_reconciliation_account_id = fields.Many2one('account.account', string='Mutabakat Hesabı')


class PosAccountingConfig(models.Model):
    _name = 'pos.accounting.config'
    _description = 'POS Muhasebe Konfigürasyonu'

    name = fields.Char(string='Ad', required=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company)
    
    # Banka
    provider_id = fields.Many2one('payment.provider', string='POS Sağlayıcısı', required=True)
    
    # Gelir Hesapları
    income_account_id = fields.Many2one('account.account', string='Satış Gelir Hesabı', required=True)
    
    # Gider Hesapları
    commission_account_id = fields.Many2one('account.account', string='POS Komisyon Gider Hesabı', required=True)
    installment_fee_account_id = fields.Many2one('account.account', string='Taksit Farkı Gider Hesabı')
    
    # Alacak Hesapları
    receivable_account_id = fields.Many2one('account.account', string='POS Alacak Hesabı', required=True)
    
    # Borç Hesapları
    payable_account_id = fields.Many2one('account.account', string='POS Borç Hesabı')
    
    # Mutabakat Hesabı
    reconciliation_account_id = fields.Many2one('account.account', string='Mutabakat Hesabı')
    
    # İade Hesabı
    refund_account_id = fields.Many2one('account.account', string='İade Hesabı')
    
    # Aktiflik
    active = fields.Boolean(string='Aktif', default=True)
    
    _sql_constraints = [
        ('unique_provider_company', 'UNIQUE(provider_id, company_id)', 
         'Her sağlayıcı için şirket başına sadece bir konfigürasyon olabilir!')
    ]


class PosJournalEntry(models.Model):
    _name = 'pos.journal.entry'
    _description = 'POS Yevmiye Kaydı'
    _order = 'date desc, id desc'
    
    name = fields.Char(string='Kayıt No', required=True, copy=False, 
                       default=lambda self: self.env['ir.sequence'].next_by_code('pos.journal.entry'))
    
    # İlişkiler
    transaction_id = fields.Many2one('payment.transaction', string='Ödeme İşlemi')
    provider_id = fields.Many2one(related='transaction_id.provider_id', string='Sağlayıcı', store=True)
    move_id = fields.Many2one('account.move', string='Yevmiye Kaydı', readonly=True)
    
    # Tarih
    date = fields.Date(string='Tarih', required=True, default=fields.Date.today)
    
    # Tutarlar
    amount = fields.Monetary(string='Tutar', required=True, currency_field='currency_id')
    commission_amount = fields.Monetary(string='Komisyon Tutarı', default=0.0, currency_field='currency_id')
    installment_fee = fields.Monetary(string='Taksit Farkı', default=0.0, currency_field='currency_id')
    net_amount = fields.Monetary(string='Net Tutar', compute='_compute_net_amount', currency_field='currency_id')
    
    # Para Birimi
    currency_id = fields.Many2one(related='transaction_id.currency_id', string='Para Birimi', store=True)
    
    # Kayıt Tipi
    entry_type = fields.Selection([
        ('sale', 'Satış'),
        ('refund', 'İade'),
        ('cancel', 'İptal'),
        ('commission', 'Komisyon'),
        ('reconciliation', 'Mutabakat'),
    ], string='Kayıt Tipi', required=True, default='sale')
    
    # Durum
    state = fields.Selection([
        ('draft', 'Taslak'),
        ('posted', 'Kaydedildi'),
        ('cancelled', 'İptal Edildi'),
    ], string='Durum', default='draft')
    
    # Açıklama
    description = fields.Text(string='Açıklama')
    
    # ==================== HESAPLAMA METOTLARI ====================
    
    @api.depends('amount', 'commission_amount', 'installment_fee')
    def _compute_net_amount(self):
        for entry in self:
            entry.net_amount = entry.amount - entry.commission_amount - entry.installment_fee
    
    # ==================== İŞ METOTLARI ====================
    
    def action_post(self):
        """Yevmiye kaydını oluşturur ve kaydeder"""
        for entry in self:
            if entry.move_id:
                continue
            
            # Konfigürasyonu al
            config = self.env['pos.accounting.config'].search([
                ('provider_id', '=', entry.provider_id.id),
                ('company_id', '=', self.env.company.id),
                ('active', '=', True),
            ], limit=1)
            
            if not config:
                raise ValidationError(_('%s için muhasebe konfigürasyonu bulunamadı!') % entry.provider_id.name)
            
            # Yevmiye kaydı satırları
            move_lines = []
            
            if entry.entry_type == 'sale':
                # Satış kaydı
                # 1. Alacak (Müşteri)
                move_lines.append({
                    'account_id': config.receivable_account_id.id,
                    'partner_id': entry.transaction_id.partner_id.id,
                    'debit': entry.amount,
                    'credit': 0.0,
                    'name': _('POS Satış - %s') % entry.transaction_id.reference,
                })
                
                # 2. Borç (Gelir)
                move_lines.append({
                    'account_id': config.income_account_id.id,
                    'partner_id': entry.transaction_id.partner_id.id,
                    'debit': 0.0,
                    'credit': entry.net_amount,
                    'name': _('POS Satış Geliri - %s') % entry.transaction_id.reference,
                })
                
                # 3. Borç (Komisyon Gideri)
                if entry.commission_amount > 0:
                    move_lines.append({
                        'account_id': config.commission_account_id.id,
                        'partner_id': entry.transaction_id.partner_id.id,
                        'debit': 0.0,
                        'credit': entry.commission_amount,
                        'name': _('POS Komisyonu - %s') % entry.transaction_id.reference,
                    })
                
                # 4. Borç (Taksit Farkı)
                if entry.installment_fee > 0:
                    move_lines.append({
                        'account_id': config.installment_fee_account_id.id or config.commission_account_id.id,
                        'partner_id': entry.transaction_id.partner_id.id,
                        'debit': 0.0,
                        'credit': entry.installment_fee,
                        'name': _('Taksit Farkı - %s') % entry.transaction_id.reference,
                    })
            
            elif entry.entry_type == 'refund':
                # İade kaydı
                # 1. Borç (Gelir İadesi)
                move_lines.append({
                    'account_id': config.income_account_id.id,
                    'partner_id': entry.transaction_id.partner_id.id,
                    'debit': entry.amount,
                    'credit': 0.0,
                    'name': _('POS İade - %s') % entry.transaction_id.reference,
                })
                
                # 2. Alacak (Müşteri)
                move_lines.append({
                    'account_id': config.receivable_account_id.id,
                    'partner_id': entry.transaction_id.partner_id.id,
                    'debit': 0.0,
                    'credit': entry.amount,
                    'name': _('POS İade - %s') % entry.transaction_id.reference,
                })
            
            # Yevmiye kaydını oluştur
            move_vals = {
                'journal_id': self.env['account.journal'].search([
                    ('is_pos_journal', '=', True),
                    ('pos_provider_id', '=', entry.provider_id.id)
                ], limit=1).id or self.env['account.journal'].search([('type', '=', 'bank')], limit=1).id,
                'date': entry.date,
                'ref': entry.name,
                'line_ids': [(0, 0, line) for line in move_lines],
            }
            
            move = self.env['account.move'].create(move_vals)
            move.action_post()
            
            entry.write({
                'move_id': move.id,
                'state': 'posted',
            })
    
    def action_cancel(self):
        """Yevmiye kaydını iptal eder"""
        for entry in self:
            if entry.move_id:
                entry.move_id.button_cancel()
            entry.state = 'cancelled'


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'
    
    pos_journal_entry_ids = fields.One2many('pos.journal.entry', 'transaction_id', string='Yevmiye Kayıtları')
    
    def _create_pos_journal_entry(self):
        """POS yevmiye kaydı oluşturur"""
        self.ensure_one()
        
        if not self.provider_id or self.provider_id.code not in ['akbank', 'garanti', 'isbank', 'ziraat', 
                                                                  'halkbank', 'vakifbank', 'vakifkatilim', 
                                                                  'yapikredi', 'finansbank', 'denizbank', 
                                                                  'teb', 'sekerbank', 'kuveytturk', 'param', 'tosla']:
            return
        
        # Konfigürasyon kontrolü
        config = self.env['pos.accounting.config'].search([
            ('provider_id', '=', self.provider_id.id),
            ('company_id', '=', self.env.company.id),
            ('active', '=', True),
        ], limit=1)
        
        if not config:
            _logger.warning('%s için muhasebe konfigürasyonu bulunamadı!', self.provider_id.name)
            return
        
        # Yevmiye kaydı oluştur
        entry = self.env['pos.journal.entry'].create({
            'transaction_id': self.id,
            'date': fields.Date.today(),
            'amount': self.amount,
            'commission_amount': self.commission_amount,
            'installment_fee': self.installment_amount - self.amount if self.installment_amount > self.amount else 0.0,
            'entry_type': 'sale',
            'description': _('POS Ödeme - %s') % self.reference,
        })
        
        entry.action_post()
        
        return entry
    
    def _create_pos_refund_entry(self):
        """POS iade yevmiye kaydı oluşturur"""
        self.ensure_one()
        
        if not self.provider_id or self.provider_id.code not in ['akbank', 'garanti', 'isbank', 'ziraat', 
                                                                  'halkbank', 'vakifbank', 'vakifkatilim', 
                                                                  'yapikredi', 'finansbank', 'denizbank', 
                                                                  'teb', 'sekerbank', 'kuveytturk', 'param', 'tosla']:
            return
        
        config = self.env['pos.accounting.config'].search([
            ('provider_id', '=', self.provider_id.id),
            ('company_id', '=', self.env.company.id),
            ('active', '=', True),
        ], limit=1)
        
        if not config:
            return
        
        entry = self.env['pos.journal.entry'].create({
            'transaction_id': self.id,
            'date': fields.Date.today(),
            'amount': self.refund_amount,
            'entry_type': 'refund',
            'description': _('POS İade - %s') % self.reference,
        })
        
        entry.action_post()
        
        return entry
