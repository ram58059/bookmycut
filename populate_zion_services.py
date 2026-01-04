
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bookings.models import Service

def populate_zion_services():
    print("Deleting existing services...")
    Service.objects.all().delete()
    
    # Boy Services
    boy_services = {
        'Facials': [
            {'name': 'Clean-up (Fruit Facial) + De-Tan', 'price': 700}, # Taking lower bound, or average? User said 700 / 899. Let's use 700 for start or split? Let's use 800 as Base or just 700. I'll use 700.
            {'name': 'Gold Facial', 'price': 1300},
            {'name': 'Tan Clear', 'price': 1500},
            {'name': 'Whitening', 'price': 1500},
            {'name': 'Brightening', 'price': 2000},
            {'name': 'Anti-Ageing', 'price': 1800},
            {'name': 'O³ Groom Facial', 'price': 3000},
        ],
        'Hair Spa': [
            {'name': 'Moisturizing', 'price': 600},
            {'name': 'Colour Save', 'price': 700},
            {'name': 'Frizz Ease', 'price': 800},
            {'name': 'Anti-Dandruff', 'price': 800},
            {'name': 'Anti-Hairfall', 'price': 800},
            {'name': 'Hair Reborn', 'price': 900},
        ],
        'Reflexology / Massage': [
            {'name': 'Head Massage (with steam, 30 mins)', 'price': 400, 'duration': 30},
            {'name': 'Head Massage (without steam, 15 mins)', 'price': 350, 'duration': 15},
            {'name': 'Neck Massage (15 mins)', 'price': 300, 'duration': 15},
            {'name': 'Eye Massage (15 mins)', 'price': 200, 'duration': 15},
            {'name': 'Nail Cut & File (hands only)', 'price': 200, 'duration': 30},
        ],
        'Express Face Masks': [
            {'name': 'Hydrating Peel-Off Mask', 'price': 500},
            {'name': 'De-Tan', 'price': 350},
            {'name': 'Charcoal Peel-Off', 'price': 200},
            {'name': 'Blackhead Removal (with steam)', 'price': 200},
            {'name': 'Blackhead Peel-Off', 'price': 150},
            {'name': 'Deep Cleansing', 'price': 100},
        ],
        'Haircut Combos': [
            {'name': 'Haircut + Trim/Shave + De-Tan', 'price': 599},
            {'name': 'Haircut + Trim/Shave + Cleansing', 'price': 449},
            {'name': 'Haircut + Trim/Shave + Deep Conditioning', 'price': 499},
            {'name': 'Haircut + Trim/Shave + Head Massage (no steam)', 'price': 599},
            {'name': 'Haircut + Trim/Shave + Moisturising Spa', 'price': 799},
            {'name': 'Haircut + Trim/Shave + Ammonia-Free Colour', 'price': 999},
            {'name': 'Haircut + Trim/Shave + Ammonia-Free Colour + De-Tan', 'price': 1299},
        ],
        'Hair Services': [
            {'name': 'Haircut (includes hair wash)', 'price': 250},
            {'name': 'Kids Cut (Boy)', 'price': 200},
            {'name': 'Beard Trim', 'price': 120},
            {'name': 'Shave', 'price': 120},
            {'name': 'Executive Shave', 'price': 350},
            {'name': 'Head Shave', 'price': 250},
            {'name': 'Hair Wash', 'price': 100},
            {'name': 'Deep Conditioning', 'price': 200}, # 200 / 250
        ],
        'Hair Colour': [
            {'name': 'Ammonia', 'price': 400},
            {'name': 'Ammonia-Free', 'price': 800},
        ],
        'Streaks': [
            {'name': '1 Streak', 'price': 150},
            {'name': '5–9 Streaks', 'price': 600},
            {'name': '10–20 Streaks', 'price': 1000},
        ]
    }

    count = 0
    for category, services in boy_services.items():
        for s_data in services:
            # Handle specific durations if provided, else default 60
            duration = s_data.get('duration', 60)
            
            # Special handling for prices that had ranges or specifics
            # "Clean-up (Fruit Facial) + De-Tan": ₹700 / ₹899 -> I used 700.
            # "Deep Conditioning": 200 (Long Hair 250). I used 200.
            
            Service.objects.create(
                name=s_data['name'],
                price=s_data['price'],
                duration_minutes=duration,
                category=category,
                gender='Boy'
            )
            count += 1
            
    print(f"Successfully created {count} services for Boy.")

if __name__ == '__main__':
    populate_zion_services()
