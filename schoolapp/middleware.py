from django.conf import settings
from django.http import Http404
from django.utils import timezone

from .logging_utils import (
    get_request_context,
    log_request_event,
    log_unhandled_exception,
    reset_request_context,
    set_request_context,
)
from .models import School


def get_subdomain(request):
    """
    Extract the leftmost subdomain from the request host.
    Returns None for the bare base domain or any unrecognised host.

    Examples (base = 'erpdomain.com'):
        erpdomain.com          → None
        school1.erpdomain.com  → 'school1'
        a.b.erpdomain.com      → None  (multi-level subdomain rejected)

    In development (base = 'localhost'):
        localhost              → None
        school1.localhost      → 'school1'
    """
    host = request.get_host().split(':')[0].lower()
    base = getattr(settings, 'TENANT_BASE_DOMAIN', 'localhost').lower()

    if host == base:
        return None

    if host.endswith('.' + base):
        sub = host[:-(len(base) + 1)]
        if sub and '.' not in sub:
            return sub

    return None


class TenantMiddleware:
    """
    Resolves the current school tenant from the request subdomain and
    attaches it to ``request.tenant``.

    * Main domain (no subdomain)  → ``request.tenant = None``
    * Known active subdomain      → ``request.tenant = <School instance>``
    * Unknown / inactive subdomain → raises Http404
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        subdomain = get_subdomain(request)

        if subdomain is None:
            request.tenant = None
        else:
            try:
                request.tenant = School.objects.get(subdomain=subdomain, is_active=True)
            except School.DoesNotExist:
                raise Http404(
                    f"No active school is registered for subdomain '{subdomain}'."
                )

        return self.get_response(request)


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_request_context(request)
        started_at = timezone.now()
        try:
            return self.get_response(request)
        except Exception as exc:
            if getattr(request, 'tenant', None) is not None:
                log_request_event(request, exc=exc, started_at=started_at)
                log_unhandled_exception(request, exc)
            raise
        finally:
            reset_request_context(token)
