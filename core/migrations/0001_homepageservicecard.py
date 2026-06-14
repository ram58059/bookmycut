from django.db import migrations, models
import django.db.models.deletion


def seed_homepage_cards(apps, schema_editor):
    HomepageServiceCard = apps.get_model('core', 'HomepageServiceCard')
    Service = apps.get_model('bookings', 'Service')

    defaults = [
        {
            'title': 'Haircut',
            'description': 'Professional and tailored haircut to get you looking your absolute best.',
            'price': '250.00',
            'service_id': 214,
            'sort_order': 1,
        },
        {
            'title': 'Haircut + Trim/Shave + De-Tan',
            'description': 'Complete grooming combo including haircut, beard styling, and revitalizing de-tan.',
            'price': '599.00',
            'service_id': 207,
            'sort_order': 2,
        },
        {
            'title': 'Clean-up (Fruit Facial) + De-Tan',
            'description': 'Deep cleansing fruit facial combined with tan removal for glowing, refreshed skin.',
            'price': '899.00',
            'service_id': 183,
            'sort_order': 3,
        },
    ]

    for item in defaults:
        linked_service = None
        if item['service_id']:
            linked_service = Service.objects.filter(pk=item['service_id']).first()
        HomepageServiceCard.objects.get_or_create(
            sort_order=item['sort_order'],
            defaults={
                'title': item['title'],
                'description': item['description'],
                'price': item['price'],
                'linked_service': linked_service,
                'is_active': True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0016_service_price_increased_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='HomepageServiceCard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField()),
                ('price', models.DecimalField(decimal_places=2, max_digits=8)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('linked_service', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='homepage_cards', to='bookings.service')),
            ],
            options={
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.RunPython(seed_homepage_cards, migrations.RunPython.noop),
    ]
