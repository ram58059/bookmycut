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
    def get(self, request):
        return render(request, 'bookings/gender_selection.html')

    def post(self, request):
        gender = request.POST.get('gender')
        if gender not in ['Boy', 'Girl']:
            return redirect('gender_selection')
        
        request.session['selected_gender'] = gender
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
        
        # Pre-select services if returning from calendar
        selected_service_ids = request.session.get('selected_service_ids', [])
        # Convert to ints for comparison in template
        try:
            selected_service_ids = [int(i) for i in selected_service_ids]
        except (ValueError, TypeError):
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
            'selected_service_ids': selected_service_ids
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
                
            return render(request, 'bookings/services.html', {
                'grouped_services': grouped_services, 
                'selected_gender': selected_gender,
                'error': 'Please select at least one service.'
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
        max_date = now.date() + timedelta(days=7)

        if selected_date_str:
            try:
                selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
                if selected_date < now.date():
                     # Prevent past dates
                     selected_date = None
                elif selected_date > max_date:
                    # Prevent dates beyond 7 days
                    selected_date = None
                elif selected_date.weekday() == 6:
                    # Prevent Sundays (6 = Sunday)
                    selected_date = None
            except ValueError:
                pass
            except ValueError:
                pass
        
        # Check if day is blocked
        is_blocked = False
        if selected_date:
            from .models import BlockedDay
            if BlockedDay.objects.filter(date=selected_date).exists():
                is_blocked = True
                slots = [] # No slots if blocked
        
        if selected_date and not is_blocked:
            # Slot generation logic
            start_hour = 10
            end_hour = 21
            
            # If today, ensuring time slot is after current time
            if selected_date == now.date():
                # E.g. if now is 15:30, next slot is 16:00.
                start_hour = max(start_hour, now.hour + 1)

            # Cleanup Stale Bookings (Requirement: block only if pending OTP < 5 mins)
            cutoff_time = timezone.now() - timedelta(minutes=5)
            
            # Delete stale pending bookings to free up slots immediately
            Booking.objects.filter(
                status='pending_otp',
                otp_created_at__lt=cutoff_time
            ).delete()

            # Fetch existing bookings
            # Logic: Confirmed/Completed block slots.
            # Pending blocks slots (we just deleted stale ones, so all remaining pending are valid blocks)
            
            existing_bookings = Booking.objects.filter(
                date=selected_date
            ).filter(
                status__in=['confirmed', 'completed', 'pending_otp']
            )
            
            # Start and End bounds
            start_dt = datetime.combine(selected_date, time(start_hour, 0))
            end_dt = datetime.combine(selected_date, time(end_hour, 0))
            lunch_start = datetime.combine(selected_date, time(14, 0))
            lunch_end = datetime.combine(selected_date, time(16, 0))

            # Find available 30-minute slots
            current_dt = start_dt
            
            # Round current_dt up to next 30-minute interval if it's today
            if selected_date == now.date():
                minutes = current_dt.minute
                remainder = minutes % 30
                if remainder != 0:
                    current_dt += timedelta(minutes=(30 - remainder))
            
            while current_dt < end_dt:
                requested_start = current_dt
                requested_end = current_dt + timedelta(minutes=total_duration)
                
                # Check 1: Exceeds closing time
                if requested_end > end_dt:
                    break
                
                # Check 2: Overlaps Barber Lunch (14:00 to 16:00)
                # Overlap condition: max(start1, start2) < min(end1, end2)
                if max(requested_start, lunch_start) < min(requested_end, lunch_end):
                    current_dt += timedelta(minutes=30)
                    continue

                # Check 3: Overlaps existing bookings
                is_valid = True
                for booking in existing_bookings:
                    ex_start = datetime.combine(selected_date, booking.time)
                    ex_end = datetime.combine(selected_date, booking.end_time) if booking.end_time else ex_start + timedelta(hours=1)
                    if max(requested_start, ex_start) < min(requested_end, ex_end):
                        is_valid = False
                        break
                
                if is_valid:
                    slots.append(current_dt.time())
                
                current_dt += timedelta(minutes=30)

        return render(request, 'bookings/calendar.html', {
            'slots': slots,
            'selected_date': selected_date,
            'today': timezone.now().date(),
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
        
        lunch_start = datetime.combine(selected_date, time(14, 0))
        lunch_end = datetime.combine(selected_date, time(16, 0))
        
        if max(requested_start, lunch_start) < min(requested_end, lunch_end):
             # Overlaps lunch
             return redirect('date_time_selection')
             
        existing_bookings = Booking.objects.filter(
            date=selected_date,
            status__in=['confirmed', 'completed', 'pending_otp']
        )
        
        for booking in existing_bookings:
            ex_start = datetime.combine(selected_date, booking.time)
            ex_end = datetime.combine(selected_date, booking.end_time) if booking.end_time else ex_start + timedelta(hours=1)
            if max(requested_start, ex_start) < min(requested_end, ex_end):
                # Overlaps existing booking, race condition hit
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
        
        return render(request, 'bookings/confirmation.html', {
            'services': services,
            'total_price': total_price,
            'date': date_str,
            'time': time_str,
            'form': form,
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
                
                # Trust Score Check for Guests
                trust_profile = CustomerTrust.objects.filter(phone_number=phone).first()
                if trust_profile and trust_profile.trust_level != 'low':
                    is_trusted_user = True
                
                # Check Global Shop Setting for OTP Bypass
                from dashboard.models import ShopSetting
                settings = ShopSetting.load()
                if not settings.is_otp_enabled:
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

            lunch_start = datetime.combine(booking_date_obj, time(14, 0))
            lunch_end = datetime.combine(booking_date_obj, time(16, 0))

            if max(requested_start_dt, lunch_start) < min(requested_end_dt, lunch_end):
                return render(request, 'bookings/error.html', {'message': 'The selected time slot now overlaps with the barber\'s lunch break. Please choose another time.'})

            existing_bookings_for_date = Booking.objects.filter(
                date=booking_date_obj,
                status__in=['confirmed', 'completed', 'pending_otp']
            )

            for existing_booking in existing_bookings_for_date:
                ex_start = datetime.combine(booking_date_obj, existing_booking.time)
                ex_end = datetime.combine(booking_date_obj, existing_booking.end_time) if existing_booking.end_time else ex_start + timedelta(hours=1) # Fallback if end_time is null
                if max(requested_start_dt, ex_start) < min(requested_end_dt, ex_end):
                    return render(request, 'bookings/error.html', {'message': 'The selected time slot was just booked by another user. Please try again.'})

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
        bookings.update(status='cancelled')
        
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
        return render(request, 'bookings/order_list.html', {'bookings': bookings})
