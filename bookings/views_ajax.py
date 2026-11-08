from django.views import View
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import json
from .models import Service, Booking, CustomerTrust
from . import utils
from . import booking_service
from . import coupons as coupon_utils
from . import addons as addon_utils
from . import slots as slot_utils


def _session_cart(request):
    """Return selected ids, synced combo overrides, priced rows, and subtotal."""
    selected_service_ids = list(request.session.get('selected_service_ids') or [])
    overrides = addon_utils.sync_combo_overrides(selected_service_ids)
    request.session['combo_price_overrides'] = overrides
    priced_rows = addon_utils.build_priced_services(selected_service_ids, overrides)
    subtotal = sum((row['price'] for row in priced_rows), Decimal('0.00'))
    return selected_service_ids, overrides, priced_rows, subtotal


def _pricing_payload(request, priced_rows, subtotal, discount_amount=None, coupon_code='', coupon_message=''):
    if discount_amount is None:
        discount_amount = Decimal('0.00')
        coupon_code = request.session.get('applied_coupon_code', '')
        if coupon_code:
            try:
                phone = ''
                if request.user.is_authenticated:
                    phone = getattr(request.user, 'phone_number', '') or ''
                coupon, discount_amount = coupon_utils.validate_and_apply_coupon(
                    coupon_code,
                    subtotal,
                    customer_phone=phone,
                    priced_rows=priced_rows,
                )
                coupon_code = coupon.code
                request.session['applied_coupon_code'] = coupon.code
            except coupon_utils.CouponError as exc:
                request.session.pop('applied_coupon_code', None)
                coupon_code = ''
                discount_amount = Decimal('0.00')
                coupon_message = exc.message

    payable = subtotal - discount_amount
    if payable < 0:
        payable = Decimal('0.00')

    return {
        'services': [
            {
                'id': row['service_id'],
                'name': row['name'],
                'price': f"{row['price']:.2f}",
                'regular_price': f"{row['regular_price']:.2f}",
                'is_combo': row['is_combo'],
            }
            for row in priced_rows
        ],
        'subtotal': f'{subtotal:.2f}',
        'discount_amount': f'{discount_amount:.2f}',
        'total_price': f'{payable:.2f}',
        'applied_coupon_code': coupon_code,
        'coupon_message': coupon_message,
        'upsell_addons': [
            {
                'service_id': card['service_id'],
                'name': card['name'],
                'already_added': card['already_added'],
                'regular_price': f"{card['regular_price']:.2f}",
                'combo_price': f"{card['combo_price']:.2f}",
                'savings': f"{card['savings']:.2f}",
            }
            for card in addon_utils.get_upsell_carousel_items(
                request.session.get('selected_service_ids') or [],
                request.session.get('combo_price_overrides') or {},
            )
        ],
    }


# ========================
# AJAX Views for Voice OTP
# ========================

class InitiateBookingView(View):
    def post(self, request):
        try:
            try:
                data = json.loads(request.body)
                customer_name = data.get('customer_name')
                phone = data.get('customer_phone')
                email = data.get('customer_email')
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'message': 'Invalid data'})

            if not phone or not customer_name or not customer_name.strip():
                 return JsonResponse({'success': False, 'message': 'Name and phone number are required.'})

            # Basic Validation
            if len(phone) < 10:
                 return JsonResponse({'success': False, 'message': 'Invalid phone number.'})
                 
            # Rate Limiting
            ip = utils.get_client_ip(request)
            allowed, message = utils.check_rate_limits(phone, ip)
            if not allowed:
                return JsonResponse({'success': False, 'message': message})

            # Retrieve session data
            selected_service_ids = request.session.get('selected_service_ids')
            date_str = request.session.get('selected_date')
            time_str = request.session.get('selected_time')
            selected_gender = request.session.get('selected_gender', 'Male')
            
            if not (selected_service_ids and date_str and time_str):
                return JsonResponse({'success': False, 'message': 'Session expired. Please start over.', 'redirect': reverse('service_list')})

            overrides = addon_utils.sync_combo_overrides(selected_service_ids)
            request.session['combo_price_overrides'] = overrides

            unique_services = Service.objects.filter(id__in=set(selected_service_ids))
            service_dict = {str(s.id): s for s in unique_services}
            sequenced_services = [service_dict[str(sid)] for sid in selected_service_ids if str(sid) in service_dict]
            
            # Trusted users: skip OTP for booking
            if request.user.is_authenticated:
                is_trusted = True
                # Keep profile in sync if customer updates details on confirm
                try:
                    user = request.user
                    changed = False
                    if customer_name and user.first_name != customer_name:
                        user.first_name = customer_name
                        changed = True
                    if email and user.email != email:
                        user.email = email
                        changed = True
                    if changed:
                        user.save(update_fields=['first_name', 'email'])
                except Exception as e:
                    print(f"Profile sync skipped: {e}")
            else:
                is_trusted = request.user.is_authenticated
                
            plain_otp = utils.generate_otp()
            hashed_otp = utils.hash_otp(plain_otp)
            now_time = timezone.now()
            
            initial_status = 'confirmed' if is_trusted else 'pending_otp'
            is_initial_verified = True if is_trusted else False
            
            start_time_obj = datetime.strptime(time_str, '%H:%M:%S').time() if len(time_str) > 5 else datetime.strptime(time_str, '%H:%M').time()
            booking_date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            try:
                priced_rows = addon_utils.build_priced_services(selected_service_ids, overrides)
                subtotal = sum((row['price'] for row in priced_rows), Decimal('0.00'))
                coupon_code = ''
                discount_amount = Decimal('0.00')
                session_coupon = request.session.get('applied_coupon_code')
                if session_coupon:
                    try:
                        coupon, discount_amount = coupon_utils.validate_and_apply_coupon(
                            session_coupon,
                            subtotal,
                            customer_phone=phone,
                            priced_rows=priced_rows,
                        )
                        coupon_code = coupon.code
                    except coupon_utils.CouponError as exc:
                        request.session.pop('applied_coupon_code', None)
                        return JsonResponse({'success': False, 'message': exc.message})

                group_id, bookings_created = booking_service.create_booking_group(
                    sequenced_services=sequenced_services,
                    booking_date=booking_date_obj,
                    start_time=start_time_obj,
                    customer_name=customer_name,
                    customer_phone=phone,
                    customer_email=email,
                    customer_gender=selected_gender,
                    booking_source='customer',
                    status=initial_status,
                    is_verified=is_initial_verified,
                    ip_address=ip,
                    otp=hashed_otp if not is_trusted else None,
                    otp_created_at=now_time if not is_trusted else None,
                    coupon_code=coupon_code,
                    discount_amount=discount_amount,
                    price_overrides=overrides,
                )
            except booking_service.BookingCreationError as exc:
                return JsonResponse({'success': False, 'message': exc.message})
            
            # Response Handling
            if is_trusted:
                # Provide auto-login if they bypassed OTP via setting or trust but were not logged in
                if not request.user.is_authenticated and phone and len(phone) > 5:
                    from django.contrib.auth import login
                    from users.models import User
                    try:
                        user, created = User.objects.get_or_create(phone_number=phone)
                        if created:
                            user.username = phone
                        if customer_name and user.first_name != customer_name:
                            user.first_name = customer_name
                        if email and user.email != email:
                            user.email = email
                        user.save()
                        login(request, user)
                    except Exception as e:
                        print(f"Auto-login failed after bypass: {e}")

                # Immediately confirm and notify
                bookings = Booking.objects.filter(booking_group_id=group_id)
                first_booking = bookings.first()
                if first_booking:
                    if first_booking.customer_email:
                        utils.send_booking_emails_async(first_booking, request)
                    utils.send_confirmation_sms(first_booking.customer_phone, f"Confirmed! Date: {first_booking.date} Time: {first_booking.time}")

                request.session['last_booking_group_id'] = str(group_id)

                # Clear session
                for key in ('selected_service_ids', 'selected_date', 'selected_time', 'applied_coupon_code', 'combo_price_overrides'):
                    if key in request.session:
                        del request.session[key]

                return JsonResponse({
                    'success': True,
                    'trusted': True,
                    'booking_source': 'customer',
                    'redirect': reverse('booking_success'),
                })
            else:
                 # Send Voice OTP
                 sent = utils.send_voice_otp_2factor(phone, plain_otp)
                 if not sent:
                     return JsonResponse({'success': False, 'message': 'Failed to send OTP. Please try again.'})
                 
                 request.session['pending_group_id'] = str(group_id)
                 return JsonResponse({
                     'success': True, 
                     'trusted': False,
                     'booking_source': 'customer',
                     'group_id': str(group_id),
                     'otp_expiry': 300 # 5 mins
                 })
                 
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Server error: {str(e)}'})

class ApplyCouponView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            code = data.get('code', '')
            customer_phone = data.get('customer_phone', '')
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid data'})

        selected_service_ids, overrides, priced_rows, subtotal = _session_cart(request)
        if not selected_service_ids:
            return JsonResponse({'success': False, 'message': 'Session expired. Please start over.'})

        if not customer_phone and request.user.is_authenticated:
            customer_phone = getattr(request.user, 'phone_number', '') or ''

        try:
            coupon, discount = coupon_utils.validate_and_apply_coupon(
                code,
                subtotal,
                customer_phone=customer_phone,
                priced_rows=priced_rows,
            )
        except coupon_utils.CouponError as exc:
            return JsonResponse({'success': False, 'message': exc.message})

        request.session['applied_coupon_code'] = coupon.code
        payload = _pricing_payload(
            request,
            priced_rows,
            subtotal,
            discount_amount=discount,
            coupon_code=coupon.code,
        )
        payload.update({
            'success': True,
            'code': coupon.code,
            'discount_label': (
                (
                    f'{coupon.discount_value}% off'
                    if coupon.discount_type == coupon.DISCOUNT_PERCENTAGE
                    else f'₹{coupon.discount_value} off'
                )
                + (f' on {coupon.service.name}' if coupon.service_id and coupon.service else '')
            ),
            'customer_specific': bool(coupon.customer_phone),
            'service_specific': bool(coupon.service_id),
            'service_name': coupon.service.name if coupon.service_id and coupon.service else '',
        })
        return JsonResponse(payload)


class RemoveCouponView(View):
    def post(self, request):
        request.session.pop('applied_coupon_code', None)
        selected_service_ids, overrides, priced_rows, subtotal = _session_cart(request)
        payload = _pricing_payload(
            request,
            priced_rows,
            subtotal,
            discount_amount=Decimal('0.00'),
            coupon_code='',
        )
        payload['success'] = True
        return JsonResponse(payload)


class EligibleCouponsView(View):
    def get(self, request):
        selected_service_ids, overrides, priced_rows, subtotal = _session_cart(request)
        if not selected_service_ids:
            return JsonResponse({'success': False, 'message': 'Session expired.', 'coupons': []})

        customer_phone = request.GET.get('customer_phone', '')
        if not customer_phone and request.user.is_authenticated:
            customer_phone = getattr(request.user, 'phone_number', '') or ''

        coupons = coupon_utils.get_eligible_coupons(
            customer_phone=customer_phone,
            subtotal=subtotal,
            priced_rows=priced_rows,
        )
        return JsonResponse({
            'success': True,
            'subtotal': f'{subtotal:.2f}',
            'coupons': coupons,
        })


class ToggleAddonView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            service_id = str(data.get('service_id', '')).strip()
            action = (data.get('action') or 'add').strip().lower()
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid data'})

        if not service_id.isdigit():
            return JsonResponse({'success': False, 'message': 'Invalid add-on.'})

        selected_service_ids = [str(sid) for sid in (request.session.get('selected_service_ids') or [])]
        if not selected_service_ids:
            return JsonResponse({'success': False, 'message': 'Session expired. Please start over.'})

        unique = Service.objects.filter(id__in=set(selected_service_ids))
        service_dict = {str(s.id): s for s in unique}
        current_services = [service_dict[sid] for sid in selected_service_ids if sid in service_dict]

        if action == 'add' and not addon_utils.selection_has_any_combo_trigger(current_services):
            return JsonResponse({
                'success': False,
                'message': 'Combo add-ons are available when you book an eligible main service.',
            })

        offer = addon_utils.get_offer_for_linked_service(int(service_id), selected_service_ids)
        if action == 'add' and not offer:
            return JsonResponse({
                'success': False,
                'message': 'This combo is not available for your selected services.',
            })

        addon = Service.objects.filter(id=int(service_id)).first()
        if not addon:
            return JsonResponse({'success': False, 'message': 'Add-on not found.'})

        date_str = request.session.get('selected_date')
        time_str = request.session.get('selected_time')
        if not date_str or not time_str:
            return JsonResponse({'success': False, 'message': 'Session expired. Please start over.'})

        if action == 'remove':
            selected_service_ids = [sid for sid in selected_service_ids if sid != service_id]
        else:
            if service_id not in selected_service_ids:
                # Use offer duration for slot check when available
                duration_minutes = offer.duration_minutes if offer else addon.duration_minutes
                other_duration = sum(s.duration_minutes for s in current_services)
                total_duration = other_duration + duration_minutes
                try:
                    booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    start_time = (
                        datetime.strptime(time_str, '%H:%M:%S').time()
                        if len(time_str) > 5
                        else datetime.strptime(time_str, '%H:%M').time()
                    )
                except ValueError:
                    return JsonResponse({'success': False, 'message': 'Invalid date or time in session.'})

                requested_start = datetime.combine(booking_date, start_time)
                requested_end = requested_start + timedelta(minutes=total_duration)
                if not slot_utils.is_interval_free(booking_date, requested_start, requested_end):
                    return JsonResponse({
                        'success': False,
                        'message': 'Your selected time slot is too short for this add-on. Please go back and choose a later slot, or continue without it.',
                    })
                selected_service_ids = selected_service_ids + [service_id]

        request.session['selected_service_ids'] = selected_service_ids
        selected_service_ids, overrides, priced_rows, subtotal = _session_cart(request)
        payload = _pricing_payload(request, priced_rows, subtotal)
        combo_price = offer.combo_price if offer else overrides.get(service_id, addon.price)
        display_name = offer.name if offer else addon.name
        payload.update({
            'success': True,
            'message': (
                f'{display_name} removed.'
                if action == 'remove'
                else f'{display_name} added at combo price ₹{Decimal(combo_price):.0f}.'
            ),
            'action': action,
            'service_id': int(service_id),
        })
        return JsonResponse(payload)


class VerifyBookingOTPView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            group_id = data.get('group_id')
            entered_otp = data.get('otp')
        except:
             return JsonResponse({'success': False, 'message': 'Invalid data'})
             
        if not group_id or not entered_otp:
            return JsonResponse({'success': False, 'message': 'Missing OTP or ID'})
            
        bookings = Booking.objects.filter(booking_group_id=group_id)
        if not bookings.exists():
            return JsonResponse({'success': False, 'message': 'Booking not found.'})
            
        booking = bookings.first()
        
        if booking.status == 'confirmed':
             return JsonResponse({'success': True, 'message': 'Already confirmed'})
             
        if booking.is_otp_expired():
             return JsonResponse({'success': False, 'message': 'OTP Expired.'})
             
        if utils.verify_otp_hash(entered_otp, booking.otp):
            # Success: OTP verified -> mark confirmed
            bookings.update(is_verified=True, status='confirmed')

            # Send notifications
            first_booking = bookings.first()
            if first_booking:
                if first_booking.customer_email:
                    utils.send_booking_emails_async(first_booking, request)
                utils.send_confirmation_sms(first_booking.customer_phone, f"Confirmed! Date: {first_booking.date} Time: {first_booking.time}")

            request.session['last_booking_group_id'] = group_id
            if 'pending_group_id' in request.session:
                del request.session['pending_group_id']

            # Clear selection data
            k = ['selected_service_ids', 'selected_date', 'selected_time', 'applied_coupon_code', 'combo_price_overrides']
            for key in k:
                if key in request.session: del request.session[key]

            return JsonResponse({'success': True, 'redirect': reverse('booking_success')})
        else:
            return JsonResponse({'success': False, 'message': 'Incorrect OTP.'})

class ResendOTPView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            group_id = data.get('group_id')
        except:
             return JsonResponse({'success': False})

        bookings = Booking.objects.filter(booking_group_id=group_id)
        if not bookings.exists():
             return JsonResponse({'success': False, 'message': 'Booking not found'})
             
        booking = bookings.first()
        if booking.status == 'confirmed':
             return JsonResponse({'success': False, 'message': 'Already confirmed'})
             
        # Generate new OTP
        plain_otp = utils.generate_otp()
        hashed_otp = utils.hash_otp(plain_otp)
        
        bookings.update(otp=hashed_otp, otp_created_at=timezone.now())
        
        sent = utils.send_voice_otp_2factor(booking.customer_phone, plain_otp)
        if sent:
            return JsonResponse({'success': True})
        else:
             return JsonResponse({'success': False, 'message': 'Failed to send OTP'})
