from decimal import Decimal

from django import forms

from bookings.models import Service

from .models import ManualServiceEntry

INPUT_CLASS = (
    'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm '
    'focus:outline-none focus:ring-2 focus:ring-amber-500'
)

# Service.price is DecimalField(max_digits=6, decimal_places=2)
MAX_SERVICE_CATALOG_PRICE = Decimal('9999.99')


class ManualServiceEntryForm(forms.ModelForm):
    service_name = forms.CharField(
        max_length=100,
        label='Service',
        widget=forms.TextInput(
            attrs={
                'class': INPUT_CLASS,
                'id': 'manual-service-name',
                'autocomplete': 'off',
                'placeholder': 'Type to search or enter a custom service',
                'role': 'combobox',
                'aria-autocomplete': 'list',
                'aria-expanded': 'false',
                'aria-controls': 'manual-service-suggestions',
            }
        ),
    )

    class Meta:
        model = ManualServiceEntry
        fields = ['quantity', 'unit_price', 'date']
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'id': 'manual-quantity'}),
            'unit_price': forms.NumberInput(
                attrs={'class': INPUT_CLASS, 'step': '0.01', 'min': '0', 'id': 'manual-unit-price'}
            ),
            'date': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date', 'id': 'manual-date'}),
        }

    def __init__(self, *args, selected_date=None, **kwargs):
        super().__init__(*args, **kwargs)
        if selected_date:
            self.fields['date'].initial = selected_date
        if self.instance and self.instance.pk and self.instance.service_id:
            self.fields['service_name'].initial = self.instance.service.name

    def clean_service_name(self):
        name = (self.cleaned_data.get('service_name') or '').strip()
        if not name:
            raise forms.ValidationError('Enter a service name.')
        return name

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity is not None and quantity < 1:
            raise forms.ValidationError('Quantity must be at least 1.')
        return quantity

    def clean_unit_price(self):
        unit_price = self.cleaned_data.get('unit_price')
        if unit_price is not None and unit_price < 0:
            raise forms.ValidationError('Unit price cannot be negative.')
        return unit_price

    def _resolve_service(self, name, unit_price):
        existing = Service.objects.filter(name__iexact=name).order_by('id').first()
        if existing:
            return existing
        catalog_price = unit_price if unit_price <= MAX_SERVICE_CATALOG_PRICE else MAX_SERVICE_CATALOG_PRICE
        return Service.objects.create(
            name=name,
            price=catalog_price,
            duration_minutes=0,
            category=Service.FINANCE_MANUAL_CATEGORY,
            description='Added from Finance additional services',
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.service = self._resolve_service(
            self.cleaned_data['service_name'],
            self.cleaned_data['unit_price'],
        )
        if commit:
            instance.save()
        return instance
