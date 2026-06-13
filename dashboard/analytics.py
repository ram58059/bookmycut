from django.db import models
from django.db.models import Sum, Count, Avg, F, Q
from django.db.models.functions import TruncDay, TruncHour, TruncMonth, ExtractWeekDay, ExtractHour
from django.utils import timezone
from datetime import timedelta, date
from bookings.models import Booking, Service

REVENUE_STATUSES = ['completed', 'confirmed']


def _revenue_bookings():
    return Booking.objects.filter(status__in=REVENUE_STATUSES)


def _period_bounds(start_date, end_date):
    return Q(date__gte=start_date, date__lte=end_date)


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
    return {
        'revenue': stats['revenue'] or 0,
        'bookings': stats['bookings'] or 0,
    }


def get_month_start(d=None):
    d = d or timezone.localtime(timezone.now()).date()
    return d.replace(day=1)


def get_business_overview():
    today = timezone.localtime(timezone.now()).date()
    month_start = get_month_start(today)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = get_month_start(last_month_end)
    week_start = today - timedelta(days=today.weekday())
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
    trend = []
    cursor = get_month_start(start_month)
    while cursor <= month_start:
        row = month_map.get(cursor, {})
        trend.append({
            'month': cursor,
            'label': cursor.strftime('%b %Y'),
            'revenue': row.get('revenue') or 0,
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
    trend = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        row = day_map.get(d, {})
        trend.append({
            'day': d,
            'label': d.strftime('%d %b'),
            'revenue': row.get('revenue') or 0,
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
    stats = []
    for weekday in display_order:
        row = row_map.get(weekday, {})
        stats.append({
            'day': day_labels[weekday],
            'bookings': row.get('bookings') or 0,
            'revenue': row.get('revenue') or 0,
        })
    return stats


def get_top_services(limit=5):
    return (
        Service.objects.annotate(
            booking_count=Count(
                'bookings',
                filter=Q(bookings__status__in=REVENUE_STATUSES),
            ),
        )
        .annotate(revenue=F('price') * F('booking_count'))
        .filter(booking_count__gt=0)
        .order_by('-revenue')[:limit]
    )

def get_kpis():
    # Calculate date ranges
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    date_7_days_ago = today - timedelta(days=7)
    date_30_days_ago = today - timedelta(days=30)
    
    # Base QuerySets
    total_qs = Booking.objects.all()
    completed_qs = total_qs.filter(status='completed')
    
    # Aggregates
    aggs = total_qs.aggregate(
        total_bookings=Count('id'),
        completed_count=Count('id', filter=Q(status='completed')),
        cancelled_count=Count('id', filter=Q(status='cancelled')),
        pending_count=Count('id', filter=Q(status='pending_otp')),
        total_revenue=Sum('service__price', filter=Q(status='completed')),
        avg_value=Avg('service__price', filter=Q(status='completed')),
    )
    
    # Recent (Last 30 days)
    recent_qs = total_qs.filter(date__gte=date_30_days_ago)
    recent_aggs = recent_qs.aggregate(
         recent_revenue=Sum('service__price', filter=Q(status='completed')),
         recent_bookings=Count('id')
    )
    
    # Customer stats
    total_customers = total_qs.values('customer_phone').distinct().count() or 1
    
    # Calculate Rates
    total = aggs['total_bookings'] or 1
    cancelled = aggs['cancelled_count'] or 0
    cancellation_rate = (cancelled / total) * 100
    
    return {
        'total_bookings': aggs['total_bookings'] or 0,
        'completed': aggs['completed_count'] or 0,
        'cancelled': aggs['cancelled_count'] or 0,
        'pending': aggs['pending_count'] or 0,
        'revenue': aggs['total_revenue'] or 0,
        'avg_booking_value': aggs['avg_value'] or 0,
        'total_customers': total_customers,
        'cancellation_rate': round(cancellation_rate, 1),
        'recent_revenue': recent_aggs['recent_revenue'] or 0,
    }

def get_revenue_trend(days=30):
    start_date = timezone.now().date() - timedelta(days=days)
    trend = Booking.objects.filter(
        status__in=['completed', 'confirmed'],
        date__gte=start_date
    ).annotate(
        day=TruncDay('date')
    ).values('day').annotate(
        daily_revenue=Sum('service__price'),
        daily_count=Count('id')
    ).order_by('day')
    
    # Fill missing days logic would go here if strict chart continuity is needed
    return list(trend)

def get_booking_status_distribution():
    dist = Booking.objects.values('status').annotate(count=Count('id'))
    return list(dist)

def get_service_performance():
    # Performance of top services
    # Revenue = price * completed bookings (since price is on Service model)
    return Service.objects.annotate(
        booking_count=Count('bookings'),
        completed_count=Count('bookings', filter=Q(bookings__status__in=['completed', 'confirmed']))
    ).annotate(
        revenue=F('price') * F('completed_count')
    ).order_by('-booking_count')


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


def get_visit_frequency_label(total_visits, first_visit, last_visit):
    if not total_visits or total_visits <= 1 or not first_visit or not last_visit:
        return 'First visit only'

    days_span = (last_visit - first_visit).days
    if days_span == 0:
        return f'{total_visits} visits on the same day'

    avg_days = days_span / (total_visits - 1)
    if avg_days < 7:
        return f'Every ~{max(1, round(avg_days))} days'
    if avg_days < 30:
        weeks = max(1, round(avg_days / 7))
        return f'About every {weeks} week{"s" if weeks > 1 else ""}'
    months = max(1, round(avg_days / 30))
    return f'About every {months} month{"s" if months > 1 else ""}'


def get_customer_loyalty_label(total_visits):
    if total_visits >= 5:
        return 'VIP'
    if total_visits >= 2:
        return 'Regular'
    return 'New'


def get_customers(query=None, sort='last_visit', direction='desc'):
    bookings = Booking.objects.all()
    if query:
        bookings = bookings.filter(
            Q(customer_phone__icontains=query) |
            Q(customer_name__icontains=query)
        )

    customers = bookings.values('customer_phone').annotate(
        customer_name=models.Max('customer_name'),
        total_visits=Count('id'),
        completed_visits=Count('id', filter=Q(status='completed')),
        cancelled_visits=Count('id', filter=Q(status='cancelled')),
        no_show_visits=Count('id', filter=Q(status='no_show')),
        total_spent=Sum('service__price', filter=Q(status='completed')),
        first_visit=models.Min('date'),
        last_visit=models.Max('date'),
    )

    valid_sort_fields = {
        'name': 'customer_name',
        'phone': 'customer_phone',
        'visits': 'total_visits',
        'completed': 'completed_visits',
        'spent': 'total_spent',
        'last_visit': 'last_visit',
        'first_visit': 'first_visit',
    }

    if sort not in valid_sort_fields:
        sort = 'last_visit'

    db_sort_field = valid_sort_fields[sort]
    if direction == 'desc':
        db_sort_field = f'-{db_sort_field}'

    return customers.order_by(db_sort_field, 'customer_phone')


def enrich_customer_row(customer):
    total_visits = customer.get('total_visits') or 0
    cancelled_visits = customer.get('cancelled_visits') or 0
    no_show_visits = customer.get('no_show_visits') or 0
    active_visits = max(total_visits - cancelled_visits - no_show_visits, 0)

    return {
        **customer,
        'total_spent': customer.get('total_spent') or 0,
        'active_visits': active_visits,
        'loyalty_label': get_customer_loyalty_label(active_visits),
        'visit_frequency': get_visit_frequency_label(
            active_visits,
            customer.get('first_visit'),
            customer.get('last_visit'),
        ),
    }

def get_cancellation_analytics():
    # Cancellation Rate
    total = Booking.objects.count() or 1
    cancelled = Booking.objects.filter(status='cancelled').count()
    rate = (cancelled / total) * 100
    
    # By Service
    service_cancellations = Service.objects.filter(bookings__status='cancelled').annotate(
        cancelled_count=Count('bookings')
    ).order_by('-cancelled_count')[:5]
    
    # By Time of Day (Hourly)
    hourly_cancellations = Booking.objects.filter(status='cancelled').annotate(
        hour=ExtractHour('time')
    ).values('hour').annotate(
        count=Count('id')
    ).order_by('hour')
    
    # No-shows (Currently we track 'cancelled', assuming no-show is a subset or same status)
    # If no-show was a separate status, we'd filter for that. 
    # For now, let's assume 'cancelled' covers both or just cancellations.
    
    return {
        'rate': round(rate, 1),
        'total_cancelled': cancelled,
        'service_breakdown': service_cancellations,
        'hourly_breakdown': list(hourly_cancellations)
    }

def generate_smart_insights():
    insights = []
    business = get_business_overview()

    if business['month_revenue_change'] > 10:
        insights.append({
            'text': f"Strong month! Sales are up {business['month_revenue_change']}% compared to last month.",
            'type': 'success',
            'icon': 'fa-arrow-trend-up',
        })
    elif business['month_revenue_change'] < -10:
        insights.append({
            'text': f"Sales are down {abs(business['month_revenue_change'])}% vs last month. Consider promotions on slower days.",
            'type': 'warning',
            'icon': 'fa-arrow-trend-down',
        })

    if business['confirmed_upcoming'] > 0:
        insights.append({
            'text': f"You have {business['confirmed_upcoming']} upcoming confirmed booking{'s' if business['confirmed_upcoming'] != 1 else ''} on the schedule.",
            'type': 'info',
            'icon': 'fa-calendar-check',
        })

    cust_insights = get_customer_insights()
    if cust_insights['returning'] > cust_insights['new']:
         insights.append({
            'text': f"Strong loyalty: {cust_insights['returning']} returning customers vs {cust_insights['new']} first-time guests.",
            'type': 'info',
            'icon': 'fa-heart'
        })
    
    cancellation = get_cancellation_analytics()
    if cancellation['rate'] > 20:
        insights.append({
            'text': f"Cancellation rate is {cancellation['rate']}%. Reminders before appointments can help reduce no-shows.",
            'type': 'warning',
            'icon': 'fa-exclamation-triangle'
        })
        
    if not insights:
        insights.append({
            'text': "Tip: Send reminders 2 hours before appointments to reduce no-shows.",
            'type': 'tip',
            'icon': 'fa-lightbulb'
        })
    
    return insights
