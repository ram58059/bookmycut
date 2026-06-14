from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0016_service_price_increased_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='booking_source',
            field=models.CharField(
                choices=[('customer', 'Customer'), ('admin', 'Admin')],
                default='customer',
                max_length=20,
            ),
        ),
    ]
