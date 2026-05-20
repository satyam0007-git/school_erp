from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_feepayment_advance'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='discount_months',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
