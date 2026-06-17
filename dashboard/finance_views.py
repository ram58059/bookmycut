import json
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from dashboard.views import is_barber_or_admin
from finance.forms import ManualServiceEntryForm
from finance.models import ManualServiceEntry
from finance.services import (
    get_booked_revenue,
    get_booked_service_rows,
    get_manual_entries,
    get_manual_revenue,
)


def _parse_selected_date(request):
    today = timezone.localtime(timezone.now()).date()
    date_str = request.GET.get('date') or request.POST.get('date') or today.isoformat()
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return today


def _finance_redirect(selected_date):
    return redirect(f"{reverse('dashboard_finance')}?date={selected_date.isoformat()}")


@user_passes_test(is_barber_or_admin, login_url='dashboard_login')
def finance_dashboard(request):
    selected_date = _parse_selected_date(request)
    edit_entry = None
    form = None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_manual':
            form = ManualServiceEntryForm(request.POST, selected_date=selected_date)
            if form.is_valid():
                form.save()
                messages.success(request, 'Additional service entry added.')
                return _finance_redirect(selected_date)
            messages.error(request, 'Could not add entry. Please check the form.')

        elif action == 'edit_manual':
            entry = get_object_or_404(ManualServiceEntry, pk=request.POST.get('entry_id'))
            form = ManualServiceEntryForm(request.POST, instance=entry, selected_date=selected_date)
            if form.is_valid():
                form.save()
                messages.success(request, 'Additional service entry updated.')
                return _finance_redirect(selected_date)
            edit_entry = entry
            messages.error(request, 'Could not update entry. Please check the form.')

        elif action == 'delete_manual':
            entry = get_object_or_404(ManualServiceEntry, pk=request.POST.get('entry_id'))
            entry.delete()
            messages.success(request, 'Additional service entry deleted.')
            return _finance_redirect(selected_date)

    edit_id = request.GET.get('edit')
    if edit_id and edit_entry is None:
        edit_entry = get_object_or_404(ManualServiceEntry, pk=edit_id)

    if form is None:
        if edit_entry:
            form = ManualServiceEntryForm(instance=edit_entry, selected_date=selected_date)
        else:
            form = ManualServiceEntryForm(selected_date=selected_date)

    booked_rows = get_booked_service_rows(selected_date)
    manual_entries = get_manual_entries(selected_date)
    booked_revenue = get_booked_revenue(selected_date)
    additional_revenue = get_manual_revenue(selected_date)
    grand_total = booked_revenue + additional_revenue

    service_prices = {
        str(service.id): str(service.price)
        for service in form.fields['service'].queryset
    }

    context = {
        'page_title': 'Finance',
        'selected_date': selected_date,
        'today': timezone.localtime(timezone.now()).date(),
        'booked_rows': booked_rows,
        'booked_revenue': booked_revenue,
        'manual_entries': manual_entries,
        'additional_revenue': additional_revenue,
        'grand_total': grand_total,
        'form': form,
        'edit_entry': edit_entry,
        'service_prices_json': json.dumps(service_prices),
    }
    return render(request, 'dashboard/finance.html', context)
