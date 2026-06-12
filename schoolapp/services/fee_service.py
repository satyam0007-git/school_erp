from decimal import Decimal

from django.db.models import Sum

from ..models import ExamFee, FeePayment, FeeStructure, SchoolProfile, MONTH_CHOICES
from ..session_utils import get_session_months


def get_monthly_tuition_fee(student, school, session=None):
    if session is None:
        session = SchoolProfile.get_for_school(school).current_academic_session
    result = FeeStructure.objects.filter(
        school_class=student.school_class,
        fee_category__school=school,
        fee_category__is_active=True,
        academic_session=session,
        frequency=FeeStructure.FREQUENCY_MONTHLY,
    ).aggregate(t=Sum('amount'))
    return result['t'] or Decimal('0.00')


def get_transport_fee(student):
    if student.transport_opted and student.transport_amount:
        return student.transport_amount
    return Decimal('0.00')


def get_unpaid_exam_fees(student, school, session=None):
    """Calculate total unpaid exam fees for a student."""
    if session is None:
        session = SchoolProfile.get_for_school(school).current_academic_session
    
    # Get all exam fees for this student's class and session
    exam_fees = ExamFee.objects.filter(
        school=school,
        school_class=student.school_class,
        academic_session=session,
    ).aggregate(total=Sum('amount'))
    total_exam_fees = exam_fees['total'] or Decimal('0.00')
    
    # Get already paid exam fees
    paid_exam_names = set()
    payments = FeePayment.objects.filter(student=student, academic_session=session)
    for items in payments.values_list('exam_fee_items', flat=True):
        for item in (items or []):
            name = item.get('name') or item.get('exam_name') or str(item)
            paid_exam_names.add(name)
    
    # Calculate unpaid exam fees
    unpaid_fees = Decimal('0.00')
    exam_list = ExamFee.objects.filter(
        school=school,
        school_class=student.school_class,
        academic_session=session,
    )
    for exam in exam_list:
        if exam.exam_name not in paid_exam_names:
            unpaid_fees += exam.amount
    
    return unpaid_fees


def get_available_advance(student, session):
    result = FeePayment.objects.filter(
        student=student, academic_session=session,
    ).aggregate(total_advance=Sum('advance_balance'), total_used=Sum('advance_used'))
    return (result['total_advance'] or Decimal('0.00')) - (result['total_used'] or Decimal('0.00'))


def get_discount_covered_months(student, school, profile):
    n = student.discount_months
    if not n or n <= 0:
        return set()
    months = get_session_months(profile.session_start_month, profile.session_end_month)
    has_transport = bool(student.transport_opted and student.transport_amount)
    tokens = set()
    for month in months[:n]:
        tokens.add(month)
        if has_transport:
            tokens.add(f'{month}_transport')
    return tokens


def _collect_paid_tokens(student, session):
    paid_tokens = set()
    paid_exam_names = set()
    payments = FeePayment.objects.filter(student=student, academic_session=session)
    for month_list in payments.values_list('payment_months', flat=True):
        if isinstance(month_list, list):
            paid_tokens.update(str(t) for t in month_list)
    for items in payments.values_list('exam_fee_items', flat=True):
        for item in (items or []):
            name = item.get('name') or item.get('exam_name') or str(item)
            paid_exam_names.add(name)
    return paid_tokens, paid_exam_names


def distribute_lump_sum(student, school, cash_amount, advance_available, profile, session=None):
    """Distribute a cash payment across unpaid months then exam fees; remainder becomes advance."""
    if session is None:
        session = student.academic_session
    session_months = get_session_months(profile.session_start_month, profile.session_end_month)

    cash_amount = Decimal(str(cash_amount))
    advance_available = Decimal(str(advance_available))
    remaining = cash_amount + advance_available

    monthly_fee = get_monthly_tuition_fee(student, school, session)
    transport_fee = get_transport_fee(student)
    has_transport = bool(student.transport_opted and student.transport_amount)

    paid_tokens, paid_exam_names = _collect_paid_tokens(student, session)
    paid_tokens |= get_discount_covered_months(student, school, profile)

    paid_month_tokens = []
    exam_fee_items = []
    transport_total = Decimal('0.00')

    if monthly_fee > 0:
        for month in session_months:
            if month in paid_tokens:
                continue
            if remaining < monthly_fee:
                break
            paid_month_tokens.append(month)
            remaining -= monthly_fee

            transport_token = f'{month}_transport'
            if has_transport and transport_token not in paid_tokens:
                if remaining < transport_fee:
                    break
                paid_month_tokens.append(transport_token)
                remaining -= transport_fee
                transport_total += transport_fee

    for ef in ExamFee.objects.filter(
        school=school, school_class=student.school_class, academic_session=session,
    ).order_by('exam_name'):
        if ef.exam_name in paid_exam_names:
            continue
        if remaining >= ef.amount:
            exam_fee_items.append({'name': ef.exam_name, 'amount': str(ef.amount)})
            remaining -= ef.amount

    advance_balance = remaining
    gross_amount = (cash_amount + advance_available) - advance_balance
    return {
        'paid_month_tokens': paid_month_tokens,
        'exam_fee_items': exam_fee_items,
        'transport_total': transport_total,
        'gross_amount': gross_amount,
        'advance_balance': advance_balance,
    }


def get_unpaid_fee_options(student, school):
    """Return selectable month/exam tokens that have not yet been paid for this student."""
    profile = SchoolProfile.get_for_school(school)
    session = student.academic_session
    session_months = get_session_months(profile.session_start_month, profile.session_end_month)

    has_monthly = FeeStructure.objects.filter(
        school_class=student.school_class,
        fee_category__school=school,
        fee_category__is_active=True,
        academic_session=session,
        frequency=FeeStructure.FREQUENCY_MONTHLY,
    ).exists()
    has_transport = bool(student.transport_opted and student.transport_amount)

    valid_tokens = set(session_months) | {f'{v}_transport' for v in session_months}
    paid_tokens = set()
    for month_list in FeePayment.objects.filter(
        student=student, academic_session=session,
    ).values_list('payment_months', flat=True):
        if isinstance(month_list, list):
            paid_tokens.update(t for t in map(str, month_list) if t in valid_tokens)
    paid_tokens |= get_discount_covered_months(student, school, profile)

    month_label_map = dict(MONTH_CHOICES)
    options = []
    for value in session_months:
        label = month_label_map[value]
        if has_monthly and value not in paid_tokens:
            options.append({'value': value, 'label': label, 'group': 'Monthly Fee'})
        transport_token = f'{value}_transport'
        if has_transport and transport_token not in paid_tokens:
            options.append({'value': transport_token, 'label': f'{label} (Transport)', 'group': 'Transport'})

    paid_exam_names = set()
    for items in FeePayment.objects.filter(
        student=student, academic_session=session,
    ).values_list('exam_fee_items', flat=True):
        for item in (items or []):
            paid_exam_names.add(item.get('name') or item.get('exam_name') or str(item))

    for ef in ExamFee.objects.filter(school=school, school_class=student.school_class, academic_session=session):
        if ef.exam_name not in paid_exam_names:
            options.append({'value': f'exam_{ef.pk}', 'label': f'{ef.exam_name} — ₹{ef.amount:,.0f}', 'group': 'Exam Fee'})

    return options


def get_editable_fee_options(payment, school):
    """Return month/exam options when editing an existing payment (keeps already-selected items available)."""
    student = payment.student
    profile = SchoolProfile.get_for_school(school)
    session = payment.academic_session
    session_months = get_session_months(profile.session_start_month, profile.session_end_month)

    has_monthly = FeeStructure.objects.filter(
        school_class=student.school_class,
        fee_category__school=school,
        fee_category__is_active=True,
        academic_session=session,
        frequency=FeeStructure.FREQUENCY_MONTHLY,
    ).exists()
    has_transport = bool(student.transport_opted and student.transport_amount)

    valid_tokens = set(session_months) | {f'{v}_transport' for v in session_months}
    other_paid = set()
    for month_list in FeePayment.objects.filter(
        student=student, academic_session=session,
    ).exclude(pk=payment.pk).values_list('payment_months', flat=True):
        if isinstance(month_list, list):
            other_paid.update(t for t in map(str, month_list) if t in valid_tokens)

    this_tokens = set(str(t) for t in (payment.payment_months or []))
    month_label_map = dict(MONTH_CHOICES)
    options = []
    for value in session_months:
        label = month_label_map[value]
        if has_monthly and (value in this_tokens or value not in other_paid):
            options.append({'value': value, 'label': label, 'selected': value in this_tokens, 'group': 'Monthly Fee'})
        transport_token = f'{value}_transport'
        if has_transport and (transport_token in this_tokens or transport_token not in other_paid):
            options.append({
                'value': transport_token, 'label': f'{label} (Transport)',
                'selected': transport_token in this_tokens, 'group': 'Transport',
            })

    other_exam_names = set()
    for items in FeePayment.objects.filter(
        student=student, academic_session=session,
    ).exclude(pk=payment.pk).values_list('exam_fee_items', flat=True):
        for item in (items or []):
            other_exam_names.add(item.get('name') or item.get('exam_name') or str(item))

    this_exam_names = {
        item.get('name') or item.get('exam_name') or str(item)
        for item in (payment.exam_fee_items or [])
    }

    for ef in ExamFee.objects.filter(school=school, school_class=student.school_class, academic_session=session):
        if ef.exam_name not in other_exam_names:
            options.append({
                'value': f'exam_{ef.pk}',
                'label': f'{ef.exam_name} — ₹{ef.amount:,.0f}',
                'selected': ef.exam_name in this_exam_names,
                'group': 'Exam Fee',
            })

    return options
