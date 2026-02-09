# Türkiye Sanal POS Ödeme Sistemi - Odoo 19

Bu modül, Türkiye'deki tüm bankaların sanal POS sistemlerini Odoo 19'da kullanmanızı sağlar. 
[mewebstudio/pos](https://github.com/mewebstudio/pos) PHP projesinden esinlenerek geliştirilmiştir.

## Desteklenen Bankalar

| Banka | Gateway | 3D Secure | İade | İptal |
|-------|---------|-----------|------|-------|
| Akbank | AkbankPos | ✓ | ✓ | ✓ |
| Garanti BBVA | GarantiPos | ✓ | ✓ | ✓ |
| İş Bankası | EST/PayFlex | ✓ | ✓ | ✓ |
| Ziraat Bankası | EST/PayFlex | ✓ | ✓ | ✓ |
| Halkbank | EST/PayFlex | ✓ | ✓ | ✓ |
| Vakıfbank | PayFlex | ✓ | ✓ | ✓ |
| Vakıf Katılım | VakifKatilimPos | ✓ | ✓ | ✓ |
| Yapı Kredi | PosNet | ✓ | ✓ | ✓ |
| QNB Finansbank | PayFor | ✓ | ✓ | ✓ |
| Denizbank | İnterPos | ✓ | ✓ | ✓ |
| TEB | EST | ✓ | ✓ | ✓ |
| Şekerbank | EST | ✓ | ✓ | ✓ |
| Kuveyt Türk | KuveytPos | ✓ | ✓ | ✓ |
| Param | ParamPos | ✓ | ✓ | ✓ |
| Tosla | ToslaPos | ✓ | ✓ | ✓ |

## Özellikler

### Ödeme Tipleri
- **3D Secure** - En güvenli ödeme yöntemi
- **3D Pay** - 3D Secure ile ödeme
- **3D Host** - Banka sayfasında ödeme
- **Non-Secure** - 3D olmadan ödeme

### Taksit Seçenekleri
- ✅ Kategori bazlı taksit tanımları
- ✅ Banka özel taksit oranları
- ✅ Kampanya taksitleri
- ✅ Komisyon hesaplama
- ✅ Vade farkı hesaplama

### İşlem Yönetimi
- ✅ İptal işlemleri
- ✅ İade işlemleri (tam ve kısmi)
- ✅ Durum sorgulama
- ✅ Sipariş tarihçesi
- ✅ Otomatik mutabakat

## Kurulum

### 1. Modülü Yükleyin

```bash
# Odoo addons dizinine kopyalayın
cp -r turkey_pos_payment /path/to/odoo/addons/

# Odoo'yu yeniden başlatın
systemctl restart odoo
```

### 2. Modülü Aktifleştirin

1. Odoo'ya giriş yapın
2. Uygulamalar menüsüne gidin
3. "Türkiye Sanal POS Ödeme Sistemi" modülünü arayın
4. Yükle butonuna tıklayın

### 3. Banka Gateway'lerini Senkronize Edin

1. Ayarlar > Genel Ayarlar > Türkiye POS Ayarları
2. "Banka Gateway'lerini Senkronize Et" butonuna tıklayın

### 4. Ödeme Sağlayıcısı Ekleyin

1. Ödemeler > Ödeme Sağlayıcıları > Türkiye POS Sağlayıcıları
2. "Yeni" butonuna tıklayın
3. Bankanızı seçin
4. API bilgilerinizi girin:
   - API Kullanıcı Adı
   - API Şifre
   - Müşteri ID / Terminal ID
   - Mağaza Anahtarı (Store Key)
5. Test/Canlı ortam seçin
6. Kaydedin

### 5. Taksit Seçeneklerini Yapılandırın

1. Türkiye POS > Taksit Yönetimi > Taksit Seçenekleri
2. Sağlayıcınız için taksit seçenekleri ekleyin
3. Komisyon oranlarını belirleyin

### 6. Kategori Bazlı Taksitler (İsteğe Bağlı)

1. Ürünler > Kategoriler
2. Bir kategori seçin
3. "Taksit Ayarları" sekmesine gidin
4. Taksit seçeneklerini yapılandırın

## API Bilgileri

### Test Ortamı

Her banka için test API bilgilerini bankanızdan alabilirsiniz. Genellikle:
- Test API URL
- Test 3D URL
- Test kullanıcı bilgileri

### Canlı Ortamı

Canlı ortama geçiş için:
1. Bankanızdan canlı API bilgilerini alın
2. Sağlayıcı ayarlarında "Ortam" alanını "Canlı Ortam" olarak değiştirin
3. Canlı API bilgilerini girin

## Dosya Yapısı

```
turkey_pos_payment/
├── __init__.py
├── __manifest__.py
├── README.md
├── controllers/
│   ├── __init__.py
│   ├── main.py
│   └── payment.py
├── data/
│   ├── payment_provider_data.xml
│   ├── payment_method_data.xml
│   ├── bank_gateway_data.xml
│   └── ir_cron_data.xml
├── models/
│   ├── __init__.py
│   ├── payment_provider.py
│   ├── payment_transaction.py
│   ├── bank_gateway.py
│   ├── installment_option.py
│   ├── product_category.py
│   ├── pos_order.py
│   ├── account_move.py
│   └── res_config_settings.py
├── security/
│   ├── turkey_pos_security.xml
│   └── ir.model.access.csv
├── static/
│   └── description/
│       └── index.html
├── views/
│   ├── payment_provider_views.xml
│   ├── payment_transaction_views.xml
│   ├── bank_gateway_views.xml
│   ├── installment_option_views.xml
│   ├── product_category_views.xml
│   ├── pos_order_views.xml
│   └── res_config_settings_views.xml
├── wizards/
│   ├── __init__.py
│   ├── pos_refund_wizard.py
│   ├── pos_cancel_wizard.py
│   ├── pos_status_query_wizard.py
│   └── pos_refund_wizard_views.xml
└── report/
    ├── __init__.py
    ├── pos_transaction_report.py
    ├── pos_transaction_report.xml
    └── pos_transaction_report_template.xml
```

## Kullanım

### Ödeme İşlemi

1. Müşteri ödeme sayfasına gider
2. Kart bilgilerini girer
3. Taksit seçeneği seçer (isteğe bağlı)
4. "Ödeme Yap" butonuna tıklar
5. 3D Secure doğrulaması yapılır
6. Ödeme tamamlanır

### İade İşlemi

1. Ödemeler > POS İşlemleri
2. İade edilecek işlemi bulun
3. "İade Yap" butonuna tıklayın
4. İade tutarını girin
5. İadeyi onaylayın

### İptal İşlemi

1. Ödemeler > POS İşlemleri
2. İptal edilecek işlemi bulun
3. "İptal Et" butonuna tıklayın
4. İptal nedenini seçin
5. İptali onaylayın

## Raporlama

### Excel Raporu

1. Ödemeler > POS İşlemleri
2. Rapor alınacak işlemleri seçin
3. "Yazdır" > "POS İşlem Raporu (Excel)"

### Günlük Rapor

1. Ödemeler > POS İşlemleri > Dashboard
2. Tarih seçin
3. "Günlük Rapor" butonuna tıklayın

### Mutabakat Raporu

1. POS İşlemleri > Mutabakat
2. Yeni mutabakat oluşturun
3. Tarih aralığı seçin
4. İşlemleri yükleyin
5. Raporu yazdırın

## Teknik Detaylar

### Hash Algoritmaları

- SHA-256 (varsayılan)
- SHA-512 (EST V3 için)

### Desteklenen Para Birimleri

- TRY (Türk Lirası) - 949
- USD (Amerikan Doları) - 840
- EUR (Euro) - 978
- GBP (İngiliz Sterlini) - 826

### API Zaman Aşımı

Varsayılan: 30 saniye
Ayarlar'dan değiştirilebilir

## Sorun Giderme

### "Hash doğrulama başarısız" hatası

1. Mağaza anahtarınızı (Store Key) kontrol edin
2. Hash algoritmasını doğru seçtiğinizden emin olun

### "İşlem bulunamadı" hatası

1. POS Sipariş ID'nin doğru olduğundan emin olun
2. İşlem durumunu kontrol edin

### Bağlantı hatası

1. API URL'lerinin doğru olduğundan emin olun
2. Zaman aşımı süresini artırın
3. Bankanızın API servisinin çalıştığını kontrol edin

## Güvenlik

- API şifreleri şifrelenerek saklanır
- 3D Secure zorunlu tutulabilir
- IP kısıtlaması yapılabilir
- İşlem logları tutulur

## Katkıda Bulunma

Katkılarınızı bekliyoruz! Lütfen:
1. Fork yapın
2. Feature branch oluşturun
3. Değişikliklerinizi commit edin
4. Pull request gönderin

## Lisans

Bu modül LGPL-3 lisansı altında dağıtılmaktadır.

## İletişim

- GitHub: https://github.com/mewebstudio/pos
- Sorunlar: https://github.com/mewebstudio/pos/issues

## Teşekkürler

Bu modül [mewebstudio/pos](https://github.com/mewebstudio/pos) projesinden esinlenerek geliştirilmiştir. 
Tüm katkıda bulunanlara teşekkürler!
