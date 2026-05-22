import json
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..decorators import school_only
from ..forms import SalaryPaymentForm
from ..models import MONTH_CHOICES, SalaryPayment, SchoolProfile, Teacher
from ..services.salary_service import build_salary_dashboard_rows, compute_salary_total
from ..session_utils import MONTH_TO_CAL


@school_only
def salary_dashboard(request):
    school = request.user.school
    profile = SchoolProfile.get_for_school(school)
    session = profile.current_academic_session

    q = request.GET.get('q', '').strip()
    pay_status = request.GET.get('pay_status', '')

    teachers = Teacher.objects.filter(school=school, academic_session=session).order_by('name')
    if q:
        teachers = teachers.filter(Q(name__icontains=q) | Q(employee_id__icontains=q))

    rows = build_salary_dashboard_rows(teachers, school, profile, session)

    if pay_status == 'paid':
        rows = [r for r in rows if r['is_paid_up']]
    elif pay_status == 'pending':
        rows = [r for r in rows if not r['is_paid_up']]

    total_due_all = sum(r['total_salary_due'] for r in rows)
    total_paid_all = sum(r['total_paid'] for r in rows)
    total_pending_all = max(total_due_all - total_paid_all, Decimal('0.00'))

    paginator = Paginator(rows, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'school/salary/salary_dashboard.html', {
        'rows': page_obj,
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1,
        'selected_q': q,
        'selected_pay_status': pay_status,
        'total_teachers': len(rows),
        'total_due_all': total_due_all,
        'total_paid_all': total_paid_all,
        'total_pending_all': total_pending_all,
    })


@school_only
def salary_pay(request):
    school = request.user.school
    profile = SchoolProfile.get_for_school(school)
    session = profile.current_academic_session
    teacher_id = request.GET.get('teacher_id') or request.POST.get('teacher')

    if request.method == 'POST':
        form = SalaryPaymentForm(request.POST, school=school, session=session)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.school = school
            payment.paid_by = request.user
            payment.academic_session = session
            teacher = form.cleaned_data['teacher']
            months = form.cleaned_data['payment_months']
            payment.amount_paid = compute_salary_total(teacher, months, session)
            payment.save()
            messages.success(request, f'Salary paid for {teacher.name} — {payment.get_payment_months_display()}.')
            return redirect('salary_dashboard')
    else:
        form = SalaryPaymentForm(school=school, session=session)
        if teacher_id:
            try:
                form.fields['teacher'].initial = int(teacher_id)
            except (ValueError, TypeError):
                pass

    today = timezone.localdate()
    session_start_year = int(session[:4]) if session and len(session) >= 4 else date.today().year
    cutoff_date = date(today.year, today.month, 1)

    available_month_choices = [
        (v, l) for v, l in MONTH_CHOICES
        if date(
            session_start_year if MONTH_TO_CAL.get(v, 1) >= 4 else session_start_year + 1,
            MONTH_TO_CAL.get(v, 1), 1
        ) <= cutoff_date
    ]

    unpaid_months = None
    selected_teacher = None
    month_amounts = {}
    if teacher_id:
        try:
            selected_teacher = Teacher.objects.get(pk=teacher_id, school=school)
            paid_set = set()
            for ml in SalaryPayment.objects.filter(
                school=school, teacher=selected_teacher, academic_session=session,
            ).values_list('payment_months', flat=True):
                paid_set.update(ml or [])

            joining_date = selected_teacher.joining_date
            joining_month_start = date(joining_date.year, joining_date.month, 1)
            unpaid_months = []

            for v, l in MONTH_CHOICES:
                if v in paid_set:
                    continue
                cal_m = MONTH_TO_CAL.get(v, 1)
                m_year = session_start_year if cal_m >= 4 else session_start_year + 1
                month_start = date(m_year, cal_m, 1)
                if month_start < joining_month_start or month_start > cutoff_date:
                    continue
                if month_start == joining_month_start:
                    import calendar as cal_mod
                    total_days = cal_mod.monthrange(m_year, cal_m)[1]
                    worked_days = total_days - joining_date.day + 1
                    ratio = Decimal(worked_days) / Decimal(total_days)
                    amount = (selected_teacher.monthly_salary * ratio).quantize(Decimal('0.01'))
                    unpaid_months.append((v, f'{l} ({worked_days}/{total_days} days — prorated)', amount, round(float(ratio), 6)))
                    month_amounts[v] = float(amount)
                else:
                    amount = (selected_teacher.monthly_salary or Decimal('0')).quantize(Decimal('0.01'))
                    unpaid_months.append((v, l, amount, 1.0))
                    month_amounts[v] = float(amount)
        except Teacher.DoesNotExist:
            pass

    salary_history = []
    if selected_teacher:
        salary_history = SalaryPayment.objects.filter(
            school=school, teacher=selected_teacher, academic_session=session,
        ).select_related('teacher').order_by('-payment_date')

    return render(request, 'school/salary/salary_form.html', {
        'form': form,
        'selected_teacher': selected_teacher,
        'unpaid_months': unpaid_months,
        'month_choices': available_month_choices,
        'month_amounts_json': json.dumps(month_amounts),
        'salary_history': salary_history,
        'session': session,
    })


@school_only
def salary_detail(request, pk):
    payment = get_object_or_404(SalaryPayment, pk=pk, school=request.user.school)
    return render(request, 'school/salary/salary_detail.html', {'payment': payment})
