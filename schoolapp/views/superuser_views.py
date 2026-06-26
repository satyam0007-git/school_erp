from decimal import Decimal

from django.conf import settings as django_settings
from django.contrib import messages
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..decorators import super_only
from ..logging_utils import log_activity_event
from ..forms import SuperUserSettingsForm
from ..models import (
    FeePayment, FeeStructure, School, SchoolBillingPayment, SchoolProfile,
    SchoolSessionRecord, Student, SuperUserSettings, User, MONTH_CHOICES,
)
from ..queries.superuser_queries import (
    get_active_student_counts_by_school_session,
    get_all_school_profiles,
    get_all_session_records,
    get_all_student_counts_by_school_session,
    get_school_billed_sessions,
)
from ..services.billing_service import (
    build_fee_dashboard_rows,
    build_superuser_dashboard_rows,
    get_billing_period_info,
    get_school_billing_months,
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
    current_session = su_default_session or profile.current_academic_session
    fee_per_student = school.fee_per_student

    is_current_profile_session = (current_session == profile.current_academic_session)
    if is_current_profile_session:
        num_students = Student.objects.filter(school=school, status=Student.STATUS_ACTIVE).count()
    else:
        num_students = Student.objects.filter(school=school, academic_session=current_session).count()
        if num_students == 0:
            num_students = Student.objects.filter(school=school, status=Student.STATUS_ACTIVE).count()

    available_sessions = sorted(
        {profile.current_academic_session}
        | set(SchoolBillingPayment.objects.filter(school=school).values_list('academic_session', flat=True).distinct())
        | set(SchoolSessionRecord.objects.filter(school=school).values_list('academic_session', flat=True)),
        reverse=True,
    )

    all_billing_months = get_school_billing_months(school, current_session)

    regular_month_students = {}
    adjustment_month_students = {}
    all_session_payments = SchoolBillingPayment.objects.filter(school=school, academic_session=current_session)
    for bp in all_session_payments:
        for m in (bp.payment_months or []):
            m = str(m)
            if bp.is_adjustment:
                adjustment_month_students[m] = adjustment_month_students.get(m, 0) + bp.num_students
            else:
                regular_month_students[m] = regular_month_students.get(m, 0) + bp.num_students

    paid_months = set(regular_month_students.keys())
    unpaid_months = [(val, label) for val, label in all_billing_months if val not in paid_months]

    adjustment_rows = []
    total_adjustment_due = Decimal('0.00')
    for token, label in all_billing_months:
        if token in paid_months:
            covered = regular_month_students.get(token, 0) + adjustment_month_students.get(token, 0)
            deficit = num_students - covered
            if deficit > 0:
                adj_amt = fee_per_student * deficit
                adjustment_rows.append({'token': token, 'label': label, 'covered': covered, 'deficit': deficit, 'amount': adj_amt})
                total_adjustment_due += adj_amt

    if request.method == 'POST':
        payment_date = request.POST.get('payment_date')
        payment_type = request.POST.get('payment_type', 'regular')

        if payment_type == 'adjustment':
            adj_by_token = {r['token']: r for r in adjustment_rows}
            selected = [m for m in request.POST.getlist('adjustment_months') if m in adj_by_token]
            if payment_date and selected:
                amount_paid = sum(adj_by_token[m]['amount'] for m in selected)
                delta = max(adj_by_token[m]['deficit'] for m in selected)
                month_labels = ', '.join(adj_by_token[m]['label'] for m in selected)
                SchoolBillingPayment.objects.create(
                    school=school, academic_session=current_session,
                    payment_date=payment_date, num_students=delta,
                    fee_per_student=fee_per_student, payment_months=selected,
                    amount_paid=amount_paid, is_adjustment=True,
                    note=f'Adjustment for {delta} additional student(s): {month_labels}',
                )
                log_activity_event(
                    request,
                    module='superuser',
                    action='billing_payment_create',
                    details={'school_id': school.pk, 'school_name': school.name, 'payment_type': 'adjustment', 'amount_paid': str(amount_paid), 'months': selected},
                )
                messages.success(request, f'Adjustment of ₹{amount_paid} recorded for {school.name}.')
                return redirect('super_school_fee_dashboard')
        else:
            valid_tokens = {val for val, _ in all_billing_months}
            selected = [m for m in request.POST.getlist('payment_months') if m in valid_tokens and m not in paid_months]
            if payment_date and selected:
                amount_paid = fee_per_student * num_students * len(selected)
                SchoolBillingPayment.objects.create(
                    school=school, academic_session=current_session,
                    payment_date=payment_date, num_students=num_students,
                    fee_per_student=fee_per_student, payment_months=selected,
                    amount_paid=amount_paid,
                )
                log_activity_event(
                    request,
                    module='superuser',
                    action='billing_payment_create',
                    details={'school_id': school.pk, 'school_name': school.name, 'payment_type': 'regular', 'amount_paid': str(amount_paid), 'months': selected},
                )
                messages.success(request, f'Payment of ₹{amount_paid} recorded for {school.name} ({current_session}).')
                return redirect('super_school_fee_dashboard')

    billing_history = all_session_payments.order_by('-payment_date')
    total_billed = billing_history.aggregate(t=Sum('amount_paid'))['t'] or Decimal('0.00')

    return render(request, 'superuser/collect_fee.html', {
        'school': school,
        'num_students': num_students,
        'fee_per_student': fee_per_student,
        'per_month_amount': fee_per_student * num_students,
        'unpaid_months': unpaid_months,
        'adjustment_rows': adjustment_rows,
        'total_adjustment_due': total_adjustment_due,
        'billing_history': billing_history,
        'total_billed': total_billed,
        'total_months': len(all_billing_months),
        'paid_count': len(all_billing_months) - len(unpaid_months),
        'current_session': current_session,
        'billing_start': all_billing_months[0][1] if all_billing_months else '',
        'billing_end': all_billing_months[-1][1] if all_billing_months else '',
        'available_sessions': available_sessions,
        'su_default_session': su_default_session,
    })


@super_only
def super_promote_school(request, pk):
    if request.method == 'POST':
        school = get_object_or_404(School, pk=pk)
        profile = SchoolProfile.get_for_school(school)
        current_session = profile.current_academic_session
        try:
            start_year = int(current_session.split('-')[0])
        except (ValueError, IndexError):
            start_year = get_session_start_year(timezone.localdate(), profile.session_start_month)
        next_session = format_academic_session(start_year + 1)

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
            if not request.FILES.get('logo'):
                instance.logo = settings_obj.logo
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

        if not name or not password or not username:
            messages.error(request, 'School name, username and password are required.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" is already taken.')
        else:
            valid_months = {m for m, _ in MONTH_CHOICES}
            billing_start = request.POST.get('billing_start_month', 'april')
            billing_end = request.POST.get('billing_end_month', 'march')
            session = request.POST.get('current_academic_session', session_choices[0][0])
            if billing_start not in valid_months:
                billing_start = 'april'
            if billing_end not in valid_months:
                billing_end = 'march'

            subdomain = request.POST.get('subdomain', '').strip().lower()
            if subdomain and School.objects.filter(subdomain=subdomain).exists():
                messages.error(request, f'Subdomain "{subdomain}" is already taken.')
                return render(request, 'superuser/school_add.html', {
                    'session_choices': session_choices, 'month_choices': MONTH_CHOICES,
                    'default_session': default_session,
                })

            school = School.objects.create(
                name=name, subdomain=subdomain or None,
                phone=request.POST.get('phone', ''), email=request.POST.get('email', ''),
                address=request.POST.get('address', ''),
                fee_per_student=request.POST.get('fee_per_student') or 0,
                logo=request.FILES.get('logo'),
                motto=request.POST.get('motto', '').strip(),
                theme_color=request.POST.get('theme_color', '#0f766e').strip(),
                campus_image=request.FILES.get('campus_image'),
                campus_image2=request.FILES.get('campus_image2'),
                campus_image3=request.FILES.get('campus_image3'),
            )
            SchoolProfile.objects.create(
                school=school, current_academic_session=session,
                billing_start_month=billing_start, billing_end_month=billing_end,
            )
            profile = SchoolProfile.objects.get(school=school)
            SchoolSessionRecord.objects.create(
                school=school, academic_session=session,
                session_start_month=profile.session_start_month,
                session_end_month=profile.session_end_month,
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
        }
        if extra:
            ctx.update(extra)
        return render(request, 'superuser/school_form.html', ctx)

    if request.method == 'POST':
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
        school.theme_color = request.POST.get('theme_color', '#0f766e').strip()
        school.is_active = 'is_active' in request.POST
        school.fee_per_student = request.POST.get('fee_per_student') or 0
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

        old_session = profile.current_academic_session
        new_session = request.POST.get('current_academic_session', old_session)
        billing_start = request.POST.get('billing_start_month', profile.billing_start_month)
        billing_end = request.POST.get('billing_end_month', profile.billing_end_month)
        if billing_start not in valid_months:
            billing_start = 'april'
        if billing_end not in valid_months:
            billing_end = 'march'
        profile.current_academic_session = new_session
        profile.billing_start_month = billing_start
        profile.billing_end_month = billing_end
        profile.save()

        if old_session != new_session:
            SchoolSessionRecord.objects.filter(school=school, academic_session=old_session).delete()
        SchoolSessionRecord.objects.update_or_create(
            school=school, academic_session=new_session,
            defaults={
                'session_start_month': profile.session_start_month,
                'session_end_month': profile.session_end_month,
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
