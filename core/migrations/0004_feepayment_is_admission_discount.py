from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_add_admission_discount'),
    ]

    operations = [
        migrations.AddField(
            model_name='feepayment',
            name='is_admission_discount',
            field=models.BooleanField(default=False),
        ),
    ]
