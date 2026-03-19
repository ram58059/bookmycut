from django.contrib import admin
from .models import Service, Booking

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'duration_minutes')

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_display', 'service', 'date', 'time', 'status')
    list_filter = ('status', 'date')
    search_fields = ('customer_name', 'customer_phone', 'customer_email')
    
    @admin.display(description='Customer')
    def customer_display(self, obj):
        return f"{obj.customer_phone} ({obj.customer_name})"
