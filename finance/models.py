from decimal import Decimal

from django.db import models

from bookings.models import Service


class ManualServiceEntry(models.Model):
    """Walk-in or off-book services not captured through the booking system."""

    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name='manual_entries')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name_plural = 'manual service entries'

    @property
    def total_amount(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f'{self.service.name} x{self.quantity} on {self.date}'
