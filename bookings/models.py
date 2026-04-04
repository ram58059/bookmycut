from django.db import models
from django.utils import timezone
from datetime import timedelta, datetime

class Service(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    duration_minutes = models.IntegerField()
    image = models.ImageField(upload_to='services/', blank=True, null=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, default='General')
    gender = models.CharField(max_length=10, choices=[('Boy', 'Boy'), ('Girl', 'Girl')], default='Boy')

    def __str__(self):
        return self.name

class CustomerTrust(models.Model):
    phone_number = models.CharField(max_length=15, unique=True)
    successful_bookings = models.IntegerField(default=0)
    no_shows = models.IntegerField(default=0)
    late_cancellations = models.IntegerField(default=0)
    
    TRUST_LEVEL_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]
    trust_level = models.CharField(max_length=10, choices=TRUST_LEVEL_CHOICES, default='medium')
    
    def update_trust_score(self):
        # Simple algorithm
        total = self.successful_bookings + self.no_shows + self.late_cancellations
        if total == 0:
            self.trust_level = 'medium'
            return

        bad_ratio = (self.no_shows + self.late_cancellations) / total
        
        if bad_ratio > 0.5 or self.no_shows > 2:
            self.trust_level = 'low'
        elif self.successful_bookings > 5 and bad_ratio < 0.1:
            self.trust_level = 'high'
        else:
            self.trust_level = 'medium'
        self.save()

    def __str__(self):
        return f"{self.phone_number} - {self.trust_level}"

class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending_otp', 'Pending OTP Verification'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]

    # Guest information
    customer_name = models.CharField(max_length=100)
    customer_phone = models.CharField(max_length=15)
    customer_email = models.EmailField(blank=True, null=True)
    customer_gender = models.CharField(max_length=10, choices=[('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')], default='Male')
    
    service = models.ForeignKey(Service, on_delete=models.CASCADE, default=1, related_name='bookings') 
    # NOTE: Default provided to allow migration, but practically required.
    
    booking_group_id = models.UUIDField(null=True, blank=True) 
    # Used to group multiple services booked in one go
    
    date = models.DateField()
    time = models.TimeField()
    end_time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_otp')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Anti-Abuse & Verification
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    otp = models.CharField(max_length=128, blank=True, null=True) # Changed max_length to store hash
    otp_created_at = models.DateTimeField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['service', 'date', 'time'],
                condition=models.Q(status__in=['confirmed', 'completed', 'pending_otp']),
                name='unique_active_service_slot'
            )
        ]

    def is_otp_expired(self):
        if not self.otp_created_at:
            return True
        return timezone.now() > self.otp_created_at + timedelta(minutes=5)

    @property
    def is_cancellable(self):
        if self.status != 'confirmed':
            return False
        # Create aware datetime for appointment
        try:
            appt_dt = timezone.make_aware(datetime.combine(self.date, self.time))
        except:
             # If settings are naive (though Django usually aware)
             appt_dt = datetime.combine(self.date, self.time)
        
        return appt_dt > timezone.now()

    def __str__(self):
        return f"Booking {self.id} - {self.customer_phone} ({self.service.name} @ {self.time})"

class BlockedDay(models.Model):
    date = models.DateField(unique=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Blocked: {self.date}"
