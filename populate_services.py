
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bookings.models import Service

def populate_services():
    services_data = [
        {'name': 'Haircut', 'price': 250, 'duration_minutes': 60},
        {'name': 'Kids Cut (Boy)', 'price': 200, 'duration_minutes': 60},
        {'name': 'Beard Trim', 'price': 120, 'duration_minutes': 30},
        {'name': 'Shave', 'price': 120, 'duration_minutes': 30},
    ]

    for data in services_data:
        service, created = Service.objects.get_or_create(
            name=data['name'],
            defaults={
                'price': data['price'],
                'duration_minutes': data['duration_minutes']
            }
        )
        if created:
            print(f'Created service: {service.name}')
        else:
            print(f'Service already exists: {service.name}')
            # Update price/duration if needed
            service.price = data['price']
            service.duration_minutes = data['duration_minutes']
            service.save()
            print(f'Updated service: {service.name}')

if __name__ == '__main__':
    populate_services()
