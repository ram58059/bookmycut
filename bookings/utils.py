import random
import string
import requests
import hashlib
import json
from django.utils import timezone
from django.utils import timezone
from datetime import timedelta, datetime
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import urllib.parse
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
# Voice OTP Service (2factor.in)
# ============================

def send_voice_otp_2factor(phone, otp):
    """
    Sends OTP via Voice Call using 2factor.in API.
    """
    api_key = "a77e1e1a-fa06-11f0-a6b2-0200cd936042"
    
    # 2factor.in requires phone number. check if we need country code.
    # Usually it handles it, or we assume +91.
    
    url = f"https://2factor.in/API/V1/{api_key}/VOICE/{phone}/{otp}"
    
    try:
        response = requests.get(url)
        # print(f"2Factor Voice Response: {response.text}") # Optional logging
        data = response.json()
        if data.get('Status') == 'Success':
            return True
        return False
    except Exception as e:
        print(f"Error sending Voice OTP: {e}")
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

def send_booking_confirmation_email(booking):
    """
    Sends a booking confirmation email to the customer.
    """
    subject = 'Booking Confirmation - BookMyCut'
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [booking.customer_email]
    
    # Simple text content for now, can be enhanced with HTML template
    text_content = f"""
    Dear Customer,
    
    Your booking with BookMyCut has been confirmed!
    
    Service: {booking.service.name}
    Date: {booking.date}
    Time: {booking.time}
    Price: ₹{booking.service.price}
    
    Thank you for choosing us!
    
    Regards,
    The BookMyCut Team
    """
    
    try:
        msg = EmailMultiAlternatives(subject, text_content, from_email, to)
        msg.send()
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

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
