from django.db import models

class ShopSetting(models.Model):
    is_otp_enabled = models.BooleanField(default=True)
    business_phone = models.CharField(max_length=15, blank=True, default='')

    def save(self, *args, **kwargs):
        # Enforce singleton
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"Shop Settings (OTP Enabled: {self.is_otp_enabled})"
