from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.db.models import F, Sum

from bookings.models import Booking, Service
from dashboard.analytics import REVENUE_STATUSES

from .models import ManualServiceEntry


def get_booked_service_rows(selected_date):
    """
    Return one finance line per booking (plus coupon discount rows).

    Each service line is editable so admins can correct what was actually
    delivered/paid that day without changing the original appointment times.
    """
    bookings = list(
        Booking.objects.filter(date=selected_date, status__in=REVENUE_STATUSES)
        .select_related('service')
        .order_by('time', 'id')
    )

    rows = []
    groups = defaultdict(list)
    for booking in bookings:
        key = str(booking.booking_group_id or f'single_{booking.id}')
        groups[key].append(booking)

    for group_bookings in groups.values():
        for booking in group_bookings:
            rows.append({
                'booking_line_id': booking.id,
                'booking_id': booking.id,
                'booking_group_id': booking.booking_group_id,
                'customer_name': booking.customer_name,
                'service_id': booking.service_id,
                'service_name': booking.service.name,
                'quantity': 1,
                'unit_price': booking.line_price,
                'total_amount': booking.line_price,
                'editable': True,
                'is_discount': False,
            })

        first = group_bookings[0]
        discount = max(
            (b.discount_amount or Decimal('0') for b in group_bookings),
            default=Decimal('0'),
        )
        if discount > 0:
            code = next((b.coupon_code for b in group_bookings if b.coupon_code), '')
            label = f'Discount ({code})' if code else 'Discount'
            rows.append({
                'booking_line_id': None,
                'booking_id': first.id,
                'booking_group_id': first.booking_group_id,
                'customer_name': first.customer_name,
                'service_id': None,
                'service_name': label,
                'quantity': 1,
                'unit_price': -discount,
                'total_amount': -discount,
                'editable': False,
                'is_discount': True,
            })

    return rows


def get_booked_revenue(selected_date):
    rows = get_booked_service_rows(selected_date)
    return sum((row['total_amount'] for row in rows), Decimal('0'))


def update_booked_service_line(booking_id, service_id, unit_price):
    """
    Update the service and charged price on a booking line for finance accuracy.

    Does not change appointment date/time slots — only what is tracked for sales.
    """
    booking = Booking.objects.select_related('service').get(pk=booking_id)
    if booking.status not in REVENUE_STATUSES:
        raise ValueError('Only confirmed or completed bookings can be edited for finance.')

    service = Service.objects.get(pk=service_id)
    try:
        price = Decimal(str(unit_price)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('Enter a valid service price.') from exc
    if price < 0:
        raise ValueError('Service price cannot be negative.')

    booking.service = service
    booking.charged_price = price
    booking.save(update_fields=['service', 'charged_price'])
    return booking


def get_manual_entries(selected_date):
    return (
        ManualServiceEntry.objects.filter(date=selected_date)
        .select_related('service')
        .order_by('created_at')
    )


def get_manual_revenue(selected_date):
    result = (
        ManualServiceEntry.objects.filter(date=selected_date)
        .aggregate(total=Sum(F('unit_price') * F('quantity')))
    )
    return result['total'] or Decimal('0')
