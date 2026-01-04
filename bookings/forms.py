from django import forms
from .models import Booking

class GuestDetailsForm(forms.ModelForm):
    class Meta:
        model = Booking
    class Meta:
        model = Booking
        fields = ['customer_phone']
        widgets = {
            'customer_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mobile Number'}),
        }
