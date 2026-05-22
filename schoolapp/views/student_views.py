import io

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from ..decorators import school_only
from ..forms import StudentForm
from ..models import SchoolClass, SchoolProfile, Student
from ..services.student_service import (
    BULK_FIELD_INFO, BULK_UPLOAD_HEADERS,
    fail_student, process_bulk_upload, promote_student,
)
from ..utils.excel_utils import set_column_widths, style_data_cell, style_header_cell


@school_only
def student_list(request):
    school = request.user.school
    profile = SchoolProfile.get_for_school(school)
    session = profile.current_academic_session

    q = request.GET.get('q', '').strip()
    class_id = request.GET.get('class')
    status = request.GET.get('status')

    qs = Student.objects.filter(school=school, academic_session=session).select_related('school_class')
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(roll_number__icontains=q) | Q(father_name__icontains=q))
    if class_id:
        qs = qs.filter(school_class_id=class_id)
    if status:
        qs = qs.filter(status=status)

    all_students = Student.objects.filter(school=school).select_related('school_class')
    session_class_ids = (
        Student.objects.filter(school=school, academic_session=session)
        .values_list('school_class_id', flat=True).distinct()
    )
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'school/admission/student_list.html', {
        'students': page_obj,
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1,
        'classes': SchoolClass.objects.filter(pk__in=session_class_ids).order_by('name'),
        'status_choices': Student.STATUS_CHOICES,
        'session_start_month': profile.session_start_month.capitalize(),
        'session_end_month': profile.session_end_month.capitalize(),
        'total_students': all_students.count(),
        'class_wise': all_students.values('school_class__name').annotate(count=Count('id')).order_by('school_class__name'),
        'session_wise': all_students.values('academic_session').annotate(count=Count('id')).order_by('-academic_session'),
        'filtered_total': qs.count(),
        'filtered_active': qs.filter(status='active').count(),
        'filtered_promoted': qs.filter(status='promoted').count(),
        'filtered_inactive': qs.filter(status='inactive').count(),
        'filtered_fail': qs.filter(status='fail').count(),
        'filtered_class_wise': qs.values('school_class__name').annotate(count=Count('id')).order_by('school_class__name'),
        'selected_class': class_id or '',
        'selected_status': status or '',
        'selected_q': q,
        'has_filters': bool(q or class_id or status),
    })


@school_only
def student_create(request):
    school = request.user.school
    profile = SchoolProfile.get_for_school(school)
    session = profile.current_academic_session
    form = StudentForm(request.POST or None, school=school, session=session)
    if request.method == 'POST' and form.is_valid():
        student = form.save(commit=False)
        student.school = school
        student.academic_session = session
        student.save()
        discount_months = form.cleaned_data.get('discount_months') or 0
        msg = f'Student admitted. First {discount_months} month(s) discounted.' if discount_months > 0 else 'Student admitted.'
        messages.success(request, msg)
        return redirect('student_list')
    return render(request, 'school/admission/student_form.html', {'form': form})


@school_only
def student_edit(request, pk):
    school = request.user.school
    student = get_object_or_404(Student, pk=pk, school=school)
    form = StudentForm(request.POST or None, instance=student, school=school, session=student.academic_session)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Student updated.')
        return redirect('student_list')
    return render(request, 'school/admission/student_form.html', {'form': form, 'object': student})


@school_only
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk, school=request.user.school)
    if request.method == 'POST':
        try:
            student.delete()
            messages.success(request, 'Student deleted.')
        except ProtectedError:
            payment_count = student.fee_payments.count()
            messages.error(
                request,
                f'Cannot delete {student.name}: they have {payment_count} fee payment record(s). '
                'Delete the payments first.',
            )
        return redirect('student_list')
    return render(request, 'school/admission/confirm_delete.html', {'object': student})


@school_only
def student_promote(request, pk):
    if request.method != 'POST':
        return redirect('student_list')
    school = request.user.school
    student = get_object_or_404(Student, pk=pk, school=school, status=Student.STATUS_ACTIVE)
    promoted, error = promote_student(student, school)
    if error:
        messages.error(request, error)
    else:
        messages.success(
            request,
            f'{student.name} promoted → {promoted.school_class.name} ({promoted.academic_session}).',
        )
    return redirect('student_list')


@school_only
def student_fail(request, pk):
    if request.method != 'POST':
        return redirect('student_list')
    school = request.user.school
    student = get_object_or_404(Student, pk=pk, school=school, status=Student.STATUS_ACTIVE)
    retained = fail_student(student)
    messages.success(
        request,
        f'{student.name} marked as failed and retained in {retained.school_class.name} ({retained.academic_session}).',
    )
    return redirect('student_list')


@school_only
def student_transfer(request, pk):
    if request.method != 'POST':
        return redirect('student_list')
    student = get_object_or_404(Student, pk=pk, school=request.user.school, status=Student.STATUS_ACTIVE)
    student.status = Student.STATUS_INACTIVE
    student.save(update_fields=['status', 'updated_at'])
    messages.success(request, f'{student.name} marked as transferred.')
    return redirect('student_list')


@school_only
def admission_bulk_template(request):
    school = request.user.school
    classes = list(SchoolClass.objects.filter(school=school).order_by('name'))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Bulk Admission'
    ws.row_dimensions[1].height = 38
    ws.append(BULK_UPLOAD_HEADERS)
    for cell in ws[1]:
        style_header_cell(cell)

    ws_lists = wb.create_sheet('Lists')
    ws_lists.sheet_state = 'hidden'
    for i, cls in enumerate(classes, start=1):
        ws_lists.cell(row=i, column=1, value=cls.name)

    def add_dropdown(formula1, col_letter):
        dv = DataValidation(type='list', formula1=formula1, allow_blank=True, showDropDown=False)
        dv.sqref = f'{col_letter}2:{col_letter}201'
        ws.add_data_validation(dv)

    if classes:
        add_dropdown(f'Lists!$A$1:$A${len(classes)}', 'C')
    add_dropdown('"Hindu,Muslim,Christian,Sikh,Buddhist,Jain,Parsi,Other"', 'H')
    add_dropdown('"General,OBC,SC,ST,EWS,Other"', 'I')
    add_dropdown('"O+,O-,A+,A-,B+,B-,AB+,AB-"', 'J')
    add_dropdown('"Yes,No"', 'N')

    for col_idx in [2, 17, 19]:
        for row_num in range(1, 203):
            ws.cell(row=row_num, column=col_idx).number_format = '@'

    set_column_widths(ws, max_w=30)
    ws.freeze_panes = 'A2'

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(buf.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="bulk_admission_template.xlsx"'
    return response


@school_only
def admission_bulk_upload(request):
    school = request.user.school
    profile = SchoolProfile.get_for_school(school)
    classes = SchoolClass.objects.filter(school=school).order_by('name')
    upload_result = None

    if request.method == 'GET':
        request.session.pop('bulk_upload_failed', None)

    if request.method == 'POST':
        uploaded_file = request.FILES.get('excel_file')
        if not uploaded_file:
            messages.error(request, 'Please select an Excel file to upload.')
        elif not uploaded_file.name.lower().endswith('.xlsx'):
            messages.error(request, 'Only .xlsx files are supported.')
        else:
            try:
                wb = openpyxl.load_workbook(uploaded_file, data_only=True)
                upload_result, failed_rows = process_bulk_upload(wb, school, profile, request.user)
                if failed_rows:
                    request.session['bulk_upload_failed'] = failed_rows
                else:
                    request.session.pop('bulk_upload_failed', None)
            except Exception as exc:
                messages.error(request, f'Failed to process file: {exc}')

    return render(request, 'school/admission/bulk_upload.html', {
        'classes': classes,
        'field_info': BULK_FIELD_INFO,
        'upload_result': upload_result,
        'has_pending_errors': bool(request.session.get('bulk_upload_failed')),
        'current_session': profile.current_academic_session,
    })


@school_only
def admission_bulk_errors_download(request):
    failed_rows = request.session.get('bulk_upload_failed', [])
    headers = [
        'Student Name', 'Date of Birth', 'Class', 'Father Name', 'Mother Name',
        'Father WhatsApp', 'Address', 'Religion', 'Caste', 'Blood Group',
        'Previous School', 'Aadhaar Number', 'PEN Number', 'Transport Opted',
        'Transport Amount', 'Discount Months', 'Admission Date', 'Paid Amount',
        'Payment Date', 'Error Remarks',
    ]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Failed Records'
    ws.row_dimensions[1].height = 30
    ws.append(headers)
    thin = Side(style='thin', color='E2E8F0')
    for col_idx, cell in enumerate(ws[1], start=1):
        style_header_cell(cell, bg_color='DC2626' if col_idx == len(headers) else '1E293B')

    for col_idx in [2, 17, 19]:
        for row_num in range(1, len(failed_rows) + 10):
            ws.cell(row=row_num, column=col_idx).number_format = '@'

    for row_idx, row_data in enumerate(failed_rows, start=2):
        ws.row_dimensions[row_idx].height = 22
        padded = list(row_data) + [''] * max(0, len(headers) - len(row_data))
        ws.append(padded[:len(headers)])
        for col_idx, cell in enumerate(ws[row_idx], start=1):
            if col_idx == len(headers):
                cell.fill = PatternFill(fill_type='solid', fgColor='FEE2E2')
                cell.font = Font(color='DC2626', size=10)
                cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
                cell.alignment = Alignment(wrap_text=True, vertical='top')
            else:
                style_data_cell(cell, row_idx)
            if col_idx in (2, 18, 20):
                cell.number_format = '@'

    set_column_widths(ws, max_w=45)
    ws.freeze_panes = 'A2'

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(buf.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="bulk_upload_errors.xlsx"'
    return response
