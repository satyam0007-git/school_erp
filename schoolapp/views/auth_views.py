from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from ..decorators import school_only
from ..models import SuperUserSettings


def login_view(request):
    tenant = getattr(request, 'tenant', None)

    if request.user.is_authenticated:
        if request.user.is_super():
            return redirect('super_dashboard')
        if tenant and request.user.school_id != tenant.pk:
            user_school = request.user.school
            if user_school and user_school.subdomain:
                return redirect(user_school.get_tenant_url() + '/school/')
        return redirect('school_dashboard')

    if request.method == 'POST':
        user = authenticate(request, username=request.POST['username'], password=request.POST['password'])
        if user:
            if tenant:
                if user.is_super():
                    messages.error(request, 'Super admin must log in from the main portal.')
                elif user.school_id != tenant.pk:
                    messages.error(request, 'These credentials do not belong to this school portal.')
                else:
                    login(request, user)
                    return redirect('school_dashboard')
            else:
                login(request, user)
                return redirect('dashboard')
        else:
            messages.error(request, 'Invalid credentials.')

    app_settings = SuperUserSettings.get_solo()
    template = 'school/login.html' if tenant else 'login.html'
    return render(request, template, {'settings': app_settings, 'tenant': tenant})


@login_required
def dashboard(request):
    if request.user.is_super():
        return redirect('super_dashboard')
    return redirect('school_dashboard')


def logout_view(request):
    logout(request)
    return redirect('login')


@school_only
def school_dashboard(request):
    return redirect('student_list')
