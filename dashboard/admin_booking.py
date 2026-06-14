from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render
from django.urls import reverse

from bookings import booking_service
from bookings.models import Service
from dashboard.models import ShopSetting
from dashboard.views import is_barber_or_admin

ADMIN_BOOKING_SESSION = 'admin_booking'


def _get_booking_draft(request):
    return request.session.get(ADMIN_BOOKING_SESSION, {})


def _save_booking_draft(request, draft):
    request.session[ADMIN_BOOKING_SESSION] = draft
    request.session.modified = True


def _clear_booking_draft(request):
    if ADMIN_BOOKING_SESSION in request.session:
        del request.session[ADMIN_BOOKING_SESSION]


def _require_business_phone(shop):
    phone = (shop.business_phone or '').strip()
    return phone if len(phone) >= 10 else None


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def admin_book_slot(request):
    shop = ShopSetting.load()
    business_phone = _require_business_phone(shop)

    if request.method == 'POST' and request.POST.get('action') == 'save_business_phone':
        phone = request.POST.get('business_phone', '').strip()
        if len(phone) < 10:
            messages.error(request, 'Enter a valid business phone number (at least 10 digits).')
        else:
            shop.business_phone = phone
            shop.save()
            messages.success(request, 'Business phone saved. You can now create bookings.')
            return redirect('dashboard_book_slot')
        business_phone = None

    if not business_phone:
        return render(request, 'dashboard/admin_book_slot_setup.html', {
            'page_title': 'Book Slot',
            'business_phone': shop.business_phone,
        })

    draft = _get_booking_draft(request)
    step = request.GET.get('step', draft.get('step', 'services'))

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'select_services':
            service_ids = request.POST.getlist('service_ids')
            if not service_ids:
                messages.error(request, 'Select at least one service.')
                step = 'services'
            else:
                draft = {'service_ids': service_ids, 'step': 'date'}
                _save_booking_draft(request, draft)
                return redirect(f"{reverse('dashboard_book_slot')}?step=date")

        elif action == 'select_date':
            date_str = request.POST.get('date')
            service_ids = draft.get('service_ids', [])
            if not service_ids:
                return redirect('dashboard_book_slot')

            try:
                selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except (TypeError, ValueError):
                messages.error(request, 'Invalid date selected.')
                return redirect(f"{reverse('dashboard_book_slot')}?step=date")

            valid, error_message = booking_service.validate_booking_date(selected_date)
            if not valid:
                messages.error(request, error_message)
                return redirect(f"{reverse('dashboard_book_slot')}?step=date")

            draft['date'] = date_str
            draft['step'] = 'time'
            _save_booking_draft(request, draft)
            return redirect(f"{reverse('dashboard_book_slot')}?step=time")

        elif action == 'select_time':
            time_str = request.POST.get('time')
            date_str = draft.get('date')
            service_ids = draft.get('service_ids', [])
            if not (date_str and service_ids):
                return redirect('dashboard_book_slot')

            try:
                selected_time = datetime.strptime(time_str, '%H:%M').time()
            except (TypeError, ValueError):
                messages.error(request, 'Invalid time selected.')
                return redirect(f"{reverse('dashboard_book_slot')}?step=time")

            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            sequenced_services = booking_service.resolve_sequenced_services(service_ids)
            available = booking_service.get_available_slots(
                selected_date,
                sequenced_services,
                enforce_advance_buffer=False,
            )
            if selected_time not in available:
                messages.error(request, 'That time slot is no longer available. Please choose another.')
                return redirect(f"{reverse('dashboard_book_slot')}?step=time")

            draft['time'] = selected_time.strftime('%H:%M')
            draft['step'] = 'confirm'
            _save_booking_draft(request, draft)
            return redirect(f"{reverse('dashboard_book_slot')}?step=confirm")

        elif action == 'confirm_booking':
            service_ids = draft.get('service_ids', [])
            date_str = draft.get('date')
            time_str = draft.get('time')
            if not (service_ids and date_str and time_str):
                messages.error(request, 'Booking session expired. Please start again.')
                _clear_booking_draft(request)
                return redirect('dashboard_book_slot')

            sequenced_services = booking_service.resolve_sequenced_services(service_ids)
            booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            start_time = datetime.strptime(time_str, '%H:%M').time()

            try:
                group_id, _ = booking_service.create_booking_group(
                    sequenced_services=sequenced_services,
                    booking_date=booking_date,
                    start_time=start_time,
                    customer_name='Admin',
                    customer_phone=business_phone,
                    customer_email='',
                    customer_gender='Male',
                    booking_source='admin',
                    status='confirmed',
                    is_verified=True,
                    ip_address=None,
                    enforce_advance_buffer=False,
                )
            except booking_service.BookingCreationError as exc:
                messages.error(request, exc.message)
                return redirect(f"{reverse('dashboard_book_slot')}?step=confirm")

            _clear_booking_draft(request)
            messages.success(request, 'Booking created successfully.')
            return redirect(f"{reverse('dashboard_orders')}?date={date_str}")

        elif action == 'reset':
            _clear_booking_draft(request)
            return redirect('dashboard_book_slot')

    draft = _get_booking_draft(request)
    step = request.GET.get('step', draft.get('step', 'services'))

    if step != 'services' and not draft.get('service_ids'):
        return redirect('dashboard_book_slot')
    if step in ('time', 'confirm') and not draft.get('date'):
        return redirect(f"{reverse('dashboard_book_slot')}?step=date")
    if step == 'confirm' and not draft.get('time'):
        return redirect(f"{reverse('dashboard_book_slot')}?step=time")

    context = {
        'page_title': 'Book Slot',
        'step': step,
        'steps': [
            {'id': 'services', 'label': 'Services'},
            {'id': 'date', 'label': 'Date'},
            {'id': 'time', 'label': 'Time'},
            {'id': 'confirm', 'label': 'Confirm'},
        ],
        'services': Service.objects.order_by('category', 'name'),
        'draft': draft,
        'business_phone': business_phone,
    }

    _, now_date, min_allowed_date, max_date = booking_service.get_date_booking_rules()
    context.update({
        'today': now_date,
        'min_allowed_date': min_allowed_date,
        'max_date': max_date,
    })

    if step in ('time', 'confirm') and draft.get('service_ids'):
        sequenced_services = booking_service.resolve_sequenced_services(draft['service_ids'])
        context['sequenced_services'] = sequenced_services
        context['total_price'] = sum(s.price for s in sequenced_services)
        context['total_duration'] = sum(s.duration_minutes for s in sequenced_services)

    if step == 'time' and draft.get('date'):
        selected_date = datetime.strptime(draft['date'], '%Y-%m-%d').date()
        sequenced_services = booking_service.resolve_sequenced_services(draft['service_ids'])
        context['selected_date'] = selected_date
        context['available_slots'] = booking_service.get_available_slots(
            selected_date,
            sequenced_services,
            enforce_advance_buffer=False,
        )

    if step == 'confirm':
        context['selected_date'] = datetime.strptime(draft['date'], '%Y-%m-%d').date()
        context['selected_time'] = datetime.strptime(draft['time'], '%H:%M').time()

    return render(request, 'dashboard/admin_book_slot.html', context)
