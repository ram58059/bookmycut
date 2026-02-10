from django import forms
from django.core.validators import RegexValidator

class PhoneLoginForm(forms.Form):
    phone_number = forms.CharField(
        max_length=15,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")],
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg bg-gray-50 border border-gray-300 focus:border-black focus:ring-0 text-gray-900',
            'placeholder': 'Enter your mobile number',
            'type': 'tel'
        })
    )

class OTPVerifyForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg bg-gray-50 border border-gray-300 focus:border-black focus:ring-0 text-gray-900 text-center tracking-widest text-2xl',
            'placeholder': '• • • • • •',
            'maxlength': '6',
            'autocomplete': 'one-time-code'
        })
    )
