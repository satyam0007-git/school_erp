import calendar
from django import template

register = template.Library()


@register.filter
def format_month_token(token):
    """Convert 'april_2025' → 'April 2025', legacy 'april' → 'April'."""
    parts = str(token).split('_')
    if len(parts) == 2 and parts[1].isdigit():
        return f"{parts[0].capitalize()} {parts[1]}"
    return str(token).capitalize()
