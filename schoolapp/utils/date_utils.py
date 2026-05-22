from datetime import date, datetime


def parse_excel_date(value):
    """Parse a date from any value an Excel cell might contain (datetime obj, date obj, or string)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    # ISO format: "2000-12-12" or "2000-12-12 00:00:00"
    if len(s) >= 10 and s[4:5] == '-':
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            pass
    for fmt in ('%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None
