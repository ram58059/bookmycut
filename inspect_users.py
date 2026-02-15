
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from users.models import User
from bookings.models import Booking

def inspect_users():
    print("--- Inspecting Users ---")
    users = User.objects.all()
    for u in users:
        print(f"ID: {u.id}, Username: '{u.username}', Phone: '{u.phone_number}', IsSuper: {u.is_superuser}")
        if str(u.phone_number) == 'None' or u.phone_number is None:
             print("!!! FOUND NONE PHONE USER !!!")
        if str(u.username) == 'None':
             print("!!! FOUND NONE USERNAME USER !!!")

    print("\n--- Inspecting Bookings with 'None' phone ---")
    bookings = Booking.objects.filter(customer_phone='None')
    print(f"Bookings with phone='None': {bookings.count()}")
    
    none_bookings = Booking.objects.filter(customer_phone__isnull=True)
    print(f"Bookings with phone=None: {none_bookings.count()}")

if __name__ == "__main__":
    inspect_users()
