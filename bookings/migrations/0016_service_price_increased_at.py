from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0015_blockedslot'),
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='price_increased_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
