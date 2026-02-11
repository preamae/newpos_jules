# -*- coding: utf-8 -*-
{
    'name': 'Türkiye Sanal POS Ödeme Sistemi',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'summary': 'Türkiye Bankaları Sanal POS Entegrasyonu - Tüm Bankalar',
    'description': """
Türkiye Sanal POS Ödeme Sistemi
================================

Bu modül ile Türkiye'deki tüm bankaların sanal POS sistemlerini Odoo'da kullanabilirsiniz.

Desteklenen Bankalar:
---------------------
- Akbank (AkbankPos)
- Garanti BBVA (GarantiPos)
- İş Bankası (EstPos/EstV3Pos/PayFlex)
- Ziraat Bankası (EstPos/EstV3Pos/PayFlex)
- Halkbank (EstPos/EstV3Pos)
- Vakıfbank (PayFlex)
- Vakıf Katılım (VakifKatilimPos)
- Yapı Kredi Bankası (PosNet)
- QNB Finansbank (PayForPos)
- Denizbank (InterPos)
- TEB (EstPos/EstV3Pos)
- Şekerbank (EstPos/EstV3Pos)
- Kuveyt Türk (KuveytPos)
- Param POS (ParamPos)
- Tosla (ToslaPos)

Özellikler:
-----------
- 3D Secure, 3D Pay, NonSecure ödeme seçenekleri
- Kategori bazlı taksit seçenekleri
- Ürün sayfasında taksit sekmesi
- Ödeme sayfasında banka ve taksit seçimi
- Taksit farkının sepete yansıtılması
- İptal ve iade işlemleri
- Durum sorgulama
- Sipariş tarihçesi sorgulama
- Tekrarlanan ödeme desteği
- QR kod ile ödeme
- Ödeme kayıtları ve raporlama
- Banka bazlı yevmiye kayıtları
- Otomatik hesap planı oluşturma

Teknik Özellikler:
------------------
- XML API entegrasyonu
- SHA-256/SHA-512 şifreleme desteği
- Güvenli 3D Secure akışı
- Webhook desteği
- Otomatik hata yönetimi
- Kart BIN numarası ile banka tespiti
    """,
    'author': 'Odoo Turkey Community',
    'website': 'https://github.com/mewebstudio/pos',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'account',
        'account_payment',
        'payment',
        'sale',
        'product',
        'website_sale',
    ],
    'data': [
        # Security
        'security/turkey_pos_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/account_chart_data.xml',
        'data/payment_provider_data.xml',
        'data/payment_method_data.xml',
        'data/bank_gateway_data.xml',
        'data/ir_cron_data.xml',
        
        # Views
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
        'views/bank_gateway_views.xml',
        'views/installment_option_views.xml',
        'views/product_category_views.xml',
        'views/pos_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/payment_portal_templates.xml',
        'views/product_template_views.xml',
        'views/account_journal_views.xml',
        
        # Wizards
        'wizards/pos_refund_wizard_views.xml',
        
        # Report
        'report/pos_transaction_report.xml',
        'report/pos_transaction_report_template.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'turkey_pos_payment/static/src/js/installment_calculator.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': 0.00,
    'currency': 'EUR',
    'support': 'https://github.com/mewebstudio/pos/issues',
}
