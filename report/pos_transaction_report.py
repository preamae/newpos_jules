# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.tools import format_datetime, format_date

_logger = logging.getLogger(__name__)


class PosTransactionReport(models.AbstractModel):
    _name = 'report.turkey_pos_payment.pos_transaction_report'
    _description = 'POS İşlem Raporu'

    @api.model
    def _get_report_values(self, docids, data=None):
        """POS İşlem raporu değerlerini döndürür"""
        transactions = self.env['payment.transaction'].browse(docids)
        
        # İstatistikleri hesapla
        total_amount = sum(transactions.filtered(lambda t: t.state == 'done').mapped('amount'))
        total_transactions = len(transactions.filtered(lambda t: t.state == 'done'))
        total_refunds = sum(transactions.mapped('refund_amount'))
        
        # Sağlayıcı bazlı istatistikler
        provider_stats = {}
        for provider in transactions.mapped('provider_id'):
            provider_txs = transactions.filtered(lambda t: t.provider_id == provider)
            provider_stats[provider.name] = {
                'count': len(provider_txs.filtered(lambda t: t.state == 'done')),
                'amount': sum(provider_txs.filtered(lambda t: t.state == 'done').mapped('amount')),
                'refunds': sum(provider_txs.mapped('refund_amount')),
            }
        
        return {
            'docs': transactions,
            'total_amount': total_amount,
            'total_transactions': total_transactions,
            'total_refunds': total_refunds,
            'provider_stats': provider_stats,
            'format_datetime': format_datetime,
            'format_date': format_date,
        }


class PosDailyReport(models.AbstractModel):
    _name = 'report.turkey_pos_payment.pos_daily_report'
    _description = 'POS Günlük Rapor'

    @api.model
    def _get_report_values(self, docids, data=None):
        date = data.get('date', fields.Date.today()) if data else fields.Date.today()
        
        # Günlük işlemleri al
        transactions = self.env['payment.transaction'].search([
            ('payment_date', '=', date),
            ('provider_code', 'in', ['akbank', 'garanti', 'isbank', 'ziraat', 'halkbank',
                                      'vakifbank', 'vakifkatilim', 'yapikredi', 'finansbank',
                                      'denizbank', 'teb', 'sekerbank', 'kuveytturk', 'param', 'tosla']),
        ])
        
        # İstatistikleri hesapla
        total_amount = sum(transactions.filtered(lambda t: t.state == 'done').mapped('amount'))
        total_transactions = len(transactions.filtered(lambda t: t.state == 'done'))
        total_refunds = sum(transactions.mapped('refund_amount'))
        
        # Sağlayıcı bazlı istatistikler
        provider_stats = {}
        for provider in transactions.mapped('provider_id'):
            provider_txs = transactions.filtered(lambda t: t.provider_id == provider)
            provider_stats[provider.name] = {
                'count': len(provider_txs.filtered(lambda t: t.state == 'done')),
                'amount': sum(provider_txs.filtered(lambda t: t.state == 'done').mapped('amount')),
                'refunds': sum(provider_txs.mapped('refund_amount')),
            }
        
        return {
            'date': date,
            'total_amount': total_amount,
            'total_transactions': total_transactions,
            'total_refunds': total_refunds,
            'provider_stats': provider_stats,
            'transactions': transactions,
        }


class PosReconciliationReport(models.AbstractModel):
    _name = 'report.turkey_pos_payment.pos_reconciliation_report'
    _description = 'POS Mutabakat Raporu'

    @api.model
    def _get_report_values(self, docids, data=None):
        reconciliations = self.env['pos.reconciliation'].browse(docids)
        
        return {
            'docs': reconciliations,
            'format_datetime': format_datetime,
            'format_date': format_date,
        }
