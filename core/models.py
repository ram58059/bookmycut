from django.db import models


class HomepageServiceCard(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    linked_service = models.ForeignKey(
        'bookings.Service',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='homepage_cards',
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.title
