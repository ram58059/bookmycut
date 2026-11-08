from django.db import models
from django.utils import timezone
from datetime import timedelta, datetime

class Service(models.Model):
    # Used for custom Finance "additional service" names without a schema change.
    # Excluded from customer/admin bookable service lists.
    FINANCE_MANUAL_CATEGORY = 'Finance Manual'

    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    duration_minutes = models.IntegerField()
    image = models.ImageField(upload_to='services/', blank=True, null=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, default='General')
    gender = models.CharField(max_length=10, choices=[('Boy', 'Boy'), ('Girl', 'Girl')], default='Boy')
    is_active = models.BooleanField(
        default=True,
        help_text='Inactive services are hidden from booking but kept for finance/booking history.',
    )
    price_increased_at = models.DateTimeField(null=True, blank=True)
    PRICE_INCREASE_NOTICE_DAYS = 30

    @classmethod
    def bookable(cls):
        return cls.objects.filter(is_active=True).exclude(category=cls.FINANCE_MANUAL_CATEGORY)

    @property
    def show_price_increase_notice(self):
        """True only for 30 days after an admin price increase."""
        if not self.price_increased_at:
            return False
        return timezone.now() <= self.price_increased_at + timedelta(days=self.PRICE_INCREASE_NOTICE_DAYS)

    def save(self, *args, **kwargs):
        if self.pk:
            try:
                old = Service.objects.get(pk=self.pk)
                if self.price > old.price:
                    self.price_increased_at = timezone.now()
                elif self.price < old.price:
                    self.price_increased_at = None
                # Same price: keep existing price_increased_at (notice window continues)
            except Service.DoesNotExist:
                pass

        if not self.image:
            name_lower = self.name.lower()
            target_category = self.category
            
            if 'beard' in name_lower or 'shave' in name_lower:
                target_category = 'General'
            elif 'haircut' in name_lower and self.category == 'General':
                target_category = 'Hair Services'
                
            existing_service = Service.objects.filter(category=target_category).exclude(image='').first()
            if existing_service:
                self.image = existing_service.image.name
            else:
                fallback = Service.objects.exclude(image='').first()
                if fallback:
                    self.image = fallback.image.name
                
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Coupon(models.Model):
    DISCOUNT_PERCENTAGE = 'percentage'
    DISCOUNT_FIXED = 'fixed'
    DISCOUNT_TYPE_CHOICES = [
        (DISCOUNT_PERCENTAGE, 'Percentage'),
        (DISCOUNT_FIXED, 'Fixed Amount'),
    ]

    code = models.CharField(max_length=40, unique=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=8, decimal_places=2)
    service = models.ForeignKey(
        'Service',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coupons',
        help_text='Optional. Leave blank for all services, or pick one service this coupon can be used on.',
    )
    customer_phone = models.CharField(
        max_length=15,
        blank=True,
        default='',
        help_text='Optional. Leave blank for all customers, or set a mobile number to restrict this coupon.',
    )
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        if self.customer_phone:
            self.customer_phone = ''.join(ch for ch in self.customer_phone if ch.isdigit())[-10:]
        else:
            self.customer_phone = ''
        super().save(*args, **kwargs)

    def is_assigned_to_customer(self):
        return bool(self.customer_phone)

    def is_currently_valid(self, now=None):
        if not self.is_active:
            return False
        now = now or timezone.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True

    def calculate_discount(self, subtotal):
        from decimal import Decimal, ROUND_HALF_UP

        subtotal = Decimal(subtotal)
        if subtotal <= 0:
            return Decimal('0.00')

        if self.discount_type == self.DISCOUNT_PERCENTAGE:
            discount = (subtotal * Decimal(self.discount_value) / Decimal('100')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        else:
            discount = Decimal(self.discount_value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if discount > subtotal:
            discount = subtotal
        if discount < 0:
            discount = Decimal('0.00')
        return discount

    def __str__(self):
        return self.code


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
    BOOKING_SOURCE_CHOICES = [
        ('customer', 'Customer'),
        ('admin', 'Admin'),
    ]
    booking_source = models.CharField(
        max_length=20,
        choices=BOOKING_SOURCE_CHOICES,
        default='customer',
    )
    coupon_code = models.CharField(max_length=40, blank=True, default='')
    discount_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    # When set (e.g. haircut combo add-on), used instead of service.price for totals.
    charged_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Anti-Abuse & Verification
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    otp = models.CharField(max_length=128, blank=True, null=True) # Changed max_length to store hash
    otp_created_at = models.DateTimeField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
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
    def line_price(self):
        if self.charged_price is not None:
            return self.charged_price
        return self.service.price

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
        
        # Prevent cancellation within 2 hours of appointment time
        return appt_dt > (timezone.now() + timedelta(hours=2))

    def __str__(self):
        return f"Booking {self.id} - {self.customer_phone} ({self.service.name} @ {self.time})"


class ComboOffer(models.Model):
    """
    Admin-managed combo upsell shown on booking confirmation when a trigger
    service (e.g. Haircut) is in the cart. Adding it books `linked_service`
    at `combo_price` instead of the list/original price.
    """
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=30)
    original_price = models.DecimalField(max_digits=8, decimal_places=2)
    combo_price = models.DecimalField(max_digits=8, decimal_places=2)
    image = models.ImageField(upload_to='combo_offers/', blank=True, null=True)
    badge_text = models.CharField(max_length=40, blank=True, default='Combo Deal')
    linked_service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name='combo_offers',
        help_text='The bookable service added to the customer cart when this combo is selected.',
    )
    trigger_services = models.ManyToManyField(
        Service,
        related_name='triggered_combo_offers',
        blank=True,
        help_text='Main services that unlock this combo on the confirmation page.',
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']

    @property
    def savings(self):
        from decimal import Decimal
        diff = Decimal(self.original_price) - Decimal(self.combo_price)
        return diff if diff > 0 else Decimal('0.00')

    def display_image_url(self):
        if self.image:
            return self.image.url
        if self.linked_service_id and self.linked_service.image:
            return self.linked_service.image.url
        return ''

    def __str__(self):
        return self.name


class BlockedDay(models.Model):
    date = models.DateField(unique=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Blocked: {self.date}"

class BlockedSlot(models.Model):
    date = models.DateField()
    time = models.TimeField()
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['date', 'time'], name='unique_blocked_slot'),
        ]
        ordering = ['date', 'time']

    def __str__(self):
        return f"Blocked: {self.date} @ {self.time}"
