from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..decorators import school_only
from ..logging_utils import log_activity_event
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
                log_activity_event(
                    request,
                    module='config',
                    action='profile_update',
                    details={
                        'current_academic_session': profile.current_academic_session,
                        'session_start_month': profile.session_start_month,
                        'session_end_month': profile.session_end_month,
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
                log_activity_event(
                    request,
                    module='config',
                    action='class_create',
                    record_id=klass.pk,
                    details={'class_name': klass.name, 'academic_session': view_session, 'monthly_fee': str(amount)},
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
                old_values = {'class_name': klass.name}
                klass.name = class_name
                klass.save(update_fields=['name'])
                category, _ = FeeCategory.objects.get_or_create(school=school, name='Monthly Fee', defaults={'is_active': True})
                FeeStructure.objects.update_or_create(
                    school_class=klass, fee_category=category, academic_session=view_session,
                    defaults={'amount': amount, 'frequency': FeeStructure.FREQUENCY_MONTHLY},
                )
                log_activity_event(
                    request,
                    module='config',
                    action='class_update',
                    record_id=klass.pk,
                    old_values=old_values,
                    new_values={'class_name': klass.name, 'academic_session': view_session, 'monthly_fee': str(amount)},
                )
                messages.success(request, 'Class updated.')

        elif 'delete_class' in request.POST:
            klass = get_object_or_404(SchoolClass, pk=request.POST.get('class_id'), school=school)
            students = Student.objects.filter(school_class=klass)
            student_count = students.count()
            FeePayment.objects.filter(student__in=students).delete()
            students.delete()
            klass.delete()
            log_activity_event(
                request,
                module='config',
                action='class_delete',
                details={'class_name': klass.name, 'student_count': student_count},
            )
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
                log_activity_event(
                    request,
                    module='config',
                    action='exam_fee_create',
                    details={'class_id': klass.pk, 'exam_name': exam_name, 'academic_session': view_session, 'amount': str(amount)},
                )
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
                old_values = {
                    'exam_name': exam.exam_name,
                    'academic_session': exam.academic_session,
                    'amount': str(exam.amount),
                    'school_class_id': exam.school_class_id,
                }
                exam.exam_name = exam_name
                exam.academic_session = view_session
                exam.amount = amount
                exam.school_class = klass
                exam.save()
                log_activity_event(
                    request,
                    module='config',
                    action='exam_fee_update',
                    record_id=exam.pk,
                    old_values=old_values,
                    new_values={'exam_name': exam.exam_name, 'academic_session': exam.academic_session, 'amount': str(exam.amount), 'school_class_id': exam.school_class_id},
                )
                messages.success(request, 'Exam fee updated.')

        elif 'delete_exam_fee' in request.POST:
            exam = get_object_or_404(ExamFee, pk=request.POST.get('exam_fee_id'), school=school)
            exam_snapshot = {'exam_name': exam.exam_name, 'academic_session': exam.academic_session, 'amount': str(exam.amount), 'school_class_id': exam.school_class_id}
            exam.delete()
            log_activity_event(
                request,
                module='config',
                action='exam_fee_delete',
                record_id=exam_snapshot.get('exam_name'),
                details=exam_snapshot,
            )
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
            wa_config.whatsapp_welcome_template_name = request.POST.get('whatsapp_welcome_template_name', '').strip()
            wa_config.whatsapp_welcome_template_language = request.POST.get('whatsapp_welcome_template_language', 'en').strip()
            wa_config.is_active = bool(request.POST.get('is_active'))
            wa_config.save()
            log_activity_event(
                request,
                module='config',
                action='whatsapp_config_update',
                record_id=wa_config.pk,
                details={
                    'phone_number_id': wa_config.phone_number_id,
                    'waba_id': wa_config.waba_id,
                    'template_name': wa_config.template_name,
                    'template_language': wa_config.template_language,
                    'announcement_template_name': wa_config.announcement_template_name,
                    'announcement_template_language': wa_config.announcement_template_language,
                    'whatsapp_welcome_template_name': wa_config.whatsapp_welcome_template_name,
                    'whatsapp_welcome_template_language': wa_config.whatsapp_welcome_template_language,
                    'is_active': wa_config.is_active,
                },
            )
            messages.success(request, 'WhatsApp configuration saved.')

        elif 'save_website_customization' in request.POST:
            school.name = request.POST.get('name', '').strip()
            school.motto = request.POST.get('motto', '').strip()
            school.theme_color = request.POST.get('theme_color', '#2563eb').strip()
            
            school.established_year = request.POST.get('established_year', '').strip()
            school.stat_students = request.POST.get('stat_students', '').strip()
            school.stat_staff = request.POST.get('stat_staff', '').strip()
            school.stat_experience = request.POST.get('stat_experience', '').strip()
            school.about_us_text = request.POST.get('about_us_text', '').strip()
            school.about_us_bullets = request.POST.get('about_us_bullets', '').strip()
            school.admission_open_session = request.POST.get('admission_open_session', '').strip()
            
            school.testimonial_1_name = request.POST.get('testimonial_1_name', '').strip()
            school.testimonial_1_role = request.POST.get('testimonial_1_role', '').strip()
            school.testimonial_1_text = request.POST.get('testimonial_1_text', '').strip()
            
            school.testimonial_2_name = request.POST.get('testimonial_2_name', '').strip()
            school.testimonial_2_role = request.POST.get('testimonial_2_role', '').strip()
            school.testimonial_2_text = request.POST.get('testimonial_2_text', '').strip()
            
            school.testimonial_3_name = request.POST.get('testimonial_3_name', '').strip()
            school.testimonial_3_role = request.POST.get('testimonial_3_role', '').strip()
            school.testimonial_3_text = request.POST.get('testimonial_3_text', '').strip()

            # Handle files
            if request.FILES.get('logo'):
                school.logo = request.FILES.get('logo')
            elif request.POST.get('clear_logo') == '1':
                school.logo = None

            if request.FILES.get('campus_image'):
                school.campus_image = request.FILES.get('campus_image')
            elif request.POST.get('clear_campus_image') == '1':
                school.campus_image = None

            if request.FILES.get('campus_image2'):
                school.campus_image2 = request.FILES.get('campus_image2')
            elif request.POST.get('clear_campus_image2') == '1':
                school.campus_image2 = None

            if request.FILES.get('campus_image3'):
                school.campus_image3 = request.FILES.get('campus_image3')
            elif request.POST.get('clear_campus_image3') == '1':
                school.campus_image3 = None

            school.save()
            log_activity_event(
                request,
                module='config',
                action='website_customization_update',
                record_id=school.pk,
                details={'name': school.name}
            )
            messages.success(request, 'Website landing page settings updated successfully.')

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
