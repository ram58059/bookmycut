from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from . import analytics
from bookings.models import Booking, Service
from django.db.models import Count, Q
from django.db.models.functions import ExtractWeekDay
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime, timedelta
import json

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
    trend_data = [float(entry['daily_revenue'] or 0) for entry in revenue_trend]
    
    status_distribution = analytics.get_booking_status_distribution()
    status_labels = [item['status'].capitalize() for item in status_distribution]
    status_data = [item['count'] for item in status_distribution]

    smart_insights = analytics.generate_smart_insights()

    from .models import ShopSetting
    shop_settings = ShopSetting.load()

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
        'otp_enabled': shop_settings.is_otp_enabled,
    }
    return render(request, 'dashboard/overview.html', context)

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def service_performance(request):
    services = analytics.get_service_performance()
    
    # Handle Search
    query = request.GET.get('q')
    if query:
        services = services.filter(
            Q(name__icontains=query) | 
            Q(category__icontains=query)
        )
    
    # Sorting Logic
    sort_by = request.GET.get('sort', 'booking_count') # Default sort
    direction = request.GET.get('direction', 'desc')
    
    # Validate sort field to prevent injection/errors
    valid_sort_fields = {
        'name': 'name', 
        'category': 'category', 
        'price': 'price', 
        'bookings': 'booking_count', 
        'revenue': 'revenue'
    }
    
    if sort_by not in valid_sort_fields:
        sort_by = 'bookings' # Fallback
        
    db_sort_field = valid_sort_fields.get(sort_by)
    
    if direction == 'desc':
        db_sort_field = f'-{db_sort_field}'
        
    # Apply sorting
    services = services.order_by(db_sort_field)
    
    # Chart Data (needs to match sorted order)
    labels = json.dumps([s.name for s in services])
    bookings_data = json.dumps([s.booking_count for s in services])
    revenue_data = json.dumps([float(s.revenue or 0) for s in services])
    
    context = {
        'page_title': 'Service Performance',
        'services': services,
        'labels': labels,
        'bookings_data': bookings_data,
        'revenue_data': revenue_data,
        'current_sort': sort_by,
        'current_direction': direction,
        'query': query,
    }
    return render(request, 'dashboard/service_performance.html', context)


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

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def manage_bookings(request):
    from bookings.models import BlockedDay
    
    today = timezone.now().date()
    
    # Handle Actions
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'block_day':
            date_str = request.POST.get('date')
            try:
                block_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                if block_date < today:
                    messages.error(request, "Cannot block past dates.")
                else:
                    # Check for existing bookings
                    active_bookings = Booking.objects.filter(
                        date=block_date,
                        status__in=['confirmed', 'pending_otp']
                    )
                    if active_bookings.exists():
                        messages.error(request, f"Cannot block {date_str}. There are {active_bookings.count()} active bookings. Please cancel them first.")
                    else:
                        BlockedDay.objects.get_or_create(date=block_date)
                        messages.success(request, f"Blocked {date_str} successfully.")
            except ValueError:
                messages.error(request, "Invalid date format.")
                
        elif action == 'unblock_day':
             date_str = request.POST.get('date')
             try:
                 # block_date = datetime.strptime(date_str, '%B %d, %Y').date() # Text format from template filter? No, use ID or ISO
                 # Better to pass ID, but date is unique. Let's use ID if possible, or ISO date.
                 # Let's assume ISO date from hidden input
                 BlockedDay.objects.filter(date=date_str).delete()
                 messages.success(request, f"Unblocked {date_str}.")
             except Exception as e:
                 messages.error(request, f"Error unblocking: {e}")

        elif action == 'cancel_booking_admin':
            booking_id = request.POST.get('booking_id')
            booking = get_object_or_404(Booking, id=booking_id)
            
            # Cancel logic (similar to user cancel but admin override)
            # Find group? Or single? User request implies "cancel order", usually means the slot.
            # If we cancel one slot of a multi-slot booking, it's tricky.
            # But usually admin wants to clear the schedule.
            # Let's cancel the specific booking ID.
            
            booking.status = 'cancelled'
            booking.save()
            
            # TODO: Notify user via SMS/Email
            # utils.send_cancellation_notice(booking) 
            
            messages.success(request, f"Booking for {booking.customer_phone} cancelled.")
            
        return redirect('dashboard_manage_bookings')


    # Data for View
    future_bookings = Booking.objects.filter(
        date__gte=today
    ).order_by('date', 'time').select_related('service')
    
    blocked_days = BlockedDay.objects.filter(date__gte=today).order_by('date')
    
    context = {
        'page_title': 'Manage Bookings',
        'future_bookings': future_bookings,
        'blocked_days': blocked_days,
        'today': today,
    }
    return render(request, 'dashboard/manage_bookings.html', context)

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def add_service(request):
    from .forms import ServiceForm
    
    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Service added successfully!')
            return redirect('dashboard_services')
    else:
        form = ServiceForm()
    
    categories = Service.objects.values_list('category', flat=True).distinct()
    
    context = {
        'page_title': 'Add New Service',
        'form': form,
        'categories': categories,
    }
    return render(request, 'dashboard/service_form.html', context)

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def edit_service(request, pk):
    from .forms import ServiceForm
    service = get_object_or_404(Service, pk=pk)
    
    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, 'Service updated successfully!')
            return redirect('dashboard_services')
    else:
        form = ServiceForm(instance=service)
    
    categories = Service.objects.values_list('category', flat=True).distinct()
    
    context = {
        'page_title': f'Edit Service: {service.name}',
        'form': form,
        'service': service, # For delete link or context
        'categories': categories,
    }
    return render(request, 'dashboard/service_form.html', context)

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def delete_service(request, pk):
    service = get_object_or_404(Service, pk=pk)
    
    if request.method == 'POST':
        service.delete()
        messages.success(request, 'Service deleted successfully!')
        return redirect('dashboard_services')
        
    context = {
        'page_title': 'Delete Service',
        'service': service,
    }
    return render(request, 'dashboard/service_confirm_delete.html', context)

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def orders_dashboard(request):
    # 1. Date Selector Data (Next 7 days)
    now_dt = timezone.localtime(timezone.now())
    today = now_dt.date()
    
    selected_date_str = request.GET.get('date')
    try:
        if selected_date_str:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        else:
            selected_date = today
    except ValueError:
        selected_date = today
    
    date_buttons = []
    for i in range(7):
        d = today + timedelta(days=i)
        date_buttons.append({
            'date': d,
            'day_name': d.strftime('%a'),
            'day_num': d.strftime('%d'),
            'is_selected': d == selected_date
        })
    
    # 2. Fetch Bookings for Selected Date
    all_bookings = Booking.objects.filter(
        date=selected_date,
        status__in=['confirmed', 'completed', 'no_show']
    ).select_related('service').order_by('time')
    
    # Identify Current/Next
    now_time = now_dt.time()
    
    # 2b. Set up grouping by (phone, time) to handle multi-service bookings
    ordered_groups = []
    group_map = {}
    
    for b in all_bookings:
        # Use a string key for the map to avoid tuple/time issues in some pyre versions
        key = f"{b.customer_phone}_{b.time}"
        
        if key not in group_map:
            # Calculate end time
            duration = b.service.duration_minutes
            start_datetime = datetime.combine(selected_date, b.time)
            end_datetime = start_datetime + timedelta(minutes=duration)
            display_end_time = b.end_time or end_datetime.time()
            
            # Status styling
            status_class = 'upcoming'
            is_ongoing = False
            if selected_date == today:
                if b.time <= now_time <= display_end_time and b.status == 'confirmed':
                    is_ongoing = True
                    status_class = 'ongoing'
                elif now_time > display_end_time or b.status in ['completed', 'no_show']:
                    status_class = 'past'
            elif selected_date < today:
                status_class = 'past'

            new_group = {
                'booking': b,
                'services_list': [], # Renamed to avoid confusion with the dict key 'services' if any
                'end_time': display_end_time,
                'status_class': status_class,
                'is_ongoing': is_ongoing
            }
            group_map[key] = new_group
            ordered_groups.append(new_group)
        
        group = group_map[key]
        item_list = group['services_list']
        
        # Add service to list
        found_service = False
        for s in item_list:
            if s['name'] == b.service.name:
                s['quantity'] += 1
                found_service = True
                break
        if not found_service:
            item_list.append({'name': b.service.name, 'quantity': 1})

    bookings_data = ordered_groups

    # 3. Next Booking Highlight (Find the first confirmed booking today after current time)
    next_booking = None
    if selected_date == today:
        for g in bookings_data:
            # g is a dict from our ordered_groups list
            b = g.get('booking')
            if b and getattr(b, 'status', '') == 'confirmed' and getattr(b, 'time', timezone.now().time()) > now_time:
                appt_dt = timezone.make_aware(datetime.combine(getattr(b, 'date', today), getattr(b, 'time', now_time)))
                diff = appt_dt - now_dt
                minutes = int(diff.total_seconds() / 60)
                
                if minutes < 60:
                    countdown_text = f"Starts in {minutes} min"
                else:
                    hours = minutes // 60
                    mins = minutes % 60
                    countdown_text = f"Starts in {hours} hr {mins} min"
                    
                next_booking = g
                next_booking['countdown_text'] = countdown_text
                next_booking['minutes_remaining'] = minutes
                break

    context = {
        'page_title': 'Orders',
        'date_buttons': date_buttons,
        'selected_date': selected_date,
        'bookings': bookings_data,
        'next_booking': next_booking,
        'today': today,
    }
    return render(request, 'dashboard/orders.html', context)

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def toggle_otp(request):
    if request.method == 'POST':
        from .models import ShopSetting
        settings = ShopSetting.load()
        settings.is_otp_enabled = not settings.is_otp_enabled
        settings.save()
        messages.success(request, f"OTP Verification is now {'enabled' if settings.is_otp_enabled else 'disabled'}.")
    # Redirect back to where they came from
    return redirect(request.META.get('HTTP_REFERER', 'dashboard_overview'))
