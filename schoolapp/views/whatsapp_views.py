import json
import urllib.error
import urllib.request
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from ..decorators import school_only
from ..models import FeePayment, FeeStructure, SchoolClass, SchoolProfile, Student, WhatsAppConfig
from ..session_utils import MONTH_TO_CAL


@login_required
@school_only
def whatsapp_dashboard(request):
    school = request.user.school
    profile = SchoolProfile.objects.filter(school=school).first()
    wa_config, _ = WhatsAppConfig.objects.get_or_create(school=school)
    current_session = profile.current_academic_session if profile else ''

    students = Student.objects.filter(
        school=school, status=Student.STATUS_ACTIVE, academic_session=current_session,
    ).select_related('school_class').order_by('school_class', 'name')

    paid_by_student = dict(
        FeePayment.objects.filter(school=school, academic_session=current_session)
        .values('student_id')
        .annotate(total=Sum('amount_paid'))
        .values_list('student_id', 'total')
    )

    pending_rows = []
    session_start = profile.session_start_month if profile else 'april'
    today = date.today()
    start_cal = MONTH_TO_CAL.get(session_start, 4)
    session_year = int(current_session[:4]) if current_session else today.year
    start_date = date(session_year, start_cal, 1)
    months_elapsed = max(1, (today.year - start_date.year) * 12 + today.month - start_date.month + 1)

    for student in students:
        paid = paid_by_student.get(student.id) or Decimal('0')
        structures = FeeStructure.objects.filter(
            fee_category__school=school,
            fee_category__is_active=True,
            academic_session=current_session,
            school_class=student.school_class,
        )
        monthly_fee = sum(s.amount for s in structures if s.frequency == 'monthly')
        if student.transport_opted and student.transport_amount:
            monthly_fee += student.transport_amount

        balance = (monthly_fee * months_elapsed) - paid
        if balance > 0:
            pending_rows.append({
                'student': student,
                'paid': paid,
                'due': monthly_fee * months_elapsed,
                'balance': balance,
                'phone': student.father_phone,
            })

    return render(request, 'school/whatsapp/dashboard.html', {
        'wa_config': wa_config,
        'pending_rows': pending_rows,
        'school': school,
        'current_session': current_session,
        'classes': SchoolClass.objects.filter(school=school).order_by('name'),
    })


@login_required
@school_only
def whatsapp_send(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)

    school = request.user.school
    wa_config = get_object_or_404(WhatsAppConfig, school=school)
    student = get_object_or_404(Student, pk=request.POST.get('student_pk'), school=school)
    balance = request.POST.get('balance', '0')

    if not wa_config.is_active:
        return JsonResponse({'ok': False, 'error': 'WhatsApp is not enabled. Please configure and enable it first.'})
    if not wa_config.phone_number_id or not wa_config.access_token:
        return JsonResponse({'ok': False, 'error': 'Missing Phone Number ID or Access Token in settings.'})

    phone = student.father_phone.strip()
    if not phone:
        return JsonResponse({'ok': False, 'error': 'No phone number on record for this student.'})
    phone = phone.lstrip('+').replace(' ', '').replace('-', '')
    if len(phone) == 10 and phone.isdigit():
        phone = '91' + phone

    template_name = wa_config.template_name.strip()
    if not template_name:
        return JsonResponse({'ok': False, 'error': 'Template 1 (fee reminder) not set. Add it in Configuration → WhatsApp.'})

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": (wa_config.template_language or '').strip() or 'en'},
            "components": [{"type": "body", "parameters": [
                {"type": "text", "text": student.name},
                {"type": "text", "text": student.roll_number},
                {"type": "text", "text": f"Rs.{balance}"},
                {"type": "text", "text": school.name},
            ]}],
        },
    }
    return _send_whatsapp_message(wa_config, payload)


@login_required
@school_only
def whatsapp_announce(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)

    school = request.user.school
    wa_config = get_object_or_404(WhatsAppConfig, school=school)
    student = get_object_or_404(Student, pk=request.POST.get('student_pk'), school=school)
    message = request.POST.get('message', '').strip()

    if not wa_config.is_active:
        return JsonResponse({'ok': False, 'error': 'WhatsApp is not enabled. Enable it in Configuration.'})
    if not wa_config.phone_number_id or not wa_config.access_token:
        return JsonResponse({'ok': False, 'error': 'Missing Phone Number ID or Access Token in Configuration.'})
    ann_template_name = wa_config.announcement_template_name.strip()
    if not ann_template_name:
        return JsonResponse({'ok': False, 'error': 'Template 2 (announcement) not set. Add it in Configuration → WhatsApp.'})
    if not message:
        return JsonResponse({'ok': False, 'error': 'Message cannot be empty.'})

    phone = (student.father_phone or '').strip()
    if not phone:
        return JsonResponse({'ok': False, 'error': 'No phone number on record for this student.'})
    phone = phone.lstrip('+').replace(' ', '').replace('-', '')
    if len(phone) == 10 and phone.isdigit():
        phone = '91' + phone

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": ann_template_name,
            "language": {"code": (wa_config.announcement_template_language or '').strip() or 'en'},
            "components": [{"type": "body", "parameters": [
                {"type": "text", "parameter_name": "announcement", "text": message},
            ]}],
        },
    }
    return _send_whatsapp_message(wa_config, payload)


@login_required
@school_only
def whatsapp_templates_debug(request):
    school = request.user.school
    wa_config = get_object_or_404(WhatsAppConfig, school=school)

    if not wa_config.access_token:
        return JsonResponse({'ok': False, 'error': 'Access Token not configured.'})
    if not wa_config.waba_id:
        return JsonResponse({'ok': False, 'error': 'WhatsApp Business Account ID (WABA ID) not configured. Add it in Configuration → WhatsApp.'})

    url = f"https://graph.facebook.com/v25.0/{wa_config.waba_id}/message_templates?fields=name,language,status"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {wa_config.access_token}'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            tpl_data = json.loads(r.read())
        templates = [
            {'name': t['name'], 'language': t['language'], 'status': t.get('status')}
            for t in tpl_data.get('data', [])
        ]
        return JsonResponse({'ok': True, 'templates': templates})
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')
        try:
            err_msg = json.loads(err_body).get('error', {}).get('message', err_body)
        except Exception:
            err_msg = err_body
        return JsonResponse({'ok': False, 'error': err_msg})


@login_required
@school_only
def announcement_dashboard(request):
    school = request.user.school
    profile = SchoolProfile.objects.filter(school=school).first()
    wa_config, _ = WhatsAppConfig.objects.get_or_create(school=school)
    current_session = profile.current_academic_session if profile else ''

    all_students = Student.objects.filter(
        school=school, status=Student.STATUS_ACTIVE, academic_session=current_session,
    ).select_related('school_class').order_by('school_class', 'name')

    return render(request, 'school/whatsapp/announcement.html', {
        'wa_config': wa_config,
        'all_students': all_students,
        'classes': SchoolClass.objects.filter(school=school).order_by('name'),
    })


def _send_whatsapp_message(wa_config, payload):
    url = f"https://graph.facebook.com/v25.0/{wa_config.phone_number_id}/messages"
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url, data=data,
        headers={'Authorization': f'Bearer {wa_config.access_token}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        return JsonResponse({'ok': True, 'message_id': result.get('messages', [{}])[0].get('id', '')})
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')
        try:
            err_msg = json.loads(err_body).get('error', {}).get('message', err_body)
        except Exception:
            err_msg = err_body
        return JsonResponse({'ok': False, 'error': err_msg})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})