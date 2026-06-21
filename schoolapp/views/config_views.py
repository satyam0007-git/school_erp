from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..decorators import school_only
from ..models import (
    ExamFee, FeeCategory, FeeStructure, SchoolClass, SchoolProfile,
    SchoolSessionRecord, Student, FeePayment, WhatsAppConfig, MONTH_CHOICES,
)
from ..session_utils import get_academic_session_choices


@school_only
def config_view(request):
    school = request.user.school
    profile = SchoolProfile.get_for_school(school)
    classes = SchoolClass.objects.filter(school=school).order_by('name')
    session_choices = get_academic_session_choices(past_years=5, future_years=10)
    cfg_url = reverse('config_view')

    if request.method == 'POST':
        view_session = request.POST.get('view_session', profile.current_academic_session)

        if 'save_profile' in request.POST:
            session = request.POST.get('current_academic_session', '').strip()
            start_month = request.POST.get('session_start_month', '').strip()
            end_month = request.POST.get('session_end_month', '').strip()
            valid_months = {m for m, _ in MONTH_CHOICES}
            if not session:
                messages.error(request, 'Session is required.')
            elif start_month not in valid_months or end_month not in valid_months:
                messages.error(request, 'Invalid session month selection.')
            else:
                profile.current_academic_session = session
                profile.session_start_month = start_month
                profile.session_end_month = end_month
                profile.save(update_fields=['current_academic_session', 'session_start_month', 'session_end_month'])
                SchoolSessionRecord.objects.update_or_create(
                    school=school,
                    academic_session=session,
                    defaults={
                        'session_start_month': start_month,
                        'session_end_month': end_month,
                        'billing_start_month': profile.billing_start_month,
                        'billing_end_month': profile.billing_end_month,
                    },
                )
                messages.success(request, 'School profile updated.')
                view_session = session

        elif 'add_class' in request.POST:
            class_name = ' '.join(request.POST.get('class_name', '').split()).upper()
            try:
                amount = Decimal(request.POST.get('monthly_fee', ''))
                assert amount >= 0
            except (InvalidOperation, AssertionError):
                amount = None
            if not class_name or amount is None:
                messages.error(request, 'Enter valid class name and fee.')
            else:
                klass = SchoolClass.objects.create(school=school, name=class_name)
                category, _ = FeeCategory.objects.get_or_create(school=school, name='Monthly Fee', defaults={'is_active': True})
                FeeStructure.objects.update_or_create(
                    school_class=klass, fee_category=category, academic_session=view_session,
                    defaults={'amount': amount, 'frequency': FeeStructure.FREQUENCY_MONTHLY},
                )
                messages.success(request, 'Class added.')

        elif 'update_class' in request.POST:
            class_id = request.POST.get('class_id')
            class_name = request.POST.get('class_name', '').strip().upper()
            try:
                amount = Decimal(request.POST.get('monthly_fee', ''))
                assert amount >= 0
            except (InvalidOperation, AssertionError):
                amount = None
            if not class_id or not class_name or amount is None:
                messages.error(request, 'Enter valid class name and fee.')
            else:
                klass = get_object_or_404(SchoolClass, pk=class_id, school=school)
                klass.name = class_name
                klass.save(update_fields=['name'])
                category, _ = FeeCategory.objects.get_or_create(school=school, name='Monthly Fee', defaults={'is_active': True})
                FeeStructure.objects.update_or_create(
                    school_class=klass, fee_category=category, academic_session=view_session,
                    defaults={'amount': amount, 'frequency': FeeStructure.FREQUENCY_MONTHLY},
                )
                messages.success(request, 'Class updated.')

        elif 'delete_class' in request.POST:
            klass = get_object_or_404(SchoolClass, pk=request.POST.get('class_id'), school=school)
            students = Student.objects.filter(school_class=klass)
            student_count = students.count()
            FeePayment.objects.filter(student__in=students).delete()
            students.delete()
            klass.delete()
            messages.success(request, f'Class "{klass.name}" and {student_count} student(s) deleted.')

        elif 'add_exam_fee' in request.POST:
            class_id = request.POST.get('exam_class_id')
            exam_name = request.POST.get('exam_name', '').strip()
            try:
                amount = Decimal(request.POST.get('exam_amount', ''))
                assert amount >= 0
            except (InvalidOperation, AssertionError):
                amount = None
            if not class_id or not exam_name or amount is None:
                messages.error(request, 'All exam fee fields are required.')
            else:
                klass = get_object_or_404(SchoolClass, pk=class_id, school=school)
                ExamFee.objects.create(school=school, school_class=klass, exam_name=exam_name, academic_session=view_session, amount=amount)
                messages.success(request, 'Exam fee added.')

        elif 'update_exam_fee' in request.POST:
            exam_id = request.POST.get('exam_fee_id')
            exam_name = request.POST.get('exam_name', '').strip()
            class_id = request.POST.get('exam_class_id')
            try:
                amount = Decimal(request.POST.get('exam_amount', ''))
                assert amount >= 0
            except (InvalidOperation, AssertionError):
                amount = None
            if not exam_id or not exam_name or amount is None or not class_id:
                messages.error(request, 'All exam fee fields are required.')
            else:
                exam = get_object_or_404(ExamFee, pk=exam_id, school=school)
                klass = get_object_or_404(SchoolClass, pk=class_id, school=school)
                exam.exam_name = exam_name
                exam.academic_session = view_session
                exam.amount = amount
                exam.school_class = klass
                exam.save()
                messages.success(request, 'Exam fee updated.')

        elif 'delete_exam_fee' in request.POST:
            exam = get_object_or_404(ExamFee, pk=request.POST.get('exam_fee_id'), school=school)
            exam.delete()
            messages.success(request, 'Exam fee deleted.')

        elif 'save_wa_config' in request.POST:
            wa_config, _ = WhatsAppConfig.objects.get_or_create(school=school)
            wa_config.phone_number_id = request.POST.get('phone_number_id', '').strip()
            wa_config.waba_id = request.POST.get('waba_id', '').strip()
            wa_config.access_token = request.POST.get('access_token', '').strip()
            wa_config.template_name = request.POST.get('template_name', '').strip()
            wa_config.template_language = request.POST.get('template_language', 'en').strip()
            wa_config.announcement_template_name = request.POST.get('announcement_template_name', '').strip()
            wa_config.announcement_template_language = request.POST.get('announcement_template_language', 'en').strip()
            wa_config.is_active = bool(request.POST.get('is_active'))
            wa_config.save()
            messages.success(request, 'WhatsApp configuration saved.')

        return redirect(f'{cfg_url}?s={view_session}')

    view_session = request.GET.get('s', profile.current_academic_session)
    wa_config, _ = WhatsAppConfig.objects.get_or_create(school=school)
    fee_structures_qs = FeeStructure.objects.filter(
        fee_category__school=school,
        academic_session=view_session,
        frequency=FeeStructure.FREQUENCY_MONTHLY,
    )
    fee_map = {fs.school_class_id: fs.amount for fs in fee_structures_qs}
    exam_fees = ExamFee.objects.filter(
        school=school, academic_session=view_session,
    ).select_related('school_class').order_by('school_class__name', 'exam_name')

    session_classes = classes.filter(pk__in=fee_map.keys())

    return render(request, 'school/config/config.html', {
        'object': profile,
        'school': school,
        'classes': session_classes,
        'session_choices': session_choices,
        'month_choices': MONTH_CHOICES,
        'exam_fees': exam_fees,
        'wa_config': wa_config,
        'current_session': view_session,
        'fee_map': fee_map,
        'session_exam_configured': exam_fees.exists(),
    })
