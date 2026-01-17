from django.db import models
from django.db.models import Sum, Count, Avg, F, Q
from django.db.models.functions import TruncDay, TruncHour, TruncMonth, ExtractWeekDay, ExtractHour
from django.utils import timezone
from datetime import timedelta
from bookings.models import Booking, Service
from users.models import User

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
        pending_count=Count('id', filter=Q(status='pending')),
        total_revenue=Sum('services__price', filter=Q(status='completed')),
        avg_value=Avg('services__price', filter=Q(status='completed')),
    )
    
    # Recent (Last 30 days)
    recent_qs = total_qs.filter(date__gte=date_30_days_ago)
    recent_aggs = recent_qs.aggregate(
         recent_revenue=Sum('services__price', filter=Q(status='completed')),
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
        status='completed',
        date__gte=start_date
    ).annotate(
        day=TruncDay('date')
    ).values('day').annotate(
        daily_revenue=Sum('services__price'),
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
        booking_count=Count('booking'),
        completed_count=Count('booking', filter=Q(booking__status='completed'))
    ).annotate(
        revenue=F('price') * F('completed_count')
    ).order_by('-booking_count')

def get_peak_times():
    # Heatmap data: Day of week + Hour
    # 1 (Sunday) to 7 (Saturday)
    return Booking.objects.annotate(
        weekday=ExtractWeekDay('date'),
        hour=ExtractHour('time')
    ).values('weekday', 'hour').annotate(
        count=Count('id')
    ).order_by('weekday', 'hour')

def get_customer_insights():
    # Repeat vs New (Simple heuristic based on phone number counts)
    customer_counts = Booking.objects.values('customer_phone').annotate(
        visits=Count('id')
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

def get_cancellation_analytics():
    # Cancellation Rate
    total = Booking.objects.count() or 1
    cancelled = Booking.objects.filter(status='cancelled').count()
    rate = (cancelled / total) * 100
    
    # By Service
    service_cancellations = Service.objects.filter(booking__status='cancelled').annotate(
        cancelled_count=Count('booking')
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

def get_utilization_metrics():
    # Assume 12 slots per day (10am-10pm) per barber.
    # We will look at the last 7 days.
    # Total capacity = 12 * 7 = 84 slots (assuming 1 barber)
    # If we have multiple barbers, we should multiply by User.objects.filter(is_barber=True).count()
    
    barber_count = User.objects.filter(is_barber=True).count() or 1
    total_daily_slots = 12 * barber_count
    
    start_date = timezone.now().date() - timedelta(days=6) # Last 7 days including today
    
    bookings_last_7d = Booking.objects.filter(
        date__gte=start_date,
        status__in=['confirmed', 'completed']
    ).annotate(
        day=TruncDay('date')
    ).values('day').annotate(
        booked_slots=Count('id')
    ).order_by('day')
    
    daily_stats = []
    total_booked = 0
    
    # Map to ensure all days are present
    for i in range(7):
        d = start_date + timedelta(days=i)
        found = next((item for item in bookings_last_7d if item['day'].date() == d), None)
        booked = found['booked_slots'] if found else 0
        total_booked += booked
        
        utilization = (booked / total_daily_slots) * 100
        idle_hours = total_daily_slots - booked
        
        daily_stats.append({
            'date': d,
            'booked': booked,
            'total_slots': total_daily_slots,
            'utilization': round(utilization, 1),
            'idle_hours': max(0, idle_hours)
        })
        
    total_capacity = total_daily_slots * 7
    total_utilization = (total_booked / total_capacity) * 100
    
    return {
        'daily_stats': daily_stats,
        'overall_utilization': round(total_utilization, 1),
        'total_booked': total_booked,
        'total_capacity': total_capacity,
        'avg_idle_hours': round((total_capacity - total_booked) / 7, 1) if barber_count else 0
    }

def generate_smart_insights():
    insights = []
    
    # 1. Peak Time Insight
    peak_times = get_peak_times()
    if peak_times.exists():
        top = peak_times.first()
        days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        # ExtractWeekDay is 1-based (Sun=1)
        day_name = days[top['weekday'] - 1] if 1 <= top['weekday'] <= 7 else 'Unknown'
        booking_count = top['count']
        if booking_count > 2:
            insights.append({
                'text': f"{day_name}s around {top['hour']}:00 are your busiest time.",
                'type': 'success',
                'icon': 'fa-clock'
            })
            
    # 2. Revenue/Repeat Insight
    cust_insights = get_customer_insights()
    if cust_insights['returning'] > cust_insights['new']:
         insights.append({
            'text': f"High loyalty! {cust_insights['returning']} returning customers vs {cust_insights['new']} new.",
            'type': 'info',
            'icon': 'fa-heart'
        })
    
    # 3. Cancellation Insight
    cancellation = get_cancellation_analytics()
    if cancellation['rate'] > 20:
         insights.append({
            'text': f"High cancellation rate detected ({cancellation['rate']}%). Consider deposit policy.",
            'type': 'warning',
            'icon': 'fa-exclamation-triangle'
        })
        
    # 4. Service Drop (Mock logic for now, or compare vs previous month)
    # Just a solid "Tip"
    insights.append({
        'text': "Tip: Send reminders 2 hours before appointments to reduce no-shows.",
        'type': 'tip',
        'icon': 'fa-lightbulb'
    })
    
    return insights
