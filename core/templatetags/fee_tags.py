import calendar
from django import template
from decimal import Decimal

register = template.Library()


@register.filter
def indian_number(value):
    """Format a number using Indian comma style: 1,23,456 or 12,34,567."""
    try:
        n = int(Decimal(str(value)))
    except Exception:
        return value
    negative = n < 0
    s = str(abs(n))
    if len(s) <= 3:
        result = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        result = ','.join(reversed(groups)) + ',' + last3
    return ('-' if negative else '') + result


@register.filter
def format_month_token(token):
    """Convert 'april_2025' → 'April 2025', legacy 'april' → 'April'."""
    parts = str(token).split('_')
    if len(parts) == 2 and parts[1].isdigit():
        return f"{parts[0].capitalize()} {parts[1]}"
    return str(token).capitalize()


@register.filter
def get_item(dictionary, key):
    """Lookup dictionary[key] in a template, e.g. {{ my_dict|get_item:key }}."""
    return dictionary.get(key)


@register.simple_tag
def smart_page_range(page_obj, window=3, end_pages=3):
    """
    Return a list of page numbers and '...' ellipsis markers for smart pagination.

    Always shows:
      - Page 1
      - Last `end_pages` pages
      - `window` pages on each side of the current page
      - '...' for any gap larger than 1 (single-page gaps are filled in directly)

    Examples (window=3, end_pages=3, num_pages=100):
      current=1  → [1, 2, 3, 4, '...', 98, 99, 100]
      current=50 → [1, '...', 47, 48, 49, 50, 51, 52, 53, '...', 98, 99, 100]
      current=99 → [1, '...', 96, 97, 98, 99, 100]
    """
    num_pages = page_obj.paginator.num_pages
    current = page_obj.number

    if num_pages <= 1:
        return []

    must_show = set()
    must_show.add(1)

    for p in range(max(1, num_pages - end_pages + 1), num_pages + 1):
        must_show.add(p)

    for p in range(max(1, current - window), min(num_pages, current + window) + 1):
        must_show.add(p)

    result = []
    prev = None
    for p in sorted(must_show):
        if prev is not None:
            gap = p - prev
            if gap == 2:
                result.append(prev + 1)   # fill single-page gaps
            elif gap > 2:
                result.append('...')
        result.append(p)
        prev = p

    return result
