from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('schoolapp', '0003_admissionbulkuploadhistory'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='bulk_upload_history',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='successful_students', to='schoolapp.admissionbulkuploadhistory'),
        ),
    ]
