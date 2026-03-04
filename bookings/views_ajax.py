from django.views import View
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.db import transaction, IntegrityError
from datetime import datetime, time, timedelta
import uuid
import json
from .models import Service, Booking, CustomerTrust
from . import utils

# ========================
# AJAX Views for Voice OTP
# ========================

class InitiateBookingView(View):
    def post(self, request):
        try:
            try:
                data = json.loads(request.body)
                phone = data.get('customer_phone')
                email = data.get('customer_email')
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'message': 'Invalid data'})

            if not phone:
                 return JsonResponse({'success': False, 'message': 'Phone number is required.'})

            # Basic Validation
            if len(phone) < 10:
                 return JsonResponse({'success': False, 'message': 'Invalid phone number.'})
                 
            # Rate Limiting
            ip = utils.get_client_ip(request)
            allowed, message = utils.check_rate_limits(phone, ip)
            if not allowed:
                return JsonResponse({'success': False, 'message': message})

            # Retrieve session data
            selected_service_ids = request.session.get('selected_service_ids')
            date_str = request.session.get('selected_date')
            time_str = request.session.get('selected_time')
            selected_gender = request.session.get('selected_gender', 'Male')
            
            if not (selected_service_ids and date_str and time_str):
                return JsonResponse({'success': False, 'message': 'Session expired. Please start over.', 'redirect': reverse('service_list')})
                
            services = Service.objects.filter(id__in=selected_service_ids)
            
            # Check Trust Score
            is_trusted = False
            trust_profile = CustomerTrust.objects.filter(phone_number=phone).first()
            if trust_profile and trust_profile.trust_level != 'low':
                is_trusted = True
                
            # Check Global Shop Setting for OTP Bypass
            from dashboard.models import ShopSetting
            shop_settings = ShopSetting.load()
            if not shop_settings.is_otp_enabled:
                is_trusted = True
                
            group_id = uuid.uuid4()
            plain_otp = utils.generate_otp()
            hashed_otp = utils.hash_otp(plain_otp)
            now_time = timezone.now()
            
            # Trusted users: confirm immediately; guests: pending OTP
            initial_status = 'confirmed' if is_trusted else 'pending_otp'
            is_initial_verified = True if is_trusted else False
            
            start_time_obj = datetime.strptime(time_str, '%H:%M:%S').time() if len(time_str) > 5 else datetime.strptime(time_str, '%H:%M').time()
            start_hour = start_time_obj.hour
            
            # Create Bookings
            try:
                with transaction.atomic():
                    bookings_created = []
                    for idx, service_id in enumerate(selected_service_ids):
                        service = services.get(id=service_id)
                        booking_time = time(start_hour + idx, 0)
                        
                        booking = Booking(
                            customer_phone=phone,
                            customer_email=email,
                            customer_gender=selected_gender,
                            service=service,
                            booking_group_id=group_id,
                            date=date_str,
                            time=booking_time,
                            status=initial_status,
                            ip_address=ip,
                            otp=hashed_otp if not is_trusted else None,
                            otp_created_at=now_time if not is_trusted else None,
                            is_verified=is_initial_verified
                        )
                        booking.save()
                        bookings_created.append(booking)
                        
            except IntegrityError:
                return JsonResponse({'success': False, 'message': 'Time slot already booked.'})
            
            # Response Handling
            if is_trusted:
                # Provide auto-login if they bypassed OTP via setting or trust but were not logged in
                if not request.user.is_authenticated and phone and len(phone) > 5:
                    from django.contrib.auth import login
                    from users.models import User
                    try:
                        user, created = User.objects.get_or_create(phone_number=phone)
                        if created:
                            user.username = phone
                            user.save()
                        login(request, user)
                    except Exception as e:
                        print(f"Auto-login failed after bypass: {e}")

                # Immediately confirm and notify
                bookings = Booking.objects.filter(booking_group_id=group_id)
                for b in bookings:
                    if b.customer_email:
                        utils.send_booking_emails_async(b, request)

                first_booking = bookings.first()
                if first_booking:
                    utils.send_confirmation_sms(first_booking.customer_phone, f"Confirmed! Date: {first_booking.date} Time: {first_booking.time}")

                request.session['last_booking_group_id'] = str(group_id)

                # Clear session
                if 'selected_service_ids' in request.session: del request.session['selected_service_ids']
                if 'selected_date' in request.session: del request.session['selected_date']
                if 'selected_time' in request.session: del request.session['selected_time']

                return JsonResponse({'success': True, 'trusted': True, 'redirect': reverse('booking_success')})
            else:
                 # Send Voice OTP
                 sent = utils.send_voice_otp_2factor(phone, plain_otp)
                 if not sent:
                     return JsonResponse({'success': False, 'message': 'Failed to send OTP. Please try again.'})
                 
                 request.session['pending_group_id'] = str(group_id)
                 return JsonResponse({
                     'success': True, 
                     'trusted': False, 
                     'group_id': str(group_id),
                     'otp_expiry': 300 # 5 mins
                 })
                 
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Server error: {str(e)}'})

class VerifyBookingOTPView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            group_id = data.get('group_id')
            entered_otp = data.get('otp')
        except:
             return JsonResponse({'success': False, 'message': 'Invalid data'})
             
        if not group_id or not entered_otp:
            return JsonResponse({'success': False, 'message': 'Missing OTP or ID'})
            
        bookings = Booking.objects.filter(booking_group_id=group_id)
        if not bookings.exists():
            return JsonResponse({'success': False, 'message': 'Booking not found.'})
            
        booking = bookings.first()
        
        if booking.status == 'confirmed':
             return JsonResponse({'success': True, 'message': 'Already confirmed'})
             
        if booking.is_otp_expired():
             return JsonResponse({'success': False, 'message': 'OTP Expired.'})
             
        if utils.verify_otp_hash(entered_otp, booking.otp):
            # Success: OTP verified -> mark confirmed
            bookings.update(is_verified=True, status='confirmed')

            # Send notifications
            for b in bookings:
                if b.customer_email:
                    utils.send_booking_emails_async(b, request)

            first_booking = bookings.first()
            if first_booking:
                utils.send_confirmation_sms(first_booking.customer_phone, f"Confirmed! Date: {first_booking.date} Time: {first_booking.time}")

            request.session['last_booking_group_id'] = group_id
            if 'pending_group_id' in request.session:
                del request.session['pending_group_id']

            # Clear selection data
            k = ['selected_service_ids', 'selected_date', 'selected_time']
            for key in k:
                if key in request.session: del request.session[key]

            return JsonResponse({'success': True, 'redirect': reverse('booking_success')})
        else:
            return JsonResponse({'success': False, 'message': 'Incorrect OTP.'})

class ResendOTPView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            group_id = data.get('group_id')
        except:
             return JsonResponse({'success': False})

        bookings = Booking.objects.filter(booking_group_id=group_id)
        if not bookings.exists():
             return JsonResponse({'success': False, 'message': 'Booking not found'})
             
        booking = bookings.first()
        if booking.status == 'confirmed':
             return JsonResponse({'success': False, 'message': 'Already confirmed'})
             
        # Generate new OTP
        plain_otp = utils.generate_otp()
        hashed_otp = utils.hash_otp(plain_otp)
        
        bookings.update(otp=hashed_otp, otp_created_at=timezone.now())
        
        sent = utils.send_voice_otp_2factor(booking.customer_phone, plain_otp)
        if sent:
            return JsonResponse({'success': True})
        else:
             return JsonResponse({'success': False, 'message': 'Failed to send OTP'})
