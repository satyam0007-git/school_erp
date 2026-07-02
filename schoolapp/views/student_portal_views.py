from datetime import date
import calendar
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Q

from ..decorators import student_only
from ..models import SchoolProfile, SchoolSessionRecord, Student, FeePayment, Notification, MONTH_CHOICES
from ..session_utils import CAL_TO_MONTH, MONTH_TO_CAL, get_session_months
from ..services.fee_service import (
    get_monthly_tuition_fee, get_transport_fee, get_unpaid_exam_fees,
    _collect_paid_tokens, get_discount_covered_months
)


@student_only
def student_dashboard(request):
    student = request.student
    school = request.tenant
    selected_session = student.academic_session
    profile = SchoolProfile.get_for_school(school)
    
    # Calculate months elapsed/due
    session_record = SchoolSessionRecord.objects.filter(
        school=school, academic_session=selected_session
    ).first()
    session_start_month = session_record.session_start_month if session_record else profile.session_start_month
    session_end_month = session_record.session_end_month if session_record else profile.session_end_month

    session_months = get_session_months(session_start_month, session_end_month)
    reference_date = timezone.localdate()
    current_month_key = CAL_TO_MONTH.get(reference_date.month)

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

    # Fee math
    monthly_fee = get_monthly_tuition_fee(student, school, session=selected_session)
    transport_fee = get_transport_fee(student)
    unpaid_exam_fees = get_unpaid_exam_fees(student, school, session=selected_session)

    total_needed = (monthly_fee + transport_fee) * months_due + unpaid_exam_fees

    total_paid = FeePayment.objects.filter(
        student=student, academic_session=selected_session,
    ).aggregate(t=Sum('amount_paid'))['t'] or Decimal('0.00')

    balance = max(total_needed - total_paid, Decimal('0.00'))

    # Receipts
    receipts = FeePayment.objects.filter(student=student, school=school).order_by('-payment_date', '-id')

    # Announcements/Notices
    today = timezone.localdate()
    announcements = Notification.objects.filter(
        school=school,
        visibility__in=[Notification.VISIBILITY_PUBLIC, Notification.VISIBILITY_STUDENTS],
        is_published=True,
        publish_date__lte=today
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
    )

    # Calculate monthly status
    paid_tokens, paid_exam_names = _collect_paid_tokens(student, selected_session)
    paid_tokens |= get_discount_covered_months(student, school, profile)

    month_map = dict(MONTH_CHOICES)
    paid_lines = []
    unpaid_lines = []

    has_transport = bool(student.transport_opted and student.transport_amount)

    for month_key in session_months:
        month_name = month_map.get(month_key, month_key.title())
        is_tuition_paid = month_key in paid_tokens

        if has_transport:
            is_transport_paid = f"{month_key}_transport" in paid_tokens

            if is_tuition_paid and is_transport_paid:
                paid_lines.append(f"{month_name}, {month_name} (Transport)")
            elif is_tuition_paid and not is_transport_paid:
                paid_lines.append(month_name)
                unpaid_lines.append(f"{month_name} (Transport)")
            elif not is_tuition_paid and is_transport_paid:
                paid_lines.append(f"{month_name} (Transport)")
                unpaid_lines.append(month_name)
            else:
                unpaid_lines.append(f"{month_name}, {month_name} (Transport)")
        else:
            if is_tuition_paid:
                paid_lines.append(month_name)
            else:
                unpaid_lines.append(month_name)

    return render(request, 'school/student_dashboard.html', {
        'student': student,
        'school': school,
        'current_session': selected_session,
        'total_paid': total_paid,
        'pending_fee': balance,
        'receipts': receipts,
        'announcements': announcements,
        'paid_lines': paid_lines,
        'unpaid_lines': unpaid_lines,
        'has_transport': has_transport,
    })


@student_only
def student_payment_detail(request, pk):
    student = request.student
    school = request.tenant
    payment = get_object_or_404(FeePayment, pk=pk, student=student, school=school)
    return render(request, 'school/student_receipt.html', {'payment': payment})
