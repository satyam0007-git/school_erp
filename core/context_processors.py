from django.db.utils import OperationalError, ProgrammingError

from .models import SuperUserSettings, SchoolProfile


def software_branding(request):
    """Expose branding, tenant, and active session for school users in all templates."""
    try:
        app_settings = SuperUserSettings.get_solo()
    except (OperationalError, ProgrammingError):
        app_settings = None

    ctx = {
        'app_settings': app_settings,
        'current_tenant': getattr(request, 'tenant', None),
    }

    # Inject active session for authenticated school users
    try:
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and hasattr(user, 'school') and user.school:
            profile = SchoolProfile.get_for_school(user.school)
            ctx['active_session'] = profile.current_academic_session
            ctx['active_session_start_month'] = profile.session_start_month
            ctx['active_session_end_month'] = profile.session_end_month
    except Exception:
        pass

    return ctx
