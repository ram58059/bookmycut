import random
import string
from django.utils import timezone
from datetime import timedelta
from .models import Booking, CustomerTrust

def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))

def send_otp_sms(phone, otp):
    # In a real app, integrate with Twilio/SNS here
    print(f"========================================")
    print(f"DTO SENDING SMS TO {phone}: Your OTP is {otp}")
    print(f"========================================")

def send_confirmation_sms(phone, booking_details):
    print(f"========================================")
    print(f"DTO SENDING SMS TO {phone}: Booking Confirmed! {booking_details}")
    print(f"To cancel, click: http://localhost:8000/bookings/cancel/TOKEN (Mock)")
    print(f"========================================")

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def check_rate_limits(phone, ip):
    today = timezone.now().date()
    
    # Check Phone limits : Max 3 bookings per day
    daily_phone_count = Booking.objects.filter(
        customer_phone=phone,
        date=today,
        status__in=['confirmed', 'pending', 'completed']
    ).count()
    
    if daily_phone_count >= 3:
        return False, "Daily booking limit reached for this phone number."
        
    # Check IP limits : Max 3 attempts per day
    # We check created_at for attempts
    start_of_day = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    daily_ip_count = Booking.objects.filter(
        ip_address=ip,
        created_at__gte=start_of_day
    ).exclude(status='cancelled').count()
    
    if daily_ip_count >= 5: # Slightly higher for IP to allow shared wifi
        return False, "Daily booking limit reached from this network."
        
    return True, ""

def update_trust_score(phone, status_change):
    # status_change: 'completed', 'no_show', 'late_cancel'
    # Get or create profile
    profile, created = CustomerTrust.objects.get_or_create(phone_number=phone)
    
    if status_change == 'completed':
        profile.successful_bookings += 1
    elif status_change == 'no_show':
        profile.no_shows += 1
    elif status_change == 'late_cancel':
        profile.late_cancellations += 1
        
    profile.update_trust_score()
    return profile.trust_level
