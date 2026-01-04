from django.db import models
from django.conf import settings

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

class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    # Guest information
    customer_phone = models.CharField(max_length=15)
    customer_gender = models.CharField(max_length=10, choices=[('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')], default='Male')
    
    # Relationships
    # Removed customer FK
    # Removed barber FK for now as per requirements it wasn't explicitly asked to choose a barber, just time slots. 
    # But for slot management we might need to know which barber is available? 
    # The requirement says "allocate 1 hour for each time slot from 10 am to 10 pm". It implies generic slots.
    # I will keep it simple: We check global availability. Or maybe we assume 1 barber for simplicity unless specified.
    # Actually, let's just model the slots.
    
    services = models.ManyToManyField(Service)
    date = models.DateField()
    time = models.TimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking {self.id} - {self.customer_phone} on {self.date} at {self.time}"
