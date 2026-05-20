from django.db.utils import OperationalError, ProgrammingError

from .models import SuperUserSettings


def software_branding(request):
    """Expose software branding and the current school tenant in all templates."""
    try:
        app_settings = SuperUserSettings.get_solo()
    except (OperationalError, ProgrammingError):
        app_settings = None
    return {
        'app_settings': app_settings,
        # The School object resolved by TenantMiddleware (None on the main domain)
        'current_tenant': getattr(request, 'tenant', None),
    }
