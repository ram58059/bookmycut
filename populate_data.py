import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from users.models import User
from bookings.models import Service, Booking
from datetime import date, time

def populate():
    # Create Services
    services = [
        {'name': 'Classic Cut', 'price': 40.00, 'duration_minutes': 30, 'description': 'Traditional scissor cut with hot towel finish.'},
        {'name': 'Beard Trim', 'price': 25.00, 'duration_minutes': 20, 'description': 'Shape and style your beard to perfection.'},
        {'name': 'The Royal Treatment', 'price': 75.00, 'duration_minutes': 60, 'description': 'Full haircut, beard trim, and facial massage.'},
    ]

    for s in services:
        Service.objects.get_or_create(name=s['name'], defaults=s)
    print("Services created.")

    # Create Barber
    if not User.objects.filter(username='barber_john').exists():
        User.objects.create_user(username='barber_john', email='john@example.com', password='password123', is_barber=True)
        print("Barber created.")
    
    # Create Customer
    if not User.objects.filter(username='customer_dave').exists():
        User.objects.create_user(username='customer_dave', email='dave@example.com', password='password123', is_barber=False)
        print("Customer created.")

if __name__ == '__main__':
    populate()
