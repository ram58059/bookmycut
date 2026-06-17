from django import forms

from bookings.models import Service

from .models import ManualServiceEntry

INPUT_CLASS = (
    'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm '
    'focus:outline-none focus:ring-2 focus:ring-amber-500'
)


class ManualServiceEntryForm(forms.ModelForm):
    class Meta:
        model = ManualServiceEntry
        fields = ['service', 'quantity', 'unit_price', 'date']
        widgets = {
            'service': forms.Select(attrs={'class': INPUT_CLASS, 'id': 'manual-service-select'}),
            'quantity': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'id': 'manual-quantity'}),
            'unit_price': forms.NumberInput(
                attrs={'class': INPUT_CLASS, 'step': '0.01', 'min': '0', 'id': 'manual-unit-price'}
            ),
            'date': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date', 'id': 'manual-date'}),
        }

    def __init__(self, *args, selected_date=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['service'].queryset = Service.objects.order_by('category', 'name')
        if selected_date:
            self.fields['date'].initial = selected_date
        if not self.instance.pk and not self.is_bound:
            service = self.initial.get('service') or self.fields['service'].initial
            if service:
                try:
                    svc = Service.objects.get(pk=service) if not isinstance(service, Service) else service
                    self.fields['unit_price'].initial = svc.price
                except Service.DoesNotExist:
                    pass

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
