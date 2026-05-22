from functools import wraps
from django.shortcuts import redirect


def super_only(fn):
    """Restrict view to authenticated superusers only."""
    @wraps(fn)
    def wrap(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_super():
            return redirect('login')
        return fn(request, *args, **kwargs)
    return wrap


def school_only(fn):
    """Restrict view to authenticated school admins bound to the current tenant."""
    @wraps(fn)
    def wrap(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.is_super():
            return redirect('super_dashboard')
        if not request.user.school_id:
            return redirect('login')
        tenant = getattr(request, 'tenant', None)
        if tenant is not None and request.user.school_id != tenant.pk:
            user_school = request.user.school
            if user_school and user_school.subdomain:
                return redirect(user_school.get_tenant_url() + '/school/')
            return redirect('login')
        return fn(request, *args, **kwargs)
    return wrap
