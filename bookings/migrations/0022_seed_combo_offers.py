from decimal import Decimal

from django.db import migrations


SEED_COMBOS = [
    {
        'name': 'Blackhead Peel-Off',
        'service_name': 'Blackhead Peel-Off',
        'description': 'Clear pores in minutes — the perfect finish after a fresh cut.',
        'combo_price': Decimal('120.00'),
        'badge_text': 'Hot Deal',
        'sort_order': 10,
    },
    {
        'name': 'Blackhead Removal (with steam)',
        'service_name': 'Blackhead Removal (with steam)',
        'description': 'Deep cleanse with steam for smoother, fresher skin.',
        'combo_price': Decimal('150.00'),
        'badge_text': 'Best Seller',
        'sort_order': 20,
    },
    {
        'name': 'Charcoal Peel-Off',
        'service_name': 'Charcoal Peel-Off',
        'description': 'Detox your skin with a purifying charcoal peel-off mask.',
        'combo_price': Decimal('150.00'),
        'badge_text': 'Glow Up',
        'sort_order': 30,
    },
    {
        'name': 'Executive Shave',
        'service_name': 'Executive Shave',
        'description': 'A premium shave upgrade for a sharper, cleaner finish.',
        'combo_price': Decimal('250.00'),
        'badge_text': 'Premium',
        'sort_order': 40,
    },
    {
        'name': 'Eye Massage (15 mins)',
        'service_name': 'Eye Massage (15 mins)',
        'description': 'Relax tired eyes and complete your grooming ritual.',
        'combo_price': Decimal('150.00'),
        'badge_text': 'Relax',
        'sort_order': 50,
    },
    {
        'name': 'Head Massage (with steam, 30 mins)',
        'service_name': 'Head Massage (with steam, 30 mins)',
        'description': 'Unwind with steam and a deep head massage.',
        'combo_price': Decimal('300.00'),
        'badge_text': 'Most Loved',
        'sort_order': 60,
    },
    {
        'name': 'Neck Massage (15 mins)',
        'service_name': 'Neck Massage (15 mins)',
        'description': 'Release tension and feel refreshed in just 15 minutes.',
        'combo_price': Decimal('200.00'),
        'badge_text': 'Quick Add',
        'sort_order': 70,
    },
    {
        'name': 'Peel off mask',
        'service_name': 'Peel off mask',
        'description': 'A spa-like peel-off mask at an exclusive combo rate.',
        'combo_price': Decimal('350.00'),
        'badge_text': 'Spa Special',
        'sort_order': 80,
    },
]

TRIGGER_NAMES = ['Haircut', 'Haircut Shave', 'Haircut trim']


def seed_combo_offers(apps, schema_editor):
    Service = apps.get_model('bookings', 'Service')
    ComboOffer = apps.get_model('bookings', 'ComboOffer')

    triggers = list(Service.objects.filter(name__in=TRIGGER_NAMES))
    if not triggers:
        return

    for item in SEED_COMBOS:
        linked = Service.objects.filter(name=item['service_name']).first()
        if not linked:
            continue
        offer, created = ComboOffer.objects.get_or_create(
            linked_service_id=linked.id,
            defaults={
                'name': item['name'],
                'description': item['description'],
                'duration_minutes': linked.duration_minutes,
                'original_price': linked.price,
                'combo_price': item['combo_price'],
                'badge_text': item['badge_text'],
                'is_active': True,
                'sort_order': item['sort_order'],
            },
        )
        if not created:
            offer.name = item['name']
            offer.description = item['description']
            offer.duration_minutes = linked.duration_minutes
            offer.original_price = linked.price
            offer.combo_price = item['combo_price']
            offer.badge_text = item['badge_text']
            offer.is_active = True
            offer.sort_order = item['sort_order']
            offer.save()
        offer.trigger_services.set(triggers)


def unseed_combo_offers(apps, schema_editor):
    ComboOffer = apps.get_model('bookings', 'ComboOffer')
    ComboOffer.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('bookings', '0021_combo_offer'),
    ]

    operations = [
        migrations.RunPython(seed_combo_offers, unseed_combo_offers),
    ]
