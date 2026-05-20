import re
import calendar as _calendar
from django.core.exceptions import ValidationError
from django.utils import timezone

ACADEMIC_SESSION_PATTERN = re.compile(r'^\d{4}-\d{2}$')

# Canonical month order for a school academic year (April-start default)
MONTH_ORDER = [
    'april', 'may', 'june', 'july', 'august', 'september',
    'october', 'november', 'december', 'january', 'february', 'march',
]

MONTH_TO_CAL = {
    'april': 4, 'may': 5, 'june': 6, 'july': 7, 'august': 8, 'september': 9,
    'october': 10, 'november': 11, 'december': 12, 'january': 1, 'february': 2, 'march': 3,
}

CAL_TO_MONTH = {v: k for k, v in MONTH_TO_CAL.items()}


def get_session_months(start_month, end_month):
    """Return ordered list of month keys from start_month through end_month (wraps across year boundary)."""
    si = MONTH_ORDER.index(start_month)
    ei = MONTH_ORDER.index(end_month)
    if ei >= si:
        return MONTH_ORDER[si:ei + 1]
    return MONTH_ORDER[si:] + MONTH_ORDER[:ei + 1]


def get_session_start_year(reference_date=None, session_start_month='april'):
    """Return the 4-digit start year of the academic session that contains reference_date.

    Respects the school's session_start_month so schools that begin in June, July,
    etc. get the correct year boundary instead of the hardcoded April assumption.
    """
    date_obj = reference_date or timezone.localdate()
    start_cal = MONTH_TO_CAL.get(session_start_month, 4)
    return date_obj.year if date_obj.month >= start_cal else date_obj.year - 1


def format_academic_session(start_year):
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def get_current_academic_session(reference_date=None, session_start_month='april'):
    return format_academic_session(get_session_start_year(reference_date, session_start_month))


def default_current_academic_session():
    return get_current_academic_session()


def get_academic_session_choices(past_years=2, future_years=10, reference_date=None, session_start_month='april'):
    """Return (value, label) tuples spanning past_years back through future_years ahead.

    Replaces the old forward-only ``years`` parameter so callers can also display
    historical sessions (needed for fee dashboards, reports, etc.).
    """
    start_year = get_session_start_year(reference_date, session_start_month)
    return [
        (format_academic_session(start_year + offset), format_academic_session(start_year + offset))
        for offset in range(-past_years, future_years + 1)
    ]


def validate_academic_session(value):
    if not ACADEMIC_SESSION_PATTERN.match(value or ''):
        raise ValidationError('Academic session must be in YYYY-YY format (e.g. 2026-27).')
    start_year = int(value[:4])
    if value != format_academic_session(start_year):
        raise ValidationError('Academic session must represent consecutive years (e.g. 2026-27).')
