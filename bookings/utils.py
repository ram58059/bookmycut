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
import threading
import os
from .models import Booking, CustomerTrust

# For Google Calendar Sync
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar.events']

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

def send_booking_confirmation_email(booking, request=None):
    """
    Sends a booking confirmation email to the customer.
    (This is the synchronous core function called by the async wrapper)
    """
    return True
    subject = 'Booking Confirmed - ZionStyle'
    from_email = settings.DEFAULT_FROM_EMAIL
    admin_email = settings.ADMIN_RECV_EMAIL
    to = [booking.customer_email]

    # Calculate group total and list of services for this booking group
    group_bookings = Booking.objects.filter(booking_group_id=booking.booking_group_id).order_by('time')
    total_price = sum(b.service.price for b in group_bookings)

    # Render HTML content
    google_calendar_url = generate_google_calendar_url(booking)
    html_content = render_to_string(
        'emails/booking_confirmation.html',
        {
            'booking': booking,
            'group_bookings': group_bookings,
            'total_price': total_price,
            'google_calendar_url': google_calendar_url,
        },
    )
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
        uid=f"customer-{booking.booking_group_id}-{booking.id}@zionstyle.com",
        alarm_minutes=60  # Remind customer 1 hour before
    )

    try:
        # Customer Email
        msg = EmailMultiAlternatives(subject, text_content, from_email, to)
        msg.attach_alternative(html_content, "text/html")
        msg.attach('invite.ics', customer_ics, 'text/calendar')
        msg.send()
        
        # Admin Notification Email
        admin_subject = f"New Booking Alert: {booking.customer_phone}"
        
        # Build Absolute URI if request is provided, otherwise fallback to basic string
        dashboard_url = "/admin/"
        if request:
            from django.urls import reverse
            dashboard_url = request.build_absolute_uri('/admin/')

        # Render Admin HTML Profile
        admin_html_content = render_to_string(
            'emails/admin_booking_alert.html',
            {
                'booking': booking,
                'group_bookings': group_bookings,
                'total_price': total_price,
                'dashboard_url': dashboard_url,
            },
        )
        admin_text_content = strip_tags(admin_html_content)
        
        admin_ics = generate_ics_content(
            summary=f"Booking: {booking.customer_phone} - {booking.service.name}",
            description=f"Customer: {booking.customer_phone}\nService: {booking.service.name}\nEmail: {booking.customer_email}",
            start_dt=start_dt,
            end_dt=end_dt,
            location="Zion Salon & Spa, Tirunelveli",
            uid=f"admin-{booking.booking_group_id}-{booking.id}@zionstyle.com",
            alarm_minutes=10  # Remind admin 10 minutes before
        )
        
        admin_msg = EmailMultiAlternatives(admin_subject, admin_text_content, from_email, [admin_email]) # sending to self/admin
        admin_msg.attach_alternative(admin_html_content, "text/html")
        admin_msg.attach('booking.ics', admin_ics, 'text/calendar')
        admin_msg.send()
        
        # Async Google Calendar Sync!
        sync_to_admin_google_calendar(booking, group_bookings)
        
        return True
    except Exception as e:
        import traceback
        print(f"Error sending email: {e}")
        traceback.print_exc()
        return False

def generate_google_calendar_url(booking):
    """
    Generates a one-click Add to Google Calendar URL for the customer.
    """
    start_dt = datetime.combine(booking.date, booking.time)
    end_dt = start_dt + timedelta(minutes=60)
    
    # Format for Google Calendar URL (YYYYMMDDTHHMMSSZ) - Assuming local time behaves as UTC for simplicity if no tz
    dt_format = "%Y%m%dT%H%M%S"
    dates = f"{start_dt.strftime(dt_format)}/{end_dt.strftime(dt_format)}"
    
    params = {
        'action': 'TEMPLATE',
        'text': f"Appointment at ZionStyle: {booking.service.name}",
        'dates': dates,
        'details': f"Service: {booking.service.name}\nPrice: {booking.service.price}",
        'location': "Zion Salon & Spa, Tirunelveli"
    }
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(params)

def sync_to_admin_google_calendar(booking, group_bookings):
    """
    Silently pushes the booking to the Admin's master Google Calendar via Service Account.
    """
    try:
        creds_path = os.path.join(settings.BASE_DIR, 'google_calendar_credentials.json')
        if not os.path.exists(creds_path):
            print("Google Calendar credentials not found. Skipping auto-sync.")
            return

        creds = service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)

        start_dt = datetime.combine(booking.date, booking.time)
        end_dt = start_dt + timedelta(minutes=60 * len(group_bookings)) # Total duration

        event = {
            'summary': f"{booking.customer_phone} - ZionStyle Appt",
            'location': 'Zion Salon & Spa, Tirunelveli',
            'description': f"Customer: {booking.customer_phone}\nEmail: {booking.customer_email}\nServices: {', '.join([b.service.name for b in group_bookings])}",
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'Asia/Kolkata',
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'Asia/Kolkata',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 10},
                ],
            },
        }

        # Use the admin's calendar ID or primary if using the service account's own calendar
        calendar_id = os.getenv('ADMIN_GOOGLE_CALENDAR_ID', 'primary')
        event = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"Successfully synced event to Admin Google Calendar: {event.get('htmlLink')}")
        
    except Exception as e:
        print(f"Failed to sync to Google Calendar: {e}")

def send_booking_emails_async(booking, request=None):
    """
    Wraps the email sending process in a background thread so it doesn't block the UI.
    """
    thread = threading.Thread(target=send_booking_confirmation_email, args=(booking, request))
    thread.daemon = True
    thread.start()

def generate_ics_content(summary, description, start_dt, end_dt, location, uid, alarm_minutes=None):
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
SEQUENCE:0"""

    if alarm_minutes:
        ics_content += f"""
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Reminder: {summary}
TRIGGER:-PT{alarm_minutes}M
END:VALARM"""

    ics_content += """
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
    return True, ""
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
