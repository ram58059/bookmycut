
import os
import django
from django.utils import timezone
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bookings.models import Booking, BlockedDay, Service

def cleanup():
    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)
    
    print(f"Cleaning up test data for {tomorrow}...")
    
    deleted_bookings = Booking.objects.filter(date=tomorrow, customer_phone="9999999999").delete()
    print(f"Deleted bookings: {deleted_bookings}")
    
    deleted_blocks = BlockedDay.objects.filter(date=tomorrow).delete()
    print(f"Deleted blocks: {deleted_blocks}")
    
    # Optional: Delete test service if created
    # Service.objects.filter(name="Test Cut").delete()

if __name__ == "__main__":
    cleanup()
