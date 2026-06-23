from datetime import time as dt_time, timedelta, date

from django.db import models
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import ExtractWeekDay, TruncDay, TruncMonth
from django.utils import timezone

from bookings.models import Booking, Service
from finance.models import ManualServiceEntry

# Bookings that count toward revenue/sales. Excludes no_show, cancelled, and pending.
REVENUE_STATUSES = ['completed', 'confirmed']


def _revenue_bookings():
    return Booking.objects.filter(status__in=REVENUE_STATUSES)


def get_upcoming_bookings():
    now = timezone.localtime(timezone.now())
    today = now.date()
    now_time = now.time()
    return (
        Booking.objects.filter(status__in=['confirmed', 'pending_otp'])
        .filter(Q(date__gt=today) | Q(date=today, time__gt=now_time))
        .select_related('service')
        .order_by('date', 'time')
    )


def _period_bounds(start_date, end_date):
    return Q(date__gte=start_date, date__lte=end_date)


def _manual_revenue_for_period(start_date, end_date=None):
    qs = ManualServiceEntry.objects.all()
    if end_date:
        qs = qs.filter(date__gte=start_date, date__lte=end_date)
    else:
        qs = qs.filter(date__gte=start_date)
    result = qs.aggregate(revenue=Sum(F('unit_price') * F('quantity')))
    return result['revenue'] or 0


def _manual_revenue_by_month(start_date, end_date):
    rows = (
        ManualServiceEntry.objects.filter(date__gte=start_date, date__lte=end_date)
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(revenue=Sum(F('unit_price') * F('quantity')))
    )
    return {_to_date(row['month']): row['revenue'] or 0 for row in rows}


def _manual_revenue_by_day(start_date, end_date):
    rows = (
        ManualServiceEntry.objects.filter(date__gte=start_date, date__lte=end_date)
        .annotate(day=TruncDay('date'))
        .values('day')
        .annotate(revenue=Sum(F('unit_price') * F('quantity')))
    )
    return {_to_date(row['day']): row['revenue'] or 0 for row in rows}


def _manual_revenue_by_weekday():
    rows = (
        ManualServiceEntry.objects.annotate(weekday=ExtractWeekDay('date'))
        .values('weekday')
        .annotate(revenue=Sum(F('unit_price') * F('quantity')))
    )
    return {row['weekday']: row['revenue'] or 0 for row in rows}


def get_period_stats(start_date, end_date=None):
    qs = _revenue_bookings()
    if end_date:
        qs = qs.filter(_period_bounds(start_date, end_date))
    else:
        qs = qs.filter(date__gte=start_date)

    stats = qs.aggregate(
        revenue=Sum('service__price'),
        bookings=Count('id'),
    )
    booking_revenue = stats['revenue'] or 0
    manual_revenue = _manual_revenue_for_period(start_date, end_date)
    return {
        'revenue': booking_revenue + manual_revenue,
        'bookings': stats['bookings'] or 0,
    }


def get_month_start(d=None):
    d = d or timezone.localtime(timezone.now()).date()
    return d.replace(day=1)


def get_week_start(d=None):
    d = d or timezone.localtime(timezone.now()).date()
    return d - timedelta(days=d.weekday())


OVERVIEW_REPORTS = {
    'sales-month': {
        'title': 'Sales This Month',
        'subtitle': 'Confirmed and completed bookings in the current month',
        'show_revenue': True,
    },
    'sales-today': {
        'title': "Today's Sale",
        'subtitle': 'Confirmed and completed bookings for today',
        'show_revenue': True,
    },
    'sales-week': {
        'title': "This Week's Sale",
        'subtitle': 'Confirmed and completed bookings this week (Mon–today)',
        'show_revenue': True,
    },
    'no-shows-month': {
        'title': 'No Visits This Month',
        'subtitle': 'Bookings marked as no visit in the current month',
        'show_revenue': False,
        'status': 'no_show',
    },
    'cancelled-month': {
        'title': 'Cancelled This Month',
        'subtitle': 'Bookings cancelled in the current month',
        'show_revenue': False,
        'status': 'cancelled',
    },
}


def get_overview_report_period(report_slug):
    today = timezone.localtime(timezone.now()).date()
    month_start = get_month_start(today)
    week_start = get_week_start(today)

    if report_slug == 'sales-today':
        return today, today
    if report_slug == 'sales-week':
        return week_start, today
    if report_slug in ('sales-month', 'no-shows-month', 'cancelled-month'):
        return month_start, today
    return None


def get_revenue_booking_rows(start_date, end_date):
    bookings = (
        _revenue_bookings()
        .filter(date__gte=start_date, date__lte=end_date)
        .select_related('service')
        .order_by('-date', '-time', 'id')
    )
    rows = []
    total = 0
    for booking in bookings:
        amount = booking.service.price
        total += amount
        rows.append({
            'id': booking.id,
            'customer_name': booking.customer_name,
            'customer_phone': booking.customer_phone,
            'service_name': booking.service.name,
            'date': booking.date,
            'time': booking.time,
            'status': booking.status,
            'status_display': booking.get_status_display(),
            'amount': amount,
        })

    manual_entries = (
        ManualServiceEntry.objects.filter(date__gte=start_date, date__lte=end_date)
        .select_related('service')
        .order_by('-date', '-created_at')
    )
    for entry in manual_entries:
        amount = entry.total_amount
        total += amount
        service_name = entry.service.name
        if entry.quantity > 1:
            service_name = f'{service_name} x{entry.quantity}'
        rows.append({
            'id': entry.id,
            'customer_name': 'Additional service',
            'customer_phone': '',
            'service_name': service_name,
            'date': entry.date,
            'time': None,
            'status': 'manual',
            'status_display': 'Additional service',
            'amount': amount,
        })

    rows.sort(key=lambda row: (row['date'], row['time'] or dt_time.min), reverse=True)
    return rows, total


def get_status_booking_rows(status, start_date, end_date):
    bookings = (
        Booking.objects.filter(status=status, date__gte=start_date, date__lte=end_date)
        .select_related('service')
        .order_by('-date', '-time', 'id')
    )
    rows = []
    for booking in bookings:
        rows.append({
            'id': booking.id,
            'customer_name': booking.customer_name,
            'customer_phone': booking.customer_phone,
            'service_name': booking.service.name,
            'date': booking.date,
            'time': booking.time,
            'status': booking.status,
            'status_display': booking.get_status_display(),
            'amount': booking.service.price,
        })
    return rows


def get_overview_report(report_slug):
    if report_slug not in OVERVIEW_REPORTS:
        return None

    period = get_overview_report_period(report_slug)
    if not period:
        return None

    start_date, end_date = period
    config = OVERVIEW_REPORTS[report_slug]

    if config.get('show_revenue'):
        rows, total_revenue = get_revenue_booking_rows(start_date, end_date)
        booking_count = len(rows)
    else:
        rows = get_status_booking_rows(config['status'], start_date, end_date)
        total_revenue = 0
        booking_count = len(rows)

    period_label = (
        start_date.strftime('%d %b %Y')
        if start_date == end_date
        else f'{start_date.strftime("%d %b")} – {end_date.strftime("%d %b %Y")}'
    )

    return {
        **config,
        'slug': report_slug,
        'rows': rows,
        'total_revenue': total_revenue,
        'booking_count': booking_count,
        'start_date': start_date,
        'end_date': end_date,
        'period_label': period_label,
    }


def get_business_overview():
    today = timezone.localtime(timezone.now()).date()
    month_start = get_month_start(today)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = get_month_start(last_month_end)
    week_start = get_week_start(today)
    year_start = today.replace(month=1, day=1)

    this_month = get_period_stats(month_start, today)
    last_month = get_period_stats(last_month_start, last_month_end)
    this_week = get_period_stats(week_start, today)
    today_stats = get_period_stats(today, today)
    lifetime = get_period_stats(date(2000, 1, 1), today)
    year_to_date = get_period_stats(year_start, today)

    revenue_change = 0
    if last_month['revenue']:
        revenue_change = round(
            ((this_month['revenue'] - last_month['revenue']) / last_month['revenue']) * 100,
            1,
        )

    total_qs = Booking.objects.all()
    total_customers = total_qs.values('customer_phone').distinct().count()
    completed_count = total_qs.filter(status='completed').count()
    confirmed_upcoming = total_qs.filter(
        status='confirmed',
        date__gte=today,
    ).count()
    cancelled_count = total_qs.filter(status='cancelled').count()
    total_bookings = total_qs.count() or 1
    cancellation_rate = round((cancelled_count / total_bookings) * 100, 1)

    avg_ticket = 0
    if lifetime['bookings']:
        avg_ticket = lifetime['revenue'] / lifetime['bookings']

    new_customers_this_month = (
        Booking.objects.values('customer_phone')
        .annotate(first_booking=models.Min('date'))
        .filter(first_booking__gte=month_start, first_booking__lte=today)
        .count()
    )

    month_bookings_qs = Booking.objects.filter(date__gte=month_start, date__lte=today)
    month_cancelled_count = month_bookings_qs.filter(status='cancelled').count()
    month_no_show_count = month_bookings_qs.filter(status='no_show').count()

    return {
        'today': today,
        'today_revenue': today_stats['revenue'],
        'today_bookings': today_stats['bookings'],
        'week_revenue': this_week['revenue'],
        'week_bookings': this_week['bookings'],
        'month_revenue': this_month['revenue'],
        'month_bookings': this_month['bookings'],
        'last_month_revenue': last_month['revenue'],
        'last_month_bookings': last_month['bookings'],
        'month_revenue_change': revenue_change,
        'lifetime_revenue': lifetime['revenue'],
        'lifetime_bookings': lifetime['bookings'],
        'year_revenue': year_to_date['revenue'],
        'year_bookings': year_to_date['bookings'],
        'avg_ticket': round(avg_ticket, 0),
        'total_customers': total_customers,
        'confirmed_upcoming': confirmed_upcoming,
        'cancellation_rate': cancellation_rate,
        'cancelled_count': cancelled_count,
        'completed_count': completed_count,
        'new_customers_this_month': new_customers_this_month,
        'month_cancelled_count': month_cancelled_count,
        'month_no_show_count': month_no_show_count,
    }


def _to_date(value):
    if hasattr(value, 'date') and callable(value.date):
        return value.date()
    return value


def get_monthly_revenue_trend(months=6):
    today = timezone.localtime(timezone.now()).date()
    month_start = get_month_start(today)
    start_month = get_month_start(month_start - timedelta(days=months * 31))

    rows = (
        _revenue_bookings()
        .filter(date__gte=start_month, date__lte=today)
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(
            revenue=Sum('service__price'),
            bookings=Count('id'),
        )
        .order_by('month')
    )

    month_map = {_to_date(row['month']): row for row in rows}
    manual_map = _manual_revenue_by_month(start_month, today)
    trend = []
    cursor = get_month_start(start_month)
    while cursor <= month_start:
        row = month_map.get(cursor, {})
        booking_revenue = row.get('revenue') or 0
        manual_revenue = manual_map.get(cursor, 0)
        trend.append({
            'month': cursor,
            'label': cursor.strftime('%b %Y'),
            'revenue': booking_revenue + manual_revenue,
            'bookings': row.get('bookings') or 0,
        })
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return trend[-months:]


def get_daily_revenue_trend(days=30):
    today = timezone.localtime(timezone.now()).date()
    start_date = today - timedelta(days=days - 1)

    rows = (
        _revenue_bookings()
        .filter(date__gte=start_date, date__lte=today)
        .annotate(day=TruncDay('date'))
        .values('day')
        .annotate(
            revenue=Sum('service__price'),
            bookings=Count('id'),
        )
        .order_by('day')
    )

    day_map = {_to_date(row['day']): row for row in rows}
    manual_map = _manual_revenue_by_day(start_date, today)
    trend = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        row = day_map.get(d, {})
        booking_revenue = row.get('revenue') or 0
        manual_revenue = manual_map.get(d, 0)
        trend.append({
            'day': d,
            'label': d.strftime('%d %b'),
            'revenue': booking_revenue + manual_revenue,
            'bookings': row.get('bookings') or 0,
        })
    return trend


def get_busiest_days():
    day_labels = {
        1: 'Sun', 2: 'Mon', 3: 'Tue', 4: 'Wed', 5: 'Thu', 6: 'Fri', 7: 'Sat',
    }
    display_order = [2, 3, 4, 5, 6, 7, 1]
    rows = (
        _revenue_bookings()
        .annotate(weekday=ExtractWeekDay('date'))
        .values('weekday')
        .annotate(
            bookings=Count('id'),
            revenue=Sum('service__price'),
        )
    )
    row_map = {row['weekday']: row for row in rows}
    manual_map = _manual_revenue_by_weekday()
    stats = []
    for weekday in display_order:
        row = row_map.get(weekday, {})
        booking_revenue = row.get('revenue') or 0
        manual_revenue = manual_map.get(weekday, 0)
        stats.append({
            'day': day_labels[weekday],
            'bookings': row.get('bookings') or 0,
            'revenue': booking_revenue + manual_revenue,
        })
    return stats


def get_service_performance():
    return Service.objects.all()


def get_customer_insights():
    # Repeat vs New (Simple heuristic based on phone number counts)
    customer_counts = Booking.objects.values('customer_phone').annotate(
        visits=Count('id'),
        customer_name=models.Max('customer_name')
    )
    
    new_customers = 0
    returning_customers = 0
    
    for c in customer_counts:
        if c['visits'] > 1:
            returning_customers += 1
        else:
            new_customers += 1
            
    top_customers = customer_counts.order_by('-visits')[:10]
    
    return {
        'new': new_customers,
        'returning': returning_customers,
        'top_customers': top_customers
    }


def get_visit_frequency_label(completed_visits, first_completed, last_completed):
    if not completed_visits:
        return 'No visits yet'
    if completed_visits <= 1 or not first_completed or not last_completed:
        return 'First visit only'

    days_span = (last_completed - first_completed).days
    if days_span == 0:
        return f'{completed_visits} visits on the same day'

    avg_days = days_span / (completed_visits - 1)
    if avg_days < 7:
        return f'Every ~{max(1, round(avg_days))} days'
    if avg_days < 30:
        weeks = max(1, round(avg_days / 7))
        return f'About every {weeks} week{"s" if weeks > 1 else ""}'
    months = max(1, round(avg_days / 30))
    return f'About every {months} month{"s" if months > 1 else ""}'


def get_customer_loyalty_label(completed_visits):
    if completed_visits >= 5:
        return 'VIP'
    if completed_visits >= 2:
        return 'Regular'
    return 'New'


def _booking_status_filters(now=None):
    """Classify bookings for customer analytics.

    A past booking counts as a visit unless it was cancelled or marked no visit.
    Future active bookings count as upcoming. The barber does not mark bookings completed.
    """
    now = now or timezone.localtime(timezone.now())
    today = now.date()
    now_time = now.time()
    future_filter = Q(date__gt=today) | Q(date=today, time__gt=now_time)
    past_filter = Q(date__lt=today) | Q(date=today, time__lte=now_time)
    active_filter = ~Q(status__in=['cancelled', 'no_show'])
    upcoming_filter = active_filter & future_filter
    visit_filter = active_filter & past_filter
    return upcoming_filter, visit_filter


def _build_booking_summary(customer):
    total = customer.get('total_visits') or 0
    visits = customer.get('completed_visits') or 0
    cancelled = customer.get('cancelled_visits') or 0
    no_show = customer.get('no_show_visits') or 0
    upcoming = customer.get('upcoming_bookings') or 0

    parts = [f'{visits} visit{"s" if visits != 1 else ""}']
    if cancelled:
        parts.append(f'{cancelled} cancelled')
    if no_show:
        parts.append(f'{no_show} no visit')
    if upcoming:
        parts.append(f'{upcoming} upcoming')

    return f'{total} bookings · ' + ' · '.join(parts)


def get_customers(query=None, sort='last_visit', direction='desc'):
    bookings = Booking.objects.all()
    if query:
        bookings = bookings.filter(
            Q(customer_phone__icontains=query) |
            Q(customer_name__icontains=query)
        )

    upcoming_filter, visit_filter = _booking_status_filters()

    customers = bookings.values('customer_phone').annotate(
        customer_name=models.Max('customer_name'),
        total_visits=Count('id'),
        completed_visits=Count('id', filter=visit_filter),
        cancelled_visits=Count('id', filter=Q(status='cancelled')),
        no_show_visits=Count('id', filter=Q(status='no_show')),
        upcoming_bookings=Count('id', filter=upcoming_filter),
        total_spent=Sum('service__price', filter=visit_filter),
        first_booking=models.Min('date'),
        first_completed=models.Min('date', filter=visit_filter),
        last_visit=models.Max('date', filter=visit_filter),
    )

    valid_sort_fields = {
        'name': 'customer_name',
        'phone': 'customer_phone',
        'visits': 'completed_visits',
        'completed': 'completed_visits',
        'spent': 'total_spent',
        'last_visit': 'last_visit',
        'first_visit': 'first_booking',
    }

    if sort not in valid_sort_fields:
        sort = 'last_visit'

    db_sort_field = valid_sort_fields[sort]
    if direction == 'desc':
        db_sort_field = f'-{db_sort_field}'

    return customers.order_by(db_sort_field, 'customer_phone')


def enrich_customer_row(customer):
    completed_visits = customer.get('completed_visits') or 0
    last_visit = customer.get('last_visit')

    return {
        **customer,
        'total_spent': customer.get('total_spent') or 0,
        'booking_summary': _build_booking_summary(customer),
        'last_visit_display': last_visit.strftime('%d %b %Y') if last_visit else 'No previous visits',
        'loyalty_label': get_customer_loyalty_label(completed_visits),
        'visit_frequency': get_visit_frequency_label(
            completed_visits,
            customer.get('first_completed'),
            last_visit,
        ),
    }

