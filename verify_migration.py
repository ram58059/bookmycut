import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from bookings.models import Service, Booking

User = get_user_model()

print(f"Users: {User.objects.count()}")
print(f"Services: {Service.objects.count()}")
print(f"Bookings: {Booking.objects.count()}")
