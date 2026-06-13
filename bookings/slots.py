from datetime import datetime, time, timedelta

from django.utils import timezone

from .models import BlockedDay, BlockedSlot, Booking

SHOP_OPEN_HOUR = 10
SHOP_CLOSE_HOUR = 21
SLOT_INTERVAL_MINUTES = 30
LUNCH_START = time(14, 0)
LUNCH_END = time(16, 0)


def ranges_overlap(start1, end1, start2, end2):
    return max(start1, start2) < min(end1, end2)


def get_lunch_bounds(selected_date):
    return (
        datetime.combine(selected_date, LUNCH_START),
        datetime.combine(selected_date, LUNCH_END),
    )


def get_shop_bounds(selected_date):
    return (
        datetime.combine(selected_date, time(SHOP_OPEN_HOUR, 0)),
        datetime.combine(selected_date, time(SHOP_CLOSE_HOUR, 0)),
    )


def cleanup_stale_pending_bookings():
    cutoff_time = timezone.now() - timedelta(minutes=5)
    Booking.objects.filter(
        status='pending_otp',
        otp_created_at__lt=cutoff_time,
    ).delete()


def get_active_bookings(selected_date):
    cleanup_stale_pending_bookings()
    return Booking.objects.filter(
        date=selected_date,
        status__in=['confirmed', 'completed', 'pending_otp'],
    )


def get_blocked_slot_times(selected_date):
    return set(
        BlockedSlot.objects.filter(date=selected_date).values_list('time', flat=True)
    )


def get_booking_range(selected_date, booking):
    ex_start = datetime.combine(selected_date, booking.time)
    if booking.end_time:
        ex_end = datetime.combine(selected_date, booking.end_time)
    else:
        ex_end = ex_start + timedelta(hours=1)
    return ex_start, ex_end


def interval_overlaps_bookings(selected_date, interval_start, interval_end, bookings):
    for booking in bookings:
        ex_start, ex_end = get_booking_range(selected_date, booking)
        if ranges_overlap(interval_start, interval_end, ex_start, ex_end):
            return True
    return False


def interval_overlaps_blocked_slots(selected_date, interval_start, interval_end, blocked_times=None):
    if blocked_times is None:
        blocked_times = get_blocked_slot_times(selected_date)

    for blocked_time in blocked_times:
        blocked_start = datetime.combine(selected_date, blocked_time)
        blocked_end = blocked_start + timedelta(minutes=SLOT_INTERVAL_MINUTES)
        if ranges_overlap(interval_start, interval_end, blocked_start, blocked_end):
            return True
    return False


def is_interval_free(selected_date, interval_start, interval_end, bookings=None, blocked_times=None):
    if BlockedDay.objects.filter(date=selected_date).exists():
        return False

    lunch_start, lunch_end = get_lunch_bounds(selected_date)
    if ranges_overlap(interval_start, interval_end, lunch_start, lunch_end):
        return False

    if bookings is None:
        bookings = get_active_bookings(selected_date)

    if interval_overlaps_bookings(selected_date, interval_start, interval_end, bookings):
        return False

    if interval_overlaps_blocked_slots(selected_date, interval_start, interval_end, blocked_times):
        return False

    return True


def iter_slot_starts(selected_date):
    start_dt, end_dt = get_shop_bounds(selected_date)
    current_dt = start_dt
    while current_dt < end_dt:
        slot_end = current_dt + timedelta(minutes=SLOT_INTERVAL_MINUTES)
        if slot_end > end_dt:
            break
        yield current_dt
        current_dt += timedelta(minutes=SLOT_INTERVAL_MINUTES)


def can_block_slot(selected_date, slot_time):
    today = timezone.localtime(timezone.now()).date()
    if selected_date < today:
        return False, 'Cannot block slots on past dates.'

    if BlockedDay.objects.filter(date=selected_date).exists():
        return False, 'This day is fully blocked.'

    if BlockedSlot.objects.filter(date=selected_date, time=slot_time).exists():
        return False, 'This slot is already blocked.'

    slot_start = datetime.combine(selected_date, slot_time)
    slot_end = slot_start + timedelta(minutes=SLOT_INTERVAL_MINUTES)
    shop_start, shop_end = get_shop_bounds(selected_date)

    if slot_start < shop_start or slot_end > shop_end:
        return False, 'This slot is outside shop hours.'

    lunch_start, lunch_end = get_lunch_bounds(selected_date)
    if ranges_overlap(slot_start, slot_end, lunch_start, lunch_end):
        return False, 'This slot is not available.'

    now = timezone.localtime(timezone.now())
    if selected_date == today and timezone.make_aware(slot_start) < now:
        return False, 'Cannot block past time slots.'

    bookings = list(get_active_bookings(selected_date))
    if interval_overlaps_bookings(selected_date, slot_start, slot_end, bookings):
        return False, 'This slot is not free. Cancel the booking first or choose another slot.'

    return True, ''


def get_manage_slots_for_date(selected_date):
    if BlockedDay.objects.filter(date=selected_date).exists():
        return []

    now = timezone.localtime(timezone.now())
    today = now.date()
    bookings = list(get_active_bookings(selected_date))
    blocked_times = get_blocked_slot_times(selected_date)
    lunch_start, lunch_end = get_lunch_bounds(selected_date)

    slots = []
    for slot_start_dt in iter_slot_starts(selected_date):
        slot_end_dt = slot_start_dt + timedelta(minutes=SLOT_INTERVAL_MINUTES)
        slot_time = slot_start_dt.time()

        if ranges_overlap(slot_start_dt, slot_end_dt, lunch_start, lunch_end):
            continue

        is_past = False
        if selected_date == today and timezone.make_aware(slot_start_dt) < now:
            is_past = True

        is_blocked = slot_time in blocked_times
        is_booked = interval_overlaps_bookings(
            selected_date, slot_start_dt, slot_end_dt, bookings
        )

        if is_past:
            status = 'past'
        elif is_booked:
            status = 'booked'
        elif is_blocked:
            status = 'blocked'
        else:
            status = 'free'

        slots.append({
            'time': slot_time,
            'status': status,
            'can_block': status == 'free',
            'can_unblock': status == 'blocked',
        })

    return slots
