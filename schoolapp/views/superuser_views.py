from decimal import Decimal

from django.conf import settings as django_settings
from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..decorators import super_only
from ..logging_utils import log_activity_event
from ..forms import SuperUserSettingsForm
from ..models import (
    FeePayment, FeeStructure, School, SchoolBillingPayment, SchoolProfile,
    SchoolSessionRecord, Student, SuperUserSettings, User, MONTH_CHOICES, YearlyPlan,
)
from ..queries.superuser_queries import (
    get_all_school_profiles,
    get_all_session_records,
    get_all_student_counts_by_school_session,
)
from ..services.billing_service import (
    build_fee_dashboard_rows,
    build_superuser_dashboard_rows,
    get_formatted_billing_period,
)
from ..session_utils import (
    format_academic_session, get_academic_session_choices, get_current_academic_session,
    get_session_start_year,
)


@super_only
def super_dashboard(request):
    su_settings = SuperUserSettings.get_solo()
    system_session = get_current_academic_session()
    default_session = su_settings.default_session or system_session

    profiles = get_all_school_profiles()
    session_records = get_all_session_records()
    student_counts = get_all_student_counts_by_school_session()

    rows = build_superuser_dashboard_rows(
        School.objects.all(), profiles, session_records, student_counts, system_session,
    )
    unique_sessions = sorted({r['session'] for r in rows if r['session'] != '—'}, reverse=True)
    total_active = sum(r['student_count'] for r in rows if r['session'] == default_session)

    return render(request, 'superuser/dashboard.html', {
        'rows': rows,
        'total_schools': School.objects.count(),
        'total_students': total_active,
        'active_schools': School.objects.filter(is_active=True).count(),
        'inactive_schools': School.objects.filter(is_active=False).count(),
        'session_options': unique_sessions,
        'system_session': system_session,
        'default_session': default_session,
    })


@super_only
def super_school_fee_dashboard(request):
    su_settings = SuperUserSettings.get_solo()
    system_session = get_current_academic_session()
    default_session = su_settings.default_session or system_session

    profiles = get_all_school_profiles()
    session_records = get_all_session_records()
    student_counts = get_all_student_counts_by_school_session()

    rows, total_monthly, total_collected = build_fee_dashboard_rows(
        School.objects.filter(is_active=True),
        profiles, session_records, student_counts, default_session,
    )
    total_pending = max(total_monthly - total_collected, Decimal('0.00'))
    session_options = sorted({r['session'] for r in rows if r.get('session')}, reverse=True)

    return render(request, 'superuser/school_fee_dashboard.html', {
        'rows': rows,
        'total_monthly': total_monthly,
        'total_collected': total_collected,
        'total_pending': total_pending,
        'session_options': session_options,
        'default_session': default_session,
    })


@super_only
def super_collect_fee(request, school_pk):
    school = get_object_or_404(School, pk=school_pk)
    profile = SchoolProfile.get_for_school(school)
    su_settings = SuperUserSettings.get_solo()
    system_session = get_current_academic_session()
    su_default_session = su_settings.default_session or system_session
    current_session = request.GET.get('session') or su_default_session or profile.current_academic_session
    is_current = (current_session == profile.current_academic_session)

    all_session_payments = SchoolBillingPayment.objects.filter(school=school, academic_session=current_session)
    total_paid = all_session_payments.aggregate(t=Sum('amount_paid'))['t'] or Decimal('0.00')

    if is_current:
        total_due = school.subscription_amount
    else:
        total_due = total_paid
    billing_period = get_formatted_billing_period(school, current_session)

    balance = max(total_due - total_paid, Decimal('0.00'))

    if request.method == 'POST':
        payment_date = request.POST.get('payment_date')
        amount_paid = Decimal(request.POST.get('amount_paid', '0.00'))
        note = request.POST.get('note', '').strip()

        if payment_date and amount_paid > 0:
            SchoolBillingPayment.objects.create(
                school=school, academic_session=current_session,
                payment_date=payment_date, num_students=0,
                fee_per_student=school.subscription_amount, payment_months=['annual_subscription'],
                amount_paid=amount_paid, note=note,
            )
            log_activity_event(
                request,
                module='superuser',
                action='billing_payment_create',
                details={
                    'school_id': school.pk,
                    'school_name': school.name,
                    'payment_type': 'annual_subscription',
                    'amount_paid': str(amount_paid),
                    'session': current_session,
                },
            )
            messages.success(request, f'Subscription payment of ₹{amount_paid} recorded for {school.name}.')
            return redirect('super_school_fee_dashboard')

    available_sessions = sorted(
        {profile.current_academic_session}
        | set(SchoolBillingPayment.objects.filter(school=school).values_list('academic_session', flat=True).distinct())
        | set(SchoolSessionRecord.objects.filter(school=school).values_list('academic_session', flat=True)),
        reverse=True,
    )

    billing_history = all_session_payments.order_by('-payment_date')

    return render(request, 'superuser/collect_fee.html', {
        'school': school,
        'yearly_plan': school.yearly_plan,
        'subscription_amount': school.subscription_amount,
        'subscription_start_date': school.subscription_start_date,
        'subscription_end_date': school.subscription_end_date,
        'total_due': total_due,
        'total_paid': total_paid,
        'balance': balance,
        'is_paid_up': balance <= Decimal('0.00'),
        'billing_history': billing_history,
        'current_session': current_session,
        'billing_period': billing_period,
        'available_sessions': available_sessions,
        'is_current': is_current,
    })


@super_only
def super_renew_school(request, pk):
    if request.method == 'POST':
        school = get_object_or_404(School, pk=pk)
        profile = SchoolProfile.get_for_school(school)
        current_session = profile.current_academic_session
        
        subscription_years = school.get_subscription_years()

        try:
            start_year = int(current_session.split('-')[0])
        except (ValueError, IndexError):
            start_year = get_session_start_year(timezone.localdate(), profile.session_start_month)
        next_session = format_academic_session(start_year + subscription_years)

        if profile.current_academic_session == next_session:
            messages.warning(request, f'{school.name} is already on session {next_session}.')
            return redirect('super_dashboard')

        SchoolSessionRecord.objects.update_or_create(
            school=school, academic_session=next_session,
            defaults={
                'session_start_month': profile.session_start_month,
                'session_end_month': profile.session_end_month,
                'billing_start_month': profile.billing_start_month,
                'billing_end_month': profile.billing_end_month,
            },
        )

        existing = FeeStructure.objects.filter(school_class__school=school, academic_session=current_session)
        new_structures = [
            FeeStructure(
                school_class=fs.school_class, fee_category=fs.fee_category,
                academic_session=next_session, amount=fs.amount, frequency=fs.frequency,
            )
            for fs in existing
            if not FeeStructure.objects.filter(
                school_class=fs.school_class, fee_category=fs.fee_category, academic_session=next_session,
            ).exists()
        ]
        if new_structures:
            FeeStructure.objects.bulk_create(new_structures)

        # Advance subscription validity period by subscription years
        if school.subscription_start_date:
            try:
                school.subscription_start_date = school.subscription_start_date.replace(year=school.subscription_start_date.year + subscription_years)
            except ValueError:
                school.subscription_start_date = school.subscription_start_date + timezone.timedelta(days=365 * subscription_years)
        if school.subscription_end_date:
            try:
                school.subscription_end_date = school.subscription_end_date.replace(year=school.subscription_end_date.year + subscription_years)
            except ValueError:
                school.subscription_end_date = school.subscription_end_date + timezone.timedelta(days=365 * subscription_years)
        school.save()

        profile.current_academic_session = next_session
        profile.save()
        log_activity_event(
            request,
            module='superuser',
            action='school_renew',
            record_id=school.pk,
            details={'school_name': school.name, 'new_session': next_session, 'copied_fee_structures': len(new_structures)},
        )
        messages.success(request, f'{school.name} renewed to {next_session}. Fee structures copied.')
    return redirect('super_dashboard')


@super_only
def super_settings(request):
    settings_obj = SuperUserSettings.get_solo()
    if request.method == 'POST':
        form = SuperUserSettingsForm(request.POST, request.FILES, instance=settings_obj)
        if form.is_valid():
            instance = form.save(commit=False)
            if not request.FILES.get('logo') and request.POST.get('clear_logo') != '1':
                instance.logo = settings_obj.logo
            elif request.POST.get('clear_logo') == '1':
                instance.logo = None

            # Handle campus image 1
            if not request.FILES.get('campus_image') and request.POST.get('clear_campus_image') != '1':
                instance.campus_image = settings_obj.campus_image
            elif request.POST.get('clear_campus_image') == '1':
                instance.campus_image = None

            # Handle campus image 2
            if not request.FILES.get('campus_image2') and request.POST.get('clear_campus_image2') != '1':
                instance.campus_image2 = settings_obj.campus_image2
            elif request.POST.get('clear_campus_image2') == '1':
                instance.campus_image2 = None

            # Handle campus image 3
            if not request.FILES.get('campus_image3') and request.POST.get('clear_campus_image3') != '1':
                instance.campus_image3 = settings_obj.campus_image3
            elif request.POST.get('clear_campus_image3') == '1':
                instance.campus_image3 = None

            instance.default_session = request.POST.get('default_session', '').strip()
            instance.save()
            settings_obj = SuperUserSettings.get_solo()
            log_activity_event(
                request,
                module='superuser',
                action='settings_update',
                record_id=settings_obj.pk,
                details={'default_session': settings_obj.default_session},
            )
            messages.success(request, 'Settings saved successfully.')
            return redirect('super_settings')
        messages.error(request, 'Could not save settings. Please check the highlighted fields.')
    else:
        form = SuperUserSettingsForm(instance=settings_obj)

    session_choices = get_academic_session_choices(past_years=5, future_years=10)
    saved_session = settings_obj.default_session or ''
    if saved_session and saved_session not in {v for v, _ in session_choices}:
        session_choices.insert(0, (saved_session, saved_session))
    return render(request, 'superuser/settings.html', {
        'form': form,
        'settings_obj': settings_obj,
        'session_choices': session_choices,
        'selected_session': saved_session,
    })


@super_only
def school_add(request):
    session_choices = get_academic_session_choices(past_years=2, future_years=10)
    su_settings = SuperUserSettings.get_solo()
    default_session = su_settings.default_session or session_choices[0][0]

    if request.method == 'POST':
        name = request.POST['name'].strip()
        password = request.POST['password']
        username = request.POST.get('username', '').strip().lower()

        sub_start_str = request.POST.get('subscription_start_date', '').strip()
        sub_end_str = request.POST.get('subscription_end_date', '').strip()

        if not name or not password or not username:
            messages.error(request, 'School name, username and password are required.')
        elif not sub_start_str or not sub_end_str:
            messages.error(request, 'Subscription start date and end date are required.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" is already taken.')
        else:
            from datetime import datetime
            from ..session_utils import CAL_TO_MONTH

            start_dt = None
            if sub_start_str:
                try:
                    start_dt = datetime.strptime(sub_start_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            end_dt = None
            if sub_end_str:
                try:
                    end_dt = datetime.strptime(sub_end_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            if start_dt:
                billing_start = CAL_TO_MONTH[start_dt.month]
                session_start = billing_start
            else:
                billing_start = 'april'
                session_start = 'april'

            if end_dt:
                billing_end = CAL_TO_MONTH[end_dt.month]
                session_end = billing_end
            else:
                billing_end = 'march'
                session_end = 'march'

            if start_dt:
                session = get_current_academic_session(start_dt, session_start)
            else:
                session = default_session

            subdomain = request.POST.get('subdomain', '').strip().lower()
            if subdomain and School.objects.filter(subdomain=subdomain).exists():
                messages.error(request, f'Subdomain "{subdomain}" is already taken.')
                return render(request, 'superuser/school_add.html', {
                    'session_choices': session_choices, 'month_choices': MONTH_CHOICES,
                    'default_session': default_session,
                    'yearly_plans': YearlyPlan.objects.all().order_by('amount'),
                })

            school = School.objects.create(
                name=name, subdomain=subdomain or None,
                phone=request.POST.get('phone', ''), email=request.POST.get('email', ''),
                address=request.POST.get('address', ''),
                fee_per_student=request.POST.get('fee_per_student') or 0,
                yearly_plan_id=request.POST.get('yearly_plan') or None,
                subscription_amount=request.POST.get('subscription_amount') or 0,
                subscription_start_date=request.POST.get('subscription_start_date') or None,
                subscription_end_date=request.POST.get('subscription_end_date') or None,
                logo=request.FILES.get('logo'),
                motto=request.POST.get('motto', '').strip(),
                theme_color=request.POST.get('theme_color', '#2563eb').strip(),
                campus_image=request.FILES.get('campus_image'),
                campus_image2=request.FILES.get('campus_image2'),
                campus_image3=request.FILES.get('campus_image3'),
            )
            SchoolProfile.objects.create(
                school=school, current_academic_session=session,
                session_start_month=session_start, session_end_month=session_end,
                billing_start_month=billing_start, billing_end_month=billing_end,
            )
            profile = SchoolProfile.objects.get(school=school)
            SchoolSessionRecord.objects.create(
                school=school, academic_session=session,
                session_start_month=session_start,
                session_end_month=session_end,
                billing_start_month=billing_start, billing_end_month=billing_end,
            )
            User.objects.create_user(username=username, password=password, role='school_admin', school=school)
            portal_url = school.get_tenant_url() if school.subdomain else '(no subdomain set)'
            log_activity_event(
                request,
                module='superuser',
                action='school_create',
                record_id=school.pk,
                details={'school_name': school.name, 'subdomain': school.subdomain, 'admin_username': username, 'session': session},
            )
            messages.success(request, f'School "{name}" created. Admin: {username}. Portal: {portal_url}')
            return redirect('super_dashboard')

    base_domain = getattr(django_settings, 'TENANT_BASE_DOMAIN', 'localhost')
    return render(request, 'superuser/school_add.html', {
        'session_choices': session_choices, 'month_choices': MONTH_CHOICES,
        'base_domain': base_domain, 'default_session': default_session,
        'yearly_plans': YearlyPlan.objects.all().order_by('amount'),
    })


@super_only
def school_edit(request, pk):
    base_domain = getattr(django_settings, 'TENANT_BASE_DOMAIN', 'localhost')
    school = get_object_or_404(School, pk=pk)
    admin_user = User.objects.filter(school=school, role='school_admin').first()
    profile = SchoolProfile.get_for_school(school)
    session_choices = get_academic_session_choices(past_years=2, future_years=10)
    valid_months = {m for m, _ in MONTH_CHOICES}

    def render_form(extra=None):
        ctx = {
            'school': school, 'admin_user': admin_user, 'base_domain': base_domain,
            'profile': profile, 'session_choices': session_choices, 'month_choices': MONTH_CHOICES,
            'yearly_plans': YearlyPlan.objects.all().order_by('amount'),
        }
        if extra:
            ctx.update(extra)
        return render(request, 'superuser/school_form.html', ctx)

    if request.method == 'POST':
        sub_start_str = request.POST.get('subscription_start_date', '').strip()
        sub_end_str = request.POST.get('subscription_end_date', '').strip()
        if not sub_start_str or not sub_end_str:
            messages.error(request, 'Subscription start date and end date are required.')
            return render_form()

        old_values = {
            'name': school.name,
            'phone': school.phone,
            'email': school.email,
            'address': school.address,
            'is_active': school.is_active,
            'fee_per_student': str(school.fee_per_student),
            'subdomain': school.subdomain,
            'motto': school.motto,
            'theme_color': school.theme_color,
            'current_academic_session': profile.current_academic_session,
            'billing_start_month': profile.billing_start_month,
            'billing_end_month': profile.billing_end_month,
        }
        school.name = request.POST['name']
        school.phone = request.POST.get('phone', '')
        school.email = request.POST.get('email', '')
        school.address = request.POST.get('address', '')
        school.motto = request.POST.get('motto', '').strip()
        school.theme_color = request.POST.get('theme_color', '#2563eb').strip()
        school.is_active = 'is_active' in request.POST
        school.fee_per_student = request.POST.get('fee_per_student') or 0
        school.yearly_plan_id = request.POST.get('yearly_plan') or None
        school.subscription_amount = request.POST.get('subscription_amount') or 0
        school.subscription_start_date = request.POST.get('subscription_start_date') or None
        school.subscription_end_date = request.POST.get('subscription_end_date') or None
        new_logo = request.FILES.get('logo')
        if new_logo:
            school.logo = new_logo
        elif request.POST.get('clear_logo') == '1':
            school.logo = None
        
        new_campus = request.FILES.get('campus_image')
        if new_campus:
            school.campus_image = new_campus
        elif request.POST.get('clear_campus_image') == '1':
            school.campus_image = None

        new_campus2 = request.FILES.get('campus_image2')
        if new_campus2:
            school.campus_image2 = new_campus2
        elif request.POST.get('clear_campus_image2') == '1':
            school.campus_image2 = None

        new_campus3 = request.FILES.get('campus_image3')
        if new_campus3:
            school.campus_image3 = new_campus3
        elif request.POST.get('clear_campus_image3') == '1':
            school.campus_image3 = None

        new_subdomain = request.POST.get('subdomain', '').strip().lower() or None
        if new_subdomain != school.subdomain:
            if new_subdomain and School.objects.filter(subdomain=new_subdomain).exclude(pk=school.pk).exists():
                messages.error(request, f'Subdomain "{new_subdomain}" is already taken.')
                return render_form()
            school.subdomain = new_subdomain
        school.save()
        from datetime import datetime
        from ..session_utils import CAL_TO_MONTH

        old_session = profile.current_academic_session

        start_dt = None
        if sub_start_str:
            try:
                start_dt = datetime.strptime(sub_start_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        end_dt = None
        if sub_end_str:
            try:
                end_dt = datetime.strptime(sub_end_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        if start_dt:
            billing_start = CAL_TO_MONTH[start_dt.month]
            session_start = billing_start
        else:
            billing_start = profile.billing_start_month
            session_start = profile.session_start_month

        if end_dt:
            billing_end = CAL_TO_MONTH[end_dt.month]
            session_end = billing_end
        else:
            billing_end = profile.billing_end_month
            session_end = profile.session_end_month

        if start_dt:
            new_session = get_current_academic_session(start_dt, session_start)
        else:
            new_session = old_session

        profile.current_academic_session = new_session
        profile.session_start_month = session_start
        profile.session_end_month = session_end
        profile.billing_start_month = billing_start
        profile.billing_end_month = billing_end
        profile.save()

        if old_session != new_session:
            SchoolSessionRecord.objects.filter(school=school, academic_session=old_session).delete()
        SchoolSessionRecord.objects.update_or_create(
            school=school, academic_session=new_session,
            defaults={
                'session_start_month': session_start,
                'session_end_month': session_end,
                'billing_start_month': billing_start,
                'billing_end_month': billing_end,
            },
        )

        if admin_user:
            new_username = request.POST.get('admin_username', '').strip()
            new_password = request.POST.get('admin_password', '').strip()
            if new_username and new_username != admin_user.username:
                if User.objects.filter(username=new_username).exclude(pk=admin_user.pk).exists():
                    messages.error(request, 'Admin username already taken.')
                    return render_form()
                admin_user.username = new_username
            if new_password:
                admin_user.set_password(new_password)
            admin_user.save()

        log_activity_event(
            request,
            module='superuser',
            action='school_update',
            record_id=school.pk,
            old_values=old_values,
            new_values={
                'name': school.name,
                'phone': school.phone,
                'email': school.email,
                'address': school.address,
                'motto': school.motto,
                'theme_color': school.theme_color,
                'is_active': school.is_active,
                'fee_per_student': str(school.fee_per_student),
                'subdomain': school.subdomain,
                'current_academic_session': profile.current_academic_session,
                'billing_start_month': profile.billing_start_month,
                'billing_end_month': profile.billing_end_month,
            },
        )
        messages.success(request, 'School updated.')
        return redirect('super_dashboard')

    return render_form()


@super_only
def school_delete(request, pk):
    school = get_object_or_404(School, pk=pk)
    if request.method == 'POST':
        school_snapshot = {'school_id': school.pk, 'school_name': school.name, 'subdomain': school.subdomain}
        FeePayment.objects.filter(school=school).delete()
        FeeStructure.objects.filter(school_class__school=school).delete()
        Student.objects.filter(school=school).delete()
        school.delete()
        log_activity_event(
            request,
            module='superuser',
            action='school_delete',
            record_id=school_snapshot['school_id'],
            details=school_snapshot,
        )
        messages.success(request, 'School deleted.')
        return redirect('super_dashboard')
    return render(request, 'confirm_delete.html', {'name': school.name})


@super_only
def user_add(request):
    if request.method == 'POST':
        username = request.POST['username'].strip()
        password = request.POST['password']
        school_id = request.POST.get('school')
        if not username or not password or not school_id:
            messages.error(request, 'All fields required.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Username taken.')
        else:
            school = get_object_or_404(School, pk=school_id)
            User.objects.create_user(username=username, password=password, role='school_admin', school=school)
            log_activity_event(
                request,
                module='superuser',
                action='user_create',
                details={'username': username, 'school_id': school.pk, 'school_name': school.name, 'role': 'school_admin'},
            )
            messages.success(request, 'User created.')
            return redirect('super_dashboard')
    return redirect('super_dashboard')


@super_only
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        user_snapshot = {'user_id': user.pk, 'username': user.username, 'role': user.role, 'school_id': user.school_id}
        user.delete()
        log_activity_event(
            request,
            module='superuser',
            action='user_delete',
            record_id=user.pk,
            details=user_snapshot,
        )
        messages.success(request, 'Deleted.')
        return redirect('super_dashboard')
    return render(request, 'confirm_delete.html', {'name': user.username})


@super_only
def super_plans_dashboard(request):
    plans = YearlyPlan.objects.all().order_by('amount')
    return render(request, 'superuser/plans_dashboard.html', {
        'plans': plans,
    })


@super_only
def super_plan_add(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        amount = request.POST.get('amount')
        duration_months = request.POST.get('duration_months', 12)
        description = request.POST.get('description', '').strip()

        if not name or not amount:
            messages.error(request, 'Name and amount are required.')
        elif YearlyPlan.objects.filter(name=name).exists():
            messages.error(request, f'Plan with name "{name}" already exists.')
        else:
            plan = YearlyPlan.objects.create(
                name=name, amount=amount,
                duration_months=duration_months, description=description
            )
            log_activity_event(
                request,
                module='superuser',
                action='plan_create',
                record_id=plan.pk,
                details={'name': name, 'amount': str(amount)},
            )
            messages.success(request, f'Yearly plan "{name}" created successfully.')
            return redirect('super_plans_dashboard')

    return render(request, 'superuser/plan_form.html', {
        'title': 'Add Yearly Plan',
    })


@super_only
def super_plan_edit(request, pk):
    plan = get_object_or_404(YearlyPlan, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        amount = request.POST.get('amount')
        duration_months = request.POST.get('duration_months', 12)
        description = request.POST.get('description', '').strip()

        if not name or not amount:
            messages.error(request, 'Name and amount are required.')
        elif YearlyPlan.objects.filter(name=name).exclude(pk=pk).exists():
            messages.error(request, f'Plan with name "{name}" already exists.')
        else:
            old_values = {'name': plan.name, 'amount': str(plan.amount)}
            plan.name = name
            plan.amount = amount
            plan.duration_months = duration_months
            plan.description = description
            plan.save()
            log_activity_event(
                request,
                module='superuser',
                action='plan_update',
                record_id=plan.pk,
                old_values=old_values,
                new_values={'name': name, 'amount': str(amount)},
            )
            messages.success(request, f'Yearly plan "{name}" updated successfully.')
            return redirect('super_plans_dashboard')

    return render(request, 'superuser/plan_form.html', {
        'plan': plan,
        'title': f'Edit Yearly Plan — {plan.name}',
    })


@super_only
def super_plan_delete(request, pk):
    plan = get_object_or_404(YearlyPlan, pk=pk)
    if request.method == 'POST':
        plan_snapshot = {'plan_id': plan.pk, 'name': plan.name, 'amount': str(plan.amount)}
        plan.delete()
        log_activity_event(
            request,
            module='superuser',
            action='plan_delete',
            record_id=plan_snapshot['plan_id'],
            details=plan_snapshot,
        )
        messages.success(request, f'Yearly plan "{plan_snapshot["name"]}" deleted.')
        return redirect('super_plans_dashboard')
    return render(request, 'confirm_delete.html', {'name': plan.name})
