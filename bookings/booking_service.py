import uuid
from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import slots as slot_utils
from .models import BlockedDay, Booking, Service


class BookingCreationError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


def get_date_booking_rules(now=None):
    now = timezone.localtime(now or timezone.now())
    now_date = now.date()
    max_date = now_date + timedelta(days=7)
    min_allowed_date = now_date + timedelta(days=1) if now_date.weekday() == 6 else now_date
    return now, now_date, min_allowed_date, max_date


def validate_booking_date(selected_date, now_date=None, min_allowed_date=None, max_date=None):
    _, now_date, min_allowed_date, max_date = get_date_booking_rules()
    if selected_date < min_allowed_date or selected_date > max_date or selected_date.weekday() == 6:
        return False, 'Invalid date selected.'
    if BlockedDay.objects.filter(date=selected_date).exists():
        return False, 'This day is blocked.'
    return True, ''


def resolve_sequenced_services(service_ids):
    if not service_ids:
        return []
    unique_services = Service.objects.filter(id__in=set(service_ids))
    service_dict = {str(s.id): s for s in unique_services}
    sequenced = [service_dict[str(sid)] for sid in service_ids if str(sid) in service_dict]
    return sequenced


def get_available_slots(selected_date, sequenced_services, *, enforce_advance_buffer=True):
    if not sequenced_services:
        return []

    total_duration = sum(s.duration_minutes for s in sequenced_services) or 30
    now = timezone.localtime(timezone.now())
    now_date = now.date()

    if BlockedDay.objects.filter(date=selected_date).exists():
        return []

    existing_bookings = list(slot_utils.get_active_bookings(selected_date))
    start_dt = datetime.combine(selected_date, time(slot_utils.SHOP_OPEN_HOUR, 0))
    end_dt = datetime.combine(selected_date, time(slot_utils.SHOP_CLOSE_HOUR, 0))

    slots = []
    current_dt = start_dt
    while current_dt < end_dt:
        requested_start = current_dt
        requested_end = current_dt + timedelta(minutes=total_duration)
        if requested_end > end_dt:
            break

        if selected_date == now_date:
            aware_req_start = timezone.make_aware(requested_start)
            if aware_req_start < now:
                current_dt += timedelta(minutes=slot_utils.SLOT_INTERVAL_MINUTES)
                continue
            if enforce_advance_buffer and aware_req_start <= now + timedelta(minutes=30):
                current_dt += timedelta(minutes=slot_utils.SLOT_INTERVAL_MINUTES)
                continue

        if slot_utils.is_interval_free(
            selected_date,
            requested_start,
            requested_end,
            bookings=existing_bookings,
        ):
            slots.append(current_dt.time())

        current_dt += timedelta(minutes=slot_utils.SLOT_INTERVAL_MINUTES)

    return slots


def create_booking_group(
    *,
    sequenced_services,
    booking_date,
    start_time,
    customer_name,
    customer_phone,
    customer_email='',
    customer_gender='Male',
    booking_source='customer',
    status='confirmed',
    is_verified=True,
    ip_address=None,
    otp=None,
    otp_created_at=None,
    enforce_advance_buffer=True,
):
    if not sequenced_services:
        raise BookingCreationError('No valid services selected.')

    total_duration = sum(s.duration_minutes for s in sequenced_services)
    requested_start = datetime.combine(booking_date, start_time)
    requested_end = requested_start + timedelta(minutes=total_duration)

    now = timezone.localtime(timezone.now())
    if booking_date == now.date() and enforce_advance_buffer:
        aware_req_start = timezone.make_aware(requested_start)
        if aware_req_start <= now + timedelta(minutes=30):
            raise BookingCreationError('Appointments must be booked at least 30 minutes in advance.')

    if not slot_utils.is_interval_free(booking_date, requested_start, requested_end):
        raise BookingCreationError('The selected time slot is no longer available.')

    group_id = uuid.uuid4()
    bookings_created = []

    try:
        with transaction.atomic():
            current_start = requested_start
            for service in sequenced_services:
                current_end = current_start + timedelta(minutes=service.duration_minutes)
                booking = Booking(
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    customer_email=customer_email or None,
                    customer_gender=customer_gender,
                    service=service,
                    booking_group_id=group_id,
                    date=booking_date,
                    time=current_start.time(),
                    end_time=current_end.time(),
                    status=status,
                    booking_source=booking_source,
                    ip_address=ip_address,
                    otp=otp,
                    otp_created_at=otp_created_at,
                    is_verified=is_verified,
                )
                booking.save()
                bookings_created.append(booking)
                current_start = current_end
    except IntegrityError as exc:
        raise BookingCreationError('Time slot already booked.') from exc

    return group_id, bookings_created
