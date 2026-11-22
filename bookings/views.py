from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views import View
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q
from django.db import transaction, IntegrityError
from django.contrib import messages
from datetime import datetime, time, timedelta
from decimal import Decimal
from .models import Service, Booking, CustomerTrust
from . import utils
from . import slots as slot_utils
from . import addons as addon_utils
from . import coupons as coupon_utils
from . import booking_service
import uuid
import json
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import login
from users.models import User

# New Wizard Views
class GenderSelectionView(View):
    """Temporarily hidden: skip straight to the services list."""

    def get(self, request):
        return redirect('service_list')

    def post(self, request):
        return redirect('service_list')

class ServiceListView(View):
    def get(self, request):
        # Gender selection is temporarily hidden — show all bookable services.
        request.session.pop('selected_gender', None)
        selected_gender = None
        services = Service.bookable()

        # Always start with a clean selection on the services page
        if 'selected_service_ids' in request.session:
            del request.session['selected_service_ids']
        selected_service_ids = []

        grouped_services = {}
        category_order = [
            'All Services', 'General', 'Hair Services', 'Haircut Combos', 'Hair Colour', 'Hair Spa',
            'Facials', 'Reflexology / Massage', 'Express Face Masks', 'Streaks'
        ]
        
        all_services = list(services)
        
        def get_category_index(name):
             try:
                 return category_order.index(name)
             except ValueError:
                 return 999
        
        all_services.sort(key=lambda s: (get_category_index(s.category), s.name))
        
        for service in all_services:
            if service.category not in grouped_services:
                grouped_services[service.category] = []
            grouped_services[service.category].append(service)

        return render(request, 'bookings/services.html', {
            'grouped_services': grouped_services,
            'selected_gender': selected_gender,
            'selected_service_ids': selected_service_ids,
        })

    def post(self, request):
        service_ids = request.POST.getlist('services')
        if not service_ids:
            selected_gender = None
            services = Service.bookable()
            grouped_services = {}
            for service in services:
                if service.category not in grouped_services:
                    grouped_services[service.category] = []
                grouped_services[service.category].append(service)

            selected_service_ids = [int(s) for s in service_ids if str(s).isdigit()]

            return render(request, 'bookings/services.html', {
                'grouped_services': grouped_services, 
                'selected_gender': selected_gender,
                'selected_service_ids': selected_service_ids,
                'error': 'Please select at least one service.',
            })

        # Infer session gender from first selected service (gender page is hidden).
        first_service = Service.objects.filter(id__in=[s for s in service_ids if str(s).isdigit()]).first()
        if first_service and first_service.gender in ('Boy', 'Girl'):
            request.session['selected_gender'] = first_service.gender
        
        # Implement service merging logic (e.g., Haircut + Beard Trim -> Haircut trim)
        haircut_id = '214'
        beard_trim_id = '216'
        haircut_trim_combo_id = '228'
        
        haircut_count = service_ids.count(haircut_id)
        beard_trim_count = service_ids.count(beard_trim_id)
        
        pairs = min(haircut_count, beard_trim_count)
        
        if pairs > 0:
            # Create a new list to avoid side effects during iteration if needed, 
            # though here we just modify the local list before session storage.
            for _ in range(pairs):
                service_ids.remove(haircut_id)
                service_ids.remove(beard_trim_id)
                service_ids.append(haircut_trim_combo_id)

        request.session['selected_service_ids'] = service_ids
        return redirect('date_time_selection')

class DateTimeSelectionView(View):
    def get(self, request):
        selected_service_ids = request.session.get('selected_service_ids')
        if not selected_service_ids:
            return redirect('service_list')
        
        # Requirement: Total duration of selected services
        unique_services = Service.objects.filter(id__in=set(selected_service_ids))
        service_dict = {str(s.id): s for s in unique_services}
        sequenced_services = [service_dict[str(sid)] for sid in selected_service_ids if str(sid) in service_dict]
        
        total_duration = sum(s.duration_minutes for s in sequenced_services)
        if total_duration == 0:
            total_duration = 30 # Fallback default
        num_services = len(selected_service_ids)
        
        selected_date_str = request.GET.get('date')
        slots = []
        selected_date = None
        
        # Calculate max date (7 days from today)
        now = timezone.localtime(timezone.now())
        now_date = now.date()
        max_date = now_date + timedelta(days=7)
        
        min_allowed_date = now_date + timedelta(days=1) if now_date.weekday() == 6 else now_date

        if not selected_date_str:
            selected_date = min_allowed_date
        else:
            try:
                selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
                if selected_date < min_allowed_date or selected_date > max_date or selected_date.weekday() == 6:
                    selected_date = min_allowed_date
            except ValueError:
                selected_date = min_allowed_date
        
        # Check if day is blocked
        is_blocked = False
        if selected_date:
            from .models import BlockedDay
            if BlockedDay.objects.filter(date=selected_date).exists():
                is_blocked = True
                slots = [] # No slots if blocked
        
        if selected_date and not is_blocked:
            start_hour = slot_utils.SHOP_OPEN_HOUR
            end_hour = slot_utils.SHOP_CLOSE_HOUR

            existing_bookings = list(slot_utils.get_active_bookings(selected_date))

            start_dt = datetime.combine(selected_date, time(start_hour, 0))
            end_dt = datetime.combine(selected_date, time(end_hour, 0))

            current_dt = start_dt
            
            while current_dt < end_dt:
                requested_start = current_dt
                requested_end = current_dt + timedelta(minutes=total_duration)
                
                if requested_end > end_dt:
                    break

                is_restricted = False
                if selected_date == now_date:
                    aware_req_start = timezone.make_aware(requested_start)
                    if aware_req_start < now:
                        current_dt += timedelta(minutes=slot_utils.SLOT_INTERVAL_MINUTES)
                        continue
                    elif aware_req_start <= now + timedelta(minutes=30):
                        is_restricted = True

                if slot_utils.is_interval_free(
                    selected_date,
                    requested_start,
                    requested_end,
                    bookings=existing_bookings,
                ):
                    slots.append({'time': current_dt.time(), 'is_restricted': is_restricted})
                
                current_dt += timedelta(minutes=slot_utils.SLOT_INTERVAL_MINUTES)

        return render(request, 'bookings/calendar.html', {
            'slots': slots,
            'selected_date': selected_date,
            'today': now_date,
            'min_allowed_date': min_allowed_date,
            'max_date': max_date,
            'num_services': num_services,
            'total_duration': total_duration,
            'is_blocked': is_blocked if 'is_blocked' in locals() else False
        })

    def post(self, request):
        date_str = request.POST.get('date')
        time_str = request.POST.get('time')
        
        if not date_str or not time_str:
            return redirect('date_time_selection')
            
        selected_service_ids = request.session.get('selected_service_ids')
        if not selected_service_ids:
            return redirect('service_list')
        
        unique_services = Service.objects.filter(id__in=set(selected_service_ids))
        if not unique_services.exists():
            return redirect('service_list')
            
        service_dict = {str(s.id): s for s in unique_services}
        sequenced_services = [service_dict[str(sid)] for sid in selected_service_ids if str(sid) in service_dict]
        
        total_duration = sum(s.duration_minutes for s in sequenced_services)

        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            selected_time = datetime.strptime(time_str, '%H:%M:%S').time()
        except ValueError:
            try:
                # Fallback for %H:%M format (e.g., 09:30)
                selected_time = datetime.strptime(time_str, '%H:%M').time()
            except ValueError:
                return redirect('date_time_selection')
        
        # Concurrency safety: Re-verify overlap exactly like GET
        requested_start = datetime.combine(selected_date, selected_time)
        requested_end = requested_start + timedelta(minutes=total_duration)
        now = timezone.localtime(timezone.now())
        
        if selected_date == now.date():
            aware_req_start = timezone.make_aware(requested_start)
            if aware_req_start <= now + timedelta(minutes=30):
                messages.error(request, 'Appointments must be booked at least 30 minutes in advance.')
                return redirect('date_time_selection')

        if not slot_utils.is_interval_free(selected_date, requested_start, requested_end):
            messages.error(request, 'The selected time slot is no longer available. Please choose another time.')
            return redirect('date_time_selection')
        
        # It's valid. Save in session.
        request.session['selected_date'] = date_str
        request.session['selected_time'] = selected_time.strftime('%H:%M:%S')
        return redirect('booking_confirmation')

class BookingConfirmationView(View):
    def get(self, request):
        # Login is required before confirm (enforced on services page; re-check here)
        if not request.user.is_authenticated:
            return redirect('service_list')

        selected_service_ids = request.session.get('selected_service_ids')
        date_str = request.session.get('selected_date')
        time_str = request.session.get('selected_time')
        
        if not (selected_service_ids and date_str and time_str):
            return redirect('service_list')

        # Keep combo pricing in sync when haircut + addon are both selected
        overrides = addon_utils.sync_combo_overrides(selected_service_ids)
        request.session['combo_price_overrides'] = overrides

        priced_rows = addon_utils.build_priced_services(selected_service_ids, overrides)
        services = [row['service'] for row in priced_rows]
        subtotal = sum((row['price'] for row in priced_rows), Decimal('0.00'))

        applied_coupon_code = request.session.get('applied_coupon_code', '')
        discount_amount = 0
        payable_total = subtotal
        coupon_error = ''

        customer_phone_for_coupon = getattr(request.user, 'phone_number', '') or ''

        if applied_coupon_code:
            try:
                coupon, discount_amount = coupon_utils.validate_and_apply_coupon(
                    applied_coupon_code,
                    subtotal,
                    customer_phone=customer_phone_for_coupon,
                    priced_rows=priced_rows,
                )
                request.session['applied_coupon_code'] = coupon.code
                payable_total = subtotal - discount_amount
            except coupon_utils.CouponError as exc:
                request.session.pop('applied_coupon_code', None)
                applied_coupon_code = ''
                coupon_error = exc.message
                discount_amount = 0
                payable_total = subtotal

        eligible_coupons = coupon_utils.get_eligible_coupons(
            customer_phone=customer_phone_for_coupon,
            subtotal=subtotal,
            priced_rows=priced_rows,
        )
        upsell_addons = addon_utils.get_upsell_carousel_items(selected_service_ids, overrides)
        
        return render(request, 'bookings/confirmation.html', {
            'services': services,
            'priced_services': priced_rows,
            'subtotal': subtotal,
            'total_price': payable_total,
            'discount_amount': discount_amount,
            'applied_coupon_code': applied_coupon_code,
            'coupon_error': coupon_error,
            'eligible_coupons': eligible_coupons,
            'upsell_addons': upsell_addons,
            'show_upsell_carousel': bool(upsell_addons),
            'date': date_str,
            'time': time_str,
        })

    def post(self, request):
        # Booking is initiated via AJAX; keep POST as a safe redirect
        if not request.user.is_authenticated:
            return redirect('service_list')
        return redirect('booking_confirmation')

class OTPVerificationView(View):
    def get(self, request):
        group_id = request.session.get('pending_group_id')
        if not group_id:
            return redirect('home')
        
        bookings = Booking.objects.filter(booking_group_id=group_id)
        if not bookings.exists():
            return redirect('service_list')
            
        booking = bookings.first()
        
        # Check if already verified
        if booking.status == 'confirmed':
            return redirect('booking_success')
             
        # Check expiration
        if booking.is_otp_expired():
             return render(request, 'bookings/error.html', {'message': 'OTP Expired. Please start over.'})
             
        return render(request, 'bookings/otp_verify.html', {'booking': booking})

    def post(self, request):
        group_id = request.session.get('pending_group_id')
        if not group_id:
            return redirect('home')
            
        bookings = Booking.objects.filter(booking_group_id=group_id)
        if not bookings.exists():
             return redirect('service_list')
             
        booking = bookings.first()
        entered_otp = request.POST.get('otp')
        
        if booking.is_otp_expired():
             return render(request, 'bookings/error.html', {'message': 'OTP Expired. Please start over.'})

        # Verify OTP Hash
        if utils.verify_otp_hash(entered_otp, booking.otp):
            # Success: mark all bookings in the group as confirmed
            bookings.update(is_verified=True, status='confirmed')

            # Auto-Login (Only if not already logged in)
            if not request.user.is_authenticated and booking.customer_phone and booking.customer_phone != 'None' and len(booking.customer_phone) > 5:
                try:
                    user, created = User.objects.get_or_create(phone_number=booking.customer_phone)
                    if created:
                        user.username = booking.customer_phone
                        user.save()
                    login(request, user)
                except Exception as e:
                    print(f"Auto-login failed: {e}")

            # Send confirmation emails & SMS
            first_booking = bookings.first()
            if first_booking:
                if first_booking.customer_email:
                    utils.send_booking_emails_async(first_booking, request)
                utils.send_confirmation_sms(first_booking.customer_phone, f"Confirmed! Date: {first_booking.date} Time: {first_booking.time}")

            # Store for success page and clear pending session
            request.session['last_booking_group_id'] = str(booking.booking_group_id)
            if 'pending_group_id' in request.session:
                del request.session['pending_group_id']

            return redirect('booking_success')

        else:
            return render(request, 'bookings/otp_verify.html', {
                'booking': booking,
                'error': 'Invalid OTP. Please try again.'
            })

class BookingSuccessView(View):

    def get(self, request):
        group_id = request.session.get('last_booking_group_id')
        if not group_id:
            return redirect('service_list')
            
        bookings = Booking.objects.filter(booking_group_id=group_id)
        booking = bookings.first()
        google_calendar_url = utils.generate_google_calendar_url(booking)
        return render(request, 'bookings/success.html', {
            'booking': booking, 
            'bookings': bookings,
            'google_calendar_url': google_calendar_url
        })

class CancelBookingView(View):
    def get(self, request, booking_id):
        # In real app, verify signature/token. Here mock with ID.
        booking = get_object_or_404(Booking, id=booking_id)
        # Find all related bookings
        bookings = Booking.objects.filter(booking_group_id=booking.booking_group_id)
        
        return render(request, 'bookings/cancel_confirm.html', {'booking': booking, 'bookings': bookings})
        
    def post(self, request, booking_id):
        booking = get_object_or_404(Booking, id=booking_id)
        bookings = Booking.objects.filter(booking_group_id=booking.booking_group_id)
        
        if booking.status in ['cancelled', 'completed']:
            return render(request, 'bookings/error.html', {'message': 'Booking already processed.'})
            
        # Check 2-hour window
        if not booking.is_cancellable:
            return render(request, 'bookings/error.html', {'message': 'Appointments cannot be cancelled within 2 hours of the scheduled time.'})
            
        # Check daily cancellation limit
        today = timezone.now().date()
        has_cancelled_today = Booking.objects.filter(
            customer_phone=booking.customer_phone,
            status='cancelled',
            cancelled_at__date=today
        ).exists()
        
        if has_cancelled_today:
             return render(request, 'bookings/error.html', {'message': 'You have already cancelled one appointment today. Please try again tomorrow.'})
            
        # Check for late cancellation (e.g., < 24 hours)
        appointment_datetime = datetime.combine(booking.date, booking.time)
        now = timezone.now() # Use timezone aware now
        # Naive vs Aware check: combine creates naive. 
        # Better:
        try:
             appointment_datetime = timezone.make_aware(datetime.combine(booking.date, booking.time))
        except:
             # If settings are naive
             appointment_datetime = datetime.combine(booking.date, booking.time)
             now = datetime.now()

        is_late = (appointment_datetime - now) < timedelta(hours=24)
        
        # Cancel ALL
        bookings.update(status='cancelled', cancelled_at=timezone.now())
        
        # Update Trust (counts as 1 cancellation event for the group)
        if is_late:
            utils.update_trust_score(booking.customer_phone, 'late_cancel')
        else:
            # Regular cancel
            pass 
            
        messages.success(request, "Your booking has been cancelled. The slot is now available for others.")
        return redirect('my_orders')

# Deprecated/Placeholders (to be removed once URLs are updated)
def book_appointment(request):
    return redirect('service_list')

def booking_success(request):
    return redirect('booking_success_new')

def customer_dashboard(request):
    return redirect('home')

def barber_dashboard(request):
    return redirect('home')

class OrderListView(LoginRequiredMixin, View):
    login_url = '/users/login/'
    
    def get(self, request):
        bookings = Booking.objects.filter(customer_phone=request.user.phone_number).order_by('-date', '-time')
        
        today = timezone.now().date()
        has_cancelled_today = Booking.objects.filter(
            customer_phone=request.user.phone_number,
            status='cancelled',
            cancelled_at__date=today
        ).exists()
        
        return render(request, 'bookings/order_list.html', {
            'bookings': bookings,
            'has_cancelled_today': has_cancelled_today
        })
