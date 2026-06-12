import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from ..models import FeePayment, SchoolClass, Student
from ..session_utils import get_current_academic_session
from ..utils.date_utils import parse_excel_date
from .fee_service import distribute_lump_sum, get_available_advance


BULK_UPLOAD_HEADERS = [
    'Student Name*', 'Date of Birth* (DD-MM-YYYY)', 'Class*',
    'Father Name*', 'Mother Name*', 'Father WhatsApp*', 'Address*',
    'Religion*', 'Caste*', 'Blood Group', 'Previous School', 'Aadhaar Number',
    'PEN Number', 'Transport Opted (Yes/No)', 'Transport Amount',
    'Discount Months (0-12)', 'Admission Date (DD-MM-YYYY)',
    'Paid Amount', 'Payment Date (DD-MM-YYYY)',
]

VALID_BLOOD_GROUPS = {'O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-'}

BULK_MAX_LENGTHS = {
    'Student Name': ('name', 150),
    'Father Name': ('father_name', 120),
    'Mother Name': ('mother_name', 120),
    'Father WhatsApp': ('father_phone', 20),
    'Blood Group': ('blood_group', 10),
    'Previous School': ('prev_school', 200),
    'PEN Number': ('pen', 20),
    'Religion': ('religion', 100),
    'Caste': ('caste', 100),
}

BULK_FIELD_INFO = [
    {'name': 'Student Name',     'required': True},
    {'name': 'Date of Birth',    'required': True},
    {'name': 'Class',            'required': True},
    {'name': 'Father Name',      'required': True},
    {'name': 'Mother Name',      'required': True},
    {'name': 'Father WhatsApp',  'required': True},
    {'name': 'Address',          'required': True},
    {'name': 'Religion',         'required': True},
    {'name': 'Caste',            'required': True},
    {'name': 'Blood Group',      'required': False},
    {'name': 'Previous School',  'required': False},
    {'name': 'Aadhaar Number',   'required': False},
    {'name': 'PEN Number',       'required': False},
    {'name': 'Transport Opted',  'required': False},
    {'name': 'Transport Amount', 'required': False},
    {'name': 'Discount Months',  'required': False},
    {'name': 'Admission Date',   'required': False},
    {'name': 'Paid Amount',      'required': False},
    {'name': 'Payment Date',     'required': False},
]


def get_next_session(current_session):
    try:
        start_year = int(current_session.split('-')[0])
        return f"{start_year + 1}-{(start_year + 2) % 100:02d}"
    except (ValueError, IndexError, AttributeError):
        return get_current_academic_session(timezone.localdate())


def promote_student(student, school):
    """Mark student as promoted and create a new active record in the next class/session."""
    classes = list(SchoolClass.objects.filter(school=school).order_by('name'))
    idx = next((i for i, c in enumerate(classes) if c.pk == student.school_class_id), None)
    if idx is None or idx >= len(classes) - 1:
        return None, f'{student.name} is already in the last class and cannot be promoted.'

    next_class = classes[idx + 1]
    next_session = get_next_session(student.academic_session)

    with transaction.atomic():
        student.status = Student.STATUS_PROMOTED
        student.save(update_fields=['status', 'updated_at'])
        promoted = Student.objects.create(
            school=student.school,
            school_class=next_class,
            name=student.name,
            date_of_birth=student.date_of_birth,
            academic_session=next_session,
            status=Student.STATUS_ACTIVE,
            father_name=student.father_name,
            father_phone=student.father_phone,
            address=student.address,
            admission_date=student.admission_date,
            transport_opted=student.transport_opted,
            transport_amount=student.transport_amount,
        )
    return promoted, None


def fail_student(student):
    """Mark student as failed and create a new active record in the same class next session."""
    next_session = get_next_session(student.academic_session)
    with transaction.atomic():
        student.status = Student.STATUS_FAIL
        student.save(update_fields=['status', 'updated_at'])
        retained = Student.objects.create(
            school=student.school,
            school_class=student.school_class,
            name=student.name,
            date_of_birth=student.date_of_birth,
            academic_session=next_session,
            status=Student.STATUS_ACTIVE,
            father_name=student.father_name,
            father_phone=student.father_phone,
            address=student.address,
            admission_date=student.admission_date,
            transport_opted=student.transport_opted,
            transport_amount=student.transport_amount,
        )
    return retained


def _parse_bulk_row(row, class_map, session, batch_keys, school):
    """Parse and validate one Excel row. Returns (cleaned_data_dict, errors_list)."""
    def gc(idx, default=''):
        val = row[idx] if idx < len(row) else None
        return str(val).strip() if val is not None and str(val).strip() else default

    name          = gc(0).title()
    dob_raw       = row[1] if len(row) > 1 else None
    class_name    = gc(2)
    father_name   = gc(3).title()
    mother_name   = gc(4).title()
    father_phone  = gc(5)
    address       = gc(6).title()
    religion      = gc(7)
    caste         = gc(8)
    blood_group   = gc(9) or 'O+'
    prev_school   = gc(10, '').title()
    aadhaar       = gc(11, '')
    pen           = gc(12, '')
    transport_str = gc(13) or 'No'
    transport_amt = gc(14, '')
    discount_str  = gc(15, '0') or '0'
    adm_raw       = row[16] if len(row) > 16 else None
    paid_str      = gc(17, '')
    fee_date_raw  = row[18] if len(row) > 18 else None

    errors = []

    if not name:         errors.append('Student Name is required')
    if not dob_raw or not str(dob_raw).strip(): errors.append('Date of Birth is required')
    if not class_name:   errors.append('Class is required')
    if not father_name:  errors.append('Father Name is required')
    if not mother_name:  errors.append('Mother Name is required')
    if not father_phone: errors.append('Father WhatsApp Number is required')
    if not address:      errors.append('Address is required')
    if not religion:     errors.append('Religion is required')
    if not caste:        errors.append('Caste is required')

    dob = parse_excel_date(dob_raw)
    if dob_raw is not None and str(dob_raw).strip() and dob is None:
        errors.append(f'Invalid Date of Birth — use DD-MM-YYYY')

    admission_dt = parse_excel_date(adm_raw) or timezone.localdate()
    school_class = class_map.get(class_name.lower()) if class_name else None
    if class_name and not school_class:
        errors.append(f'Class "{class_name}" not found (available: {", ".join(sorted(class_map))})')

    phone_digits = re.sub(r'\D', '', father_phone) if father_phone else ''
    if father_phone and len(phone_digits) != 10:
        errors.append(f'Father phone must be exactly 10 digits')
    elif father_phone:
        father_phone = phone_digits

    aadhaar_digits = re.sub(r'\D', '', aadhaar) if aadhaar else ''
    if aadhaar and len(aadhaar_digits) != 12:
        errors.append('Aadhaar Number must be exactly 12 digits')
    elif aadhaar:
        aadhaar = aadhaar_digits

    if blood_group and blood_group.upper() not in VALID_BLOOD_GROUPS:
        errors.append(f'Invalid Blood Group "{blood_group}"')
        blood_group = ''

    transport_opted = transport_str.lower() in ('yes', 'y', '1', 'true')
    transport_amount = None
    if transport_opted:
        if transport_amt:
            try:
                transport_amount = Decimal(transport_amt)
                if transport_amount <= 0:
                    errors.append('Transport Amount must be greater than zero')
            except InvalidOperation:
                errors.append(f'Invalid Transport Amount "{transport_amt}"')
        else:
            errors.append('Transport Amount is required when Transport Opted is Yes')

    discount_months = 0
    try:
        discount_months = int(float(discount_str))
        if not 0 <= discount_months <= 12:
            errors.append(f'Discount Months must be 0–12')
            discount_months = 0
    except (ValueError, TypeError):
        pass

    paid_amount = None
    fee_date = None
    if paid_str:
        try:
            paid_amount = Decimal(paid_str)
            if paid_amount < 0:
                errors.append('Paid Amount must be zero or positive')
                paid_amount = None
        except InvalidOperation:
            errors.append(f'Invalid Paid Amount "{paid_str}"')

    if paid_amount and paid_amount > 0:
        fee_date = parse_excel_date(fee_date_raw)
        if fee_date is None:
            errors.append('Payment Date is required when Paid Amount is provided — use DD-MM-YYYY')

    if not errors and name and father_name and school_class and session and dob:
        batch_key = (name.lower(), father_name.lower(), school_class.pk, session, str(dob))
        if batch_key in batch_keys:
            errors.append('Duplicate row within this upload batch')
        elif Student.objects.filter(
            school=school, name__iexact=name, father_name__iexact=father_name,
            school_class=school_class, academic_session=session, date_of_birth=dob,
        ).exists():
            errors.append('Duplicate: student already exists in the system')
        else:
            batch_keys.add(batch_key)

    field_values = {
        'name': name,
        'father_name': father_name,
        'mother_name': mother_name,
        'father_phone': father_phone,
        'blood_group': blood_group,
        'prev_school': prev_school,
        'pen': pen,
        'religion': religion,
        'caste': caste,
    }
    for label, (field_name, max_length) in BULK_MAX_LENGTHS.items():
        value = field_values.get(field_name) or ''
        if len(value) > max_length:
            errors.append(f'{label} must be {max_length} characters or fewer')

    if errors:
        return None, errors

    return {
        'name': name, 'dob': dob, 'school_class': school_class,
        'father_name': father_name, 'mother_name': mother_name,
        'father_phone': father_phone, 'address': address,
        'religion': religion, 'caste': caste, 'blood_group': blood_group,
        'prev_school': prev_school, 'aadhaar': aadhaar, 'pen': pen,
        'transport_opted': transport_opted, 'transport_amount': transport_amount,
        'discount_months': discount_months, 'admission_dt': admission_dt,
        'paid_amount': paid_amount, 'fee_date': fee_date,
    }, []


def process_bulk_upload(workbook, school, profile, user):
    """Process a bulk-admission Excel workbook. Returns (result_dict, failed_rows)."""
    classes = list(SchoolClass.objects.filter(school=school).order_by('name'))
    class_map = {c.name.lower(): c for c in classes}
    session = profile.current_academic_session

    total = success = fee_success = fee_skipped = fee_provided = 0
    fee_last_error = ''
    failed_rows = []
    batch_keys = set()
    successful_student_ids = []

    for row in workbook.active.iter_rows(min_row=2, values_only=True):
        first_val = str(row[0] or '').strip() if row else ''
        if not first_val or first_val.upper().startswith('NOTE:'):
            continue
        total += 1

        raw_row = [str(v) if v is not None else '' for v in row[:19]]
        while len(raw_row) < 19:
            raw_row.append('')

        data, errors = _parse_bulk_row(row, class_map, session, batch_keys, school)
        if errors:
            raw_row.append('; '.join(errors))
            failed_rows.append(raw_row)
            continue

        if data['paid_amount'] and data['paid_amount'] > 0:
            fee_provided += 1

        try:
            with transaction.atomic():
                student = Student.objects.create(
                    school=school, school_class=data['school_class'],
                    name=data['name'], date_of_birth=data['dob'],
                    academic_session=session, status=Student.STATUS_ACTIVE,
                    father_name=data['father_name'], mother_name=data['mother_name'],
                    father_phone=data['father_phone'], address=data['address'],
                    religion=data['religion'], caste=data['caste'],
                    blood_group=data['blood_group'], previous_school=data['prev_school'],
                    aadhaar_number=data['aadhaar'], pen_number=data['pen'],
                    transport_opted=data['transport_opted'], transport_amount=data['transport_amount'],
                    discount_months=data['discount_months'], admission_date=data['admission_dt'],
                )
            success += 1
            successful_student_ids.append(student.pk)

            if data['paid_amount'] and data['paid_amount'] > 0 and data['fee_date']:
                try:
                    advance = get_available_advance(student, session)
                    dist = distribute_lump_sum(student, school, data['paid_amount'], advance, profile, session)
                    if dist['paid_month_tokens'] or dist['exam_fee_items'] or dist['advance_balance'] > 0:
                        FeePayment.objects.create(
                            school=school, student=student,
                            payment_date=data['fee_date'], academic_session=session,
                            payment_months=dist['paid_month_tokens'],
                            exam_fee_items=dist['exam_fee_items'],
                            transport_amount=dist['transport_total'],
                            amount_paid=data['paid_amount'], gross_amount=dist['gross_amount'],
                            advance_used=advance, advance_balance=dist['advance_balance'],
                            is_lump_sum=True, is_admission_discount=False, collected_by=user,
                        )
                        fee_success += 1
                    else:
                        fee_skipped += 1
                except Exception as e:
                    fee_skipped += 1
                    fee_last_error = str(e)

        except Exception as exc:
            raw_row.append(f'Save error: {exc}')
            failed_rows.append(raw_row)

    return {
        'total': total, 'success': success,
        'fee_success': fee_success, 'fee_skipped': fee_skipped,
        'fee_provided': fee_provided, 'fee_last_error': fee_last_error,
        'failed': len(failed_rows), 'has_errors': bool(failed_rows),
        'successful_student_ids': successful_student_ids,
    }, failed_rows
