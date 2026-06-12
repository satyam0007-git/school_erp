from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('schoolapp', '0002_remove_teacher_salary'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdmissionBulkUploadHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('academic_session', models.CharField(blank=True, default='', max_length=20)),
                ('file_name', models.CharField(blank=True, max_length=255)),
                ('total_records', models.PositiveIntegerField(default=0)),
                ('admissions_created', models.PositiveIntegerField(default=0)),
                ('fee_submissions', models.PositiveIntegerField(default=0)),
                ('failed_records', models.PositiveIntegerField(default=0)),
                ('fee_skipped', models.PositiveIntegerField(default=0)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='admission_bulk_uploads', to='schoolapp.school')),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='admission_bulk_uploads', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-uploaded_at', '-id'],
            },
        ),
    ]
