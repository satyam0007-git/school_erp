from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_feepayment_is_admission_discount'),
    ]

    operations = [
        migrations.AddField(
            model_name='school',
            name='subdomain',
            field=models.SlugField(
                blank=True,
                help_text='URL slug for this school, e.g. "greenwood" → greenwood.erpdomain.com',
                max_length=63,
                null=True,
                unique=True,
            ),
        ),
    ]
