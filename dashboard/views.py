from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from . import analytics
from bookings.models import Booking, Service, Coupon, ComboOffer
from django.db.models import Count, Q
from django.db.models.functions import ExtractWeekDay
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
    if request.method == 'POST' and request.POST.get('action') == 'cancel_booking_admin':
        booking = get_object_or_404(Booking, id=request.POST.get('booking_id'))
        booking.status = 'cancelled'
        booking.save()
        messages.success(request, f"Booking for {booking.customer_phone} cancelled.")
        return redirect('dashboard_overview')

    business = analytics.get_business_overview()
    growth = analytics.get_growth_insights()
    monthly_trend = analytics.get_monthly_revenue_trend(months=6)
    daily_trend = analytics.get_daily_revenue_trend(days=30)
    busiest_days = analytics.get_busiest_days()
    upcoming_bookings = analytics.get_upcoming_bookings()

    from .models import ShopSetting
    shop_settings = ShopSetting.load()

    context = {
        'page_title': 'Overview',
        'business': business,
        'growth': growth,
        'upcoming_bookings': upcoming_bookings,
        'busiest_days': busiest_days,
        'monthly_labels': json.dumps([item['label'] for item in monthly_trend]),
        'monthly_revenue': json.dumps([float(item['revenue']) for item in monthly_trend]),
        'daily_labels': json.dumps([item['label'] for item in daily_trend]),
        'daily_revenue': json.dumps([float(item['revenue']) for item in daily_trend]),
        'busiest_day_labels': json.dumps([item['day'] for item in busiest_days]),
        'busiest_day_revenue': json.dumps([float(item['revenue']) for item in busiest_days]),
        'peak_hour_labels': json.dumps([item['label'] for item in growth['peak_hours']]),
        'peak_hour_bookings': json.dumps([item['bookings'] for item in growth['peak_hours']]),
        'otp_enabled': shop_settings.is_otp_enabled,
        'business_phone': shop_settings.business_phone,
    }
    return render(request, 'dashboard/overview.html', context)


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def overview_report(request, report):
    report_data = analytics.get_overview_report(report)
    if not report_data:
        messages.error(request, 'Report not found.')
        return redirect('dashboard_overview')

    context = {
        'page_title': report_data['title'],
        'report': report_data,
    }
    return render(request, 'dashboard/overview_report.html', context)


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def service_performance(request):
    from core.models import HomepageServiceCard
    from decimal import Decimal, InvalidOperation

    if request.method == 'POST' and request.POST.get('action') == 'upload_service_image':
        from .forms import ServiceImageForm

        service = get_object_or_404(Service, pk=request.POST.get('service_id'))
        form = ServiceImageForm(request.POST, request.FILES)
        if form.is_valid():
            service.image = form.cleaned_data['image']
            service.save()
            messages.success(request, f'Photo for "{service.name}" was replaced.')
        else:
            error = form.errors.get('image')
            messages.error(request, error[0] if error else 'Could not upload that photo.')
        next_url = request.POST.get('next') or ''
        if not next_url.startswith('/') or next_url.startswith('//'):
            next_url = reverse('dashboard_services')
        return redirect(next_url)

    if request.method == 'POST' and request.POST.get('action') == 'update_homepage_cards':
        errors = []
        for card in HomepageServiceCard.objects.all():
            card.title = request.POST.get(f'card_{card.id}_title', card.title).strip()
            card.description = request.POST.get(f'card_{card.id}_description', card.description).strip()
            price_str = request.POST.get(f'card_{card.id}_price', str(card.price)).strip()
            try:
                card.price = Decimal(price_str)
            except InvalidOperation:
                errors.append(f'Invalid price for "{card.title}".')
                continue
            service_id = request.POST.get(f'card_{card.id}_service', '').strip()
            card.linked_service_id = int(service_id) if service_id else None
            card.save()
        if errors:
            for err in errors:
                messages.error(request, err)
        else:
            messages.success(request, 'Homepage service cards updated.')
        return redirect('dashboard_services')

    services = analytics.get_service_performance()

    query = request.GET.get('q')
    if query:
        services = services.filter(
            Q(name__icontains=query) |
            Q(category__icontains=query)
        )

    sort_by = request.GET.get('sort', 'name')
    direction = request.GET.get('direction', 'asc')

    valid_sort_fields = {
        'name': 'name',
        'category': 'category',
        'price': 'price',
    }

    if sort_by not in valid_sort_fields:
        sort_by = 'name'

    db_sort_field = valid_sort_fields[sort_by]
    if direction == 'desc':
        db_sort_field = f'-{db_sort_field}'

    services = services.order_by(db_sort_field)

    context = {
        'page_title': 'Services',
        'services': services,
        'homepage_cards': HomepageServiceCard.objects.all(),
        'all_services': Service.bookable().order_by('name'),
        'current_sort': sort_by,
        'current_direction': direction,
        'query': query,
    }
    return render(request, 'dashboard/service_performance.html', context)


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def customer_insights(request):
    from django.core.paginator import Paginator
    from bookings.models import CustomerTrust

    if request.method == 'POST' and request.POST.get('action') == 'delete_customer':
        phone = request.POST.get('customer_phone', '').strip()
        query = request.POST.get('q', '').strip()
        sort = request.POST.get('sort', 'last_visit')
        direction = request.POST.get('direction', 'desc')
        page_number = request.POST.get('page', 1)

        if phone:
            deleted_count, _ = Booking.objects.filter(customer_phone=phone).delete()
            CustomerTrust.objects.filter(phone_number=phone).delete()
            if deleted_count:
                messages.success(request, f'Customer {phone} and their booking history were deleted.')
            else:
                messages.warning(request, f'No records found for {phone}.')
        else:
            messages.error(request, 'Customer phone is required.')

        redirect_url = reverse('dashboard_customers')
        params = []
        if query:
            params.append(f'q={query}')
        if sort:
            params.append(f'sort={sort}')
        if direction:
            params.append(f'direction={direction}')
        if page_number and str(page_number) != '1':
            params.append(f'page={page_number}')
        if params:
            redirect_url = f'{redirect_url}?{"&".join(params)}'
        return redirect(redirect_url)

    query = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'last_visit')
    direction = request.GET.get('direction', 'desc')
    page_number = request.GET.get('page', 1)

    customers_qs = analytics.get_customers(query=query or None, sort=sort, direction=direction)
    total_customers = customers_qs.count()

    paginator = Paginator(customers_qs, 20)
    page_obj = paginator.get_page(page_number)
    customers = [analytics.enrich_customer_row(customer) for customer in page_obj]

    summary = analytics.get_customer_insights()

    context = {
        'page_title': 'Customers',
        'customers': customers,
        'page_obj': page_obj,
        'query': query,
        'current_sort': sort,
        'current_direction': direction,
        'total_customers': total_customers,
        'summary': summary,
    }
    return render(request, 'dashboard/customer_insights.html', context)

@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def manage_bookings(request):
    from bookings.models import BlockedDay, BlockedSlot
    from bookings import slots as slot_utils
    
    today = timezone.localtime(timezone.now()).date()
    
    # Handle Actions
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'block_day':
            date_str = request.POST.get('date')
            reason = (request.POST.get('reason') or '').strip()[:255]
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
                        blocked, created = BlockedDay.objects.get_or_create(
                            date=block_date,
                            defaults={'reason': reason},
                        )
                        if not created and reason and blocked.reason != reason:
                            blocked.reason = reason
                            blocked.save(update_fields=['reason'])
                        messages.success(request, f"Blocked {date_str} successfully.")
            except ValueError:
                messages.error(request, "Invalid date format.")

        elif action == 'block_slot':
            date_str = request.POST.get('date')
            time_str = request.POST.get('time')
            try:
                block_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                block_time = datetime.strptime(time_str, '%H:%M').time()
                allowed, error_message = slot_utils.can_block_slot(block_date, block_time)
                if allowed:
                    BlockedSlot.objects.get_or_create(date=block_date, time=block_time)
                    messages.success(
                        request,
                        f"Blocked {block_date.strftime('%d %b %Y')} at {block_time.strftime('%I:%M %p').lstrip('0')}."
                    )
                else:
                    messages.error(request, error_message)
            except ValueError:
                messages.error(request, "Invalid date or time format.")

        elif action == 'unblock_slot':
            date_str = request.POST.get('date')
            time_str = request.POST.get('time')
            try:
                block_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                block_time = datetime.strptime(time_str, '%H:%M').time()
                deleted, _ = BlockedSlot.objects.filter(date=block_date, time=block_time).delete()
                if deleted:
                    messages.success(
                        request,
                        f"Unblocked {block_date.strftime('%d %b %Y')} at {block_time.strftime('%I:%M %p').lstrip('0')}."
                    )
                else:
                    messages.error(request, "Blocked slot not found.")
            except ValueError:
                messages.error(request, "Invalid date or time format.")
                
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
            
            booking.status = 'cancelled'
            booking.save()
            
            messages.success(request, f"Booking for {booking.customer_phone} cancelled.")

        elif action == 'mark_no_show':
            booking_id = request.POST.get('booking_id')
            booking = get_object_or_404(Booking, id=booking_id)
            now_dt = timezone.localtime(timezone.now())
            no_visit_cutoff = today - timedelta(days=7)

            if booking.status != 'confirmed':
                messages.error(request, 'Only confirmed bookings can be marked as no visit.')
            elif booking.date < no_visit_cutoff:
                messages.error(request, 'No visit can only be marked within 7 days of the appointment.')
            else:
                appt_dt = timezone.make_aware(datetime.combine(booking.date, booking.time))
                if appt_dt > now_dt:
                    messages.error(request, 'Cannot mark a future booking as no visit.')
                else:
                    from bookings import utils as booking_utils

                    bookings_to_update = Booking.objects.filter(pk=booking.pk)
                    if booking.booking_group_id:
                        bookings_to_update = Booking.objects.filter(
                            booking_group_id=booking.booking_group_id,
                            date=booking.date,
                            status='confirmed',
                        )

                    updated_count = bookings_to_update.update(status='no_show')
                    if updated_count:
                        booking_utils.update_trust_score(booking.customer_phone, 'no_show')
                        messages.success(
                            request,
                            f"Marked {booking.customer_name} ({booking.customer_phone}) as no visit. "
                            f"This will no longer count toward sales."
                        )
                    else:
                        messages.error(request, 'No bookings were updated.')
            
        slot_date_param = (
            request.POST.get('slot_date')
            or request.POST.get('date')
            or today.strftime('%Y-%m-%d')
        )
        no_visit_page_param = request.POST.get('no_visit_page', 1)
        return redirect(
            f"{reverse('dashboard_manage_bookings')}?slot_date={slot_date_param}&no_visit_page={no_visit_page_param}"
        )


    # Data for View
    now_dt = timezone.localtime(timezone.now())
    no_visit_cutoff = today - timedelta(days=7)

    past_confirmed_qs = Booking.objects.filter(
        status='confirmed',
        date__gte=no_visit_cutoff,
    ).filter(
        Q(date__lt=today) | Q(date=today, time__lte=now_dt.time())
    ).order_by('-date', '-time').select_related('service')

    from django.core.paginator import Paginator
    past_confirmed_paginator = Paginator(past_confirmed_qs, 5)
    past_confirmed_page = past_confirmed_paginator.get_page(request.GET.get('no_visit_page', 1))
    
    blocked_days = BlockedDay.objects.filter(date__gte=today).order_by('date')
    blocked_slots = BlockedSlot.objects.filter(date__gte=today).order_by('date', 'time')

    slot_date_str = request.GET.get('slot_date', today.strftime('%Y-%m-%d'))
    try:
        slot_date = datetime.strptime(slot_date_str, '%Y-%m-%d').date()
        if slot_date < today:
            slot_date = today
    except ValueError:
        slot_date = today

    day_slots = slot_utils.get_manage_slots_for_date(slot_date)
    
    context = {
        'page_title': 'Manage Bookings',
        'past_confirmed_page': past_confirmed_page,
        'blocked_days': blocked_days,
        'blocked_slots': blocked_slots,
        'slot_date': slot_date,
        'day_slots': day_slots,
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
    
    categories = (
        Service.bookable()
        .exclude(category='')
        .values_list('category', flat=True)
        .distinct()
    )
    
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
    
    categories = (
        Service.bookable()
        .exclude(category='')
        .values_list('category', flat=True)
        .distinct()
    )
    
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
    history_count = (
        service.manual_entries.count()
        + service.bookings.count()
        + service.combo_offers.count()
    )

    if request.method == 'POST':
        # Soft-delete: ManualServiceEntry uses PROTECT, and hard delete
        # would also cascade booking history. Archive instead.
        service.is_active = False
        service.save(update_fields=['is_active'])
        messages.success(
            request,
            f'"{service.name}" was removed from the booking catalog. '
            'Finance and booking history for this service were kept.',
        )
        return redirect('dashboard_services')

    context = {
        'page_title': 'Delete Service',
        'service': service,
        'has_history': history_count > 0,
        'history_count': history_count,
    }
    return render(request, 'dashboard/service_confirm_delete.html', context)


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def offers_list(request):
    coupons = Coupon.objects.select_related('service').all()
    now = timezone.now()
    coupon_rows = []
    for coupon in coupons:
        if not coupon.is_active:
            status_label = 'Inactive'
            status_class = 'bg-gray-100 text-gray-600'
        elif coupon.valid_until and now > coupon.valid_until:
            status_label = 'Expired'
            status_class = 'bg-red-50 text-red-700'
        elif coupon.valid_from and now < coupon.valid_from:
            status_label = 'Scheduled'
            status_class = 'bg-blue-50 text-blue-700'
        else:
            status_label = 'Active'
            status_class = 'bg-green-50 text-green-700'
        coupon_rows.append({
            'coupon': coupon,
            'status_label': status_label,
            'status_class': status_class,
        })

    return render(request, 'dashboard/offers.html', {
        'page_title': 'Offers',
        'coupon_rows': coupon_rows,
    })


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def search_coupon_customers(request):
    """Return matching customer phones/names for coupon assignment autocomplete."""
    from django.http import JsonResponse
    from django.db.models import Max

    q = (request.GET.get('q') or '').strip()
    digits = ''.join(ch for ch in q if ch.isdigit())
    if len(digits) < 2 and len(q) < 2:
        return JsonResponse({'results': []})

    bookings = Booking.objects.exclude(customer_phone='').exclude(customer_phone__isnull=True)
    if digits:
        bookings = bookings.filter(customer_phone__icontains=digits)
    elif q:
        bookings = bookings.filter(
            Q(customer_phone__icontains=q) | Q(customer_name__icontains=q)
        )

    rows = (
        bookings.values('customer_phone')
        .annotate(
            customer_name=Max('customer_name'),
            last_visit=Max('date'),
        )
        .order_by('-last_visit')[:12]
    )

    results = []
    seen = set()
    for row in rows:
        phone = ''.join(ch for ch in (row['customer_phone'] or '') if ch.isdigit())[-10:]
        if not phone or phone in seen:
            continue
        seen.add(phone)
        results.append({
            'phone': phone,
            'name': (row['customer_name'] or '').strip(),
            'label': f"{phone}" + (f" — {row['customer_name']}" if row['customer_name'] else ''),
        })

    return JsonResponse({'results': results})


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def add_coupon(request):
    from .forms import CouponForm

    if request.method == 'POST':
        form = CouponForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Coupon created successfully!')
            return redirect('dashboard_offers')
    else:
        form = CouponForm(initial={'is_active': True})

    return render(request, 'dashboard/coupon_form.html', {
        'page_title': 'Create Coupon',
        'form': form,
    })


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def edit_coupon(request, pk):
    from .forms import CouponForm
    coupon = get_object_or_404(Coupon, pk=pk)

    if request.method == 'POST':
        form = CouponForm(request.POST, instance=coupon)
        if form.is_valid():
            form.save()
            messages.success(request, 'Coupon updated successfully!')
            return redirect('dashboard_offers')
    else:
        form = CouponForm(instance=coupon)

    return render(request, 'dashboard/coupon_form.html', {
        'page_title': f'Edit Coupon: {coupon.code}',
        'form': form,
        'coupon': coupon,
    })


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def delete_coupon(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)

    if request.method == 'POST':
        coupon.delete()
        messages.success(request, 'Coupon deleted successfully!')
        return redirect('dashboard_offers')

    return render(request, 'dashboard/coupon_confirm_delete.html', {
        'page_title': 'Delete Coupon',
        'coupon': coupon,
    })


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def combo_services_list(request):
    combos = (
        ComboOffer.objects.select_related('linked_service')
        .prefetch_related('trigger_services')
        .order_by('sort_order', 'name')
    )
    return render(request, 'dashboard/combo_services.html', {
        'page_title': 'Combo Services',
        'combos': combos,
    })


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def add_combo_service(request):
    from .forms import ComboOfferForm

    if request.method == 'POST':
        form = ComboOfferForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Combo service created successfully!')
            return redirect('dashboard_combo_services')
    else:
        default_triggers = Service.bookable().filter(
            name__in=['Haircut', 'Haircut Shave', 'Haircut trim']
        )
        form = ComboOfferForm(initial={
            'is_active': True,
            'badge_text': 'Combo Deal',
            'sort_order': (ComboOffer.objects.count() + 1) * 10,
        })
        form.fields['trigger_services'].initial = default_triggers

    return render(request, 'dashboard/combo_service_form.html', {
        'page_title': 'Add Combo Service',
        'form': form,
    })


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def edit_combo_service(request, pk):
    from .forms import ComboOfferForm
    combo = get_object_or_404(ComboOffer, pk=pk)

    if request.method == 'POST':
        form = ComboOfferForm(request.POST, request.FILES, instance=combo)
        if form.is_valid():
            form.save()
            messages.success(request, 'Combo service updated successfully!')
            return redirect('dashboard_combo_services')
    else:
        form = ComboOfferForm(instance=combo)

    return render(request, 'dashboard/combo_service_form.html', {
        'page_title': f'Edit Combo: {combo.name}',
        'form': form,
        'combo': combo,
    })


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def delete_combo_service(request, pk):
    combo = get_object_or_404(ComboOffer, pk=pk)
    if request.method == 'POST':
        combo.delete()
        messages.success(request, 'Combo service deleted successfully!')
        return redirect('dashboard_combo_services')
    return render(request, 'dashboard/combo_service_confirm_delete.html', {
        'page_title': 'Delete Combo Service',
        'combo': combo,
    })


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def reorder_combo_service(request, pk, direction):
    combo = get_object_or_404(ComboOffer, pk=pk)
    combos = list(ComboOffer.objects.order_by('sort_order', 'name', 'id'))
    try:
        index = next(i for i, item in enumerate(combos) if item.id == combo.id)
    except StopIteration:
        return redirect('dashboard_combo_services')

    if direction == 'up' and index > 0:
        other = combos[index - 1]
    elif direction == 'down' and index < len(combos) - 1:
        other = combos[index + 1]
    else:
        return redirect('dashboard_combo_services')

    combo.sort_order, other.sort_order = other.sort_order, combo.sort_order
    # Ensure uniqueness even if both had the same order
    if combo.sort_order == other.sort_order:
        if direction == 'up':
            combo.sort_order = max(other.sort_order - 1, 0)
        else:
            combo.sort_order = other.sort_order + 1
    ComboOffer.objects.bulk_update([combo, other], ['sort_order'])
    return redirect('dashboard_combo_services')


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def toggle_combo_service(request, pk):
    combo = get_object_or_404(ComboOffer, pk=pk)
    if request.method == 'POST':
        combo.is_active = not combo.is_active
        combo.save(update_fields=['is_active', 'updated_at'])
        messages.success(
            request,
            f'Combo "{combo.name}" is now {"active" if combo.is_active else "inactive"}.',
        )
    return redirect('dashboard_combo_services')


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
def update_business_phone(request):
    if request.method == 'POST':
        from .models import ShopSetting
        shop = ShopSetting.load()
        phone = request.POST.get('business_phone', '').strip()
        if len(phone) < 10:
            messages.error(request, 'Enter a valid business phone number (at least 10 digits).')
        else:
            shop.business_phone = phone
            shop.save()
            messages.success(request, 'Business phone updated.')
    return redirect(request.META.get('HTTP_REFERER', 'dashboard_overview'))


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
