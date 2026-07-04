from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from ..models import SchoolBillingPayment, SchoolProfile, SchoolSessionRecord
from ..session_utils import (
    CAL_TO_MONTH, format_academic_session,
)


def get_school_subscription_period(school, session):
    """Return (start_date, end_date) for the given school and academic session.
    Calculated relative to the school's current academic session and subscription dates.
    """
    profile = SchoolProfile.get_for_school(school)
    current_session = profile.current_academic_session
    sub_start = school.subscription_start_date
    sub_end = school.subscription_end_date

    if not sub_start or not sub_end:
        return None, None

    try:
        current_year = int(current_session.split('-')[0])
        target_year = int(session.split('-')[0])
        diff_years = current_year - target_year
    except (ValueError, IndexError, AttributeError):
        diff_years = 0

    try:
        hist_start = sub_start.replace(year=sub_start.year - diff_years)
    except ValueError:
        hist_start = sub_start - timezone.timedelta(days=365 * diff_years)

    try:
        hist_end = sub_end.replace(year=sub_end.year - diff_years)
    except ValueError:
        hist_end = sub_end - timezone.timedelta(days=365 * diff_years)

    return hist_start, hist_end


def get_formatted_billing_period(school, session):
    """Return a formatted string representing the billing period for the school and session."""
    start_dt, end_dt = get_school_subscription_period(school, session)
    if start_dt and end_dt:
        return f"{start_dt.strftime('%d %b %Y')} – {end_dt.strftime('%d %b %Y')}"
    # Fallback to session record start/end months or profile if not set
    profile = SchoolProfile.get_for_school(school)
    sr = SchoolSessionRecord.objects.filter(school=school, academic_session=session).first()
    if sr:
        return f"{sr.session_start_month.capitalize()} – {sr.session_end_month.capitalize()}"
    return f"{profile.session_start_month.capitalize()} – {profile.session_end_month.capitalize()}"



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

            rows.append({
                'school': school,
                'session': session,
                'is_current_session': is_current,
                'is_renewed': not is_current,
                'student_count': active_students,
                'fee_per_student': school.fee_per_student,
                'billing_period': get_formatted_billing_period(school, session),
                'subscription_years': school.get_subscription_years(),
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

            paid = SchoolBillingPayment.objects.filter(
                school=school, academic_session=session,
            ).aggregate(t=Sum('amount_paid'))['t'] or Decimal('0.00')

            if is_current:
                total_due = school.subscription_amount
            else:
                total_due = paid
            billing_period = get_formatted_billing_period(school, session)

            balance = max(total_due - paid, Decimal('0.00'))

            rows.append({
                'school': school,
                'session': session,
                'is_current_session': is_current,
                'active_students': active_students,
                'fee_per_student': Decimal('0.00'),
                'monthly_bill': Decimal('0.00'),
                'total_due': total_due,
                'month_count': 12,
                'total_paid': paid,
                'balance': balance,
                'is_paid_up': balance <= Decimal('0.00'),
                'billing_period': billing_period,
            })

            if session == default_session:
                total_monthly += total_due
                total_collected += paid

    return rows, total_monthly, total_collected
