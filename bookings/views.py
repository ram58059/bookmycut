from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views import View
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q
from django.db import transaction, IntegrityError
from django.contrib import messages
from datetime import datetime, time, timedelta
from .models import Service, Booking, CustomerTrust
from .forms import GuestDetailsForm
from . import utils
from . import slots as slot_utils
import uuid
import json
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import login
from users.models import User
from dashboard.models import ShopSetting

# New Wizard Views
class GenderSelectionView(View):
    def get(self, request):
        return render(request, 'bookings/gender_selection.html')

    def post(self, request):
        gender = request.POST.get('gender')
        if gender not in ['Boy', 'Girl']:
            return redirect('gender_selection')
        
        request.session['selected_gender'] = gender
        if 'selected_service_ids' in request.session:
            del request.session['selected_service_ids']
        if gender == 'Girl':
            # Option to redirect to an empty page or valid page with no services
            pass
            
        return redirect('service_list')

class ServiceListView(View):
    def get(self, request):
        selected_gender = request.session.get('selected_gender')
        if not selected_gender:
            return redirect('gender_selection')

        services = Service.objects.filter(gender=selected_gender)

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
            selected_gender = request.session.get('selected_gender')
            services = Service.objects.filter(gender=selected_gender)
            grouped_services = {}
            for service in services:
                if service.category not in grouped_services:
                    grouped_services[service.category] = []
                grouped_services[service.category].append(service)

            price_increased_services = list(services.filter(price_increased_at__isnull=False))
            selected_service_ids = [int(s) for s in service_ids if str(s).isdigit()]

            return render(request, 'bookings/services.html', {
                'grouped_services': grouped_services, 
                'selected_gender': selected_gender,
                'selected_service_ids': selected_service_ids,
                'error': 'Please select at least one service.',
                'price_increased_services': price_increased_services,
            })
        
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
        selected_service_ids = request.session.get('selected_service_ids')
        date_str = request.session.get('selected_date')
        time_str = request.session.get('selected_time')
        
        if not (selected_service_ids and date_str and time_str):
            return redirect('service_list')
            
        # Fix: Filter returns unique objects, but we need to preserve duplicates from session
        unique_services = Service.objects.filter(id__in=set(selected_service_ids))
        service_dict = {str(s.id): s for s in unique_services}
        services = [service_dict[str(sid)] for sid in selected_service_ids if str(sid) in service_dict]
        total_price = sum(s.price for s in services)
        
        initial_data = {}
        if request.user.is_authenticated:
            initial_data['customer_name'] = getattr(request.user, 'first_name', '')
            initial_data['customer_phone'] = getattr(request.user, 'phone_number', '')
            initial_data['customer_email'] = getattr(request.user, 'email', '')
            
        form = GuestDetailsForm(initial=initial_data)
        
        shop_setting = ShopSetting.objects.first()
        is_otp_enabled = shop_setting.is_otp_enabled if shop_setting else True
        
        return render(request, 'bookings/confirmation.html', {
            'services': services,
            'total_price': total_price,
            'date': date_str,
            'time': time_str,
            'form': form,
            'is_otp_enabled': is_otp_enabled,
        })

    def post(self, request):
        form = GuestDetailsForm(request.POST)
        if form.is_valid():
            # Source all details from the form ALWAYS (independent of login info)
            phone = form.cleaned_data['customer_phone']
            name = form.cleaned_data['customer_name']
            email = form.cleaned_data['customer_email']
            
            ip = utils.get_client_ip(request)
            
            allowed, message = utils.check_rate_limits(phone, ip)
            if not allowed:
                return render(request, 'bookings/error.html', {'message': message})
            
            # Retrieve session data
            selected_service_ids = request.session.get('selected_service_ids')
            date_str = request.session.get('selected_date')
            time_str = request.session.get('selected_time')
            
            if not (selected_service_ids and date_str and time_str):
                return redirect('service_list')
            
            unique_services = Service.objects.filter(id__in=set(selected_service_ids))
            service_dict = {str(s.id): s for s in unique_services}
            sequenced_services = [service_dict[str(sid)] for sid in selected_service_ids if str(sid) in service_dict]
            
            # Determine if trusted or logged in
            if request.user.is_authenticated:
                is_trusted_user = True
            else:
                is_trusted_user = False
                
                is_trusted_user = True

            # Create Bookings Transactionally
            group_id = uuid.uuid4()
            plain_otp = utils.generate_otp()
            hashed_otp = utils.hash_otp(plain_otp)
            now_time = timezone.now()
            
            # Determine initial status
            # Trusted/logged-in users get immediate confirmation without OTP
            initial_status = 'confirmed' if is_trusted_user else 'pending_otp'
            is_initial_verified = True if is_trusted_user else False
            
            try:
                booking_date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                booking_time_obj = datetime.strptime(time_str, '%H:%M:%S').time()
            except ValueError:
                return render(request, 'bookings/error.html', {'message': 'Invalid date or time format.'})

            # Re-verify slot availability one last time before creating bookings
            total_duration_for_all_services = sum(s.duration_minutes for s in sequenced_services)
            requested_start_dt = datetime.combine(booking_date_obj, booking_time_obj)
            requested_end_dt = requested_start_dt + timedelta(minutes=total_duration_for_all_services)

            if not slot_utils.is_interval_free(booking_date_obj, requested_start_dt, requested_end_dt):
                return render(request, 'bookings/error.html', {'message': 'The selected time slot is no longer available. Please choose another time.'})

            try:
                with transaction.atomic():
            
                    # Create bookings for each service sequentially
                    current_start_time_dt = datetime.combine(booking_date_obj, booking_time_obj)
                    
                    for service in sequenced_services:
                        # Compute end_time dynamically based on service duration
                        current_end_time_dt = current_start_time_dt + timedelta(minutes=service.duration_minutes)
                        
                        booking = Booking(
                            customer_name=name,
                            customer_phone=phone,
                            customer_email=email,
                            customer_gender=request.session.get('selected_gender', 'Male'),
                            service=service,
                            booking_group_id=group_id,
                            date=booking_date_obj,
                            time=current_start_time_dt.time(),
                            end_time=current_end_time_dt.time(), # Store end time
                            status=initial_status,
                            ip_address=ip,
                            otp=hashed_otp if not is_trusted_user else None, # Store hash only if needed
                            otp_created_at=now_time if not is_trusted_user else None,
                            is_verified=is_initial_verified
                        )
                        booking.save()
                        
                        # Set next service start time
                        current_start_time_dt = current_end_time_dt
                        
            except IntegrityError:
                return render(request, 'bookings/error.html', {
                    'message': 'One of the selected time slots was just booked by another user. Please try again.'
                })
            except Exception as e:
                 return render(request, 'bookings/error.html', {'message': f'An error occurred: {str(e)}'})

            if is_trusted_user:
                # Provide auto-login if they bypassed OTP via setting but were not logged in 
                if not request.user.is_authenticated and phone and len(phone) > 5:
                    try:
                        user, created = User.objects.get_or_create(phone_number=phone)
                        if created:
                            user.username = phone
                            user.save()
                        login(request, user)
                    except Exception as e:
                        print(f"Auto-login failed after bypass: {e}")

                # Immediately confirm booking and send notifications
                bookings = Booking.objects.filter(booking_group_id=group_id)
                first_booking = bookings.first()
                if first_booking:
                    if first_booking.customer_email:
                        utils.send_booking_emails_async(first_booking, request)
                    utils.send_confirmation_sms(first_booking.customer_phone, f"Confirmed! Date: {first_booking.date} Time: {first_booking.time}")

                # Store for success page
                request.session['last_booking_group_id'] = str(group_id)

                # Cleanup selection session
                if 'selected_service_ids' in request.session: del request.session['selected_service_ids']
                if 'selected_date' in request.session: del request.session['selected_date']
                if 'selected_time' in request.session: del request.session['selected_time']

                return redirect('booking_success')
            else:
                # Send OTP (Voice)
                sms_sent = utils.send_voice_otp_2factor(phone, plain_otp)
                if not sms_sent:
                     # Fallback logging
                     print(f"CRITICAL: Failed to send Voice OTP. OTP was: {plain_otp}")
                
                # Store ID in session for verification step
                request.session['pending_group_id'] = str(group_id)
                
                # Clear selection session data
                if 'selected_service_ids' in request.session: del request.session['selected_service_ids']
                if 'selected_date' in request.session: del request.session['selected_date']
                if 'selected_time' in request.session: del request.session['selected_time']
                
                return redirect('otp_verification')
        
        # If invalid, re-render confirmation
        selected_service_ids = request.session.get('selected_service_ids')
        # Fix: Filter returns unique objects, but we need to preserve duplicates from session
        unique_services = Service.objects.filter(id__in=set(selected_service_ids))
        service_dict = {str(s.id): s for s in unique_services}
        services = [service_dict[str(sid)] for sid in selected_service_ids if str(sid) in service_dict]
        total_price = sum(s.price for s in services)
        
        return render(request, 'bookings/confirmation.html', {
            'services': services,
            'total_price': total_price,
            'date': request.session.get('selected_date'),
            'time': request.session.get('selected_time'),
            'form': form,
            'error': 'Please correct the errors below.'
        })

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
