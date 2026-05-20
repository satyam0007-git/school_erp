from django import forms
from django.core.exceptions import ValidationError
from .models import Student, Teacher, SalaryPayment, FeePayment, MONTH_CHOICES, SchoolClass, SchoolProfile, SuperUserSettings
from .session_utils import get_academic_session_choices, get_current_academic_session


def to_title_case(name: str) -> str:
    return name.title()


# ── Admission ─────────────────────────────────────────────────────────────────

RELIGION_CHOICES = [
    ('Hindu', 'Hindu'),
    ('Muslim', 'Muslim'),
    ('Christian', 'Christian'),
    ('Sikh', 'Sikh'),
    ('Buddhist', 'Buddhist'),
    ('Jain', 'Jain'),
    ('Parsi', 'Parsi'),
    ('Other', 'Other'),
]

CASTE_CHOICES = [
    ('General', 'General'),
    ('OBC', 'OBC'),
    ('SC', 'SC'),
    ('ST', 'ST'),
    ('EWS', 'EWS'),
    ('Other', 'Other'),
]

_RELIGION_VALUES = {c[0] for c in RELIGION_CHOICES if c[0]}
_CASTE_VALUES    = {c[0] for c in CASTE_CHOICES    if c[0]}


class StudentForm(forms.ModelForm):
    academic_session = forms.ChoiceField(choices=(), widget=forms.Select(attrs={'class': 'form-select'}))

    religion = forms.ChoiceField(
        choices=RELIGION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    religion_other = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Specify religion…'}),
    )

    caste = forms.ChoiceField(
        choices=CASTE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    caste_other = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Specify caste…'}),
    )

    class Meta:
        model = Student
        fields = ['name', 'date_of_birth', 'school_class', 'academic_session',
                  'father_name', 'mother_name', 'father_phone', 'address',
                  'religion', 'caste',
                  'blood_group', 'previous_school', 'aadhaar_number', 'pen_number',
                  'transport_opted', 'transport_amount', 'discount_months']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Enter student's full name"}),
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'school_class': forms.Select(attrs={'class': 'form-select'}),
            'father_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': " "}),
            'mother_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': " "}),
            'father_phone': forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric', 'maxlength': '10', 'placeholder': '10-digit mobile number'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'House no., street, city, state…'}),
            'religion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Hindu, Muslim, Christian, Sikh…'}),
            'caste': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. General, OBC, SC, ST…'}),
            'blood_group': forms.Select(choices=[
                ('O+', 'O+'), ('O-', 'O-'),
                ('A+', 'A+'), ('A-', 'A-'),
                ('B+', 'B+'), ('B-', 'B-'),
                ('AB+', 'AB+'), ('AB-', 'AB-'),
            ], attrs={'class': 'form-select'}),
            'previous_school': forms.TextInput(attrs={'class': 'form-control', 'placeholder': ' '}),
            'aadhaar_number': forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric', 'maxlength': '12', 'placeholder': ' '}),
            'pen_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': ' '}),
            'transport_opted': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'transport_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': ''}),
            'discount_months': forms.Select(choices=[(0, 'None')] + [(i, f'{i} Month{"s" if i > 1 else ""}') for i in range(1, 13)], attrs={'class': 'form-select', 'id': 'id_discount_months'}),
        }

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        session_choices = get_academic_session_choices(past_years=2, future_years=10)
        self.fields['academic_session'].choices = session_choices

        if school:
            qs = SchoolClass.objects.filter(school=school)
            self.fields['school_class'].queryset = qs
        else:
            qs = SchoolClass.objects.none()
            self.fields['school_class'].queryset = qs

        self.fields['school_class'].empty_label = None

        profile = SchoolProfile.objects.filter(school=school).first() if school else None
        default_session = profile.current_academic_session if profile else get_current_academic_session()
        if not self.instance.pk:
            self.initial['academic_session'] = default_session
            self.initial['religion'] = 'Hindu'
            self.initial['caste'] = 'General'
            self.initial['blood_group'] = 'O+'
            self.initial['discount_months'] = 0
            first_class = qs.first()
            if first_class:
                self.initial['school_class'] = first_class.pk

        # When editing, pre-fill "Other" text boxes for non-standard saved values
        if self.instance.pk:
            saved_religion = self.instance.religion or ''
            if saved_religion and saved_religion not in _RELIGION_VALUES:
                self.initial['religion'] = 'Other'
                self.initial['religion_other'] = saved_religion
            saved_caste = self.instance.caste or ''
            if saved_caste and saved_caste not in _CASTE_VALUES:
                self.initial['caste'] = 'Other'
                self.initial['caste_other'] = saved_caste

    def clean_name(self):
        return to_title_case(self.cleaned_data.get('name', '').strip())

    def clean_father_name(self):
        return to_title_case(self.cleaned_data.get('father_name', '').strip())

    def clean_mother_name(self):
        return to_title_case(self.cleaned_data.get('mother_name', '').strip())

    def clean_address(self):
        return to_title_case(self.cleaned_data.get('address', '').strip())

    def clean_previous_school(self):
        val = self.cleaned_data.get('previous_school', '') or ''
        return to_title_case(val.strip())

    def clean_religion(self):
        value = self.cleaned_data.get('religion', '')
        if value == 'Other':
            other = self.data.get('religion_other', '').strip()
            if not other:
                raise forms.ValidationError('Please specify the religion.')
            return other
        return value

    def clean_caste(self):
        value = self.cleaned_data.get('caste', '')
        if value == 'Other':
            other = self.data.get('caste_other', '').strip()
            if not other:
                raise forms.ValidationError('Please specify the caste.')
            return other
        return value

    def clean(self):
        cleaned_data = super().clean()
        transport_opted = cleaned_data.get('transport_opted')
        transport_amount = cleaned_data.get('transport_amount')
        if transport_opted and transport_amount is None:
            self.add_error('transport_amount', 'Please enter transport amount.')
        elif transport_opted and transport_amount and transport_amount <= 0:
            self.add_error('transport_amount', 'Transport amount must be greater than zero.')
        if not transport_opted:
            cleaned_data['transport_amount'] = None

        # Duplicate admission check
        name = cleaned_data.get('name', '').strip()
        father_name = cleaned_data.get('father_name', '').strip()
        school_class = cleaned_data.get('school_class')
        academic_session = cleaned_data.get('academic_session')
        date_of_birth = cleaned_data.get('date_of_birth')

        if self.school and name and father_name and school_class and academic_session and date_of_birth:
            qs = Student.objects.filter(
                school=self.school,
                name__iexact=name,
                father_name__iexact=father_name,
                school_class=school_class,
                academic_session=academic_session,
                date_of_birth=date_of_birth,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    'A student with the same name, father\'s name, class, session, and date of birth '
                    'already exists. Duplicate admission is not allowed.'
                )

        return cleaned_data

    def clean_father_phone(self):
        phone = (self.cleaned_data.get('father_phone') or '').strip()
        if not phone.isdigit() or len(phone) != 10:
            raise ValidationError('Father phone must be exactly 10 digits.')
        return phone


# ── Teachers ──────────────────────────────────────────────────────────────────

class TeacherForm(forms.ModelForm):
    academic_session = forms.ChoiceField(choices=(), widget=forms.Select(attrs={'class': 'form-select'}))
    gender = forms.ChoiceField(
        choices=Teacher.GENDER_CHOICES,
        initial=Teacher.GENDER_MALE,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = Teacher
        fields = [
            'name', 'gender', 'date_of_birth', 'phone', 'email',
            'address', 'qualification',
            'joining_date', 'monthly_salary', 'status', 'academic_session',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Teacher's full name"}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric', 'maxlength': '10', 'placeholder': '10-digit mobile number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'teacher@example.com'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Residential address'}),
            'qualification': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. B.Ed, M.Sc, M.Ed'}),
            'subjects_taught': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Maths, Science, English'}),
            'class_teacher_of': forms.Select(attrs={'class': 'form-select'}),
            'joining_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'employment_type': forms.Select(attrs={'class': 'form-select'}),
            'monthly_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        session_choices = get_academic_session_choices(past_years=2, future_years=10)
        self.fields['academic_session'].choices = session_choices

        profile = SchoolProfile.objects.filter(school=school).first() if school else None
        default_session = profile.current_academic_session if profile else get_current_academic_session()
        if not self.instance.pk:
            self.initial['academic_session'] = default_session

    def clean_phone(self):
        phone = (self.cleaned_data.get('phone') or '').strip()
        if not phone.isdigit() or len(phone) != 10:
            raise forms.ValidationError('Phone must be exactly 10 digits.')
        return phone


# ── Salary Submission ─────────────────────────────────────────────────────────

class SalaryPaymentForm(forms.ModelForm):
    payment_months = forms.MultipleChoiceField(
        choices=MONTH_CHOICES,
        widget=forms.CheckboxSelectMultiple(),
        required=True,
        label='Select Month(s)',
    )

    class Meta:
        model = SalaryPayment
        fields = ['teacher', 'payment_date', 'payment_months', 'amount_paid', 'remarks', 'academic_session']
        widgets = {
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'readonly': 'readonly'}),
            'remarks': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional note…'}),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        session_choices = get_academic_session_choices(past_years=2, future_years=10)
        self.fields['academic_session'] = forms.ChoiceField(
            choices=session_choices,
            widget=forms.Select(attrs={'class': 'form-select'}),
        )
        if school:
            self.fields['teacher'].queryset = Teacher.objects.filter(school=school, status=Teacher.STATUS_ACTIVE)
        else:
            self.fields['teacher'].queryset = Teacher.objects.none()

        profile = SchoolProfile.objects.filter(school=school).first() if school else None
        if not self.instance.pk:
            self.initial['academic_session'] = profile.current_academic_session if profile else get_current_academic_session()

    def clean_payment_months(self):
        months = list(dict.fromkeys(self.cleaned_data.get('payment_months', [])))
        valid = {v for v, _ in MONTH_CHOICES}
        invalid = [m for m in months if m not in valid]
        if invalid:
            raise forms.ValidationError('Invalid month selection.')
        return months

    def clean(self):
        cleaned_data = super().clean()
        teacher = cleaned_data.get('teacher')
        months = cleaned_data.get('payment_months', [])
        session = cleaned_data.get('academic_session')
        if teacher and months and session and self.school:
            already_paid = SalaryPayment.objects.filter(
                school=self.school, teacher=teacher, academic_session=session,
            ).values_list('payment_months', flat=True)
            paid_set = set()
            for m_list in already_paid:
                paid_set.update(m_list)
            duplicates = [m for m in months if m in paid_set]
            if duplicates:
                month_map = dict(MONTH_CHOICES)
                dup_labels = ', '.join(month_map.get(m, m) for m in duplicates)
                raise forms.ValidationError(f'Salary already paid for: {dup_labels}')
        return cleaned_data


# ── Fee Submission ────────────────────────────────────────────────────────────

class PaymentMonthsField(forms.MultipleChoiceField):
    _valid_months = {v for v, _ in MONTH_CHOICES}

    def valid_value(self, value):
        value = str(value)
        if value in self._valid_months:
            return True
        if value.endswith('_transport') and value[:-10] in self._valid_months:
            return True
        if value.startswith('exam_'):
            return True
        return False


class FeePaymentForm(forms.ModelForm):
    payment_months = PaymentMonthsField(
        choices=[],  # populated dynamically via AJAX
        widget=forms.SelectMultiple(attrs={'class': 'form-select month-multi-select'}),
        required=True,
    )

    class Meta:
        model = FeePayment
        fields = ['student', 'payment_date', 'payment_months', 'amount_paid']

    def __init__(self, *args, student_queryset=None, initial_student_id=None, lump_sum_mode=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.lump_sum_mode = lump_sum_mode
        self.fields['student'].queryset = student_queryset or Student.objects.filter(status=Student.STATUS_ACTIVE)
        self.fields['student'].widget.attrs.update({'class': 'form-select'})
        self.fields['payment_date'].widget = forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
        self.fields['amount_paid'].widget.attrs.update({'class': 'form-control', 'readonly': 'readonly'})
        if lump_sum_mode:
            self.fields['payment_months'].required = False
            self.fields['amount_paid'].required = False
        if initial_student_id:
            try:
                self.fields['student'].initial = int(initial_student_id)
            except (ValueError, TypeError):
                pass

    def clean_payment_months(self):
        if self.lump_sum_mode:
            return []
        months = list(dict.fromkeys(self.cleaned_data.get('payment_months', [])))
        valid = {v for v, _ in MONTH_CHOICES}
        valid |= {f'{v}_transport' for v in valid}
        invalid = [m for m in months if m not in valid and not str(m).startswith('exam_')]
        if invalid:
            raise forms.ValidationError('Select valid months only.')
        return months


class SuperUserSettingsForm(forms.ModelForm):
    class Meta:
        model = SuperUserSettings
        fields = [
            'software_name', 'superuser_name', 'superuser_email', 'superuser_phone',
            'logo', 'organization_address', 'notes',
        ]
        widgets = {
            'software_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ERP software name', 'required': 'required'}),
            'superuser_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Super user full name', 'required': 'required'}),
            'superuser_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com', 'required': 'required'}),
            'superuser_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mobile number', 'required': 'required'}),
            'logo': forms.FileInput(attrs={'id': 'logo-input', 'accept': 'image/*', 'style': 'display:none;'}),
            'organization_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Office or business address', 'required': 'required'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Internal notes, support details, or future-use information'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['software_name'].required = True
        self.fields['superuser_name'].required = True
        self.fields['superuser_email'].required = True
        self.fields['superuser_phone'].required = True
        self.fields['organization_address'].required = True
        self.fields['logo'].required = not (self.instance and self.instance.logo)
