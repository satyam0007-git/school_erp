from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('schoolapp', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(
            name='SalaryPayment',
        ),
        migrations.DeleteModel(
            name='Teacher',
        ),
    ]
