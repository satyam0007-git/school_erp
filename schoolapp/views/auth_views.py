from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from ..decorators import school_only
from ..models import SuperUserSettings


def login_view(request):
    tenant = getattr(request, 'tenant', None)

    # Redirect if already logged in
    if request.session.get('student_id'):
        return redirect('student_dashboard')

    if request.user.is_authenticated:
        if request.user.is_super():
            return redirect('super_dashboard')
        if tenant and request.user.school_id != tenant.pk:
            user_school = request.user.school
            if user_school and user_school.subdomain:
                return redirect(user_school.get_tenant_url() + '/school/')
        return redirect('school_dashboard')

    active_tab = 'staff'

    if request.method == 'POST':
        login_type = request.POST.get('login_type', 'staff')
        if login_type == 'student':
            active_tab = 'student'
            dob_input = request.POST.get('dob', '').strip()
            student_search = request.POST.get('student_search', '').strip()
            
            from datetime import datetime
            dob_date = None
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
                try:
                    dob_date = datetime.strptime(dob_input, fmt).date()
                    break
                except ValueError:
                    continue

            if not student_search or not dob_date:
                messages.error(request, 'Please enter a valid Name/Admission Number and Date of Birth.')
            else:
                from django.db.models import Q
                from ..models import Student
                
                if not tenant:
                    messages.error(request, 'Students must log in through their school portal subdomain.')
                else:
                    student = Student.objects.filter(
                        school=tenant,
                        date_of_birth=dob_date
                    ).exclude(status='inactive').filter(
                        Q(roll_number=student_search) | Q(name__iexact=student_search)
                    ).first()
                    
                    if student:
                        logout(request)
                        request.session['student_id'] = student.id
                        return redirect('student_dashboard')
                    else:
                        messages.error(request, 'Invalid Admission Number/Name or Date of Birth.')
        else:
            active_tab = 'staff'
            user = authenticate(request, username=request.POST['username'], password=request.POST['password'])
            if user:
                if tenant:
                    if user.is_super():
                        messages.error(request, 'Super admin must log in from the main portal.')
                    elif user.school_id != tenant.pk:
                        messages.error(request, 'These credentials do not belong to this school portal.')
                    else:
                        request.session.pop('student_id', None)
                        login(request, user)
                        return redirect('school_dashboard')
                else:
                    request.session.pop('student_id', None)
                    login(request, user)
                    return redirect('dashboard')
            else:
                messages.error(request, 'Invalid credentials.')

    # Public Notifications
    public_notifications = []
    if tenant:
        from django.db.models import Q
        from ..models import Notification
        today = timezone.localdate()
        public_notifications = Notification.objects.filter(
            school=tenant,
            visibility=Notification.VISIBILITY_PUBLIC,
            is_published=True,
            publish_date__lte=today
        ).filter(
            Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
        )[:5]

    app_settings = SuperUserSettings.get_solo()
    template = 'school/login.html' if tenant else 'login.html'
    return render(request, template, {
        'settings': app_settings,
        'tenant': tenant,
        'public_notifications': public_notifications,
        'active_tab': active_tab
    })


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

