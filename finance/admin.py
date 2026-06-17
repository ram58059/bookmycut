from django.contrib import admin

from .models import ManualServiceEntry


@admin.register(ManualServiceEntry)
class ManualServiceEntryAdmin(admin.ModelAdmin):
    list_display = ('service', 'quantity', 'unit_price', 'date', 'created_at')
    list_filter = ('date',)
    search_fields = ('service__name',)
    date_hierarchy = 'date'
