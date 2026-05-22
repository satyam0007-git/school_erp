from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..decorators import school_only
from ..forms import TeacherForm
from ..models import SchoolClass, SchoolProfile, Teacher
from ..session_utils import get_current_academic_session


@school_only
def teacher_list(request):
    school = request.user.school
    profile = SchoolProfile.get_for_school(school)
    session = profile.current_academic_session

    q = request.GET.get('q', '').strip()
    class_id = request.GET.get('class', '')
    status_filter = request.GET.get('status', '')
    employment_filter = request.GET.get('employment', '')

    teachers = Teacher.objects.filter(school=school, academic_session=session).select_related('class_teacher_of')
    if q:
        teachers = teachers.filter(
            Q(name__icontains=q) | Q(employee_id__icontains=q) |
            Q(phone__icontains=q) | Q(subjects_taught__icontains=q)
        )
    if class_id:
        teachers = teachers.filter(class_teacher_of_id=class_id)
    if status_filter:
        teachers = teachers.filter(status=status_filter)
    if employment_filter:
        teachers = teachers.filter(employment_type=employment_filter)

    paginator = Paginator(teachers.order_by('name'), 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'school/teachers/teacher_list.html', {
        'teachers': page_obj,
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1,
        'classes': SchoolClass.objects.filter(school=school),
        'selected_class': class_id,
        'selected_q': q,
        'selected_status': status_filter,
        'selected_employment': employment_filter,
        'total_active': Teacher.objects.filter(school=school, status=Teacher.STATUS_ACTIVE, academic_session=session).count(),
        'total_inactive': Teacher.objects.filter(school=school, status__in=[Teacher.STATUS_INACTIVE, Teacher.STATUS_RESIGNED], academic_session=session).count(),
        'total_filtered': teachers.count(),
        'status_choices': Teacher.STATUS_CHOICES,
        'employment_choices': Teacher.EMPLOYMENT_CHOICES,
    })


@school_only
def teacher_create(request):
    school = request.user.school
    profile = SchoolProfile.get_for_school(school)
    form = TeacherForm(request.POST or None, school=school)
    if request.method == 'POST' and form.is_valid():
        teacher = form.save(commit=False)
        teacher.school = school
        teacher.academic_session = profile.current_academic_session
        teacher.save()
        messages.success(request, f'Teacher {teacher.name} ({teacher.employee_id}) added successfully.')
        return redirect('teacher_list')
    return render(request, 'school/teachers/teacher_form.html', {
        'form': form, 'title': 'Add Teacher', 'submit_label': 'Add Teacher',
    })


@school_only
def teacher_edit(request, pk):
    school = request.user.school
    teacher = get_object_or_404(Teacher, pk=pk, school=school)
    form = TeacherForm(request.POST or None, instance=teacher, school=school)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'{teacher.name} updated successfully.')
        return redirect('teacher_list')
    return render(request, 'school/teachers/teacher_form.html', {
        'form': form, 'teacher': teacher,
        'title': f'Edit — {teacher.name}', 'submit_label': 'Save Changes',
    })


@school_only
def teacher_delete(request, pk):
    school = request.user.school
    teacher = get_object_or_404(Teacher, pk=pk, school=school)
    if request.method == 'POST':
        name = teacher.name
        teacher.delete()
        messages.success(request, f'Teacher {name} deleted.')
        return redirect('teacher_list')
    return render(request, 'school/teachers/teacher_confirm_delete.html', {'teacher': teacher})


@school_only
def teacher_promote(request, pk):
    if request.method != 'POST':
        return redirect('teacher_list')
    school = request.user.school
    teacher = get_object_or_404(Teacher, pk=pk, school=school, status=Teacher.STATUS_ACTIVE)

    try:
        pct = float(request.POST.get('increment_pct', ''))
        if pct <= 0 or pct > 100:
            raise ValueError
    except (ValueError, TypeError):
        messages.error(request, 'Invalid increment percentage.')
        return redirect('teacher_list')

    old_salary = teacher.monthly_salary
    old_session = teacher.academic_session
    increment = (old_salary * Decimal(str(pct)) / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    teacher.monthly_salary = old_salary + increment

    try:
        start_year = int(old_session.split('-')[0])
        teacher.academic_session = f"{start_year + 1}-{(start_year + 2) % 100:02d}"
    except (ValueError, IndexError, AttributeError):
        teacher.academic_session = get_current_academic_session(timezone.localdate())

    teacher.save(update_fields=['monthly_salary', 'academic_session', 'updated_at'])
    messages.success(
        request,
        f'{teacher.name} promoted — {old_session} → {teacher.academic_session}, '
        f'salary ₹{old_salary} → ₹{teacher.monthly_salary} (+{pct}%).',
    )
    return redirect('teacher_list')
