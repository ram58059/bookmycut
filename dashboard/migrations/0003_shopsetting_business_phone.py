from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0002_rename_shopsettings_shopsetting_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopsetting',
            name='business_phone',
            field=models.CharField(blank=True, default='', max_length=15),
        ),
    ]
