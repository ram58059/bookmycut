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
    subject = 'Booking Confirmed - ZionStyle'
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [booking.customer_email]
    
    # Render HTML content
    html_content = render_to_string('emails/booking_confirmation.html', {'booking': booking})
    text_content = strip_tags(html_content)
    
    # Generate Customer ICS
    start_dt = datetime.combine(booking.date, booking.time)
    end_dt = start_dt + timedelta(minutes=60) # Assuming 1 hour per service
    
    # Convert to UTC or use local time with TZID is complex without libraries. 
    # We will use floating time (local) which usually works for single timezone apps, 
    # or simple UTC conversion if timezone is uniform. 
    # Let's try to format as YYYYMMDDTHHMMSS (Floating)
    
    customer_ics = generate_ics_content(
        summary=f"Appointment at ZionStyle: {booking.service.name}",
        description=f"Service: {booking.service.name}\nPrice: {booking.service.price}\nLocation: Zion Salon & Spa, Tirunelveli.",
        start_dt=start_dt,
        end_dt=end_dt,
        location="Zion Salon & Spa, Tirunelveli",
        uid=f"customer-{booking.booking_group_id}-{booking.id}@zionstyle.com"
    )

    try:
        # Customer Email
        msg = EmailMultiAlternatives(subject, text_content, from_email, to)
        msg.attach_alternative(html_content, "text/html")
        msg.attach('invite.ics', customer_ics, 'text/calendar')
        msg.send()
        
        # Admin Notification Email
        admin_subject = f"New Booking: {booking.customer_phone} - {booking.service.name}"
        admin_body = f"Customer: {booking.customer_phone}\nService: {booking.service.name}\nDate: {booking.date}\nTime: {booking.time}"
        
        admin_ics = generate_ics_content(
            summary=f"Booking: {booking.customer_phone} - {booking.service.name}",
            description=f"Customer: {booking.customer_phone}\nService: {booking.service.name}\nEmail: {booking.customer_email}",
            start_dt=start_dt,
            end_dt=end_dt,
            location="Zion Salon & Spa, Tirunelveli",
            uid=f"admin-{booking.booking_group_id}-{booking.id}@zionstyle.com"
        )
        
        admin_msg = EmailMultiAlternatives(admin_subject, admin_body, from_email, [from_email]) # sending to self/admin
        admin_msg.attach('booking.ics', admin_ics, 'text/calendar')
        admin_msg.send()
        
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def generate_ics_content(summary, description, start_dt, end_dt, location, uid):
    """
    Generates iCalendar (RFC 5545) content string.
    """
    # Format dates as YYYYMMDDTHHMMSS
    dt_format = "%Y%m%dT%H%M%S"
    start_str = start_dt.strftime(dt_format)
    end_str = end_dt.strftime(dt_format)
    now_str = datetime.now().strftime(dt_format)
    
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//ZionStyle//Booking System//EN
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{now_str}
DTSTART:{start_str}
DTEND:{end_str}
SUMMARY:{summary}
DESCRIPTION:{description}
LOCATION:{location}
STATUS:CONFIRMED
SEQUENCE:0
END:VEVENT
END:VCALENDAR"""
    return ics_content

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
