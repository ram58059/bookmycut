from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0014_booking_cancelled_at_alter_booking_customer_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='BlockedSlot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('time', models.TimeField()),
                ('reason', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['date', 'time'],
            },
        ),
        migrations.AddConstraint(
            model_name='blockedslot',
            constraint=models.UniqueConstraint(fields=('date', 'time'), name='unique_blocked_slot'),
        ),
    ]
