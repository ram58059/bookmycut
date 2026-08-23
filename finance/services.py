from collections import defaultdict
from decimal import Decimal

from django.db.models import F, Sum

from bookings.models import Booking
from dashboard.analytics import REVENUE_STATUSES

from .models import ManualServiceEntry


def get_booked_service_rows(selected_date):
    """Return line items for revenue-eligible bookings on the given date."""
    bookings = (
        Booking.objects.filter(date=selected_date, status__in=REVENUE_STATUSES)
        .select_related('service')
        .order_by('time', 'id')
    )

    groups = defaultdict(list)
    for booking in bookings:
        key = booking.booking_group_id or f'single_{booking.id}'
        groups[key].append(booking)

    rows = []
    for group_bookings in groups.values():
        first = group_bookings[0]
        service_counts = defaultdict(lambda: {'quantity': 0, 'unit_price': Decimal('0')})

        for booking in group_bookings:
            name = booking.service.name
            service_counts[name]['quantity'] += 1
            service_counts[name]['unit_price'] = booking.line_price

        for name, data in service_counts.items():
            quantity = data['quantity']
            unit_price = data['unit_price']
            rows.append({
                'booking_id': first.id,
                'customer_name': first.customer_name,
                'service_name': name,
                'quantity': quantity,
                'unit_price': unit_price,
                'total_amount': unit_price * quantity,
            })

        discount = max((b.discount_amount or Decimal('0') for b in group_bookings), default=Decimal('0'))
        if discount > 0:
            code = next((b.coupon_code for b in group_bookings if b.coupon_code), '')
            label = f'Discount ({code})' if code else 'Discount'
            rows.append({
                'booking_id': first.id,
                'customer_name': first.customer_name,
                'service_name': label,
                'quantity': 1,
                'unit_price': -discount,
                'total_amount': -discount,
            })

    return rows


def get_booked_revenue(selected_date):
    rows = get_booked_service_rows(selected_date)
    return sum(row['total_amount'] for row in rows)


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
