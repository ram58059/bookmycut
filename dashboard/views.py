from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from . import analytics
from bookings.models import Booking, Service
from django.db.models import Count
from django.db.models.functions import ExtractWeekDay

def is_barber_or_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser or getattr(user, 'is_barber', False))

def dashboard_login(request):
    if request.user.is_authenticated:
        if is_barber_or_admin(request.user):
            return redirect('dashboard_overview')
        else:
            messages.error(request, "You do not have permission to access the dashboard.")
            return redirect('home')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if is_barber_or_admin(user):
                login(request, user)
                return redirect('dashboard_overview')
            else:
                messages.error(request, "Access denied. Barber or Admin privileges required.")
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()

    return render(request, 'dashboard/login.html', {'form': form})

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def overview(request):
    kpis = analytics.get_kpis()
    revenue_trend = analytics.get_revenue_trend(days=30)
    service_performance = analytics.get_service_performance()[:5] # Top 5
    recent_bookings = Booking.objects.select_related('service').order_by('-created_at')[:5]
    
    # Prepare data for Chart.js
    trend_labels = [entry['day'].strftime('%d %b') for entry in revenue_trend]
    trend_data = [entry['daily_revenue'] or 0 for entry in revenue_trend]
    
    status_distribution = analytics.get_booking_status_distribution()
    status_labels = [item['status'].capitalize() for item in status_distribution]
    status_data = [item['count'] for item in status_distribution]

    smart_insights = analytics.generate_smart_insights()

    context = {
        'page_title': 'Overview',
        'kpis': kpis,
        'smart_insights': smart_insights,
        'recent_bookings': recent_bookings,
        'top_services': service_performance,
        'trend_labels': trend_labels,
        'trend_data': trend_data,
        'status_labels': status_labels,
        'status_data': status_data,
    }
    return render(request, 'dashboard/overview.html', context)

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def service_performance(request):
    services = analytics.get_service_performance()
    
    # Chart Data
    labels = [s.name for s in services]
    bookings_data = [s.booking_count for s in services]
    revenue_data = [s.revenue or 0 for s in services]
    
    context = {
        'page_title': 'Service Performance',
        'services': services,
        'labels': labels,
        'bookings_data': bookings_data,
        'revenue_data': revenue_data,
    }
    return render(request, 'dashboard/service_performance.html', context)

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def peak_time(request):
    heatmap_data = analytics.get_peak_times()
    
    # Process for Heatmap (7 days x 24 hours - though shop hours likely 10-22)
    # We will pass raw list and process in JS or Python. 
    # Let's map to a structured grid for easier template rendering if needed, 
    # but Chart.js heatmap or custom grid is better.
    # For simplicity, we'll use a custom HTML grid or a simple chart. 
    # Let's use a 7x12 grid (10am to 10pm)
    
    # Initialize grid
    hours = range(10, 22) # 10 AM to 9 PM (last slot)
    weekdays = [1, 2, 3, 4, 5, 6, 7] # Sun to Sat
    grid = {d: {h: 0 for h in hours} for d in weekdays}
    
    for entry in heatmap_data:
        d = entry['weekday']
        h = entry['hour']
        if d in grid and h in grid[d]:
            grid[d][h] = entry['count']
            
    # Flatten for template convenience if needed, or keep dict.
    
    bookings_by_day_qs = Booking.objects.annotate(weekday=ExtractWeekDay('date')).values('weekday').annotate(count=Count('id')).order_by('weekday')
    bookings_by_day = [0]*7
    for b in bookings_by_day_qs:
        # Django WeekDay: 1=Sun, 7=Sat. Index 0=Sun.
        if 1 <= b['weekday'] <= 7:
            bookings_by_day[b['weekday']-1] = b['count']
            
    day_labels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

    context = {
        'page_title': 'Peak Time & Demand',
        'grid': grid,
        'hours': hours,
        'weekdays': weekdays,
        'day_labels': day_labels,
        'bookings_by_day': bookings_by_day,
    }
    return render(request, 'dashboard/peak_time.html', context)

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def customer_insights(request):
    insights = analytics.get_customer_insights()
    
    context = {
        'page_title': 'Customer Insights',
        'insights': insights,
        'new_pct': round((insights['new'] / (insights['new'] + insights['returning'] + 0.0001)) * 100, 1),
        'return_pct': round((insights['returning'] / (insights['new'] + insights['returning'] + 0.0001)) * 100, 1),
    }
    return render(request, 'dashboard/customer_insights.html', context)

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def cancellation_analytics(request):
    data = analytics.get_cancellation_analytics()
    
    # Prepare chart data
    service_labels = [s.name for s in data['service_breakdown']]
    service_data = [s.cancelled_count for s in data['service_breakdown']]
    
    hourly_labels = [f"{item['hour']}:00" for item in data['hourly_breakdown']]
    hourly_data = [item['count'] for item in data['hourly_breakdown']]
    
    context = {
        'page_title': 'Cancellation Analytics',
        'data': data,
        'service_labels': service_labels,
        'service_data': service_data,
        'hourly_labels': hourly_labels,
        'hourly_data': hourly_data,
    }
    return render(request, 'dashboard/cancellation.html', context)

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def utilization(request):
    data = analytics.get_utilization_metrics()
    
    # Chart Data
    days = [item['date'].strftime('%a') for item in data['daily_stats']]
    util_data = [item['utilization'] for item in data['daily_stats']]
    idle_data = [item['idle_hours'] for item in data['daily_stats']]
    
    context = {
        'page_title': 'Shop Utilization',
        'data': data,
        'days': days,
        'util_data': util_data,
        'idle_data': idle_data,
    }
    return render(request, 'dashboard/utilization.html', context)
