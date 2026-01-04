import os
import django
from django.test import Client
from django.test.utils import setup_test_environment

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
setup_test_environment()

from bookings.models import Service, Booking
from datetime import date, time, timedelta
from django.utils import timezone

def verify():
    c = Client()
    
    print("1. Testing Service Selection...")
    services = Service.objects.all()
    if not services.exists():
        print("No services found! Run populate_services.py")
        return
        
    s1 = services[0]
    s2 = services[1]
    
    # POST select services
    response = c.post('/bookings/book/', {
        'services': [s1.id, s2.id]
    })
    
    if response.status_code == 302 and response.url == '/bookings/book/calendar/':
        print("Service selection successful (redirected).")
    else:
        print(f"Service selection failed. Status: {response.status_code}")
        return
        
    session = c.session
    if 'selected_service_ids' in session:
        print(f"Session has services: {session['selected_service_ids']}")
    else:
        print("Session missing services!")
        return

    print("\n2. Testing Date/Time Selection...")
    # Choose a date tomorrow
    tomorrow = timezone.now().date() + timedelta(days=1)
    
    # GET with date to see slots
    response = c.get('/bookings/book/calendar/', {'date': str(tomorrow)})
    if response.status_code == 200:
        print("Calendar page loaded with date.")
        # We can check context for slots
        slots = response.context.get('slots')
        if slots:
            print(f"Found {len(slots)} available slots.")
            chosen_time = slots[0] # e.g. 10:00
        else:
            print("No slots found! Check allocation logic.")
            # force a time for testing valid post
            chosen_time = time(10, 0)
    else:
        print(f"Calendar page failed. Status: {response.status_code}")
        return

    # POST selection
    response = c.post('/bookings/book/calendar/', {
        'date': str(tomorrow),
        'time': chosen_time.strftime('%H:%M')
    })
    
    if response.status_code == 302 and response.url == '/bookings/book/confirm/':
        print("Date/Time selection successful (redirected).")
    else:
        print(f"Date/Time selection failed. Status: {response.status_code}")
        return

    print("\n3. Testing Confirmation...")
    # POST confirmation
    response = c.post('/bookings/book/confirm/', {
        'customer_phone': '9876543210',
        'customer_gender': 'Male'
    })
    
    if response.status_code == 302 and response.url == '/bookings/book/success/':
        print("Confirmation successful (redirected).")
    else:
        print(f"Confirmation failed. Status: {response.status_code}")
        print(response.content) # Debug
        return
        
    # Verify DB
    booking = Booking.objects.last()
    if booking and booking.customer_phone == '9876543210' and booking.date == tomorrow:
        print(f"Booking verified in DB: {booking}")
        print(f"Services: {list(booking.services.all())}")
        if booking.services.count() == 2:
            print("Correct number of services linked.")
        else:
            print("Incorrect service count.")
    else:
        print("Booking NOT found or incorrect in DB.")

if __name__ == '__main__':
    verify()
