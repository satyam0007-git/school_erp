from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_school_subdomain'),
    ]

    operations = [
        migrations.AddField(
            model_name='schoolbillingpayment',
            name='is_adjustment',
            field=models.BooleanField(default=False),
        ),
    ]
