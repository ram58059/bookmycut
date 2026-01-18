from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.utils import timezone
from django.db.models import Q
from django.contrib import messages
from datetime import datetime, time, timedelta
from .models import Service, Booking, CustomerTrust
from .forms import GuestDetailsForm
from . import utils

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
            'Facials', 'Hair Spa', 'Reflexology / Massage', 'Express Face Masks',
            'Haircut Combos', 'Hair Services', 'Hair Colour', 'Streaks'
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
        
        if selected_date_str:
            try:
                selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
                if selected_date < timezone.now().date():
                     # Prevent past dates
                     selected_date = None
            except ValueError:
                pass
        
        if selected_date:
            # Slot generation logic
            start_hour = 10
            end_hour = 22
            
            # If today, ensuring time slot is after current time
            now = timezone.now()
            if selected_date == now.date():
                # E.g. if now is 15:30, next slot is 16:00.
                start_hour = max(start_hour, now.hour + 1)

            # Fetch existing bookings
            # Logic: Confirmed/Completed block slots.
            # Pending blocks slots ONLY if < 5 mins old (held for verification).
            # Cancelled/NoShow do not block slots.
            
            cutoff_time = timezone.now() - timedelta(minutes=5)
            
            existing_bookings = Booking.objects.filter(
                date=selected_date
            ).filter(
                Q(status__in=['confirmed', 'completed']) |
                Q(status='pending', otp_created_at__gt=cutoff_time)
            ).prefetch_related('services')
            
            booked_hours = set()
            for booking in existing_bookings:
                # Each booking takes N hours where N = num of services
                # Logic: We assume each service takes 1 hour as per requirement
                duration_hours = booking.services.count()
                booking_start = booking.time.hour
                for i in range(duration_hours):
                    booked_hours.add(booking_start + i)
            
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
                    slots.append(time(h, 0))

        return render(request, 'bookings/calendar.html', {
            'slots': slots,
            'selected_date': selected_date,
            'today': timezone.now().date(),
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
            'form': form
        })

    def post(self, request):
        form = GuestDetailsForm(request.POST)
        if form.is_valid():
            # Rate Limiting & Abuse Check
            phone = form.cleaned_data['customer_phone']
            ip = utils.get_client_ip(request)
            
            allowed, message = utils.check_rate_limits(phone, ip)
            if not allowed:
                return render(request, 'bookings/error.html', {'message': message})
            
            # Trust Score Check (Optional: Block low trust users or forcing manual review?)
            # For now we just proceed, but we could enforce rules here.
            
            # Retrieve session data
            selected_service_ids = request.session.get('selected_service_ids')
            date_str = request.session.get('selected_date')
            time_str = request.session.get('selected_time')
            
            if not (selected_service_ids and date_str and time_str):
                return redirect('service_list')
            
            # Create Pending Booking
            booking = form.save(commit=False)
            booking.date = date_str
            booking.time = time_str
            booking.customer_gender = request.session.get('selected_gender', 'Male')
            booking.status = 'pending' # Pending verification
            booking.ip_address = ip
            
            # Generate OTP
            booking.otp = utils.generate_otp()
            booking.otp_created_at = timezone.now()
            booking.is_verified = False
            
            booking.save()
            booking.services.set(selected_service_ids)
            booking.save()
            
            # Send OTP
            utils.send_otp_sms(booking.customer_phone, booking.otp)
            
            # Store ID in session for verification step
            request.session['pending_booking_id'] = booking.id
            
            # Clear selection session data (not booking ID)
            del request.session['selected_service_ids']
            del request.session['selected_date']
            del request.session['selected_time']
            
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
        booking_id = request.session.get('pending_booking_id')
        if not booking_id:
            return redirect('home')
        
        booking = get_object_or_404(Booking, id=booking_id)
        
        # Check if already verified
        if booking.status == 'confirmed':
             return redirect('booking_success')
             
        # Check expiration
        if booking.is_otp_expired():
             return render(request, 'bookings/error.html', {'message': 'OTP Expired. Please start over.'})
             
        return render(request, 'bookings/otp_verify.html', {'booking': booking})

    def post(self, request):
        booking_id = request.session.get('pending_booking_id')
        if not booking_id:
            return redirect('home')
            
        booking = get_object_or_404(Booking, id=booking_id)
        entered_otp = request.POST.get('otp')
        
        if booking.is_otp_expired():
             return render(request, 'bookings/error.html', {'message': 'OTP Expired. Please start over.'})

        if entered_otp == booking.otp:
            # Success!
            booking.is_verified = True
            booking.status = 'confirmed'
            booking.save()
            
            # Update Trust Stats
            utils.update_trust_score(booking.customer_phone, 'new_booking') # Just updates created
            
            # Send Confirmation
            utils.send_confirmation_sms(booking.customer_phone, f"Date: {booking.date} Time: {booking.time}")
            
            request.session['last_booking_id'] = booking.id
            del request.session['pending_booking_id']
            return redirect('booking_success')
        else:
            return render(request, 'bookings/otp_verify.html', {
                'booking': booking,
                'error': 'Invalid OTP. Please try again.'
            })

class BookingSuccessView(View):
    def get(self, request):
        booking_id = request.session.get('last_booking_id')
        if not booking_id:
            return redirect('service_list')
            
        booking = Booking.objects.filter(id=booking_id).first()
        return render(request, 'bookings/success.html', {'booking': booking})

class CancelBookingView(View):
    def get(self, request, booking_id):
        # In real app, verify signature/token. Here mock with ID.
        booking = get_object_or_404(Booking, id=booking_id)
        return render(request, 'bookings/cancel_confirm.html', {'booking': booking})
        
    def post(self, request, booking_id):
        booking = get_object_or_404(Booking, id=booking_id)
        
        if booking.status in ['cancelled', 'completed']:
            return render(request, 'bookings/error.html', {'message': 'Booking already processed.'})
            
        # Check for late cancellation (e.g., < 24 hours)
        appointment_datetime = datetime.combine(booking.date, booking.time)
        now = datetime.now()
        is_late = (appointment_datetime - now) < timedelta(hours=24)
        
        booking.status = 'cancelled'
        booking.save()
        
        # Update Trust
        if is_late:
            utils.update_trust_score(booking.customer_phone, 'late_cancel')
        else:
            # Regular cancel
            pass 
            
        return render(request, 'bookings/error.html', {'message': 'Booking cancelled successfully.'}) # Reusing error template for msg

# Deprecated/Placeholders (to be removed once URLs are updated)
def book_appointment(request):
    return redirect('service_list')

def booking_success(request):
    return redirect('booking_success_new')

def customer_dashboard(request):
    return redirect('home')

def barber_dashboard(request):
    return redirect('home')
