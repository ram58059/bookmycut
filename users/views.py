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

class AJAXLoginInitiateView(View):
    def post(self, request):
        import json
        from dashboard.models import ShopSetting
        from django.http import JsonResponse
        
        data = json.loads(request.body)
        phone = data.get('phone_number')
        first_name = data.get('first_name', '')
        
        if not phone or len(phone) < 10:
            return JsonResponse({'success': False, 'message': 'Valid phone number is required.'})

        shop_settings = ShopSetting.load()
        
        if shop_settings.is_otp_enabled:
            # Send OTP
            plain_otp = utils.generate_otp()
            hashed_otp = utils.hash_otp(plain_otp)
            
            sms_sent = utils.send_voice_otp_2factor(phone, plain_otp)
            if not sms_sent:
                 print(f"DEBUG: Failed to send Voice OTP for Login. OTP: {plain_otp}")
            
            # Store in session
            request.session['login_phone'] = phone
            request.session['login_first_name'] = first_name
            request.session['login_otp_hash'] = hashed_otp
            request.session['login_otp_created_at'] = str(timezone.now())
            
            return JsonResponse({'success': True, 'require_otp': True})
        else:
            # Login Directly
            user, created = User.objects.get_or_create(phone_number=phone)
            if created:
                user.username = phone
            if first_name:
                user.first_name = first_name
            user.save()
            
            login(request, user)
            return JsonResponse({'success': True, 'require_otp': False})

class AJAXLoginVerifyView(View):
    def post(self, request):
        import json
        from django.http import JsonResponse
        
        data = json.loads(request.body)
        entered_otp = data.get('otp')
        phone = request.session.get('login_phone')
        otp_hash = request.session.get('login_otp_hash')
        
        if not phone or not otp_hash:
            return JsonResponse({'success': False, 'message': 'Session expired. Please try again.'})
            
        if utils.verify_otp_hash(entered_otp, otp_hash):
            user, created = User.objects.get_or_create(phone_number=phone)
            if created:
                user.username = phone
            
            first_name = request.session.get('login_first_name')
            if first_name:
                user.first_name = first_name
            user.save()
            
            login(request, user)
            
            # Cleanup
            if 'login_phone' in request.session: del request.session['login_phone']
            if 'login_otp_hash' in request.session: del request.session['login_otp_hash']
            
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'message': 'Invalid OTP.'})
