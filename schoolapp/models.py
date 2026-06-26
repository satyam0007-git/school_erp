from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from .session_utils import default_current_academic_session, validate_academic_session


def _make_receipt_number(model_class, prefix_code, **scope_filter):
    year = timezone.now().year
    prefix = f"{prefix_code}-{year}-"
    last = model_class.objects.filter(receipt_number__startswith=prefix, **scope_filter).order_by('-id').first()
    next_number = 1
    if last and last.receipt_number:
        try:
            next_number = int(last.receipt_number.split('-')[-1]) + 1
        except (ValueError, IndexError):
            next_number = model_class.objects.filter(**scope_filter).count() + 1
    return f"{prefix}{next_number:04d}"


MONTH_CHOICES = [
    ('april', 'April'), ('may', 'May'), ('june', 'June'),
    ('july', 'July'), ('august', 'August'), ('september', 'September'),
    ('october', 'October'), ('november', 'November'), ('december', 'December'),
    ('january', 'January'), ('february', 'February'), ('march', 'March'),
]


# ── Tenant ────────────────────────────────────────────────────────────────────

class School(models.Model):
    name = models.CharField(max_length=200)
    subdomain = models.SlugField(
        max_length=63, unique=True, null=True, blank=True,
        help_text='URL slug for this school, e.g. "greenwood" → greenwood.erpdomain.com',
    )
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to='school_logos/', blank=True, null=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    fee_per_student = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    motto = models.CharField(max_length=255, blank=True, default='')
    campus_image = models.ImageField(upload_to='school_campus/', blank=True, null=True)
    campus_image2 = models.ImageField(upload_to='school_campus/', blank=True, null=True)
    campus_image3 = models.ImageField(upload_to='school_campus/', blank=True, null=True)
    theme_color = models.CharField(max_length=7, default='#0f766e', help_text='Primary theme color in hex, e.g. #0f766e')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def get_tenant_url(self, scheme='http'):
        from django.conf import settings as _s
        base = getattr(_s, 'TENANT_BASE_DOMAIN', 'localhost')
        if self.subdomain:
            return f'{scheme}://{self.subdomain}.{base}'
        return f'{scheme}://{base}'


class SchoolBillingPayment(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='billing_payments')
    receipt_number = models.CharField(max_length=20, editable=False, blank=True)
    academic_session = models.CharField(max_length=20, blank=True, default='')
    payment_date = models.DateField()
    num_students = models.PositiveIntegerField()
    fee_per_student = models.DecimalField(max_digits=8, decimal_places=2)
    payment_months = models.JSONField(default=list)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    is_adjustment = models.BooleanField(default=False)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = _make_receipt_number(SchoolBillingPayment, 'BILL', school=self.school)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.school.name} — ₹{self.amount_paid} on {self.payment_date}'


class User(AbstractUser):
    SUPERUSER = 'superuser'
    SCHOOL_ADMIN = 'school_admin'
    ROLES = [(SUPERUSER, 'Super User'), (SCHOOL_ADMIN, 'School Admin')]
    role = models.CharField(max_length=20, choices=ROLES, default=SCHOOL_ADMIN)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)

    def is_super(self):
        return self.role == self.SUPERUSER or self.is_superuser


class SuperUserSettings(models.Model):
    software_name = models.CharField(max_length=150, default='SchoolERP')
    superuser_name = models.CharField(max_length=150, blank=True)
    superuser_email = models.EmailField(blank=True)
    superuser_phone = models.CharField(max_length=20, blank=True)
    logo = models.ImageField(upload_to='software_logos/', blank=True, null=True)
    organization_address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    default_session = models.CharField(max_length=20, blank=True, default='',
                                       help_text='Default academic session shown on superuser dashboard and school fee pages.')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.software_name or 'Super User Settings'

    @classmethod
    def get_solo(cls):
        obj = cls.objects.order_by('pk').first()
        if obj:
            return obj
        return cls.objects.create()


# ── Configuration ─────────────────────────────────────────────────────────────

class SchoolProfile(models.Model):
    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name='profile')
    current_academic_session = models.CharField(
        max_length=20,
        default=default_current_academic_session,
        validators=[validate_academic_session],
    )
    session_start_month = models.CharField(max_length=15, choices=MONTH_CHOICES, default='april')
    session_end_month = models.CharField(max_length=15, choices=MONTH_CHOICES, default='march')
    billing_start_month = models.CharField(max_length=15, choices=MONTH_CHOICES, default='april')
    billing_end_month = models.CharField(max_length=15, choices=MONTH_CHOICES, default='march')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.school.name} Profile"

    @classmethod
    def get_for_school(cls, school):
        obj, _ = cls.objects.get_or_create(
            school=school,
            defaults={'current_academic_session': default_current_academic_session()},
        )
        return obj

class SchoolSessionRecord(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='session_records')
    academic_session = models.CharField(
        max_length=20,
        validators=[validate_academic_session],
    )
    session_start_month = models.CharField(max_length=15, choices=MONTH_CHOICES, default='april')
    session_end_month = models.CharField(max_length=15, choices=MONTH_CHOICES, default='march')
    billing_start_month = models.CharField(max_length=15, choices=MONTH_CHOICES, default='april')
    billing_end_month = models.CharField(max_length=15, choices=MONTH_CHOICES, default='march')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('school', 'academic_session')
        ordering = ['-academic_session', '-id']

    def __str__(self):
        return f'{self.school.name} — {self.academic_session}'


class SchoolClass(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class FeeCategory(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('school', 'name')
        ordering = ['name']

    def __str__(self):
        return self.name


class FeeStructure(models.Model):
    FREQUENCY_MONTHLY = 'monthly'
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name='fee_structures')
    fee_category = models.ForeignKey(FeeCategory, on_delete=models.PROTECT, related_name='fee_structures')
    academic_session = models.CharField(
        max_length=20,
        default=default_current_academic_session,
        validators=[validate_academic_session],
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    frequency = models.CharField(max_length=20, default=FREQUENCY_MONTHLY)

    class Meta:
        unique_together = ('school_class', 'fee_category', 'academic_session')

    def __str__(self):
        return f"{self.school_class} - {self.fee_category}"


# ── Admission ─────────────────────────────────────────────────────────────────

class Student(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_PROMOTED = 'promoted'
    STATUS_FAIL = 'fail'
    STATUS_CHOICES = [
        (STATUS_INACTIVE, 'Transferred'),
        (STATUS_PROMOTED, 'Promoted'),
        (STATUS_FAIL, 'Fail'),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name='students')
    roll_number = models.CharField(max_length=20, editable=False)
    name = models.CharField(max_length=150)
    date_of_birth = models.DateField()
    academic_session = models.CharField(
        max_length=20,
        default=default_current_academic_session,
        validators=[validate_academic_session],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    father_name = models.CharField(max_length=120)
    mother_name = models.CharField(max_length=120, default='')
    father_phone = models.CharField(
        max_length=20,
        validators=[RegexValidator(r'^\d{10}$', message='Father phone must be exactly 10 digits.')],
    )
    address = models.TextField()
    blood_group = models.CharField(max_length=10, blank=True, default='')
    previous_school = models.CharField(max_length=200, blank=True, default='')
    aadhaar_number = models.CharField(max_length=12, blank=True, default='')
    pen_number = models.CharField(max_length=20, blank=True, default='')
    religion = models.CharField(max_length=100, default='')
    caste = models.CharField(max_length=100, default='')
    admission_date = models.DateField(default=timezone.localdate)
    transport_opted = models.BooleanField(default=False)
    transport_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    discount_months = models.PositiveSmallIntegerField(blank=True, null=True)
    bulk_upload_history = models.ForeignKey(
        'schoolapp.AdmissionBulkUploadHistory',
        on_delete=models.SET_NULL,
        related_name='successful_students',
        blank=True,
        null=True,
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.roll_number} - {self.name}"

    def _get_session_code(self):
        try:
            return f"{int(self.academic_session[:4]) % 100:02d}"
        except (TypeError, ValueError, IndexError):
            return '00'

    def _get_class_code(self):
        class_name = getattr(self.school_class, 'name', '') or ''
        for part in class_name.split():
            if not part.isdigit():
                return part.lower()
        for part in class_name.split():
            if part.isdigit():
                return f"{int(part):02d}"
        return f"{self.school_class_id or 0:02d}"

    def _generate_roll_number(self):
        prefix = f"{self._get_session_code()}{self._get_class_code()}"
        last_roll = (
            Student.objects.filter(school=self.school, roll_number__startswith=prefix)
            .order_by('-roll_number')
            .values_list('roll_number', flat=True)
            .first()
        )
        next_number = 1
        if last_roll:
            try:
                next_number = int(last_roll[len(prefix):]) + 1
            except (TypeError, ValueError):
                next_number = 1
        return f"{prefix}{next_number:03d}"

    def save(self, *args, **kwargs):
        if self.pk:
            original = Student.objects.filter(pk=self.pk).values_list('school_class_id', 'roll_number').first()
            if original and original[0] != self.school_class_id:
                self.roll_number = self._generate_roll_number()
        if not self.transport_opted:
            self.transport_amount = None
        if not self.roll_number:
            self.roll_number = self._generate_roll_number()
        super().save(*args, **kwargs)


class AdmissionBulkUploadHistory(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='admission_bulk_uploads')
    uploaded_by = models.ForeignKey('schoolapp.User', on_delete=models.PROTECT, related_name='admission_bulk_uploads')
    academic_session = models.CharField(max_length=20, blank=True, default='')
    file_name = models.CharField(max_length=255, blank=True)
    total_records = models.PositiveIntegerField(default=0)
    admissions_created = models.PositiveIntegerField(default=0)
    fee_submissions = models.PositiveIntegerField(default=0)
    failed_records = models.PositiveIntegerField(default=0)
    fee_skipped = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at', '-id']

    def __str__(self):
        return f'{self.school.name} bulk upload — {self.uploaded_at:%d %b %Y %H:%M}'


# ── Fees ──────────────────────────────────────────────────────────────────────


class ExamFee(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name='exam_fees')
    exam_name = models.CharField(max_length=100)
    academic_session = models.CharField(
        max_length=20,
        default=default_current_academic_session,
        validators=[validate_academic_session],
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['exam_name']

    def __str__(self):
        return f"{self.exam_name} - {self.school_class}"


class FeePayment(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    receipt_number = models.CharField(max_length=20, editable=False)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='fee_payments')
    payment_date = models.DateField(default=timezone.localdate)
    academic_session = models.CharField(max_length=20, blank=True, default='')
    payment_months = models.JSONField(default=list, blank=True)
    exam_fee_items = models.JSONField(default=list, blank=True)
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    transport_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    balance_due = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    advance_balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    advance_used = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    is_lump_sum = models.BooleanField(default=False)
    is_admission_discount = models.BooleanField(default=False)
    collected_by = models.ForeignKey('schoolapp.User', on_delete=models.PROTECT, related_name='collected_payments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date', '-id']

    def __str__(self):
        return self.receipt_number

    def get_payment_months_display(self):
        month_map = dict(MONTH_CHOICES)
        return ', '.join(month_map.get(m, m) for m in self.payment_months)

    def save(self, *args, **kwargs):
        if self.student.status != Student.STATUS_ACTIVE:
            raise ValidationError('Fees can only be collected for active students.')
        if not self.receipt_number:
            self.receipt_number = _make_receipt_number(FeePayment, 'FEE', student=self.student)
        self.balance_due = self.gross_amount - self.amount_paid
        super().save(*args, **kwargs)


class WhatsAppConfig(models.Model):
    """Stores Meta WhatsApp Cloud API credentials per school."""
    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name='whatsapp_config')
    phone_number_id = models.CharField(max_length=80, blank=True, help_text='Meta WhatsApp Phone Number ID')
    waba_id = models.CharField(max_length=80, blank=True, help_text='WhatsApp Business Account ID')
    access_token = models.TextField(blank=True, help_text='Permanent Meta access token')
    template_name = models.CharField(max_length=100, blank=True, default='',
                                     help_text='Pre-approved WhatsApp template name')
    template_language = models.CharField(max_length=20, blank=True, default='en_US',
                                         help_text='Template language code, e.g. en_US')
    is_active = models.BooleanField(default=False, help_text='Enable WhatsApp sending')
    announcement_template_name = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Pre-approved WhatsApp template for announcements (should have 1 body param {{1}})'
    )
    announcement_template_language = models.CharField(
        max_length=20, blank=True, default='en_US',
        help_text='Language code for announcement template, e.g. en_US'
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"WhatsApp Config — {self.school.name}"
