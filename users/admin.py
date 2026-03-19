from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'phone_display', 'is_barber', 'is_staff')
    
    @admin.display(description='Phone (Name)')
    def phone_display(self, obj):
        if obj.first_name:
            return f"{obj.phone_number} ({obj.first_name})"
        return obj.phone_number

admin.site.register(User, CustomUserAdmin)
