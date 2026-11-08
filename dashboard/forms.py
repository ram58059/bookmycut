from django import forms
from bookings.models import Service, Coupon, ComboOffer
from bookings.coupons import normalize_phone


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['name', 'category', 'price', 'duration_minutes', 'gender', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500', 'placeholder': 'Service Name'}),
            'category': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500', 'placeholder': 'Category', 'list': 'category-list'}),
            'price': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500', 'placeholder': 'Price'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500', 'placeholder': 'Duration (min)'}),
            'gender': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500', 'rows': 4, 'placeholder': 'Optional description'}),
        }


class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = [
            'code',
            'discount_type',
            'discount_value',
            'service',
            'customer_phone',
            'is_active',
            'valid_from',
            'valid_until',
        ]
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500 uppercase',
                'placeholder': 'e.g. SAVE20',
            }),
            'discount_type': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
            }),
            'discount_value': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
                'placeholder': 'Discount value',
                'step': '0.01',
                'min': '0',
            }),
            'service': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
            }),
            'customer_phone': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
                'placeholder': 'Start typing a mobile number...',
                'autocomplete': 'off',
                'inputmode': 'numeric',
                'id': 'id_customer_phone',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-amber-500 border-gray-300 rounded focus:ring-amber-500',
            }),
            'valid_from': forms.DateTimeInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
                'type': 'datetime-local',
            }, format='%Y-%m-%dT%H:%M'),
            'valid_until': forms.DateTimeInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
                'type': 'datetime-local',
            }, format='%Y-%m-%dT%H:%M'),
        }
        labels = {
            'code': 'Coupon Code',
            'discount_type': 'Discount Type',
            'discount_value': 'Discount Value',
            'service': 'Apply to Service (optional)',
            'customer_phone': 'Assign to Customer (optional)',
            'is_active': 'Active',
            'valid_from': 'Valid From (optional)',
            'valid_until': 'Valid Until (optional)',
        }
        help_texts = {
            'discount_value': 'Enter percent (e.g. 10 for 10%) or fixed amount in ₹.',
            'service': 'Leave blank for any service. If set, the coupon only works when that service is in the booking.',
            'customer_phone': 'Leave blank for all customers. Type to search existing customer mobile numbers.',
            'valid_from': 'Leave blank to make the coupon available immediately.',
            'valid_until': 'Leave blank if the coupon never expires.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['valid_from'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']
        self.fields['valid_until'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']
        self.fields['valid_from'].required = False
        self.fields['valid_until'].required = False
        self.fields['customer_phone'].required = False
        self.fields['service'].required = False
        self.fields['service'].empty_label = 'All services'

        bookable = Service.bookable().order_by('name')
        if self.instance and self.instance.pk and self.instance.service_id:
            bookable = (bookable | Service.objects.filter(pk=self.instance.service_id)).distinct().order_by('name')
        self.fields['service'].queryset = bookable

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().upper()
        if not code:
            raise forms.ValidationError('Coupon code is required.')
        qs = Coupon.objects.filter(code__iexact=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('A coupon with this code already exists.')
        return code

    def clean_customer_phone(self):
        phone = normalize_phone(self.cleaned_data.get('customer_phone'))
        if not phone:
            return ''
        if len(phone) != 10:
            raise forms.ValidationError('Enter a valid 10-digit mobile number.')
        return phone

    def clean(self):
        cleaned = super().clean()
        discount_type = cleaned.get('discount_type')
        discount_value = cleaned.get('discount_value')
        valid_from = cleaned.get('valid_from')
        valid_until = cleaned.get('valid_until')

        if discount_value is not None:
            if discount_value <= 0:
                self.add_error('discount_value', 'Discount value must be greater than zero.')
            elif discount_type == Coupon.DISCOUNT_PERCENTAGE and discount_value > 100:
                self.add_error('discount_value', 'Percentage discount cannot exceed 100.')

        if valid_from and valid_until and valid_until <= valid_from:
            self.add_error('valid_until', 'Valid until must be after valid from.')

        return cleaned


class ComboOfferForm(forms.ModelForm):
    class Meta:
        model = ComboOffer
        fields = [
            'name',
            'description',
            'duration_minutes',
            'original_price',
            'combo_price',
            'image',
            'badge_text',
            'linked_service',
            'trigger_services',
            'is_active',
            'sort_order',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
                'placeholder': 'Combo service name',
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
                'rows': 3,
                'placeholder': 'Short marketing description shown on the card',
            }),
            'duration_minutes': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
                'min': 1,
            }),
            'original_price': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
                'step': '0.01',
                'min': '0',
            }),
            'combo_price': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
                'step': '0.01',
                'min': '0',
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'w-full text-sm text-gray-600',
            }),
            'badge_text': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
                'placeholder': 'e.g. Hot Deal',
            }),
            'linked_service': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
                'id': 'id_linked_service',
            }),
            'trigger_services': forms.SelectMultiple(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500 min-h-[140px]',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-amber-500 border-gray-300 rounded focus:ring-amber-500',
            }),
            'sort_order': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500',
                'min': 0,
            }),
        }
        labels = {
            'name': 'Service Name',
            'description': 'Description',
            'duration_minutes': 'Duration (minutes)',
            'original_price': 'Original Price (₹)',
            'combo_price': 'Combo Price (₹)',
            'image': 'Image / Icon',
            'badge_text': 'Badge Text',
            'linked_service': 'Bookable Service',
            'trigger_services': 'Show When Customer Selects',
            'is_active': 'Active',
            'sort_order': 'Display Order',
        }
        help_texts = {
            'linked_service': 'The actual service added to the booking when customers tap Add.',
            'trigger_services': 'Hold Ctrl/Cmd to select multiple main services (Haircut, Haircut Shave, etc.).',
            'combo_price': 'Discounted price applied only as a combo with a trigger service.',
            'sort_order': 'Lower numbers appear first in the customer carousel.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bookable = Service.bookable().order_by('name')
        self.fields['linked_service'].queryset = bookable
        self.fields['trigger_services'].queryset = bookable
        self.fields['trigger_services'].required = True

    def clean(self):
        cleaned = super().clean()
        original = cleaned.get('original_price')
        combo = cleaned.get('combo_price')
        if original is not None and original <= 0:
            self.add_error('original_price', 'Original price must be greater than zero.')
        if combo is not None and combo <= 0:
            self.add_error('combo_price', 'Combo price must be greater than zero.')
        if original is not None and combo is not None and combo > original:
            self.add_error('combo_price', 'Combo price should not exceed the original price.')
        triggers = cleaned.get('trigger_services')
        if triggers is not None and len(triggers) == 0:
            self.add_error('trigger_services', 'Select at least one main service that unlocks this combo.')
        return cleaned
