import calendar
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from ..models import SchoolBillingPayment, SchoolProfile, SchoolSessionRecord
from ..session_utils import (
    CAL_TO_MONTH, MONTH_TO_CAL, format_academic_session,
    get_session_months, get_session_start_year,
)

_MONTH_ABBR = {
    'april': 'Apr', 'may': 'May', 'june': 'Jun', 'july': 'Jul',
    'august': 'Aug', 'september': 'Sep', 'october': 'Oct', 'november': 'Nov',
    'december': 'Dec', 'january': 'Jan', 'february': 'Feb', 'march': 'Mar',
}


def get_school_billing_months(school, session=None):
    """Return (token, label) for every month in the school's billing window for the given session."""
    profile = SchoolProfile.get_for_school(school)
    target_session = session or profile.current_academic_session

    if target_session == profile.current_academic_session:
        start_key, end_key = profile.billing_start_month, profile.billing_end_month
    else:
        sr = SchoolSessionRecord.objects.filter(school=school, academic_session=target_session).first()
        if sr:
            start_key, end_key = sr.billing_start_month, sr.billing_end_month
        else:
            start_key, end_key = profile.billing_start_month, profile.billing_end_month

    try:
        session_start_year = int(target_session.split('-')[0])
    except (ValueError, IndexError):
        session_start_year = get_session_start_year(timezone.localdate(), start_key)

    start_cal = MONTH_TO_CAL[start_key]
    result = []
    for m in get_session_months(start_key, end_key):
        cal = MONTH_TO_CAL[m]
        token_year = session_start_year if cal >= start_cal else session_start_year + 1
        result.append((f"{m}_{token_year}", f"{calendar.month_name[cal]} {token_year}"))
    return result


def get_billing_period_info(session, b_start, b_end, is_current):
    """Return (month_count, period_label) for a school's billing row."""
    today = timezone.localdate()
    current_month_key = CAL_TO_MONTH[today.month]
    all_months = get_session_months(b_start, b_end)

    if is_current:
        billed = all_months[:all_months.index(current_month_key) + 1] if current_month_key in all_months else []
    else:
        billed = all_months

    if not billed:
        return 0, '—'

    s = _MONTH_ABBR.get(billed[0], billed[0].capitalize())
    e = _MONTH_ABBR.get(billed[-1], billed[-1].capitalize())
    return len(billed), (s if billed[0] == billed[-1] else f"{s} – {e}")


def build_superuser_dashboard_rows(schools, profiles, session_records, student_counts, system_session):
    """Build the row data for the superuser main dashboard."""
    rows = []
    for school in schools:
        profile = profiles.get(school.pk)
        current_session = profile.current_academic_session if profile else ''
        sessions_to_show = {current_session} if current_session else set()

        try:
            start_year = int(current_session.split('-')[0])
            prev = format_academic_session(start_year - 1)
            if prev == system_session:
                sessions_to_show.add(prev)
        except (ValueError, IndexError, AttributeError):
            pass

        billed_sessions = set(
            SchoolBillingPayment.objects.filter(school=school)
            .values_list('academic_session', flat=True).distinct()
        )
        sessions_to_show.update(billed_sessions)
        sessions_to_show.update(
            sr_session for (sid, sr_session) in session_records if sid == school.pk
        )

        for session in sorted(sessions_to_show, reverse=True):
            is_current = session == current_session
            active_students = student_counts.get((school.pk, session), 0)

            if is_current and profile:
                b_start, b_end = profile.billing_start_month, profile.billing_end_month
            else:
                sr = session_records.get((school.pk, session))
                if sr:
                    b_start, b_end = sr.billing_start_month, sr.billing_end_month
                elif profile:
                    b_start, b_end = profile.billing_start_month, profile.billing_end_month
                else:
                    b_start = b_end = '—'

            rows.append({
                'school': school,
                'session': session,
                'is_current_session': is_current,
                'is_renewed': not is_current,
                'student_count': active_students,
                'fee_per_student': school.fee_per_student,
                'billing_start_month': b_start,
                'billing_end_month': b_end,
            })
    return rows


def build_fee_dashboard_rows(schools, profiles, session_records, student_counts, default_session):
    """Build the row data for the superuser school-fee billing dashboard."""
    rows = []
    total_monthly = Decimal('0.00')
    total_collected = Decimal('0.00')

    for school in schools:
        profile = profiles.get(school.pk)
        current_session = profile.current_academic_session if profile else ''
        sessions_to_show = {current_session} if current_session else set()

        try:
            start_year = int(current_session.split('-')[0])
            prev = format_academic_session(start_year - 1)
            sessions_to_show.add(prev)
        except (ValueError, IndexError, AttributeError):
            pass

        billed_sessions = set(
            SchoolBillingPayment.objects.filter(school=school)
            .values_list('academic_session', flat=True).distinct()
        )
        sessions_to_show.update(billed_sessions)

        for session in sorted(sessions_to_show, reverse=True):
            is_current = session == current_session
            active_students = student_counts.get((school.pk, session), 0)
            per_month = school.fee_per_student * active_students

            paid = SchoolBillingPayment.objects.filter(
                school=school, academic_session=session,
            ).aggregate(t=Sum('amount_paid'))['t'] or Decimal('0.00')

            if is_current:
                p = profile or SchoolProfile.get_for_school(school)
                b_start, b_end = p.billing_start_month, p.billing_end_month
            else:
                sr = session_records.get((school.pk, session))
                if sr:
                    b_start, b_end = sr.billing_start_month, sr.billing_end_month
                else:
                    p = profile or SchoolProfile.get_for_school(school)
                    b_start, b_end = p.billing_start_month, p.billing_end_month

            month_count, billing_period = get_billing_period_info(session, b_start, b_end, is_current)
            total_due = per_month * month_count
            balance = max(total_due - paid, Decimal('0.00'))

            rows.append({
                'school': school,
                'session': session,
                'is_current_session': is_current,
                'active_students': active_students,
                'fee_per_student': school.fee_per_student,
                'monthly_bill': per_month,
                'total_due': total_due,
                'month_count': month_count,
                'total_paid': paid,
                'balance': balance,
                'is_paid_up': balance <= Decimal('0.00'),
                'billing_period': billing_period,
            })

            if session == default_session:
                total_monthly += total_due
                total_collected += paid

    return rows, total_monthly, total_collected
