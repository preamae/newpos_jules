odoo.define('turkey_pos_payment.installment_calculator', function (require) {
    'use strict';

    const publicWidget = require('web.public.widget');
    const ajax = require('web.ajax');
    const core = require('web.core');
    const _t = core._t;

    // Kart BIN numarasına göre banka tespiti
    const CARD_BIN_RANGES = {
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
    };

    // Kart markası tespiti
    function detectCardBrand(cardNumber) {
        const patterns = {
            'visa': /^4/,
            'mastercard': /^5[1-5]|^2[2-7]/,
            'amex': /^3[47]/,
            'troy': /^9792|^9793|^65/,
        };
        
        for (const [brand, pattern] of Object.entries(patterns)) {
            if (pattern.test(cardNumber)) {
                return brand;
            }
        }
        return 'unknown';
    }

    // Kart numarasından banka tespiti
    function detectBankFromCard(cardNumber) {
        const bin = cardNumber.replace(/\s/g, '').substring(0, 6);
        
        for (const [bank, bins] of Object.entries(CARD_BIN_RANGES)) {
            if (bins.includes(bin)) {
                return bank;
            }
        }
        return null;
    }

    // Kart numarası formatlama
    function formatCardNumber(value) {
        return value.replace(/\s/g, '').replace(/(\d{4})(?=\d)/g, '$1 ').trim();
    }

    // Ürün sayfası taksit widget'ı
    publicWidget.registry.ProductInstallments = publicWidget.Widget.extend({
        selector: '#product_installments_section',
        
        start: function () {
            this._super.apply(this, arguments);
            this.productId = this.$el.closest('form').find('input[name="product_id"]').val();
            this.productPrice = parseFloat(this.$el.closest('form').find('.oe_price .oe_currency_value').first().text().replace(',', '.')) || 0;
            this._bindEvents();
            this._loadInstallments();
        },

        _bindEvents: function () {
            var self = this;
            
            // Kart numarası input'u ekle
            var cardInputHtml = `
                <div class="form-group mt-3">
                    <label for="installment-card-number">Kart Numarası (Taksit seçeneklerini görmek için)</label>
                    <input type="text" class="form-control" id="installment-card-number" 
                           placeholder="1234 5678 9012 3456" maxlength="19"/>
                    <small class="form-text text-muted" id="installment-card-info"></small>
                </div>
            `;
            this.$('#installment-content').prepend(cardInputHtml);
            
            // Kart numarası değişikliği
            this.$el.on('input', '#installment-card-number', function (ev) {
                var value = $(this).val().replace(/\D/g, '').substring(0, 16);
                $(this).val(formatCardNumber(value));
                
                if (value.length >= 6) {
                    self._onCardNumberChange(value);
                }
            });
        },

        _onCardNumberChange: function (cardNumber) {
            var self = this;
            var bank = detectBankFromCard(cardNumber);
            var brand = detectCardBrand(cardNumber);
            
            // Kart bilgisi göster
            var cardInfo = '';
            if (brand !== 'unknown') {
                cardInfo += '<span class="badge badge-info mr-2">' + brand.toUpperCase() + '</span>';
            }
            
            if (bank) {
                cardInfo += '<span class="badge badge-success">' + bank.toUpperCase() + '</span>';
                this.$('#installment-info').hide();
                this._loadBankInstallments(bank, this.productPrice);
            } else {
                cardInfo += '<span class="badge badge-warning">Tanımlanamayan Banka</span>';
                this.$('#installment-info').html(
                    'Bu kart için taksit seçeneği bulunamadı. <strong>Varsayılan banka</strong> ile tek çekim ödeme yapabilirsiniz.'
                ).show();
                this._loadDefaultInstallments(this.productPrice);
            }
            
            this.$('#installment-card-info').html(cardInfo);
        },

        _loadInstallments: function () {
            this.$('#installment-loading').hide();
            this.$('#installment-content').show();
        },

        _loadBankInstallments: function (bankCode, amount) {
            var self = this;
            
            ajax.jsonRpc('/payment/turkey_pos/get_product_installments', 'call', {
                'bank_code': bankCode,
                'amount': amount,
                'product_id': this.productId
            }).then(function (result) {
                if (result.success) {
                    self._renderInstallmentTable(result.installments, amount);
                } else {
                    self._loadDefaultInstallments(amount);
                }
            }).catch(function () {
                self._loadDefaultInstallments(amount);
            });
        },

        _loadDefaultInstallments: function (amount) {
            var self = this;
            
            ajax.jsonRpc('/payment/turkey_pos/get_default_installments', 'call', {
                'amount': amount
            }).then(function (result) {
                if (result.success) {
                    self._renderInstallmentTable(result.installments, amount, true);
                }
            });
        },

        _renderInstallmentTable: function (installments, amount, isDefault) {
            var html = '<table class="table table-bordered table-striped">';
            html += '<thead><tr>';
            html += '<th>Taksit</th>';
            html += '<th>Aylık Tutar</th>';
            html += '<th>Toplam</th>';
            if (!isDefault) {
                html += '<th>Komisyon</th>';
            }
            html += '</tr></thead><tbody>';
            
            // Tek çekim her zaman ekle
            html += '<tr>';
            html += '<td>Tek Çekim</td>';
            html += '<td>' + this._formatCurrency(amount) + '</td>';
            html += '<td>' + this._formatCurrency(amount) + '</td>';
            if (!isDefault) html += '<td>-</td>';
            html += '</tr>';
            
            // Taksit seçenekleri
            if (installments && installments.length > 0) {
                installments.forEach(function (inst) {
                    html += '<tr>';
                    html += '<td>' + inst.count + ' Taksit</td>';
                    html += '<td>' + self._formatCurrency(inst.monthly_amount) + '</td>';
                    html += '<td>' + self._formatCurrency(inst.total_amount) + '</td>';
                    if (!isDefault) html += '<td>%' + inst.commission_rate + '</td>';
                    html += '</tr>';
                });
            }
            
            html += '</tbody></table>';
            
            if (isDefault) {
                html = '<div class="alert alert-info">Varsayılan banka ile tek çekim ödeme</div>' + html;
            }
            
            this.$('#installment-table-container').html(html);
        },

        _formatCurrency: function (amount) {
            return parseFloat(amount).toLocaleString('tr-TR', {
                style: 'currency',
                currency: 'TRY'
            });
        }
    });

    // Ödeme sayfası widget'ı
    publicWidget.registry.PaymentPosOptions = publicWidget.Widget.extend({
        selector: '#payment-pos-options',
        
        start: function () {
            this._super.apply(this, arguments);
            this.cartTotal = parseFloat($('#order_total .oe_currency_value').first().text().replace(/\./g, '').replace(',', '.')) || 0;
            this.selectedInstallment = 1;
            this.installmentFee = 0;
            this._bindEvents();
        },

        _bindEvents: function () {
            var self = this;
            
            // Kart numarası formatlama
            this.$el.on('input', '#pos-card-number', function (ev) {
                var value = $(this).val().replace(/\D/g, '').substring(0, 16);
                $(this).val(formatCardNumber(value));
                
                if (value.length >= 6) {
                    self._onCardNumberChange(value);
                }
            });
            
            // Son kullanma tarihi formatlama
            this.$el.on('input', '#pos-card-expiry', function (ev) {
                var value = $(this).val().replace(/\D/g, '').substring(0, 4);
                if (value.length >= 2) {
                    value = value.substring(0, 2) + '/' + value.substring(2);
                }
                $(this).val(value);
            });
            
            // CVV sadece sayı
            this.$el.on('input', '#pos-card-cvv', function (ev) {
                $(this).val($(this).val().replace(/\D/g, '').substring(0, 4));
            });
            
            // Banka seçimi
            this.$el.on('change', '#pos-bank-selection', function (ev) {
                var providerId = $(this).val();
                if (providerId) {
                    self._loadInstallmentOptions(providerId);
                } else {
                    self.$('#pos-installment-group').hide();
                }
            });
            
            // Taksit seçimi
            this.$el.on('change', '#pos-installment-count', function (ev) {
                var option = $(this).find('option:selected');
                var fee = parseFloat(option.data('fee')) || 0;
                var total = parseFloat(option.data('total')) || self.cartTotal;
                
                self.selectedInstallment = parseInt($(this).val()) || 1;
                self.installmentFee = fee;
                
                if (fee > 0) {
                    self.$('#pos-fee-amount').text(fee.toLocaleString('tr-TR', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                    }));
                    self.$('#pos-installment-fee-warning').show();
                    self._updateCartTotalWithFee(fee);
                } else {
                    self.$('#pos-installment-fee-warning').hide();
                    self._resetCartTotal();
                }
                
                // Taksit detaylarını göster
                var detailsHtml = '';
                if (self.selectedInstallment > 1) {
                    var monthly = total / self.selectedInstallment;
                    detailsHtml = '<strong>' + self.selectedInstallment + ' Taksit:</strong> ' +
                                  monthly.toLocaleString('tr-TR', {style: 'currency', currency: 'TRY'}) + ' x ' +
                                  self.selectedInstallment + ' ay = ' +
                                  total.toLocaleString('tr-TR', {style: 'currency', currency: 'TRY'});
                } else {
                    detailsHtml = '<strong>Tek Çekim:</strong> ' +
                                  self.cartTotal.toLocaleString('tr-TR', {style: 'currency', currency: 'TRY'});
                }
                self.$('#pos-installment-details').html(detailsHtml).show();
            });
        },

        _onCardNumberChange: function (cardNumber) {
            var bank = detectBankFromCard(cardNumber);
            var brand = detectCardBrand(cardNumber);
            
            // Kart markası göster
            var brandHtml = '';
            if (brand !== 'unknown') {
                brandHtml = '<span class="badge badge-info">' + brand.toUpperCase() + '</span>';
            }
            this.$('#pos-card-brand').html(brandHtml);
            
            // Banka otomatik seç
            if (bank) {
                var $option = this.$('#pos-bank-selection option[data-code="' + bank + '"]');
                if ($option.length) {
                    this.$('#pos-bank-selection').val($option.val()).trigger('change');
                } else {
                    // Banka bulunamadı, varsayılanı seç
                    this._selectDefaultBank();
                }
            }
        },

        _selectDefaultBank: function () {
            var self = this;
            ajax.jsonRpc('/payment/turkey_pos/get_default_provider', 'call', {}).then(function (result) {
                if (result.provider_id) {
                    self.$('#pos-bank-selection').val(result.provider_id).trigger('change');
                }
            });
        },

        _loadInstallmentOptions: function (providerId) {
            var self = this;
            
            ajax.jsonRpc('/payment/turkey_pos/installment_options', 'call', {
                'provider_id': providerId,
                'amount': this.cartTotal
            }).then(function (result) {
                if (result.success && result.options) {
                    self._renderInstallmentOptions(result.options);
                    self.$('#pos-installment-group').show();
                } else {
                    // Taksit seçeneği yok, sadece tek çekim
                    self.$('#pos-installment-count').html('<option value="1">Tek Çekim</option>');
                    self.$('#pos-installment-group').show();
                }
            });
        },

        _renderInstallmentOptions: function (options) {
            var html = '<option value="1" data-fee="0" data-total="' + this.cartTotal + '">Tek Çekim</option>';
            
            options.forEach(function (opt) {
                html += '<option value="' + opt.installment_count + '" ' +
                        'data-fee="' + (opt.commission_amount || 0) + '" ' +
                        'data-total="' + opt.total_amount + '">' +
                        opt.installment_count + ' Taksit - ' +
                        opt.monthly_amount.toLocaleString('tr-TR', {style: 'currency', currency: 'TRY'}) + ' x ' + opt.installment_count +
                        (opt.commission_amount > 0 ? ' (+' + opt.commission_amount.toLocaleString('tr-TR', {style: 'currency', currency: 'TRY'}) + ')' : '') +
                        '</option>';
            });
            
            this.$('#pos-installment-count').html(html);
        },

        _updateCartTotalWithFee: function (fee) {
            // Sepet toplamını güncelle (taksit farkını ekle)
            var newTotal = this.cartTotal + fee;
            $('#order_total .oe_currency_value').text(newTotal.toLocaleString('tr-TR', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }));
            
            // Gizli input'a ekle
            if (!$('input[name="installment_fee"]').length) {
                $('form[action="/shop/payment/transaction"]').append(
                    '<input type="hidden" name="installment_fee" value="' + fee + '"/>'
                );
            } else {
                $('input[name="installment_fee"]').val(fee);
            }
        },

        _resetCartTotal: function () {
            $('#order_total .oe_currency_value').text(this.cartTotal.toLocaleString('tr-TR', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }));
            $('input[name="installment_fee"]').val(0);
        }
    });

    return {
        detectCardBrand: detectCardBrand,
        detectBankFromCard: detectBankFromCard,
        formatCardNumber: formatCardNumber
    };
});
