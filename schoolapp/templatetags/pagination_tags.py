from django import template

register = template.Library()


@register.simple_tag
def smart_page_range(page_obj, window=3, end_pages=3):
    """
    Return a list of page numbers and '...' ellipsis markers for smart pagination.

    Algorithm:
      - Always show page 1.
      - Always show the last `end_pages` pages.
      - Always show `window` pages on each side of the current page.
      - Insert '...' wherever there is a gap larger than 1 between adjacent shown pages.
      - If the gap is exactly 1 (a single missing page) just show that page instead of '...'

    Examples (window=3, end_pages=3, num_pages=100):
      current=1  → [1, 2, 3, 4, '...', 98, 99, 100]
      current=50 → [1, '...', 47, 48, 49, 50, 51, 52, 53, '...', 98, 99, 100]
      current=99 → [1, '...', 96, 97, 98, 99, 100]
    """
    num_pages = page_obj.paginator.num_pages
    current = page_obj.number

    if num_pages <= 1:
        return []

    # Collect the page numbers we must show
    must_show = set()

    # First page
    must_show.add(1)

    # Last end_pages pages
    for p in range(max(1, num_pages - end_pages + 1), num_pages + 1):
        must_show.add(p)

    # Window around the current page
    for p in range(max(1, current - window), min(num_pages, current + window) + 1):
        must_show.add(p)

    sorted_pages = sorted(must_show)

    # Build result list with '...' inserted for gaps > 1
    result = []
    prev = None
    for p in sorted_pages:
        if prev is not None:
            gap = p - prev
            if gap == 2:
                # Only one page is missing — just show it rather than '...'
                result.append(prev + 1)
            elif gap > 2:
                result.append('...')
        result.append(p)
        prev = p

    return result
