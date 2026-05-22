import calendar
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from ..models import FeePayment, SchoolSessionRecord, Student
from ..session_utils import CAL_TO_MONTH, MONTH_TO_CAL, get_session_months
from .fee_service import get_monthly_tuition_fee, get_transport_fee


def get_student_report_queryset(school, session, filters=None):
    qs = (
        Student.objects.filter(school=school, academic_session=session)
        .select_related('school_class')
        .order_by('admission_date', 'name')
    )
    if not filters:
        return qs
    if filters.get('date_from'):
        try:
            qs = qs.filter(admission_date__gte=date.fromisoformat(filters['date_from']))
        except ValueError:
            pass
    if filters.get('date_to'):
        try:
            qs = qs.filter(admission_date__lte=date.fromisoformat(filters['date_to']))
        except ValueError:
            pass
    if filters.get('class_id'):
        qs = qs.filter(school_class_id=filters['class_id'])
    return qs


def get_fee_payment_queryset(school, session, filters=None):
    qs = (
        FeePayment.objects.filter(school=school, academic_session=session)
        .select_related('student', 'student__school_class', 'collected_by')
        .order_by('payment_date', 'student__name')
    )
    if not filters:
        return qs
    if filters.get('date_from'):
        try:
            qs = qs.filter(payment_date__gte=date.fromisoformat(filters['date_from']))
        except ValueError:
            pass
    if filters.get('date_to'):
        try:
            qs = qs.filter(payment_date__lte=date.fromisoformat(filters['date_to']))
        except ValueError:
            pass
    if filters.get('class_id'):
        qs = qs.filter(student__school_class_id=filters['class_id'])
    return qs


def build_fee_dashboard_data(school, profile, filters=None):
    """Build the payment summary used by the fee dashboard export and print views."""
    filters = filters or {}
    reference_date = timezone.localdate()
    selected_session = filters.get('session') or profile.current_academic_session

    sr = SchoolSessionRecord.objects.filter(school=school, academic_session=selected_session).first()
    session_start_month = sr.session_start_month if sr else profile.session_start_month
    session_end_month = sr.session_end_month if sr else profile.session_end_month

    students = Student.objects.filter(
        school=school, status=Student.STATUS_ACTIVE, academic_session=selected_session,
    ).select_related('school_class')

    q = filters.get('q', '').strip()
    class_id = filters.get('class_id')
    if q:
        students = students.filter(Q(name__icontains=q) | Q(father_name__icontains=q) | Q(roll_number__icontains=q))
    if class_id:
        students = students.filter(school_class_id=class_id)

    session_months = get_session_months(session_start_month, session_end_month)
    current_month_key = CAL_TO_MONTH[reference_date.month]

    try:
        sess_start_year = int(selected_session.split('-')[0])
    except (ValueError, IndexError):
        sess_start_year = reference_date.year

    sess_start_cal = MONTH_TO_CAL.get(session_start_month, 1)
    sess_end_cal = MONTH_TO_CAL.get(session_end_month, 3)
    sess_end_year = sess_start_year if sess_end_cal >= sess_start_cal else sess_start_year + 1
    sess_start_date = date(sess_start_year, sess_start_cal, 1)
    sess_end_date = date(sess_end_year, sess_end_cal, calendar.monthrange(sess_end_year, sess_end_cal)[1])

    if reference_date < sess_start_date:
        months_due = 0
    elif reference_date > sess_end_date:
        months_due = len(session_months)
    elif current_month_key in session_months:
        months_due = session_months.index(current_month_key) + 1
    else:
        months_due = len(session_months)

    payment_data = []
    for student in students.order_by('school_class__name', 'name'):
        monthly_fee = get_monthly_tuition_fee(student, school, session=selected_session)
        transport_fee = get_transport_fee(student)
        total_needed = (monthly_fee + transport_fee) * months_due
        total_paid = FeePayment.objects.filter(
            student=student, academic_session=selected_session,
        ).aggregate(t=Sum('amount_paid'))['t'] or Decimal('0.00')
        balance = max(total_needed - total_paid, Decimal('0.00'))
        payment_data.append({
            'student_name': student.name,
            'roll_number': student.roll_number,
            'father_name': student.father_name,
            'student_class': str(student.school_class),
            'total_amount_paid': total_paid,
            'total_payment_need_to_pay_till_month': total_needed,
            'balance_payment': balance,
            'is_paid_up': balance <= Decimal('0.00'),
        })

    payment_status = filters.get('payment_status', '')
    if payment_status == 'pending':
        payment_data = [p for p in payment_data if p['balance_payment'] > 0]
    elif payment_status == 'paid':
        payment_data = [p for p in payment_data if p['balance_payment'] <= 0]

    total_due = sum(p['total_payment_need_to_pay_till_month'] for p in payment_data)
    total_collected = sum(p['total_amount_paid'] for p in payment_data)
    total_pending = sum(p['balance_payment'] for p in payment_data if p['balance_payment'] > 0)

    range_start = session_months[0] if session_months else session_start_month
    range_end = session_months[months_due - 1] if months_due > 0 and session_months else range_start
    label_year = lambda k: sess_start_year if MONTH_TO_CAL[k] >= sess_start_cal else sess_start_year + 1
    fee_range_label = f"{range_start.capitalize()} {label_year(range_start)} → {range_end.capitalize()} {label_year(range_end)}"

    return {
        'payment_data': payment_data,
        'total_due': total_due,
        'total_collected': total_collected,
        'total_pending': total_pending,
        'selected_session': selected_session,
        'school': school,
        'profile': profile,
        'fee_range_label': fee_range_label,
    }
