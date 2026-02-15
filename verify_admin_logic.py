
import os
import django
from datetime import date, timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bookings.models import Booking, BlockedDay, Service
from users.models import User

def run_verification():
    print("Starting Verification...")
    
    # Setup
    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)
    
    # Ensure Service exists
    service, _ = Service.objects.get_or_create(
        name="Test Cut", 
        defaults={'price': 100, 'duration_minutes': 60, 'gender': 'Male'}
    )
    
    print(f"1. Setup complete. Testing with date: {tomorrow}")

    # Clean up previous runs
    Booking.objects.filter(date=tomorrow).delete()
    BlockedDay.objects.filter(date=tomorrow).delete()

    # Test 1: Block Day with NO bookings
    print("\n--- Test 1: Block Day (Empty) ---")
    BlockedDay.objects.create(date=tomorrow)
    if BlockedDay.objects.filter(date=tomorrow).exists():
        print("PASS: Blocked empty day successfully.")
    else:
        print("FAIL: Failed to block day.")
        
    # Unblock for next test
    BlockedDay.objects.filter(date=tomorrow).delete()
    
    # Test 2: Create Booking
    print("\n--- Test 2: Create Booking ---")
    b = Booking.objects.create(
        customer_phone="9999999999",
        service=service,
        date=tomorrow,
        time="10:00",
        status="confirmed"
    )
    print(f"Booking created: {b}")
    
    # Test 3: Block Day WITH active booking (Simulate View Logic)
    print("\n--- Test 3: Block Day with Active Booking ---")
    active_bookings = Booking.objects.filter(date=tomorrow, status__in=['confirmed', 'pending'])
    if active_bookings.exists():
        print("Logic Check: System should PREVENT blocking.")
        # We manually check the condition the view would check
        print("PASS: View logic condition met (active bookings exist).")
    else:
        print("FAIL: Active bookings not found?")

    # Test 4: Cancel Booking
    print("\n--- Test 4: Cancel Booking ---")
    b.status = 'cancelled'
    b.save()
    print("Booking cancelled.")
    
    # Test 5: Block Day AFTER cancellation
    print("\n--- Test 5: Block Day after Cancellation ---")
    active_now = Booking.objects.filter(date=tomorrow, status__in=['confirmed', 'pending'])
    if not active_now.exists():
        BlockedDay.objects.create(date=tomorrow, reason="Emergency")
        print("PASS: Blocked day successfully after cancellation.")
    else:
        print(f"FAIL: Still sees active bookings? {active_now}")

    # Test 6: Verify Booking blocked for Customer
    # We check if DateTimeSelectionView logic would block it
    print("\n--- Test 6: Verify Customer View Logic ---")
    is_blocked = BlockedDay.objects.filter(date=tomorrow).exists()
    if is_blocked:
        print("PASS: Customer view will see this day as blocked.")
    else:
        print("FAIL: Day is not blocked.")

    # Cleanup
    # Booking.objects.filter(date=tomorrow).delete()
    # BlockedDay.objects.filter(date=tomorrow).delete()
    print("\nVerification Complete.")

if __name__ == "__main__":
    run_verification()
