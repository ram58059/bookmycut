from django import forms
from .models import Booking

class GuestDetailsForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['customer_phone', 'customer_email']
        widgets = {
            'customer_phone': forms.TextInput(attrs={
                'class': 'w-full p-4 rounded-xl border border-gray-200 bg-gray-50 text-base text-gray-800 transition-all duration-200 focus:outline-none focus:border-yellow-500 focus:bg-white focus:ring-4 focus:ring-yellow-500/10 placeholder-gray-400', 
                'placeholder': 'Mobile Number'
            }),
            'customer_email': forms.EmailInput(attrs={
                'class': 'w-full p-4 rounded-xl border border-gray-200 bg-gray-50 text-base text-gray-800 transition-all duration-200 focus:outline-none focus:border-yellow-500 focus:bg-white focus:ring-4 focus:ring-yellow-500/10 placeholder-gray-400', 
                'placeholder': 'Email Address'
            }),
        }
