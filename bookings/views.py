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
import razorpay
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
            'Haircut Services', 'General', 'Facials', 'Hair Spa', 'Reflexology / Massage', 'Express Face Masks',
            'Haircut Combos', 'Hair Colour', 'Streaks'
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
        
        request.session['selected_service_ids'] = service_ids
        return redirect('date_time_selection')

class DateTimeSelectionView(View):
    def get(self, request):
        selected_service_ids = request.session.get('selected_service_ids')
        if not selected_service_ids:
            return redirect('service_list')
        
        # Requirement: 1 hour per service
        num_services = len(selected_service_ids)
        
        selected_date_str = request.GET.get('date')
        slots = []
        selected_date = None
        
        # Calculate max date (14 days from today)
        now = timezone.localtime(timezone.now())
        max_date = now.date() + timedelta(days=14)

        if selected_date_str:
            try:
                selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
                if selected_date < now.date():
                     # Prevent past dates
                     selected_date = None
                elif selected_date > max_date:
                    # Prevent dates beyond 14 days
                    selected_date = None
                elif selected_date.weekday() == 6:
                    # Prevent Sundays (6 = Sunday)
                    selected_date = None
            except ValueError:
                pass
        
        if selected_date:
            # Slot generation logic
            start_hour = 10
            end_hour = 22
            
            # If today, ensuring time slot is after current time
            if selected_date == now.date():
                # E.g. if now is 15:30, next slot is 16:00.
                start_hour = max(start_hour, now.hour + 1)

            # Cleanup Stale Bookings (Requirement: block only if pending < 5 mins)
            cutoff_time = timezone.now() - timedelta(minutes=5)
            
            # Delete stale pending bookings to free up slots immediately
            Booking.objects.filter(
                status='pending',
                otp_created_at__lt=cutoff_time
            ).delete()

            # Fetch existing bookings
            # Logic: Confirmed/Completed block slots.
            # Pending blocks slots (we just deleted stale ones, so all remaining pending are valid blocks)
            
            existing_bookings = Booking.objects.filter(
                date=selected_date
            ).filter(
                status__in=['confirmed', 'completed', 'pending']
            )
            
            booked_hours = set()
            for booking in existing_bookings:
                # Each booking now represents ONE service = ONE hour
                booked_hours.add(booking.time.hour)
            
            # Find consecutive available slots
            for h in range(start_hour, end_hour):
                if h + num_services > end_hour:
                    break
                
                # Check if all needed hours are free
                is_valid = True
                for i in range(num_services):
                    if (h + i) in booked_hours:
                        is_valid = False
                        break
                
                if is_valid:
                    # Explicitly creating datetime.time object as requested
                    t_obj = time(h, 0)
                    slots.append(t_obj)
                    # Debug print to verify type in console
                    if len(slots) == 1:
                        print(f"DEBUG: Slot type is {type(t_obj)}")

        return render(request, 'bookings/calendar.html', {
            'slots': slots,
            'selected_date': selected_date,
            'today': timezone.now().date(),
            'max_date': max_date,
            'num_services': num_services
        })

    def post(self, request):
        date_str = request.POST.get('date')
        time_str = request.POST.get('time')
        
        if not date_str or not time_str:
            return redirect('date_time_selection')
            
        request.session['selected_date'] = date_str
        request.session['selected_time'] = time_str
        return redirect('booking_confirmation')

class BookingConfirmationView(View):
    def get(self, request):
        selected_service_ids = request.session.get('selected_service_ids')
        date_str = request.session.get('selected_date')
        time_str = request.session.get('selected_time')
        
        if not (selected_service_ids and date_str and time_str):
            return redirect('service_list')
            
        services = Service.objects.filter(id__in=selected_service_ids)
        total_price = sum(s.price for s in services)
        
        form = GuestDetailsForm()
        
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
            # Rate Limiting & Abuse Check
            if request.user.is_authenticated:
                phone = request.user.phone_number
            else:
                phone = form.cleaned_data['customer_phone']
            
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
            
            services = Service.objects.filter(id__in=selected_service_ids)
            
            # Determine if trusted or logged in
            if request.user.is_authenticated:
                is_trusted_user = True
            else:
                is_trusted_user = False
                # Trust Score Check for Guests
                trust_profile = CustomerTrust.objects.filter(phone_number=phone).first()
                if trust_profile and trust_profile.trust_level != 'low':
                    is_trusted_user = True

            # Create Bookings Transactionally
            group_id = uuid.uuid4()
            plain_otp = utils.generate_otp()
            hashed_otp = utils.hash_otp(plain_otp)
            now_time = timezone.now()
            
            # Determine initial status
            initial_status = 'payment_pending' if is_trusted_user else 'pending'
            is_initial_verified = True if is_trusted_user else False
            
            start_time_obj = datetime.strptime(time_str, '%H:%M:%S').time() if len(time_str) > 5 else datetime.strptime(time_str, '%H:%M').time()
            start_hour = start_time_obj.hour
            
            try:
                with transaction.atomic():
                    for idx, service_id in enumerate(selected_service_ids):
                        service = services.get(id=service_id)
                        booking_time = time(start_hour + idx, 0)
                        
                        booking = Booking(
                            customer_phone=phone,
                            customer_gender=request.session.get('selected_gender', 'Male'),
                            service=service,
                            booking_group_id=group_id,
                            date=date_str,
                            time=booking_time,
                            status=initial_status,
                            ip_address=ip,
                            otp=hashed_otp if not is_trusted_user else None, # Store hash only if needed
                            otp_created_at=now_time if not is_trusted_user else None,
                            is_verified=is_initial_verified
                        )
                        booking.save()
                        
            except IntegrityError:
                return render(request, 'bookings/error.html', {
                    'message': 'One of the selected time slots was just booked by another user. Please try again.'
                })
            except Exception as e:
                 return render(request, 'bookings/error.html', {'message': f'An error occurred: {str(e)}'})

            if is_trusted_user:
                # Direct to Payment
                request.session['pending_group_id'] = str(group_id)
                
                # Cleanup selection session
                if 'selected_service_ids' in request.session: del request.session['selected_service_ids']
                if 'selected_date' in request.session: del request.session['selected_date']
                if 'selected_time' in request.session: del request.session['selected_time']

                return redirect('payment_process')
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
        services = Service.objects.filter(id__in=selected_service_ids)
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
            # Success!
            # bookings.update(is_verified=True, status='confirmed') # OLD
            
            # Auto-Login (New Requirement)
            try:
                user, created = User.objects.get_or_create(phone_number=booking.customer_phone)
                if created:
                    user.username = booking.customer_phone
                    user.save()
                login(request, user)
            except Exception as e:
                print(f"Auto-login failed: {e}")

            # New Flow: OTP Verified -> Payment Pending -> Payment Process View
            bookings.update(is_verified=True, status='payment_pending')
            return redirect('payment_process')

        else:
            return render(request, 'bookings/otp_verify.html', {
                'booking': booking,
                'error': 'Invalid OTP. Please try again.'
            })

@method_decorator(csrf_exempt, name='dispatch')
class PaymentProcessView(View):
    def get(self, request):
        group_id = request.session.get('pending_group_id')
        if not group_id:
            return redirect('home')
            
        bookings = Booking.objects.filter(booking_group_id=group_id)
        if not bookings.exists():
            return redirect('service_list')
            
        # If already confirmed, skip payment
        if bookings.first().status == 'confirmed':
            return redirect('booking_success')
            
        # Initialize Razorpay
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        
        # Calculate Amount
        total_amount = sum(b.service.price for b in bookings)
        amount_paise = int(total_amount * 100)
        
        booking = bookings.first()
        
        # Create Order (if not already exists for this group to avoid duplicates on refresh)
        if booking.razorpay_order_id:
            order_id = booking.razorpay_order_id
        else:
            order_currency = 'INR'
            order_receipt = str(group_id)
            notes = {'booking_group_id': str(group_id)}
            try:
                payment_order = client.order.create(dict(amount=amount_paise, currency=order_currency, receipt=order_receipt, notes=notes))
                order_id = payment_order['id']
                bookings.update(razorpay_order_id=order_id, status='payment_pending')
            except Exception as e:
                print(f"Razorpay Order Error: {e}")
                return render(request, 'bookings/error.html', {'message': 'Error initializing payment.'})

        context = {
            'booking': booking,
            'bookings': bookings,
            'total_amount': total_amount,
            'razorpay_order_id': order_id,
            'razorpay_merchant_key': settings.RAZORPAY_KEY_ID,
            'razorpay_amount': amount_paise,
            'currency': 'INR',
            'razorpay_amount': amount_paise,
            'currency': 'INR',
            'callback_url': reverse('payment_verify'), # Dynamic URL construction
            'customer_phone': booking.customer_phone,
            'customer_email': booking.customer_email or ''
        }
        
        return render(request, 'bookings/payment.html', context)

@method_decorator(csrf_exempt, name='dispatch')
class PaymentVerificationView(View):
    def post(self, request):
        payment_id = request.POST.get('razorpay_payment_id')
        order_id = request.POST.get('razorpay_order_id')
        signature = request.POST.get('razorpay_signature')
        
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        
        try:
            # Verify Signature
            data = {
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': signature
            }
            client.utility.verify_payment_signature(data)
            
            # SUCCESS
            bookings = Booking.objects.filter(razorpay_order_id=order_id)
            if not bookings.exists():
                 return render(request, 'bookings/error.html', {'message': 'Order not found.'})
            
            # Transition Status
            bookings.update(
                status='confirmed',
                razorpay_payment_id=payment_id
            )
            
            first_booking = bookings.first()
            
            # Update Trust
            utils.update_trust_score(first_booking.customer_phone, 'new_booking')
            
            # Send Email (NOW we send it)
            # We can send one email for the group
            # Ideally utils.send_booking_confirmation_email handles single booking object, 
            # if we want to show all services, we might need to adjust utils or just send for first.
            # Current util sends for 'booking', mentioning service name.
            # If multiple services, we send multiple emails OR update util.
            # Let's send for each to be safe/consistent with previous logic, 
            # OR better: update util to handle group (but that's extra scope).
            # The previous logic in BookingConfirmationView loop was to send for each.
            
            for b in bookings:
                utils.send_booking_confirmation_email(b)
                
            utils.send_confirmation_sms(first_booking.customer_phone, f"Confirmed! Date: {first_booking.date} Time: {first_booking.time}")
            
            # Set session for Success Page
            request.session['last_booking_group_id'] = str(first_booking.booking_group_id)
            
            # Clean up pending session if exists (though we might be in a new tab/session context if redirect happens differently, 
            # but usually it's same browser session)
            if 'pending_group_id' in request.session:
                del request.session['pending_group_id']
                
            return redirect('booking_success')
            
        except razorpay.errors.SignatureVerificationError:
            # FAILURE
            bookings = Booking.objects.filter(razorpay_order_id=order_id)
            bookings.update(status='payment_failed')
            return render(request, 'bookings/error.html', {'message': 'Payment Verification Failed. Please contact support if money was deducted.'})
        except Exception as e:
            print(f"Payment Verification Error: {e}")
            return render(request, 'bookings/error.html', {'message': 'An error occurred during payment verification.'})

class BookingSuccessView(View):
    def get(self, request):
        group_id = request.session.get('last_booking_group_id')
        if not group_id:
            return redirect('service_list')
            
        bookings = Booking.objects.filter(booking_group_id=group_id)
        booking = bookings.first()
        return render(request, 'bookings/success.html', {'booking': booking, 'bookings': bookings})

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
            
        messages.success(request, "Your booking has been cancelled. The payment will be credited back to your account within 2–7 business days.")
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
