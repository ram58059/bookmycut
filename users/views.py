from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.views import View
from django.contrib import messages
from django.utils import timezone
from .forms import PhoneLoginForm, OTPVerifyForm
from .models import User
from bookings import utils  # Reuse existing utils
import uuid

class PhoneLoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('home')
        form = PhoneLoginForm()
        return render(request, 'users/login.html', {'form': form})

    def post(self, request):
        form = PhoneLoginForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data['phone_number']
            first_name = form.cleaned_data['first_name']
            
            # Generate OTP
            plain_otp = utils.generate_otp()
            hashed_otp = utils.hash_otp(plain_otp)
            
            # Send OTP (Reuse utils)
            # Send OTP (Reuse utils)
            sms_sent = utils.send_voice_otp_2factor(phone, plain_otp)
            if not sms_sent:
                 print(f"DEBUG: Failed to send Voice OTP. OTP was: {plain_otp}")
            
            # Store in session
            request.session['login_phone'] = phone
            request.session['login_first_name'] = first_name
            request.session['login_otp_hash'] = hashed_otp
            request.session['login_otp_created_at'] = str(timezone.now())
            
            return redirect('verify_login_otp')
            
        return render(request, 'users/login.html', {'form': form})

class VerifyLoginOTPView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('home')
            
        phone = request.session.get('login_phone')
        if not phone:
            return redirect('login')
            
        form = OTPVerifyForm()
        return render(request, 'users/otp_verify.html', {'form': form, 'phone': phone})

    def post(self, request):
        phone = request.session.get('login_phone')
        otp_hash = request.session.get('login_otp_hash')
        
        if not phone or not otp_hash:
            return redirect('login')
            
        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            entered_otp = form.cleaned_data['otp']
            
            if utils.verify_otp_hash(entered_otp, otp_hash):
                # Valid OTP
                # Get or Create User
                user, created = User.objects.get_or_create(phone_number=phone)
                
                if created:
                    # Set a dummy username if sticking to AbstractUser defaults
                    # but we are using phone_number as effective ID.
                    # AbstractUser requires username.
                    user.username = phone
                    user.first_name = request.session.get('login_first_name', '')
                    user.save()
                else:
                    # Update previously submitted names transparently resolving existing guests
                    new_name = request.session.get('login_first_name')
                    if new_name and user.first_name != new_name:
                        user.first_name = new_name
                        user.save()
                
                login(request, user)
                
                # Cleanup session
                if 'login_phone' in request.session: del request.session['login_phone']
                if 'login_otp_hash' in request.session: del request.session['login_otp_hash']
                
                return redirect('home')
            else:
                form.add_error('otp', 'Invalid OTP')
                
        return render(request, 'users/otp_verify.html', {'form': form, 'phone': phone})

class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect('home')
