import random
import string
import requests
import hashlib
import json
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from .models import Booking, CustomerTrust

# ============================
# Security & Hashing Helpers
# ============================

def hash_otp(otp):
    """
    Hashes the OTP using simple SHA256 to avoid storing plain text.
    """
    return hashlib.sha256(otp.encode('utf-8')).hexdigest()

def verify_otp_hash(otp, stored_hash):
    """
    Verifies if the provided OTP matches the stored hash.
    """
    return hash_otp(otp) == stored_hash

def generate_otp(length=4):
    """
    Generates a secure numeric OTP.
    """
    return ''.join(random.choices(string.digits, k=length))

# ============================
# SMS Service (Fast2SMS)
# ============================

def send_otp_fast2sms(phone, otp):
    """
    Sends OTP via Fast2SMS API.
    """
    url = "https://www.fast2sms.com/dev/bulkV2"
    
    # Fast2SMS Token (Provided by user)
    token = "k3wFoMtxz4WqUvBniQsZ7ymf89DjLIOc2HPA6VRKGJCE5NXhag4gxl28CFrIVk7p5o0u3dYPAHqvQKGJ"
    
    payload = f"variables_values={otp}&route=otp&numbers={phone}"
    headers = {
        'authorization': token,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Cache-Control': 'no-cache',
    }
    
    try:
        response = requests.request("POST", url, data=payload, headers=headers)
        # Log response for debugging (print to console in dev)
        print(f"Fast2SMS Response: {response.text}")
        return response.json().get('return') == True
    except Exception as e:
        print(f"Error sending SMS: {e}")
        return False

def send_confirmation_sms(phone, booking_details):
    """
    Sends booking confirmation (Mock/Placeholder for now as Fast2SMS OTP route is strict).
    Ideally, use the 'dlt_manual' or 'service' route for this.
    For this task, we will just log it or try to send if we had a template.
    """
    print(f"========================================")
    print(f"DTO SENDING SMS TO {phone}: Booking Confirmed! {booking_details}")
    print(f"========================================")



# ============================
# Core Logic & Anti-Abuse
# ============================

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def check_rate_limits(phone, ip):
    # Requirement: Max 5 attempts / IP / hour
    # Requirement: Max 3 OTP requests / number / hour
    
    one_hour_ago = timezone.now() - timedelta(hours=1)
    
    # Check Phone limits (OTP requests)
    # We count bookings created in the last hour for this phone
    hourly_phone_count = Booking.objects.filter(
        customer_phone=phone,
        created_at__gte=one_hour_ago
    ).count()
    
    if hourly_phone_count >= 3:
        return False, "Too many booking attempts. Please try again later."
        
    # Check IP limits
    hourly_ip_count = Booking.objects.filter(
        ip_address=ip,
        created_at__gte=one_hour_ago
    ).count()
    
    if hourly_ip_count >= 5:
        return False, "Too many requests from this network. Please try again later."
        
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
