from django.db import migrations, models


def forwards_update_status(apps, schema_editor):
    Booking = apps.get_model('bookings', 'Booking')
    for booking in Booking.objects.all():
        if booking.status == 'pending':
            booking.status = 'pending_otp'
        elif booking.status == 'payment_pending':
            # In the new flow, bookings that had reached payment stage are treated as confirmed
            booking.status = 'confirmed'
        elif booking.status == 'payment_failed':
            booking.status = 'cancelled'
        booking.save(update_fields=['status'])


def backwards_update_status(apps, schema_editor):
    Booking = apps.get_model('bookings', 'Booking')
    for booking in Booking.objects.all():
        if booking.status == 'pending_otp':
            booking.status = 'pending'
        # Bookings that were confirmed/cancelled remain as-is; we don't restore payment_* states
        booking.save(update_fields=['status'])


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0009_blockedday'),
    ]

    operations = [
        migrations.RunPython(forwards_update_status, backwards_update_status),
        migrations.AlterField(
            model_name='booking',
            name='status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('pending_otp', 'Pending OTP Verification'),
                    ('confirmed', 'Confirmed'),
                    ('completed', 'Completed'),
                    ('cancelled', 'Cancelled'),
                    ('no_show', 'No Show'),
                ],
                default='pending_otp',
            ),
        ),
        migrations.RemoveField(
            model_name='booking',
            name='razorpay_order_id',
        ),
        migrations.RemoveField(
            model_name='booking',
            name='razorpay_payment_id',
        ),
    ]

