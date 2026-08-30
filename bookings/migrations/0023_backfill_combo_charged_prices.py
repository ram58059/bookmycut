from decimal import Decimal

from django.db import migrations
from django.db.models import Q


def backfill_combo_charged_prices(apps, schema_editor):
    """
    For past bookings that included a combo trigger + linked service but never
    stored charged_price, set charged_price to the offer's combo_price so sales
    reports stop using the higher list price.
    """
    Booking = apps.get_model('bookings', 'Booking')
    ComboOffer = apps.get_model('bookings', 'ComboOffer')

    for offer in ComboOffer.objects.all():
        trigger_ids = list(offer.trigger_services.values_list('pk', flat=True))
        linked_id = offer.linked_service_id
        if not trigger_ids or not linked_id:
            continue

        combo_price = Decimal(offer.combo_price)
        group_ids = (
            Booking.objects.filter(service_id__in=trigger_ids)
            .exclude(booking_group_id__isnull=True)
            .values_list('booking_group_id', flat=True)
            .distinct()
        )

        Booking.objects.filter(
            booking_group_id__in=group_ids,
            service_id=linked_id,
        ).filter(Q(charged_price__isnull=True)).update(charged_price=combo_price)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0022_seed_combo_offers'),
    ]

    operations = [
        migrations.RunPython(backfill_combo_charged_prices, noop_reverse),
    ]
