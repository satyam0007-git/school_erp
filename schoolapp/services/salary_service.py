import calendar
from datetime import date
from decimal import Decimal

from django.utils import timezone

from ..models import MONTH_CHOICES, SalaryPayment
from ..session_utils import MONTH_TO_CAL


def compute_salary_total(teacher, months, session):
    """Compute salary for the given months, prorating the teacher's joining month."""
    total = Decimal('0.00')
    session_start_year = int(session[:4]) if session and len(session) >= 4 else date.today().year
    joining_date = teacher.joining_date
    joining_month_start = date(joining_date.year, joining_date.month, 1)

    for m in months:
        cal_m = MONTH_TO_CAL.get(m, 1)
        m_year = session_start_year if cal_m >= 4 else session_start_year + 1
        month_start = date(m_year, cal_m, 1)
        if month_start == joining_month_start:
            total_days = calendar.monthrange(m_year, cal_m)[1]
            worked_days = total_days - joining_date.day + 1
            total += (teacher.monthly_salary * Decimal(worked_days) / Decimal(total_days)).quantize(Decimal('0.01'))
        else:
            total += teacher.monthly_salary or Decimal('0.00')
    return total


def build_salary_dashboard_rows(teachers, school, profile, session):
    """Return per-teacher salary summary rows for the salary dashboard."""
    salary_records = SalaryPayment.objects.filter(
        school=school, academic_session=session,
    ).values('teacher_id', 'payment_months', 'amount_paid')

    paid_months_map = {}
    total_paid_map = {}
    for rec in salary_records:
        tid = rec['teacher_id']
        paid_months_map.setdefault(tid, set()).update(rec['payment_months'] or [])
        total_paid_map[tid] = total_paid_map.get(tid, Decimal('0.00')) + rec['amount_paid']

    session_start_year = int(session[:4]) if session and len(session) >= 4 else date.today().year
    today = timezone.localdate()
    profile_session = profile.current_academic_session

    if session < profile_session:
        end_cal = MONTH_TO_CAL[profile.session_end_month]
        end_year = session_start_year if end_cal >= 4 else session_start_year + 1
        cutoff_date = date(end_year, end_cal, 1)
    elif session == profile_session:
        cutoff_date = date(today.year, today.month, 1)
    else:
        cutoff_date = None  # future session — nothing due yet

    rows = []
    for t in teachers:
        paid_months = paid_months_map.get(t.id, set())
        monthly_sal = t.monthly_salary or Decimal('0.00')
        joining_date = t.joining_date
        joining_month_start = date(joining_date.year, joining_date.month, 1)
        total_due = Decimal('0.00')
        payable_count = 0

        if cutoff_date is not None:
            for v, _ in MONTH_CHOICES:
                cal_m = MONTH_TO_CAL.get(v, 1)
                m_year = session_start_year if cal_m >= 4 else session_start_year + 1
                month_start = date(m_year, cal_m, 1)
                if month_start < joining_month_start or month_start > cutoff_date:
                    continue
                payable_count += 1
                if month_start == joining_month_start:
                    total_days = calendar.monthrange(m_year, cal_m)[1]
                    worked_days = total_days - joining_date.day + 1
                    total_due += (monthly_sal * Decimal(worked_days) / Decimal(total_days)).quantize(Decimal('0.01'))
                else:
                    total_due += monthly_sal

        total_paid = total_paid_map.get(t.id, Decimal('0.00'))
        balance = max(total_due - total_paid, Decimal('0.00'))
        rows.append({
            'teacher': t,
            'paid_months': paid_months,
            'paid_count': len(paid_months),
            'payable_count': payable_count,
            'pending_count': max(payable_count - len(paid_months), 0),
            'total_salary_due': total_due,
            'total_paid': total_paid,
            'balance': balance,
            'is_paid_up': balance <= Decimal('0.00'),
        })
    return rows
